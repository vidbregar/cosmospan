import argparse
import jinja2
import pandas as pd
import numpy as np
import shutil
import os
import json
import yaml


def gib_to_kib(gib_value):
    GiB_to_Bytes = 1024 ** 3
    Bytes_to_KiB = 1024

    value_bytes = gib_value * GiB_to_Bytes
    value_kib = value_bytes / Bytes_to_KiB

    value_kib_rounded = round(value_kib)

    return value_kib_rounded


def create_batches(lst, batch_size=10):
    return [lst[i:i + batch_size] for i in range(0, len(lst), batch_size)]


def prepare_node_specs(nodes_file: str, node_latencies_file: str, scheduler_name: str):
    output_dir = "data/node_specs"

    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    node_template = None
    environment = jinja2.Environment()
    with open("node.yaml.j2", "r") as f:
        node_template = environment.from_string(f.read())

    if node_template is None:
        exit(1)

    df = None
    with open(nodes_file) as f:
        df = pd.read_csv(f, comment='#')
        df = df.replace({np.nan: None})

    if df is None:
        exit(1)

    nodes_rendered = []
    for _, node in df.iterrows():
        node = node.to_dict()
        node["scheduler_name"] = scheduler_name
        node["normalized_cores"] = float(node["cpu_cores"]) * (
                float(node["single_core_score"]) / float(node["base_single_core_score"]))
        node["memory_KiB"] = gib_to_kib(float(node["memory_GiB"]))
        nodes_rendered.append(node_template.render(node))

    nodes_rendered_batched = create_batches(nodes_rendered, 30)

    i = 0
    for batch in nodes_rendered_batched:
        content = "\n---\n".join(batch)
        with open(f"{output_dir}/batch-{i:04d}.yaml", "w") as f:
            f.write(content)

        i += 1

    # Prepare NetworkTopology Custom Resource
    network_topology_output_dir = "data/network_topology_specs"
    os.makedirs(network_topology_output_dir, exist_ok=True)

    inter_cluster_data = {}
    with open(node_latencies_file, "r") as f:
        full_latencies_data = json.load(f)
        inter_cluster_data = full_latencies_data.get("inter-cluster", {})

    # Create a symmetric cost matrix
    symmetric_inter_cluster_data = {k: v.copy() for k, v in inter_cluster_data.items()}
    for origin, destinations in inter_cluster_data.items():
        for destination, cost in destinations.items():
            if destination not in symmetric_inter_cluster_data:
                symmetric_inter_cluster_data[destination] = {}
            if origin not in symmetric_inter_cluster_data[destination]:
                symmetric_inter_cluster_data[destination][origin] = cost

    origin_costs_list = []
    for origin, destinations in symmetric_inter_cluster_data.items():
        costs = []
        for destination, network_cost in destinations.items():
            costs.append({
                "destination": destination,
                # Spec also defines this, but currently network aware scheduler does not use it, thus it's pointless to set it.
                # "bandwidthCapacity": "",
                "networkCost": network_cost
            })
        origin_costs_list.append({
            "origin": origin,
            "costList": costs
        })

    network_topology = {
        "apiVersion": "networktopology.diktyo.x-k8s.io/v1alpha1",
        "kind": "NetworkTopology",
        "metadata": {
            "name": "net-topology-test",  # must match whatever is in the scheduler-config.yaml
            "namespace": "default"
        },
        "spec": {
            "configmapName": "cosmospandataset",
            "weights": [
                {
                    "name": "UserDefined",
                    "topologyList": [
                        {
                            "topologyKey": "topology.kubernetes.io/region",
                            "originList": origin_costs_list
                        }
                    ]
                }
            ]
        }
    }

    with open(f"{network_topology_output_dir}/network-topology.yaml", "w") as f:
        yaml.dump(network_topology, f, sort_keys=False)


