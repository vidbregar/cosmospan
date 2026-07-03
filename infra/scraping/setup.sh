#!/bin/bash
set -euxo pipefail

export CTX_CLUSTER1="cloud-k3s-master1"
export CTX_CLUSTER2="fog-k3s-master1"
export CTX_CLUSTER3="fog-k0s"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install --kube-context $CTX_CLUSTER1 kube-state-metrics \
  prometheus-community/kube-state-metrics \
  -n monitoring \
  --create-namespace
helm install --kube-context $CTX_CLUSTER2 kube-state-metrics \
  prometheus-community/kube-state-metrics \
  -n monitoring \
  --create-namespace
helm install --kube-context $CTX_CLUSTER3 kube-state-metrics \
  prometheus-community/kube-state-metrics \
  -n monitoring \
  --create-namespace

kubectl --context $CTX_CLUSTER1 create namespace alloy
kubectl label --context $CTX_CLUSTER1 namespace alloy \
  istio-injection=enabled
helm install \
  --kube-context $CTX_CLUSTER1 \
  --namespace alloy alloy grafana/alloy \
  --version 1.8.2 --values config.yaml

kubectl --context $CTX_CLUSTER2 create namespace alloy
kubectl label --context $CTX_CLUSTER2 namespace alloy \
  istio-injection=enabled
helm install \
  --kube-context $CTX_CLUSTER2 \
  --namespace alloy alloy grafana/alloy \
  --version 1.8.2 --values config.yaml

kubectl --context $CTX_CLUSTER3 create namespace alloy
kubectl label --context $CTX_CLUSTER3 namespace alloy \
  istio-injection=enabled
helm install \
  --kube-context $CTX_CLUSTER3 \
  --namespace alloy alloy grafana/alloy \
  --version 1.8.2 --values config.yaml
