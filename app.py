#!/usr/bin/env python

import xml.etree.ElementTree
import requests
import pprint
import redis
import time
import datetime
from datetime import datetime, timedelta
from flask import Flask
from flask import request,make_response
from redis.sentinel import Sentinel
import xml
from xml.etree.ElementTree import Element, SubElement, Comment, tostring
import xml.dom.minidom
import os

nburl="http://webservices.nextbus.com/service/publicXMLFeed?command="
try:
    config_slow=os.env['MYBUSAPP_SLOW'] # timeout for slow queries
except AttributeError:
    config_slow=5000

try:
    config_slow=os.env['MYBUSAPP_SENTINEL'] # hostname of redis sentinel
except AttributeError:
    config_slow="redis-sentinel"

try:
    config_cachetime=os.env['MYBUSAPP_CACHETIME'] # hostname of redis sentinel
except AttributeError:
    config_cachetime=1800

valid_endpoints=["/agencyList","/doesNotRunAtTime","/health-check","/slow-queries","/stats","/routeList","/routeConfig","/predictions","/predictionForMultiStops","/schedule","/messages","/vehicleLocations"]

app = Flask(__name__)

try:
    # try connecting to local redis first
    print("Trying local redis first")
    red = redis.StrictRedis(host='localhost', port=6379, db=0)
    red.set("a","1")
    red.expire("a",1)
    rwdis=red
    rodis=red

except Exception as e:
    try:
        print("Trying to find Redis to connect to ...")
        sentinel=Sentinel([("redis-sentinel", 26379)])
        rwdis=sentinel.master_for("mymaster")
        rodis=sentinel.slave_for("mymaster")
        rwdis.get(None)
        rodis.get(None)
        print("Sentinel found, working in HA mode")
    except Exception as e:
        print("Can't connect to any Redis, dying")
        print(str(e))
        exit(1)

def log_slow_request(url,t):
    """Log requests that are slower than t"""
    if t>config_slow:
        timeofevent=time.strftime("%a, %d %b %Y %H:%M:%S GMT")
        rwdis.sadd("slowrequests",timeofevent+" Query "+url+" took "+str(t)+" milliseconds.")

def cachepage(url):
    """Lookup the page in cache (Redis) of fetch it and store it there"""
    print("Requesting "+url)

    if rodis.exists(url):
        return rodis.get(url)
    else:
        print("Getting "+url)
        try:
            r=requests.get(url)
            print("Status code: "+str(r.status_code))
            rwdis.set(url,r.content, ex=config_cachetime)
            return r.content
        except:
            return 1

def myresponse(url):
    """Creates response object, adds Expire header and code"""
    expiry_time = timedelta(0,rodis.ttl(url)) + datetime.utcnow()
    contents=cachepage(url)
    response.mimetype = "text/plain"
    if contents != 1:
        response = make_response(contents)
        response.headers["Expires"] = expiry_time.strftime("%a, %d %b %Y %H:%M:%S GMT")
        response.code=200
    else:
        err500 = Element("body")
        err = SubElement(err404, "Error", attrib={"shouldRetry":"True"})
        err.text = "Something bad happened on the server. System administrator might find error in the log."
        s=xml.dom.minidom.parseString(tostring(err500))
        out=s.toprettyxml()
        response=make_response(out)
        response.code=500
    return response

@app.route("/stats")
def stats():
    """Returns site statistics (endpoint access count)"""
    rwdis.incr("requests:/stats", amount=1)
    out = Element("body", attrib={})
    for e in valid_endpoints:
        ep = SubElement(out, 'endpoint', attrib={'url':e,'accesscount':str(rodis.get("requests:"+e))})
    response=xml.dom.minidom.parseString(tostring(out))
    return response.toprettyxml()

@app.route("/doesNotRunAtTime/<int:hour>")
def doesnotrunattime(hour):
    """Returns routes that do not run at specified hour"""
    t_start=time.time()
    if rodis.exists("nonruntimes:"+str(hour)):
        body = Element("body")
        lnorun = SubElement(body, "doesnotrunat", attrib={"oclock":str(hour)})
        for member in rodis.smembers("nonruntimes:"+str(hour)):
            agency,route=str.split(member,":")
            xmember = SubElement(lnorun, "route", attrib={"agency":agency,"tag":route})
        response=make_response(xml.dom.minidom.parseString(tostring(body)).toprettyxml())
        log_slow_request(request.url,time.time()-t_start)
        return response

    if not rodis.exists("agencies"):
        r = cachepage("http://webservices.nextbus.com/service/publicXMLFeed?command=agencyList")
        e = xml.etree.ElementTree.fromstring(r)

        for agency in e.findall('agency'):
            a=agency.get('tag')
            print("Adding "+a)
            rwdis.sadd("agencies",a)
        rwdis.expire("agencies", 86400) # I guess agencies dont' update more frequently than daily ...

    for a in rodis.smembers("agencies"):
        if not rodis.exists(a+":routes"):
            print("getting route list for "+a)
            r = cachepage("http://webservices.nextbus.com/service/publicXMLFeed?command=routeList&a="+a)
            routes=xml.etree.ElementTree.fromstring(r)
            print("parsing route list...")
            for route in routes.findall('route'):
                print("Adding route "+route.get('tag')+" for agency "+a)
                rwdis.sadd(a+":routes",route.get('tag'))
            rwdis.expire(a+":routes",86400) # ... and routes as well

    for a in rodis.smembers("agencies"):
        for r in rodis.smembers(a+":routes"):
            print("Processing "+r)
    #            print("Getting schedule of route "+r+" of agency "+a)
            out = cachepage("http://webservices.nextbus.com/service/publicXMLFeed?command=schedule&a="+a+"&r="+r)
            schedule=xml.etree.ElementTree.fromstring(out)
            runtimes=set()
            for row in schedule.findall("route", namespaces=None):
                for tr in row.findall('tr'):
                    for stop in tr.findall('stop'):
                        if int(stop.attrib['epochTime']) > 0:
                            hh,mm,ss=stop.text.split(':')
                            runtimes.add(int(hh))

            for h in range(0, 24):
                if h not in runtimes:
                    rwdis.sadd("nonruntimes:"+str(h),a+":"+r)
                    rwdis.expire("nonruntimes:"+str(h), 86400)
    response=make_response(str(rodis.smembers("nonruntimes:"+str(hour))))
    log_slow_request(request.url,time.time()-t_start)
    return response


