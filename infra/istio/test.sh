#!/bin/bash
set -euxo pipefail

export CTX_CLUSTER1="cloud-k3s-master1"
export CTX_CLUSTER2="fog-k3s-master1"
export CTX_CLUSTER3="fog-k0s"

kubectl create --context="${CTX_CLUSTER1}" namespace sample
kubectl create --context="${CTX_CLUSTER2}" namespace sample
kubectl create --context="${CTX_CLUSTER3}" namespace sample

kubectl label --context="${CTX_CLUSTER1}" namespace sample \
  istio-injection=enabled
kubectl label --context="${CTX_CLUSTER2}" namespace sample \
  istio-injection=enabled
kubectl label --context="${CTX_CLUSTER3}" namespace sample \
  istio-injection=enabled

kubectl apply --context="${CTX_CLUSTER1}" \
  -f test/helloworld.yaml \
  -l service=helloworld -n sample
kubectl apply --context="${CTX_CLUSTER2}" \
  -f test/helloworld.yaml \
  -l service=helloworld -n sample
kubectl apply --context="${CTX_CLUSTER3}" \
  -f test/helloworld.yaml \
  -l service=helloworld -n sample

kubectl apply --context="${CTX_CLUSTER1}" \
  -f test/helloworld.yaml \
  -l version=v1 -n sample
kubectl apply --context="${CTX_CLUSTER2}" \
  -f test/helloworld.yaml \
  -l version=v2 -n sample
kubectl apply --context="${CTX_CLUSTER3}" \
  -f test/helloworld.yaml \
  -l version=v3 -n sample

kubectl apply --context="${CTX_CLUSTER1}" \
  -f test/curl.yaml -n sample
kubectl apply --context="${CTX_CLUSTER2}" \
  -f test/curl.yaml -n sample
kubectl apply --context="${CTX_CLUSTER3}" \
  -f test/curl.yaml -n sample

# Verify, that we're load balancing across v1, v2 and v3

kubectl exec --context="${CTX_CLUSTER1}" -n sample -c curl \
  "$(kubectl get pod --context="${CTX_CLUSTER1}" -n sample -l app=curl -o jsonpath='{.items[0].metadata.name}')" \
  -- sh -c 'while true; do curl -sS helloworld.sample:5000/hello; sleep 0.1; done'

kubectl exec --context="${CTX_CLUSTER2}" -n sample -c curl \
  "$(kubectl get pod --context="${CTX_CLUSTER2}" -n sample -l app=curl -o jsonpath='{.items[0].metadata.name}')" \
  -- sh -c 'while true; do curl -sS helloworld.sample:5000/hello; sleep 0.1; done'

kubectl exec --context="${CTX_CLUSTER3}" -n sample -c curl \
  "$(kubectl get pod --context="${CTX_CLUSTER3}" -n sample -l app=curl -o jsonpath='{.items[0].metadata.name}')" \
  -- sh -c 'while true; do curl -sS helloworld.sample:5000/hello; sleep 0.1; done'