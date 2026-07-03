#!/bin/bash
set -euxo pipefail

helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install --kube-context cloud-k3s-master1 grafana grafana/grafana
kubectl get secret --namespace default grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
