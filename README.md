# mybusapp

This is a simple API wrapper for nextbus.com public service. It wraps all original endpoints + adds one for getting a list of routes that do not run at a specified time.

It also caches every request to NextBus api so it fullfills the requirement for not sending the same request to NextBus API within 30 minutes.

Original API docs: http://www.nextbus.com/xmlFeedDocs/NextBusXMLFeed.pdf

## Original assignment text:

For this project you will need to write a scalable and highly available service that will provide real-time data of San Francisco’s buses and trains (SF Muni).

You will be required to write your application in Python or Go and use Docker containers.

The containers will be serving an API, which should be stateless and be able to work seamlessly in your highly available setup. You will need to decide which setup to use.  Make reasonable assumptions, state your assumptions, and proceed.

The system will be complex enough to require multiple containers. Use a system of your choice to run the containers (e.g. Docker Compose, Kubernetes, etc).

NextBus provides a real-time data feed that exposes bus and train service information to the public. The instructions for using the real-time data feed are here:
http://www.nextbus.com/xmlFeedDocs/NextBusXMLFeed.pdf

Your project will extend and wrap NextBus public XML feed as a RESTful HTTP API with the following requirements:
Expose all of the endpoints in the NextBus API
An endpoint to retrieve the routes that are not running at a specific time. For example, the 6 bus does not run between 1 AM and 5 AM, so the output of a query for 2 AM should include the 6.
Two endpoints to retrieve internal statistics about your service:
The total number of queries made to each of the endpoints in your API
A list of slow requests
The output can be in either JSON or XML format (or both).
Do not hurt the NextBus service. The same request should not be made more than once within a 30 second interval.

Please submit all of your code, configuration files and instructions on how to run your service.

Before submitting your project, keep in mind that we will be reviewing your submission not just for completeness, but for code/design quality as well.

## Architecture

This scalable/HA service consists of several components:
- API program, a lousy Python script that exposes itself to port 5000
- Redis, distributed in-memory database
- Load Balancer, which exposes the service to wild

Everything is pre-packed into Docker containers and contains Yaml definitions for Kubernetes as well.

## Endpoints

* `/health-check` - check whether the service is running and has an active Redis connection
* `/slow-queries` - show list of slow queries (and clean them)
* `/stats` - show statistics of number of requests to every endpoint
* `/doesNotRunAtTime/<int:hour>`
* `/routeList/<string:agency>`
* `/routeConfig/<string:agency>/<string:route>`
* `/schedule/<string:agency>/<string:route>`
* `/predictions/bystopid/<string:agency>/<string:stopid>`
* `/predictions/bystopid/<string:agency>/<string:stopid>/<string:routetag>`
* `/predictions/bystoptag/<string:agency>/<string:routetag>/<string:stoptag>`
* `/predictionsForMultiStops/<string:agency>/<string:stop>/... unlimited optional stops`§
* `/messages/<string:agency>/<string:r>/... unlimited optional r's`
* `/vehicleLocations/<string:agency>/<string:routetag>/<string:epoch>`
 
The application also accepts the original format of the nextbus api:

* `http://myendpointurl/agencyList`
* `http://myendpointurl/routeList`
* `http://myendpointurl/routeConfig`
* `http://myendpointurl/predictions`
* `http://myendpointurl/predictionForMultiStops`
* `http://myendpointurl/schedule`
* `http://myendpointurl/messages`
* `http://myendpointurl/vehicleLocations`

Those endpoints just pass `?command=<endpoint>&originalparameters...`

## Deployment

Deploment consists of multiple steps. 

### Prerequisities

You need Docker on the machine where building the image

You need gcloud installed and configured to work against GCE (with some container cluster privileges that are hard to specify within GCE :-)

You need to set `$YOURGCEPROJECTIDENTIFIER` to your project name in GCE:

    export YOURGCEPROJECTIDENTIFIER=google-dummy-name-123

### Create a container cluster.

To create a demo container cluster in GCE, run this command:

    gcloud container --project "$YOURGCEPROJECTIDENTIFIER" clusters create "mybusappcluster" --zone "europe-west1-c" --machine-type "g1-small" --scope "https://www.googleapis.com/auth/compute","https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly" --num-nodes "3" --network "default" --no-enable-cloud-logging --no-enable-cloud-monitoring --enable-autoscaling --min-nodes "3" --max-nodes "10"

This cluster will cost you around $0.08 per hour.

WARNING this cluster will not persist Redis data (we do not store anything that can't be redownloaded). Should you need data to persist, you need to add persistent storage to Redis pods (out of scope of this assignment).

Test that kubectl is working:

    kubectl get pods

You should get an empty output and exitcode=0.

If you were able to deploy the GKE cluster, you should be fine. In case of any problem, refer to GKE documentation.

### Deploy Redis 

Redis deployment files are unmodified from kubernetes repo (https://github.com/kubernetes/kubernetes/). They are included in this repository just for the convenience.

#### Create a bootstrap master
   
    kubectl create -f k8s/redis/redis-master.yaml

#### Create a service to track the sentinels
    
    kubectl create -f k8s/redis/redis-sentinel-service.yaml

#### Create a replication controller for redis servers

    kubectl create -f k8s/redis/redis-controller.yaml

#### Create a replication controller for redis sentinels

    kubectl create -f k8s/redis/redis-sentinel-controller.yaml

Wait for the pods to be in "Running" state (kubectl get pods)

#### Scale both replication controllers

    kubectl scale rc redis --replicas=3
    kubectl scale rc redis-sentinel --replicas=3

Wait for all pods to be in "Running" state (kubectl get pods)

#### Delete the original master pod

    kubectl delete pods redis-master
    
### Clone this repo

Clone this repo to your local dir

    mkdir -p tmp && cd tmp
    git clone https://github.com/michalmedvecky/mybusapp
    cd mybusapp
 
### Build containers for the app

    cd Docker/mybusapp
    docker build -t gcr.io/$YOURGCEPROJECTIDENTIFIER/mybusapp:latest .
    gcloud docker push gcr.io/$YOURGCEPROJECTIDENTIFIER/mybusapp:latest
    cd ../..

### Deploy it to Kubernetes

    sed -i bak 's/YOURGCEPROJECTIDENTIFIER/'$YOURGCEPROJECTIDENTIFIER'/g' k8s/mybusapp/*.yaml
    kubectl create -f k8s/mybusapp/mybusapp.yaml
    kubectl create -f k8s/mybusapp/svc-mybusapp.yaml

### Get the LB public IP

    kubectl get svc mybusapp

Be patient, assigning public IP to the service takes a while

### Access the api
   
    curl http://ip.address.of.the.deployment/agencyList

## Notes 

* The cluster scales automatically, based on cpu load, to more machines. So does the deployment (pods). Autoscaling based on different metrics (reported by container) is in Alpha on k8s.
* The deployment uses k8s loadbalancer. Health check is implemented to check for pods health; in case something fails the container is automatically restarted
* There is no cloud logging, you can get logs from every pod itself (should be done somehow better)

## Known problems

### Couldn't find type: v1beta1.Deployment

    error validating "k8s/mybusapp/mybusapp.yaml": error validating data: couldn't find type: v1beta1.Deployment; if you choose to ignore these errors, turn validation off with --validate=false
 
This means you have an old version of `kubectl`. You have two options
- update kubectl, but be warned that then you might run into trouble 2 (below)
- just add `--validate=false` before `-f` in `kubectl create ...` and you are done.

### "error" : "invalid_grant"

It's your precious `kubectl` that is broken. This happens with version 1.2.5, but 1.2.4 works fine.


