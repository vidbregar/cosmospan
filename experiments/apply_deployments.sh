#!/bin/bash
set -euo pipefail


export KUBECONFIG=$(cd .. && pwd)/kubeconfig.yaml
DEP_DIRECTORY="data/deployment_specs"
APP_GRP_DIRECTORY="data/app_group_specs"

if [[ "$(kubectl config current-context)" != "kwok" ]]; then
  echo "kubectl context is not kwok, something must be wrong, aborting"
  exit 1
fi

for FILE in $APP_GRP_DIRECTORY/*.yaml; do
  kubectl apply --server-side -f "$FILE"

  if [ $? -eq 0 ]; then
    echo "Successfully applied $FILE"
  else
    echo "Failed to apply $FILE"
  fi
done

echo "Finished applying app groups. Continuing with deployments..."
sleep 5

for FILE in $DEP_DIRECTORY/*.yaml; do
  kubectl apply --server-side -f "$FILE"

  if [ $? -eq 0 ]; then
    echo "Successfully applied $FILE"
  else
    echo "Failed to apply $FILE"
  fi
  # Deployment compared to batches of pods incur significant overhead
  # since we need to wait for the controller to create pods.
  # Batching deployments more aggressively and slowly deploying helps speed up the process.
  # sleep 2
  # sleep 1
done
