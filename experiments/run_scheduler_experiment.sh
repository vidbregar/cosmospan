#!/bin/bash
set -euo pipefail

export KUBECONFIG=$(cd .. && pwd)/kubeconfig.yaml

if [[ "$(kubectl config current-context)" != "kwok" ]]; then
  echo "kubectl context is not kwok, something must be wrong, aborting"
  exit 1
fi

if [ -z "$1" ]; then
  echo "Error: Dataset path argument is missing."
  echo "Example: ../datasets_new/300_nodes_50_util_1"
  exit 1
fi

if [ -z "$2" ]; then
  echo "Error: Scheduler name is missing."
  echo "Example: cosmospan-scheduler"
  exit 1
fi

DATASET="$1"
SCHEDULER="$2"

function wait_for_scheduling() {
  prev=""
  stable=0

  echo "Waiting for scheduling to finish..."

  while [ $stable -lt 15 ]; do
    curr=$(kubectl get pods -A --field-selector spec.nodeName= --no-headers | wc -l)

    if [ "$curr" = "$prev" ]; then
      ((stable += 3))
    else
      stable=0
    fi

    echo "Unscheduled pods: $curr (${stable}s stable)"
    prev=$curr
    sleep 3
  done
}

echo "Resetting simulator..."

docker compose -f ../kubernetes-default-scheduler/docker-compose.yaml down --volumes --timeout 0
docker compose -f ../cosmospan-scheduler/docker-compose.yaml down --volumes --timeout 0
docker compose -f ../network-aware-scheduler/docker-compose.yaml down --volumes --timeout 0

docker compose down --volumes --timeout 0
docker compose up -d

sleep 10

echo "Applying crds..."
kubectl apply -f ../network-aware-scheduler/crds


echo "Bootstrapping scheduler"
cp -r "$DATASET/." ../cosmospan-scheduler/dataset/

cd "../$SCHEDULER" || {
  echo "Failed cd-ing to ../$SCHEDULER"
}
docker compose up -d
cd - || exit 1

sleep 10

echo "Preparing resource specs..."
uv run prepare_resource_specs.py \
  --scheduler "$SCHEDULER" \
  --nodes "$DATASET/nodes.csv" \
  --node-latencies "$DATASET/node-latencies.json" \
  --pods "$DATASET/pods.csv" \
  --workload-latency-requests "$DATASET/workload-latency-requests.json"

./apply_nodes.sh

sleep 1

while kubectl get nodes --no-headers | awk '{print $2}' | grep -qv '^Ready$'; do
    echo "Waiting for the nodes to be ready..."
    sleep 2
done

sleep 5

deploy_start="$(date +%s)"
./apply_deployments.sh

wait_for_scheduling

deploy_end="$(date +%s)"
duration=$((deploy_end - deploy_start - 15))

case "$SCHEDULER" in
    "kubernetes-default-scheduler")
        suffix="default"
        ;;
    "network-aware-scheduler")
        suffix="network_aware"
        ;;
    "cosmospan-scheduler")
        suffix="cosmospan"
        ;;
    *)
        exit 1
esac

OUTPUT_FILE_SCHEDULING="results/pods_and_nodes_${suffix}.csv"
OUTPUT_FILE_TIME="results/scheduling_time_seconds_${suffix}.txt"

if [[ "$(kubectl config current-context)" != "kwok" ]]; then
  echo "kubectl context is not kwok, something must be wrong, aborting"
  exit 1
fi

echo "pod_name    node_name" >$OUTPUT_FILE_SCHEDULING

kubectl get pods -o custom-columns=POD_NAME:.metadata.name,NODE_NAME:.spec.nodeName --no-headers >>$OUTPUT_FILE_SCHEDULING


echo "$duration" >$OUTPUT_FILE_TIME

echo "Results have been written to $OUTPUT_FILE_SCHEDULING and $OUTPUT_FILE_TIME"
echo "Copy files in ./results/ to the global results"
