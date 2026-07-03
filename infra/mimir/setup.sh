#!/bin/bash
set -euxo pipefail

export CTX_CLUSTER1="cloud-k3s-master1"
export CTX_CLUSTER2="fog-k3s-master1"
export CTX_CLUSTER3="fog-k0s"

#### Cloud cluster
kubectl --context $CTX_CLUSTER1 create namespace mimir
kubectl label --context $CTX_CLUSTER1 namespace mimir \
  istio-injection=enabled

helm install mimir grafana/mimir-distributed \
  --kube-context $CTX_CLUSTER1 \
  --version 6.0.6 \
  --namespace mimir

#### Fog (access to Mimir API only)
kubectl --context $CTX_CLUSTER2 create namespace mimir
kubectl label --context $CTX_CLUSTER2 namespace mimir \
  istio-injection=enabled

kubectl --context $CTX_CLUSTER2 apply -f mimir-gateway-service.yaml

kubectl --context $CTX_CLUSTER3 create namespace mimir
kubectl label --context $CTX_CLUSTER3 namespace mimir \
  istio-injection=enabled

kubectl --context $CTX_CLUSTER3 apply -f mimir-gateway-service.yaml
