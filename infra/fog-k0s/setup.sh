#!/bin/bash
set -e

apt update
apt install -y yq
wget https://github.com/derailed/k9s/releases/latest/download/k9s_linux_amd64.deb && sudo apt install ./k9s_linux_amd64.deb && rm k9s_linux_amd64.deb

export K0S_VERSION="v1.35.4+k0s.0"

if command -v k0s &>/dev/null && k0s version | grep -q "${K0S_VERSION}"; then
  echo "k0s version ${K0S_VERSION} is already installed."
else
  echo "Installing k0s version ${K0S_VERSION}..."
  curl -sSLf https://get.k0s.sh | sudo sh
fi

echo "Detecting Public IP..."
TARGET_IP=$(ip route get 1.1.1.1 | grep -oP 'src \K\S+')
if [ -z "$TARGET_IP" ]; then
  echo "Could not automatically detect public IP."
  exit 1
fi
echo "Found Public IP: $TARGET_IP"

echo "Cleaning up existing k0s cluster installations..."
if systemctl is-active --quiet k0scontroller; then
  echo "Stopping k0s service..."
  sudo systemctl stop k0scontroller || true
fi

if command -v k0s &>/dev/null; then
  echo "Running native k0s reset..."
  sudo k0s reset || true
fi

sudo rm -rf /etc/k0s /var/lib/k0s /run/k0s
sudo rm -f /etc/systemd/system/k0scontroller.service
sudo systemctl daemon-reload

echo "Installing fresh k0s binary..."
curl -sSLf https://get.k0s.sh | sudo sh

echo "Creating k0s configuration directory..."
sudo mkdir -p /etc/k0s

echo "Generating k0s.yaml configuration..."
sudo tee /etc/k0s/k0s.yaml >/dev/null <<EOF
apiVersion: k0s.sh/v1beta1
kind: ClusterConfig
metadata:
  name: k0s
spec:
  api:
    address: $TARGET_IP
    sans:
    - $TARGET_IP
    - 127.0.0.1
  extensions:
    storage:
      type: openebs
    helm:
      repositories:
      - name: metallb
        url: https://metallb.github.io/metallb
      charts:
      - name: metallb
        chartname: metallb/metallb
        version: 0.14.5
        namespace: metallb-system
        values: |
          apiWebhook:
            enable: false
          speaker:
            memberlist:
              enabled: true
EOF

echo "Installing and starting k0s service..."
sudo k0s install controller --config /etc/k0s/k0s.yaml --enable-worker --no-taints
sudo systemctl start k0scontroller
sudo systemctl enable k0scontroller

echo "Waiting for Kubernetes API to come online..."
until sudo k0s kubeconfig admin &>/dev/null; do
  sleep 2
done

echo "Syncing kubeconfig..."
mkdir -p "$HOME/.kube"
sudo k0s kubeconfig admin >~/.kube/config
export KUBECONFIG="$HOME/.kube/config"
tmp=$(mktemp)
yq -y '
  .clusters[].name = "fog-k0s" |
  .contexts[].name = "fog-k0s" |
  .contexts[].context.cluster = "fog-k0s" |
  .contexts[].context.user = "fog-k0s" |
  .users[].name = "fog-k0s" |
  .["current-context"] = "fog-k0s"
' $KUBECONFIG >"$tmp" && mv "$tmp" $KUBECONFIG
chmod 600 "$HOME/.kube/config"

echo "Checking kubectl..."
if ! command -v kubectl &>/dev/null; then
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x ./kubectl
  sudo mv ./kubectl /usr/local/bin/kubectl
else
  echo "kubectl is already installed."
fi

echo "Waiting for MetalLB controller deployment..."
until kubectl get deployment metallb-controller -n metallb-system &>/dev/null; do
  sleep 3
done
kubectl rollout status deployment/metallb-controller -n metallb-system --timeout=120s

echo "Applying MetalLB Custom Resources for IP ($TARGET_IP)..."
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: public-ip-pool
  namespace: metallb-system
spec:
  addresses:
  - ${TARGET_IP}/32
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: public-ip-advertisement
  namespace: metallb-system
spec:
  ipAddressPools:
  - public-ip-pool
EOF

echo "Script execution finished successfully!"
echo "Kubeconfig is updated at ~/.kube/config"
