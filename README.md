# mybusapp

This is a simple API wrapper for nextbus.com public service. It wraps all original endpoints + adds one for getting a list of routes that do not run at a specified time.

It also caches every request to NextBus api so it fullfills the requirement for not sending the same request to NextBus API within 30 minutes.

Original API docs: http://www.nextbus.com/xmlFeedDocs/NextBusXMLFeed.pdf

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

WARNING this cluster will not persist Redis data (we do not store anything that can't be redownloaded). Should you need data to persist, you need to add persistent storage to Redis pods (out of scope of this excercise).

### Deploy Redis 

Redis deployment files are unmodified from kubernetes repo (https://github.com/kubernetes/kubernetes/). They are included in this repository just for the convenience.

#### Create a bootstrap master
   
    kubectl create -f examples/storage/redis/redis-master.yaml

#### Create a service to track the sentinels
    
    kubectl create -f examples/storage/redis/redis-sentinel-service.yaml

#### Create a replication controller for redis servers

    kubectl create -f examples/storage/redis/redis-controller.yaml

#### Create a replication controller for redis sentinels

    kubectl create -f examples/storage/redis/redis-sentinel-controller.yaml

#### Scale both replication controllers

    kubectl scale rc redis --replicas=3
    kubectl scale rc redis-sentinel --replicas=3

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

### Deploy it to Kubernetes
TODO

