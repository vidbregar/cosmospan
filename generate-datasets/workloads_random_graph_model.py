import os
import random
import shutil

import networkx as nx
from datetime import datetime
import csv
import json
import collections
import copy

config = {
    "total_cpu_cores": 57660,  # sum of cpu cores of all nodes in the cluster
    "total_memory_GB": 173488,  # sum of memory of all nodes in the cluster
    "total_ingress": 12990850.22702597,
    "total_egress": 13105161.22732197,
    "target_utilization_percent": 70,  # either memory or cpu, whatever is reached first
    "number_of_apps": 60,
    "min_max_api_composition_workloads_top_level": [10, 20],
    "min_max_api_composition_call_depth": [4, 10],
    "min_max_api_composition_randomly_connected_workloads_percent": 20,
    "min_max_messaging_workloads_per_app": [3, 7],
    "min_max_messaging_call_depth": [0, 1],
    "min_max_replication": [6, 30],
    "fog_only_workloads_percentage": 10,
    "cloud_only_workloads_percentage": 10,
    "uptime_request_workloads_percentage": 10,
    "min_max_uptime_request_percentage_30_days": [92, 100],
    "bandwidth_request_workloads_percentage": 7,
    "min_max_ingress_bandwidth_request_per_core": [5, 1500],
    "min_max_egress_bandwidth_request_per_core": [5, 1500],
    "latency_request_workloads_percentage": 10,
    # if node specifies latencies it will be to at least one neighbor and up to max percentage of neighbors
    "max_latency_request_to_neighbors_percentage": 5,
    "min_max_latency_request_value": [7, 30],  # 90p ms
    "min_max_cpu_request_cores": [0.1, 1],
    "min_max_memory_request_GB": [0.5, 3]
}

workloads_global = 0


def create_pod(app_id, app_type, workload_id, replica_id):
    app_type_short = "msg" if app_type == "messaging" else "api-comp"

    cpu_request = round(random.uniform(
        config["min_max_cpu_request_cores"][0],
        config["min_max_cpu_request_cores"][1]
    ), 1)

    memory_request = round(random.uniform(
        config["min_max_memory_request_GB"][0],
        config["min_max_memory_request_GB"][1]
    ), 1)

    layer = random.choices(
        ["fog", "cloud", "edge-cloud"],
        [
            config["fog_only_workloads_percentage"],
            config["cloud_only_workloads_percentage"],
            100 - (config["fog_only_workloads_percentage"] + config["cloud_only_workloads_percentage"])
        ]
    )[0]

    data = {
        "id": f"app-{app_type_short}-{app_id}-workload-{workload_id}-replica-{replica_id}",
        "app_id": app_id,
        "app_type": app_type,
        "workload_id": workload_id,
        "replica_id": replica_id,
        "layer": layer,
        "cpu_request_cores": cpu_request,
        "memory_request_GiB": memory_request,
        "ingress_bandwidth_request_Mbps": None,
        "egress_bandwidth_request_Mbps": None,
        "uptime_30d_percentage_request": None
    }

    has_uptime_request = random.choices(
        [True, False],
        [config["uptime_request_workloads_percentage"], 100 - config["uptime_request_workloads_percentage"]]
    )[0]

    if has_uptime_request:
        uptime_request = round(random.uniform(
            config["min_max_uptime_request_percentage_30_days"][0],
            config["min_max_uptime_request_percentage_30_days"][1]
        ))

        data["uptime_30d_percentage_request"] = uptime_request

    has_bandwidth_request = random.choices(
        [True, False],
        [config["bandwidth_request_workloads_percentage"], 100 - config["bandwidth_request_workloads_percentage"]]
    )[0]

    if has_bandwidth_request:
        ingress_request = round(
            random.uniform(
                config["min_max_ingress_bandwidth_request_per_core"][0],
                config["min_max_ingress_bandwidth_request_per_core"][1]
            )
        ) * cpu_request

        egress_request = round(
            random.uniform(
                config["min_max_egress_bandwidth_request_per_core"][0],
                config["min_max_egress_bandwidth_request_per_core"][1]
            )
        ) * cpu_request

        data["ingress_bandwidth_request_Mbps"] = ingress_request
        data["egress_bandwidth_request_Mbps"] = egress_request

    return data