def prepare_deployment_specs(pods_file: str, workload_latency_requests_file: str, scheduler_name: str):
    output_dir = "data/deployment_specs"

    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    app_group_output_dir = "data/app_group_specs"
    shutil.rmtree(app_group_output_dir, ignore_errors=True)
    os.makedirs(app_group_output_dir, exist_ok=True)

    pod_template = None
    environment = jinja2.Environment()
    with open("deployment.yaml.j2", "r") as f:
        pod_template = environment.from_string(f.read())

    if pod_template is None:
        exit(1)

    df = None
    with open(pods_file) as f:
        df = pd.read_csv(f, comment='#')
        df = df.replace({np.nan: None})

    if df is None:
        exit(1)

    # Transform from pods to deployments
    df["id"] = df["id"].str.rsplit("-replica-", n=1).str[0]
    replica_counts = df["id"].value_counts()
    df = df.drop(columns=["replica_id"]).drop_duplicates(subset=["id"]).copy()
    df["replicas"] = df["id"].map(replica_counts)

    deployments_rendered = []
    for _, deployment in df.iterrows():
        deployment = deployment.to_dict()
        deployment["scheduler_name"] = scheduler_name
        deployment["memory_request_KiB"] = gib_to_kib(float(deployment["memory_request_GiB"]))
        deployments_rendered.append(pod_template.render(deployment))

    deployments_rendered_batched = create_batches(deployments_rendered, 1)

    i = 0
    for batch in deployments_rendered_batched:
        content = "\n---\n".join(batch)
        with open(f"{output_dir}/batch-{i:04d}.yaml", "w") as f:
            f.write(content)

        i += 1

    # Prepare AppGroup Custom Resources
    with open(workload_latency_requests_file) as f:
        workload_dependencies = json.load(f)

    df["app_group"] = (
            "app-"
            + df["app_type"].astype(str)
            + "-"
            + df["app_id"].astype(str)
    )

    app_groups = df["app_group"].unique()

    for i, app_group in enumerate(app_groups):
        workloads = df[df["app_group"] == app_group]

        all_workloads = workloads["id"].tolist()

        app_group_spec = {
            "apiVersion": "appgroup.diktyo.x-k8s.io/v1alpha1",
            "kind": "AppGroup",
            "metadata": {
                "name": f"{app_group}",
            },
            "spec": {
                "numMembers": len(all_workloads),
                "topologySortingAlgorithm": "KahnSort",  # picking default from examples
                "workloads": []
            }
        }

        for workload_name in all_workloads:
            workload_object = {
                "workload": {
                    "kind": "Deployment",
                    "name": workload_name,
                    "selector": workload_name,
                    "apiVersion": "apps/v1",
                    "namespace": "default"
                }
            }

            if workload_name in workload_dependencies:
                dependencies = []
                for dep_name, _ in workload_dependencies[workload_name].items():
                    dependency = {
                        "workload": {
                            "kind": "Deployment",
                            "name": dep_name,
                            "selector": dep_name,
                            "apiVersion": "apps/v1",
                            "namespace": "default"
                        },
                        # Spec also defines this, but currently network aware scheduler does not use it, thus it's pointless to set it.
                        # "minBandwidth": "",
                        "maxNetworkCost": workload_dependencies[workload_name][dep_name]
                    }
                    dependencies.append(dependency)

                if dependencies:
                    workload_object["dependencies"] = dependencies

            app_group_spec["spec"]["workloads"].append(workload_object)

        with open(f"{app_group_output_dir}/batch-{i:04d}.yaml", "w") as f:
            yaml.dump(app_group_spec, f, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(description="Prepare resource specifications for different schedulers.")
    parser.add_argument(
        "--scheduler",
        type=str,
        choices=["kubernetes-default-scheduler", "network-aware-scheduler", "cosmospan-scheduler"],
        help="Specify the scheduler type (kubernetes-default-scheduler, network-aware-scheduler, cosmospan-scheduler).",
        required=True,
    )

    parser.add_argument(
        "--nodes",
        type=str,
        help="Specify path to the nodes dataset we want to use to prepare the simulation for. Example: ../datasets/1000_nodes_50_util_1/nodes.csv",
        required=True,
    )

    parser.add_argument(
        "--node-latencies",
        type=str,
        help="Specify path to the node latencies dataset we want to use to prepare the simulation for. Example: ../datasets/1000_nodes_50_util_1/node-latencies",
        required=True,
    )

    parser.add_argument(
        "--pods",
        type=str,
        help="Specify path to the pods dataset we want to use to prepare the simulation for. Example: ../datasets/1000_nodes_50_util_1/pods.csv",
        required=True,
    )

    parser.add_argument(
        "--workload-latency-requests",
        type=str,
        help="Specify path to the workload latency requests dataset we want to use to prepare the simulation for. Example: ../datasets/1000_nodes_50_util_1/workload-latency-requests.json",
        required=True,
    )

    args = parser.parse_args()

    scheduler_name = args.scheduler
    nodes_file = args.nodes
    node_latencies_file = args.node_latencies
    pods_file = args.pods
    workload_latency_requests_file = args.workload_latency_requests

    prepare_node_specs(nodes_file, node_latencies_file, scheduler_name)
    prepare_deployment_specs(pods_file, workload_latency_requests_file, scheduler_name)

    print("Finished preparing resource specs")


if __name__ == "__main__":
    main()
