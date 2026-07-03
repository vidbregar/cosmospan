Generate a temporary SSH key to be used for all VMs (no passphrase)
ssh-keygen -t ed25519 -f ~/.ssh/hetzner -C "example@example.com"

What we'll use:
- https://docs.k0sproject.io/v0.9.1/k0s-single-node/
- https://k3s.io/
- https://github.com/vitobotta/hetzner-k3s
- https://grafana.com/oss/mimir/
- https://grafana.com/oss/alloy-opentelemetry-collector/
- https://karmada.io/
- https://istio.io/latest/docs/setup/install/multicluster/multi-primary_multi-network/

Set this env with your Hetzner token
```bash
export HCLOUD_TOKEN="<token>"
```

## Spin up fog node

In the UI create cpx41 in Hillsboro, OR datacenter.

```bash
cd fog-k0s
export FOG_K0S_IP="5.78.70.17"
rsync -avz -e "ssh -i ~/.ssh/hetzner" . root@$FOG_K0S_IP:/root/k0s/
ssh -i ~/.ssh/hetzner root@$FOG_K0S_IP
# on the VM
cd ~/k0s
./setup.sh
exit
scp -i ~/.ssh/hetzner root@$FOG_K0S_IP:/root/.kube/config ./kubeconfig
cd ..
```

## Spin up fog cluster

```bash
cd fog-k3s
hetzner-k3s create --config cluster.yaml
cd ..
```

## Spin up cloud cluster

```bash
cd cloud-k3s
hetzner-k3s create --config cluster.yaml
cd ..
```

## Merge all kubeconfigs

```bash
export KUBECONFIG="$(pwd)/fog-k0s/kubeconfig:$(pwd)/fog-k3s/kubeconfig:$(pwd)/cloud-k3s/kubeconfig"
kubectl config view --flatten > kubeconfig
export KUBECONFIG="$(pwd)/kubeconfig"
```

## Install Istio

```bash
cd istio
# or run commands one by one, it's not idempotent...
./setup.sh
# optionally run commands in test.sh to see if everything is set tup correctly
cd ..
```

# Install Karmada

```bash
cd karmada
kubectl config use-context cloud-k3s-master1
export K3S_CLOUD_IP="$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' | awk -F '[/:]' '{print $4}')"
rsync -avz -e "ssh -i ~/.ssh/hetzner" . root@$K3S_CLOUD_IP:/root/karmada/

ssh -i ~/.ssh/hetzner root@$K3S_CLOUD_IP
# on the VM
cd ~/karmada
./setup_control_plane.sh
exit

rsync -e "ssh -i ~/.ssh/hetzner" ../fog-k0s/kubeconfig root@$K3S_CLOUD_IP:/root/karmada/config/fog-k0s-kubeconfig
rsync -e "ssh -i ~/.ssh/hetzner" ../fog-k3s/kubeconfig root@$K3S_CLOUD_IP:/root/karmada/config/fog-k3s-kubeconfig

ssh -i ~/.ssh/hetzner root@$K3S_CLOUD_IP
# on the VM
cd ~/karmada
karmadactl --kubeconfig config/karmada-apiserver.config join fog-k0s --cluster-context fog-k0s --cluster-kubeconfig=./config/fog-k0s-kubeconfig
karmadactl --kubeconfig config/karmada-apiserver.config join fog-k3s --cluster-context fog-k3s-master1 --cluster-kubeconfig=./config/fog-k3s-kubeconfig
# see that both fog clusters are joined
kubectl --kubeconfig config/karmada-apiserver.config get clusters
exit
cd ..
```

## Install Mimir

```bash
cd mimir
./setup.sh
cd ..
```

## Install Alloy and kube-state-metrics

```bash
cd scraping
./setup.sh
# Optionally, install Grafana with grafana.sh in cloud cluster to verify data scraping works.
# Port forward and add http://mimir-gateway.mimir.svc.cluster.local:80/prometheus datasource.
cd ..
```

All done. Now see, latency-benchmark[latency-benchmark](latency-benchmark) and [resource-overhead-benchmark](resource-overhead-benchmark).
Move results to [results](../results).

## Cleanup

```bash
# Delete fog-k0s in the UI, for the rest:
cd cloud-k3s
hetzner-k3s delete --config cluster.yaml
cd ..

cd fog-k3s
hetzner-k3s delete --config cluster.yaml
cd ..
```
