# kube-state-metrics
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install --kube-context cloud-k3s-master1 kube-state-metrics \
prometheus-community/kube-state-metrics \
-n monitoring \
--create-namespace

helm install --kube-context fog-k0s kube-state-metrics \
prometheus-community/kube-state-metrics \
-n monitoring \
--create-namespace

helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm install --kube-context cloud-k3s-master1 grafana grafana/grafana
kubectl get secret --namespace default grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo

kubectl --context cloud-k3s-master1 create namespace alloy
kubectl label --context cloud-k3s-master1 namespace alloy \
istio-injection=enabled

helm install \
--kube-context cloud-k3s-master1 \
--namespace alloy alloy grafana/alloy \
--version 1.8.2 --values config.yaml

kubectl --context fog-k0s create namespace alloy
kubectl label --context fog-k0s namespace alloy \
istio-injection=enabled

helm install \
--kube-context fog-k0s \
--namespace alloy alloy grafana/alloy \
--version 1.8.2 --values config.yaml