def create_messaging_app(G, app_id, app_type):
    workload_id = 0
    broker = create_pod(app_id, app_type, workload_id, 0)
    G.add_node(broker["id"], **broker)

    total_workloads = random.randint(
        config["min_max_messaging_workloads_per_app"][0],
        config["min_max_messaging_workloads_per_app"][1]
    )

    global workloads_global
    workloads_global += total_workloads

    while True:
        workload_id += 1

        api_comp_call_depth = random.randint(
            config["min_max_messaging_call_depth"][0],
            config["min_max_messaging_call_depth"][1]
        )

        if workload_id + 1 + api_comp_call_depth > total_workloads:
            api_comp_call_depth = config["min_max_messaging_call_depth"][0]

        if workload_id + 1 + api_comp_call_depth > total_workloads:
            break

        workload = create_pod(app_id, app_type, workload_id, 0)
        G.add_node(workload["id"], **workload)
        G.add_edge(workload["id"], broker["id"])

        parent = workload
        for _ in range(0, api_comp_call_depth):
            workload_id += 1

            comp_workload = create_pod(app_id, app_type, workload_id, 0)

            G.add_node(comp_workload["id"], **comp_workload)
            G.add_edge(comp_workload["id"], parent["id"])

            parent = comp_workload


def create_api_composition_app(G, app_id, app_type):
    top_level_size = random.randint(
        config["min_max_api_composition_workloads_top_level"][0],
        config["min_max_api_composition_workloads_top_level"][1]
    )

    workloads = []
    icicles = []
    workload_id = 0
    for _ in range(0, top_level_size):
        call_depth = random.randint(
            config["min_max_api_composition_call_depth"][0],
            config["min_max_api_composition_call_depth"][1]
        )

        global workloads_global
        workloads_global += call_depth

        icicle = []
        prev_icicle = None
        for i in range(0, call_depth):
            workload = create_pod(app_id, app_type, workload_id, 0)
            workload["layer"] = i
            workloads.append(workload)

            G.add_node(workload["id"], **workload)

            if prev_icicle is None:
                prev_icicle = workload
            else:
                G.add_edge(workload["id"], prev_icicle["id"])
                prev_icicle = workload

            icicle.append(workload)

            workload_id += 1

        icicles.append(icicle)

    # pick X% of node pairs that are not already connected and connect them
    random_workloads = random.sample(
        workloads,
        round(config["min_max_api_composition_randomly_connected_workloads_percent"] / 100 * len(workloads))
    )

    for w1 in random_workloads:
        # find w2 that is not already connected to w1
        while True:
            w2 = random.choice(workloads)
            if w1 != w2 and not G.has_edge(w1["id"], w2["id"]):
                break

        G.add_edge(w1["id"], w2["id"])


def create_app(G, app_id, app_type):
    if app_type == "messaging":
        create_messaging_app(G, app_id, app_type)
    else:
        create_api_composition_app(G, app_id, app_type)


def replicate_pod(data, replica_id):
    app_type_short = "msg" if data["app_type"] == "messaging" else "api-comp"
    data["id"] = f"app-{app_type_short}-{data['app_id']}-workload-{data['workload_id']}-replica-{replica_id}"
    return data


def replicate(G):
    workloads = list(G.nodes(data=True))
    for id, data in workloads:
        neighbors = list(G.neighbors(id))

        replication_factor = random.randint(
            config["min_max_replication"][0],
            config["min_max_replication"][1]
        )

        for i in range(0, replication_factor):
            d = copy.deepcopy(data)
            replica = replicate_pod(d, i + 1)
            G.add_node(replica["id"], **replica)

            for neighbor in neighbors:
                G.add_edge(replica["id"], neighbor)


