#!/bin/bash
set -euxo pipefail

export CTX_CLUSTER1="cloud-k3s-master1"
export CTX_CLUSTER2="fog-k3s-master1"
export CTX_CLUSTER3="fog-k0s"

export ISTIO_VERSION="1.29.3"

mkdir -p certs
cd certs || exit 1
make -f ../tools/certs/Makefile.selfsigned.mk \
  ROOTCA_CN="Root CA" \
  ROOTCA_ORG=istio.io \
  root-ca

make -f ../tools/certs/Makefile.selfsigned.mk \
  INTERMEDIATE_CN="Cluster 1 Intermediate CA" \
  INTERMEDIATE_ORG=istio.io \
  cluster1-cacerts

make -f ../tools/certs/Makefile.selfsigned.mk \
  INTERMEDIATE_CN="Cluster 2 Intermediate CA" \
  INTERMEDIATE_ORG=istio.io \
  cluster2-cacerts

make -f ../tools/certs/Makefile.selfsigned.mk \
  INTERMEDIATE_CN="Cluster 3 Intermediate CA" \
  INTERMEDIATE_ORG=istio.io \
  cluster3-cacerts

cd .. || exit 1

kubectl --context="${CTX_CLUSTER1}" create namespace istio-system || true
kubectl --context="${CTX_CLUSTER1}" create secret generic cacerts -n istio-system \
  --from-file=ca-cert.pem=certs/cluster1/ca-cert.pem \
  --from-file=ca-key.pem=certs/cluster1/ca-key.pem \
  --from-file=root-cert.pem=certs/cluster1/root-cert.pem \
  --from-file=cert-chain.pem=certs/cluster1/cert-chain.pem

kubectl --context="${CTX_CLUSTER2}" create namespace istio-system || true
kubectl --context="${CTX_CLUSTER2}" create secret generic cacerts -n istio-system \
  --from-file=ca-cert.pem=certs/cluster2/ca-cert.pem \
  --from-file=ca-key.pem=certs/cluster2/ca-key.pem \
  --from-file=root-cert.pem=certs/cluster2/root-cert.pem \
  --from-file=cert-chain.pem=certs/cluster2/cert-chain.pem

kubectl --context="${CTX_CLUSTER3}" create namespace istio-system || true
kubectl --context="${CTX_CLUSTER3}" create secret generic cacerts -n istio-system \
  --from-file=ca-cert.pem=certs/cluster3/ca-cert.pem \
  --from-file=ca-key.pem=certs/cluster3/ca-key.pem \
  --from-file=root-cert.pem=certs/cluster3/root-cert.pem \
  --from-file=cert-chain.pem=certs/cluster3/cert-chain.pem

helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo update

#### Cluster 1
kubectl --context="${CTX_CLUSTER1}" get namespace istio-system &&
  kubectl --context="${CTX_CLUSTER1}" label namespace istio-system topology.istio.io/network=network1

helm upgrade --install istio-base istio/base -n istio-system --kube-context "${CTX_CLUSTER1}" --version $ISTIO_VERSION
helm upgrade --install istiod istio/istiod -n istio-system --kube-context "${CTX_CLUSTER1}" \
  --set global.meshID=mesh1 \
  --set global.multiCluster.clusterName=cluster1 \
  --set global.network=network1 \
  --version $ISTIO_VERSION
helm upgrade --install istio-eastwestgateway istio/gateway -n istio-system --kube-context "${CTX_CLUSTER1}" \
  --set name=istio-eastwestgateway \
  --set networkGateway=network1 \
  --version $ISTIO_VERSION

kubectl --context="${CTX_CLUSTER1}" apply -n istio-system -f \
  expose-services.yaml

#### Cluster 2
kubectl --context="${CTX_CLUSTER2}" get namespace istio-system &&
  kubectl --context="${CTX_CLUSTER2}" label namespace istio-system topology.istio.io/network=network2

helm upgrade --install istio-base istio/base -n istio-system --kube-context "${CTX_CLUSTER2}" --version $ISTIO_VERSION
helm upgrade --install istiod istio/istiod -n istio-system --kube-context "${CTX_CLUSTER2}" \
  --set global.meshID=mesh1 \
  --set global.multiCluster.clusterName=cluster2 \
  --set global.network=network2 \
  --version $ISTIO_VERSION
helm upgrade --install istio-eastwestgateway istio/gateway -n istio-system --kube-context "${CTX_CLUSTER2}" \
  --set name=istio-eastwestgateway \
  --set networkGateway=network2 \
  --version $ISTIO_VERSION

kubectl --context="${CTX_CLUSTER2}" apply -n istio-system -f \
  expose-services.yaml

#### Cluster 3
kubectl --context="${CTX_CLUSTER3}" get namespace istio-system &&
  kubectl --context="${CTX_CLUSTER3}" label namespace istio-system topology.istio.io/network=network3

helm upgrade --install istio-base istio/base -n istio-system --kube-context "${CTX_CLUSTER3}" --version $ISTIO_VERSION
helm upgrade --install istiod istio/istiod -n istio-system --kube-context "${CTX_CLUSTER3}" \
  --set global.meshID=mesh1 \
  --set global.multiCluster.clusterName=cluster3 \
  --set global.network=network3 \
  --version $ISTIO_VERSION
helm upgrade --install istio-eastwestgateway istio/gateway -n istio-system --kube-context "${CTX_CLUSTER3}" \
  --set name=istio-eastwestgateway \
  --set networkGateway=network3 \
  --version $ISTIO_VERSION

kubectl --context="${CTX_CLUSTER3}" apply -n istio-system -f \
  expose-services.yaml

echo "Waiting for 30s..."
sleep 30

istioctl create-remote-secret \
  --context="${CTX_CLUSTER2}" \
  --name=cluster2 |
  kubectl apply -f - --context="${CTX_CLUSTER1}"

istioctl create-remote-secret \
  --context="${CTX_CLUSTER3}" \
  --name=cluster3 |
  kubectl apply -f - --context="${CTX_CLUSTER1}"

istioctl create-remote-secret \
  --context="${CTX_CLUSTER1}" \
  --name=cluster1 |
  kubectl apply -f - --context="${CTX_CLUSTER2}"

istioctl create-remote-secret \
  --context="${CTX_CLUSTER3}" \
  --name=cluster3 |
  kubectl apply -f - --context="${CTX_CLUSTER2}"

istioctl create-remote-secret \
  --context="${CTX_CLUSTER1}" \
  --name=cluster1 |
  kubectl apply -f - --context="${CTX_CLUSTER3}"

istioctl create-remote-secret \
  --context="${CTX_CLUSTER2}" \
  --name=cluster2 |
  kubectl apply -f - --context="${CTX_CLUSTER3}"

echo "Waiting for 30s..."
sleep 30

# Verify
echo "=================================================="
istioctl remote-clusters --context="${CTX_CLUSTER1}"
istioctl remote-clusters --context="${CTX_CLUSTER2}"
istioctl remote-clusters --context="${CTX_CLUSTER3}"
echo "=================================================="
