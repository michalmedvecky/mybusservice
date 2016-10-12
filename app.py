#!api/bin/python

import xml.etree.ElementTree
import requests
import pprint
import redis
import datetime
import time
from flask import Flask
from flask import request,make_response

nburl="http://webservices.nextbus.com/service/publicXMLFeed?command="
app = Flask(__name__)
red = redis.StrictRedis(host='localhost', port=6379, db=0)
config_slow=-1 # Queries longer than this will be considered slow

def log_slow_request(url,t):
    if t>config_slow:
        timeofevent=time.strftime("%a, %d %b %Y %H:%M:%S GMT")
        red.sadd("slowrequests",timeofevent+" Query "+url+" took "+str(t)+" milliseconds.")

def cachepage(url):
    print("Requesting "+url)
    red.incr("stats:validrequests", amount=1)

    if red.exists(url):
        return red.get(url)
    else:
        print("Getting "+url)
        r=requests.get(url)
        print("Status code: "+str(r.status_code))
        red.set(url,r.content, ex=180000)
        return r.content

def myresponse(url):
    expiry_time = datetime.timedelta(0,red.ttl(url)) + datetime.datetime.utcnow()
    response = make_response(cachepage(url))
    response.mimetype = "text/plain"
    response.headers["Expires"] = expiry_time.strftime("%a, %d %b %Y %H:%M:%S GMT")
    response.code=200
    return response

@app.route("/doesNotRunAtTime/<int:hour>")
def doesnotrunattime(hour):
    t_start=time.time()
    if red.exists("nonruntimes:"+str(hour)):
        response=make_response(str(red.smembers("nonruntimes:"+str(hour))))
        log_slow_request(request.url,time.time()-t_start)
        return response

    if not red.exists("agencies"):
        r = cachepage("http://webservices.nextbus.com/service/publicXMLFeed?command=agencyList")
        e = xml.etree.ElementTree.fromstring(r)

        for agency in e.findall('agency'):
            a=agency.get('tag')
            print("Adding "+a)
            red.sadd("agencies",a)
        red.expire("agencies", 86400) # I guess agencies dont' update more frequently than daily

    #    pprint.pprint(red.smembers("agencies"))
    for a in red.smembers("agencies"):
        if not red.exists(a+":routes"):
            print("getting route list for "+a)
            r = cachepage("http://webservices.nextbus.com/service/publicXMLFeed?command=routeList&a="+a)
            routes=xml.etree.ElementTree.fromstring(r)
            print("parsing route list...")
            for route in routes.findall('route'):
                print("Adding route "+route.get('tag')+" for agency "+a)
                red.sadd(a+":routes",route.get('tag'))
            red.expire(a+":routes",86400)

    for a in red.smembers("agencies"):
        for r in red.smembers(a+":routes"):
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
                    red.sadd("nonruntimes:"+str(h),a+":"+r)
                    red.expire("nonruntimes:"+str(h), 86400)
    response=make_response(str(red.smembers("nonruntimes:"+str(hour))))
    log_slow_request(request.url,time.time()-t_start)
    return response


@app.route('/health-check')
def health_check():
    red.incr("requests:/health-check", amount=1)
    try:
        response = red.client_list()
        response = make_response("OK\n")
        response.code=200

    except redis.ConnectionError:
        response = make_response("Error in redis connection")
        response.code=500

    return response

@app.route('/routeList/<string:agency>')
def myrouteList(agency):
    red.incr("requests:/routeList")
    url=nburl+"routeList&a="+agency
    return myresponse(url)

@app.route('/routeConfig/<string:agency>/<string:route>')
def routeConfig(agency,route):
    red.incr("requests:/routeConfig", amount=1)
    red.incr("stats:validrequests", amount=1)
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
    red.incr("requests:"+request.path, amount=1)
    url=nburl+request.path[1:]+"{q}".format(q="&" if len(request.query_string)>0 else "")+request.query_string
    contents=myresponse(url)
    log_slow_request(request.url,time.time()-t_start)
    return contents

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def notfound(path):
    red.incr("stats:invalidrequests", amount=1)
    response=make_response("Not found\n")
    response.code=404
#    return 'You want path: %s \n' % path+" "+request.method
    return response

if __name__ == '__main__':
    app.run(debug=True)