def get_total_resources(pods):
    total_memory_GB = 0
    total_total_cpu_cores = 0
    total_ingress = 0
    total_egress = 0

    for pod in pods:
        total_memory_GB += pod["memory_request_GiB"]
        total_total_cpu_cores += pod["cpu_request_cores"]
        total_ingress += 0 if pod["ingress_bandwidth_request_Mbps"] is None else float(
            pod["ingress_bandwidth_request_Mbps"])
        total_egress += 0 if pod["egress_bandwidth_request_Mbps"] is None else float(
            pod["egress_bandwidth_request_Mbps"])

    return total_memory_GB, total_total_cpu_cores, total_ingress, total_egress


def create_latency_requests(G):
    latency_requests = {}

    workloads = list(filter(lambda x: x.endswith("replica-0"), G.nodes()))
    workloads_with_latency_requests = random.sample(workloads, len(workloads) * config[
        "latency_request_workloads_percentage"] // 100)

    for workload in workloads_with_latency_requests:
        neighbors = list(filter(lambda x: x.endswith("replica-0"), G.neighbors(workload)))
        workload = workload.removesuffix("-replica-0")

        selected_neighbors = random.sample(
            neighbors,
            max(1, len(neighbors) * config["max_latency_request_to_neighbors_percentage"] // 100)
        )

        for neighbor in selected_neighbors:
            neighbor = neighbor.removesuffix("-replica-0")

            if workload not in latency_requests:
                latency_requests[workload] = {}
            if neighbor not in latency_requests:
                latency_requests[neighbor] = {}

            value = round(random.uniform(
                config["min_max_latency_request_value"][0],
                config["min_max_latency_request_value"][1]
            ))

            # pod -> neighbor == neighbor -> pods
            latency_requests[workload][neighbor] = value
            latency_requests[neighbor][workload] = value

    return latency_requests


def print_config(f):
    for key, value in config.items():
        f.write(f'# {key}: {value}\n')

    f.write("#\n")


def main():
    G = nx.Graph()

    for app_id in range(0, config["number_of_apps"]):
        app_type = random.choice(["api-composition", "messaging"])
        create_app(G, app_id, app_type)

    replicate(G)

    pods = [x[1] for x in G.nodes(data=True)]

    duplicates = [item for item, count in collections.Counter(map(lambda x: x["id"], pods)).items() if count > 1]
    assert len(duplicates) == 0

    latency_requests = create_latency_requests(G)

    total_memory_GiB, total_cpu_cores, total_ingress, total_egress = get_total_resources(pods)

    output_dir = "output"
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/pods.csv", 'w', newline='') as f:
        f.write(f"# generated at: {datetime.now()}\n")
        f.write(f"#\n")
        f.write(f"# total pods: {len(pods)}\n")
        f.write(f"# total workloads: {workloads_global}\n")
        f.write(f"# total requested memory of goal:  {round(total_memory_GiB / config['total_memory_GB'] * 100, 1)}%\n")
        f.write(f"# total requested CPU of goal: {round(total_cpu_cores / config['total_cpu_cores'] * 100, 1)}%\n")
        f.write(f"# total requested ingress of goal: {round(total_ingress / config['total_ingress'] * 100, 1)}%\n")
        f.write(f"# total requested egress of goal: {round(total_egress / config['total_egress'] * 100, 1)}%\n")
        f.write(f"#\n")
        print_config(f)

        keys = pods[0].keys()
        dc = csv.DictWriter(f, keys)
        dc.writeheader()
        dc.writerows(pods)

    with open(f"{output_dir}/workload-latency-requests.json", 'w', newline='') as f:
        f.write(json.dumps(latency_requests, indent=2))


if __name__ == '__main__':
    main()