@app.route('/health-check')
def health_check():
    """Health check. Checks the redis connection(s) and returns ok/non ok"""
    try:
        response = rodis.client_list()
        response = rwdis.client_list()
        response = make_response("OK\n")
        rwdis.incr("requests:/health-check", amount=1)
        response.code=200

    except redis.ConnectionError:
        response = make_response("Error in redis connection")
        response.code=500

    return response

@app.route('/routeList/<string:agency>')
def myrouteList(agency):
    """Get route list for agency"""
    t_start=time.time()
    rwdis.incr("requests:/routeList")
    url=nburl+"routeList&a="+agency
    contents=myresponse(url)
    log_slow_request(url, t_start)
    return contents

@app.route('/routeConfig/<string:agency>/<string:route>')
@app.route('/schedule/<string:agency>/<string:route>')
def routeConfig(agency,route):
    """Get Route config for agency/route"""
    t_start=time.time()
    rwdis.incr("requests:/"+request.path[1:], amount=1)
    url=nburl+request.path[1:]+"&a="+agency+"&r="+route
    contents=myresponse(url)
    log_slow_request(url, t_start)
    return contents

@app.route('/predictions/bystopid/<string:agency>/<string:stopid>')
def predictions1(agency,stopid):
    """Get route predictions by stopid for agency/stopid"""
    t_start=time.time()
    rwdis.incr("requests:/predictions", amount=1)
    url=nburl+"predictions&a="+agency+"&stopId="+stopId
    contents=myresponse(url)
    log_slow_request(url, t_start)
    return contents

@app.route('/predictions/bystopid/<string:agency>/<string:stopid>/<string:routetag>')
def predictions2(agency,stopid,routetag):
    """Get route predictions by stopid for agency/stopid/routetag"""
    t_start=time.time()
    rwdis.incr("requests:/predictions", amount=1)
    url=nburl+"predictions&a="+agency+"&stopId="+stopId+"&routeTag="+routetag
    contents=myresponse(url)
    log_slow_request(url, t_start)
    return contents

@app.route('/predictions/bystoptag/<string:agency>/<string:routetag>/<string:stoptag>')
def predictions3(agency,routetag,stoptag):
    """Get route predictions by stoptag for agency/routetag/stoptag"""
    t_start=time.time()
    rwdis.incr("requests:/predictions", amount=1)
    url=nburl+"predictions&a="+agency+"&s="+stoptag+"&r="+routetag
    contents=myresponse(url)
    log_slow_request(url, t_start)
    return contents

@app.route('/predictionsForMultiStops/<string:agency>/<path:varargs>')
@app.route('/messages/<string:agency>/<path:varargs>')

def predictionsformultistops(agency,varargs):
    """Get predictions for multistops (varargs)"""
    t_start=time.time()
    rwdis.incr("requests:/"+request.path[1:], amount=1)
    extra=""
    print(request.path)
    if "predictionsForMultiStops" in request.path:
        extrakw="stops"
    else:
        extrakw="r"
    for item in varargs.split("/"):
        print(extrakw+": "+item)
        extra+="&"+extrakw+"="+item
    url=nburl+"{param}".format(param="predictionsForMultiStops" if "predictionsForMultiStops" in request.path else "messages")+"&a="+agency+extra
    print(url)
    contents=myresponse(url)
    log_slow_request(url, t_start)
    return contents

@app.route('/vehicleLocations/<string:agency>/<string:routetag>/<string:epoch>')
def vehiclelocations(agency,routetag,epoch):
    """Fetch vehicle locations for agency/routetag/epoch"""
    t_start=time.time()
    rwdis.incr("requests:/vehicleLocations", amount=1)
    url=nburl+"vehicleLocations&a="+agency+"&t="+epoch+"&r="+routetag
    contents=myresponse(url)
    log_slow_request(url, t_start)
    return contents

@app.route('/agencyList')
@app.route('/routeList')
@app.route('/predictions')
@app.route('/schedule')
@app.route('/messages')
@app.route('/vehicleLocations')
@app.route('/predictionsForMultiStops')
@app.route('/routeConfig')
def proxyHandler():
    """Just proxy the received request to upstream server (nburl)"""
    t_start=time.time()
    rwdis.incr("requests:"+request.path, amount=1)
    url=nburl+request.path[1:]+"{q}".format(q="&" if len(request.query_string)>0 else "")+request.query_string
    contents=myresponse(url)
    log_slow_request(request.url,time.time()-t_start)
    return contents

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def notfound(path):
    """Default handler for nonexistent endpoints"""
    err404 = Element("body")
    err = SubElement(err404, "Error", attrib={"shouldRetry":"False"})
    err.text = "But I still haven't found what I was looking for."
    s=xml.dom.minidom.parseString(tostring(err404))
    out=s.toprettyxml()
    response=make_response(out)
    response.code=404
    print("Not found "+request.method+" /"+path)
    return response

if __name__ == '__main__':
    app.run(debug=False,host="0.0.0.0")
