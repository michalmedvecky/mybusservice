#!api/bin/python

import xml.etree.ElementTree
import requests
import pprint
import redis
import datetime
from datetime import datetime
import time
from flask import Flask
from flask import request,make_response
from redis.sentinel import Sentinel
import xml
from xml.etree.ElementTree import Element, SubElement, Comment, tostring
import xml.dom.minidom

nburl="http://webservices.nextbus.com/service/publicXMLFeed?command="
config_slow=-1 # Queries longer than this will be considered slow
valid_endpoints=["/agencyList","/doesNotRunAtTime","/health-check","/slow-queries","/stats","/routeList","/routeConfig","/predictions","/predictionForMultiStops","/schedule","/messages","/vehicleLocations"]

app = Flask(__name__)

try:
    # try connecting to local redis first
    red = redis.StrictRedis(host='localhost', port=6379, db=0)
    red.ping
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
    except Exception as e:
        print("Can't connect to any Redis, dying")
        exit(1)

def log_slow_request(url,t):
    if t>config_slow:
        timeofevent=time.strftime("%a, %d %b %Y %H:%M:%S GMT")
        rwdis.sadd("slowrequests",timeofevent+" Query "+url+" took "+str(t)+" milliseconds.")

def cachepage(url):
    print("Requesting "+url)
    rwdis.incr("stats:validrequests", amount=1)

    if rodis.exists(url):
        return rodis.get(url)
    else:
        print("Getting "+url)
        r=requests.get(url)
        print("Status code: "+str(r.status_code))
        rwdis.set(url,r.content, ex=180000)
        return r.content

def myresponse(url):
    expiry_time = datetime.timedelta(0,rodis.ttl(url)) + datetime.datetime.utcnow()
    response = make_response(cachepage(url))
    response.mimetype = "text/plain"
    response.headers["Expires"] = expiry_time.strftime("%a, %d %b %Y %H:%M:%S GMT")
    response.code=200
    return response

@app.route("/stats")
def stats():
    rwdis.incr("requests:/stats", amount=1)
    out = Element("body", attrib={})
    for e in valid_endpoints:
        ep = SubElement(out, 'endpoint', attrib={'url':e,'accesscount':str(rodis.get("requests:"+e))})
    response=xml.dom.minidom.parseString(tostring(out))
    return response.toprettyxml()

@app.route("/doesNotRunAtTime/<int:hour>")
def doesnotrunattime(hour):
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
        rwdis.expire("agencies", 86400) # I guess agencies dont' update more frequently than daily

    for a in rodis.smembers("agencies"):
        if not rodis.exists(a+":routes"):
            print("getting route list for "+a)
            r = cachepage("http://webservices.nextbus.com/service/publicXMLFeed?command=routeList&a="+a)
            routes=xml.etree.ElementTree.fromstring(r)
            print("parsing route list...")
            for route in routes.findall('route'):
                print("Adding route "+route.get('tag')+" for agency "+a)
                rwdis.sadd(a+":routes",route.get('tag'))
            rwdis.expire(a+":routes",86400)

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
    rwdis.incr("requests:/health-check", amount=1)
    try:
        response = rodis.client_list()
        response = rwdis.client_list()
        response = make_response("OK\n")
        response.code=200

    except redis.ConnectionError:
        response = make_response("Error in redis connection")
        response.code=500

    return response

@app.route('/routeList/<string:agency>')
def myrouteList(agency):
    rwdis.incr("requests:/routeList")
    url=nburl+"routeList&a="+agency
    return myresponse(url)

@app.route('/routeConfig/<string:agency>/<string:route>')
def routeConfig(agency,route):
    rwdis.incr("requests:/routeConfig", amount=1)
    rwdis.incr("stats:validrequests", amount=1)
    url=nburl+"routeConfig&a="+agency+"&r="+route
    return myresponse(url)

@app.route('/agencyList')
@app.route('/routeList')
@app.route('/predictions')
@app.route('/schedule')
@app.route('/messages')
@app.route('/vehicleLocations')
@app.route('/predictionsForMultiStops')
@app.route('/routeConfig')
def proxyHandler():
    t_start=time.time()
    rwdis.incr("requests:"+request.path, amount=1)
    url=nburl+request.path[1:]+"{q}".format(q="&" if len(request.query_string)>0 else "")+request.query_string
    contents=myresponse(url)
    log_slow_request(request.url,time.time()-t_start)
    return contents

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def notfound(path):
    rwdis.incr("stats:invalidrequests", amount=1)
    response=make_response("Not found\n")
    response.code=404
#    return 'You want path: %s \n' % path+" "+request.method
    return response

if __name__ == '__main__':
    app.run(debug=True)
