#!/bin/bash
set -euo pipefail


export KUBECONFIG=$(cd .. && pwd)/kubeconfig.yaml
NODE_DIRECTORY="data/node_specs"
NET_TOP_DIRECTORY="data/network_topology_specs"

if [[ "$(kubectl config current-context)" != "kwok" ]]; then
  echo "kubectl context is not kwok, something must be wrong, aborting"
  exit 1
fi

for FILE in $NODE_DIRECTORY/*.yaml; do
  kubectl apply --server-side -f "$FILE"

  if [ $? -eq 0 ]; then
    echo "Successfully applied $FILE"
  else
    echo "Failed to apply $FILE"
  fi
done

echo "Applying network topology"

kubectl apply --server-side -f "$NET_TOP_DIRECTORY"
