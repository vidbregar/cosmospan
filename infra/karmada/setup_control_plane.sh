#!/bin/bash
set -e

export KARMADA_VERSION="1.18.0"

curl -s https://raw.githubusercontent.com/karmada-io/karmada/master/hack/install-cli.sh | sudo INSTALL_CLI_VERSION=$KARMADA_VERSION bash
mkdir -p configs

export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"

karmadactl init --context="default" \
  --karmada-data="config" \
  --karmada-pki="config/pki" \
  --crds="https://github.com/karmada-io/karmada/releases/download/v$KARMADA_VERSION/crds.tar.gz" \
  --karmada-aggregated-apiserver-image="docker.io/karmada/karmada-aggregated-apiserver:v$KARMADA_VERSION" \
  --karmada-controller-manager-image="docker.io/karmada/karmada-controller-manager:v$KARMADA_VERSION" \
  --karmada-scheduler-image="docker.io/karmada/karmada-scheduler:v$KARMADA_VERSION" \
  --karmada-webhook-image="docker.io/karmada/karmada-webhook:v$KARMADA_VERSION"
