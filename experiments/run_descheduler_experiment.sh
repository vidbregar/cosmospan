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

DATASET="$1"

SCHEDULER="cosmospan-scheduler"

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

function simulate_mutations() {
  local is_baseline="$1"

  echo "Resetting simulator..."

  docker compose -f ../kubernetes-default-scheduler/docker-compose.yaml down --volumes --timeout 0
  docker compose -f ../cosmospan-scheduler/docker-compose.yaml down --volumes --timeout 0
  docker compose -f ../network-aware-scheduler/docker-compose.yaml down --volumes --timeout 0

  docker compose down --volumes --timeout 0
  docker compose up -d

  sleep 10

  echo "Applying crds..."
  kubectl apply -f ../network-aware-scheduler/crds

  if [[ ! -d "$DATASET/mutations" ]]; then
    echo "Invalid dataset provided. It must include pre-generated mutations."
    exit 1
  fi

  echo "Bootstrapping scheduler"
  cp -R "$DATASET/." ../cosmospan-scheduler/dataset/

  cd "../$SCHEDULER" || {
    echo "Failed cd-ing to ../$SCHEDULER"
  }
  docker compose up -d
  cd - || exit 1

  sleep 10

  for i in {0..10}; do
    echo "============================="
    echo "Starting with mutation $i..."

    echo "Preparing resource specs..."
    uv run prepare_resource_specs.py \
      --scheduler "$SCHEDULER" \
      --nodes "$DATASET/mutations/nodes_$i.csv" \
      --node-latencies "$DATASET/mutations/node-latencies_$i.json" \
      --pods "$DATASET/pods.csv" \
      --workload-latency-requests "$DATASET/workload-latency-requests.json"

    cp "../cosmospan-scheduler/dataset/mutations/nodes_$i.csv" "../$SCHEDULER/dataset/nodes.csv"
    cp "../cosmospan-scheduler/dataset/mutations/node-latencies_$i.json" "../$SCHEDULER/dataset/node-latencies.json"

    if ((i == 0)); then
      ./apply_nodes.sh
      ./apply_deployments.sh
    fi

    if [[ "$is_baseline" == "false" && $i -gt 0 ]]; then
      ./apply_nodes.sh

      [[ "$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/refresh)" == "200" ]] || {
        echo "Error: Refresh failed"
        exit 1
      }

      sleep 30

      echo "Running descheduler..."

      docker run --rm \
        -v ../$SCHEDULER/kubeconfig.yaml:/etc/kubernetes/kubeconfig.yaml \
        -v ../$SCHEDULER/dataset/node-latencies.json:/dataset/node-latencies.json \
        -v ../$SCHEDULER/dataset/workload-latency-requests.json:/dataset/workload-latency-requests.json \
        federation-descheduler:latest
    fi

    wait_for_scheduling

    echo "Fetching results..."

    suffix="proposed"
    if [[ "$is_baseline" == "true" ]]; then
      suffix="baseline"
    fi

    output_file="results/pods_and_nodes_${suffix}_${i}.csv"

    echo "pod_name    node_name" >$output_file

    kubectl get pods -o custom-columns=POD_NAME:.metadata.name,NODE_NAME:.spec.nodeName --no-headers >>$output_file

    echo "Results have been written to $output_file"

  done
}

echo "Running proposed for 10 mutations..."
echo ""
echo ""

simulate_mutations "false"

echo "Running baseline for 10 mutations..."
echo ""
echo ""

simulate_mutations "true"
