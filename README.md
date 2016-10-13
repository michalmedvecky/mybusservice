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

* `/agencyList` - list agencies
* `/routeList/<agency>` - list routes of the specific agency
* `/routeConfig/<agency>/<route>` - show route config for a specific agency and route

* `/doesNotRunAtTime/<hour>` - list lines that do not run at <hour> (0-23). WARNING! Takes a long time (several minutes) when lines are not cached.
* `/health-check` - check whether the service is running and has an active Redis connection
* `/slow-queries` - show list of slow queries (and clean them)
* `/stats` - show statistics of number of requests to every endpoint
 
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

### Create a container cluster.

To create a demo container cluster in GCE, run this command:

    gcloud container --project "stellar-forest-96608" clusters create "mybusappcluster" --zone "europe-west1-c" --machine-type "g1-small" --scope "https://www.googleapis.com/auth/compute","https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly" --num-nodes "3" --network "default" --no-enable-cloud-logging --no-enable-cloud-monitoring --enable-autoscaling --min-nodes "3" --max-nodes "10"

This cluster will cost you around $0.08 per hour.

### Deploy Redis 

Redis deployment files are unmodified from kubernetes repo (https://github.com/kubernetes/kubernetes/). They are included in this repository just for the convenience.

    
### Clone this repo

Clone this repo to your local dir
    mkdir tmp
    git clone https://github.com/michalmedvecky/mybusapp
    cd mybusapp
 
### Build containers for the app
    cd Docker/mybusapp
    docker build .

### Deploy it to Kubernetes

