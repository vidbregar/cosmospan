import math
import os
import random
import itertools
import csv
import json
import shutil
from datetime import datetime

node_types = {
    "T1": {
        "cpu_cores": 2,
        "memory_GiB": 4
    },
    "T2": {
        "cpu_cores": 2,
        "memory_GiB": 8
    },
    "T3": {
        "cpu_cores": 4,
        "memory_GiB": 8
    },
    "T4": {
        "cpu_cores": 4,
        "memory_GiB": 16
    },
    "T5": {
        "cpu_cores": 8,
        "memory_GiB": 16
    },
    "T6": {
        "cpu_cores": 8,
        "memory_GiB": 32
    },
    "T7": {
        "cpu_cores": 16,
        "memory_GiB": 32
    },
    "T8": {
        "cpu_cores": 16,
        "memory_GiB": 64
    },
    "T9": {
        "cpu_cores": 32,
        "memory_GiB": 64
    },
    "T10": {
        "cpu_cores": 32,
        "memory_GiB": 128
    },
}

config = {
    "n": 900,  # total number of nodes
    "cloud_size_percentage": 20,  # % of n that are cloud nodes
    "fog_size_percentage": 80,  # % of n that are fog nodes
    "min_max_cloud_cluster_size_percentage": [5, 15],  # % of cloud size rounded down
    "min_max_fog_cluster_size_percentage": [1, 5],  # % of fog size rounded down
    "cloud_node_types": ["T4", "T5", "T6", "T7", "T8", "T9", "T10"],
    "fog_node_types": ["T1", "T2", "T3", "T4"],
    "base_node_single_core_score": 1000,
    "min_max_cloud_node_single_core_score": [900, 1800],
    "min_max_fog_node_single_core_score": [500, 1200],
    "min_max_cluster_node_cost_per_core": [100, 300],  # unit not important, but higher value means more expensive
    "nodes_with_bandwidth_capacity_percentage": 30,  # % of all nodes that specify bandwidth capacity
    "min_max_ingress_bandwidth_per_core": [10, 1500],  # Mbps
    "min_max_egress_bandwidth_per_core": [10, 1500],  # Mbps
    "min_max_cloud_uptime_percentage_30_days": [97, 100],
    "min_max_fog_uptime_percentage_30_days": [90, 100],
    "min_max_intra_cluster_latencies": [2, 5],  # 90p ms (within same region)
    "min_max_inter_cluster_latencies": [15, 50]  # 90p ms (regions in Europe)
}


def create_node(layer,
                location,
                layer_node_types,
                min_single_core_score,
                max_single_core_score,
                base_single_core_score,
                has_bandwidth_specified,
                min_ingress_bandwidth_per_core, max_ingress_bandwidth_per_core,
                min_egress_bandwidth_per_core, max_egress_bandwidth_per_core,
                min_uptime_percentage_30_days, max_uptime_percentage_30_days,
                min_cost_per_core, max_cost_per_core):
    node_type = node_types[random.choice(layer_node_types)]
    cpu_cores = node_type["cpu_cores"]
    memory = node_type["memory_GiB"]
    single_core_score = random.randint(min_single_core_score, max_single_core_score)

    cost = random.uniform(min_cost_per_core, max_cost_per_core) * cpu_cores
    uptime = random.uniform(min_uptime_percentage_30_days, max_uptime_percentage_30_days)

    node = {
        "hostname": None,
        "layer": layer,
        "location": location, # fog location or more granular cloud region
        "cpu_cores": cpu_cores,
        "single_core_score": single_core_score,
        "base_single_core_score": base_single_core_score,
        "memory_GiB": memory,
        "ingress_bandwidth_Mbps": None,
        "egress_bandwidth_Mbps": None,
        "uptime_30d_percentage": uptime,
        "cost": cost
    }

    if has_bandwidth_specified:
        ingress_bandwidth = random.uniform(min_ingress_bandwidth_per_core, max_ingress_bandwidth_per_core) * cpu_cores
        egress_bandwidth = random.uniform(min_egress_bandwidth_per_core, max_egress_bandwidth_per_core) * cpu_cores

        node["ingress_bandwidth_Mbps"] = f"{ingress_bandwidth}"
        node["egress_bandwidth_Mbps"] = f"{egress_bandwidth}"

    return node


def create_fog_clusters(nodes_count,
                        min_size,
                        max_size,
                        has_bandwidth_count,
                        ):
    layer_node_types = config["fog_node_types"]
    min_single_core_score = config["min_max_fog_node_single_core_score"][0]
    max_single_core_score = config["min_max_fog_node_single_core_score"][1]
    base_single_core_score = config["base_node_single_core_score"]
    min_ingress_bandwidth_per_core = config["min_max_ingress_bandwidth_per_core"][0]
    max_ingress_bandwidth_per_core = config["min_max_ingress_bandwidth_per_core"][1]
    min_egress_bandwidth_per_core = config["min_max_egress_bandwidth_per_core"][0]
    max_egress_bandwidth_per_core = config["min_max_egress_bandwidth_per_core"][1]
    min_uptime_percentage_30_days = config["min_max_fog_uptime_percentage_30_days"][0]
    max_uptime_percentage_30_days = config["min_max_fog_uptime_percentage_30_days"][1]
    min_cost_per_core = config["min_max_cluster_node_cost_per_core"][0]
    max_cost_per_core = config["min_max_cluster_node_cost_per_core"][1]
    layer = "fog"

    clusters = []
    with_bandwidth_nodes_left = has_bandwidth_count
    i = 0
    id = 0
    while i < nodes_count:
        cluster_size = random.randint(
            min_size,
            max_size
        )

        # random cluster would overflow nodes_count
        if i + cluster_size > nodes_count:
            # cluster is too small, break loop and use nodes_left strategy
            if nodes_count - i < min_size:
                break

            # try setting size to what is left
            cluster_size = nodes_count - i

        i += cluster_size

        # impossible to create another cluster, break loop and use nodes_left strategy
        if i > nodes_count:
            break

        cluster = []
        for j in range(0, cluster_size):
            has_bandwidth_specified = False
            if with_bandwidth_nodes_left >= 0:
                has_bandwidth_specified = True
                with_bandwidth_nodes_left -= 1

            cluster.append(create_node(
                layer=layer,
                location=f"fog-location-{id}",
                layer_node_types=layer_node_types,
                min_single_core_score=min_single_core_score,
                max_single_core_score=max_single_core_score,
                base_single_core_score=base_single_core_score,
                has_bandwidth_specified=has_bandwidth_specified,
                min_ingress_bandwidth_per_core=min_ingress_bandwidth_per_core,
                max_ingress_bandwidth_per_core=max_ingress_bandwidth_per_core,
                min_egress_bandwidth_per_core=min_egress_bandwidth_per_core,
                max_egress_bandwidth_per_core=max_egress_bandwidth_per_core,
                min_uptime_percentage_30_days=min_uptime_percentage_30_days,
                max_uptime_percentage_30_days=max_uptime_percentage_30_days,
                min_cost_per_core=min_cost_per_core, max_cost_per_core=max_cost_per_core)
            )

        clusters.append(cluster)

        id += 1

    # add missing nodes to existing clusters that have space since a new cluster cannot be created
    nodes_left = nodes_count - i
    for cluster in clusters:
        if nodes_left <= 0:
            break

        if len(cluster) < max_size:
            space = max_size - len(cluster)
            for _ in range(0, space):
                has_bandwidth_specified = False
                if with_bandwidth_nodes_left >= 0:
                    has_bandwidth_specified = True
                    with_bandwidth_nodes_left -= 1

                cluster.append(create_node(
                    layer=layer,
                    location=cluster[0]["location"],
                    layer_node_types=layer_node_types,
                    min_single_core_score=min_single_core_score,
                    max_single_core_score=max_single_core_score,
                    base_single_core_score=base_single_core_score,
                    has_bandwidth_specified=has_bandwidth_specified,
                    min_ingress_bandwidth_per_core=min_ingress_bandwidth_per_core,
                    max_ingress_bandwidth_per_core=max_ingress_bandwidth_per_core,
                    min_egress_bandwidth_per_core=min_egress_bandwidth_per_core,
                    max_egress_bandwidth_per_core=max_egress_bandwidth_per_core,
                    min_uptime_percentage_30_days=min_uptime_percentage_30_days,
                    max_uptime_percentage_30_days=max_uptime_percentage_30_days,
                    min_cost_per_core=min_cost_per_core, max_cost_per_core=max_cost_per_core)
                )
            nodes_left -= space

    return clusters


def create_cloud_clusters(nodes_count,
                          min_size,
                          max_size,
                          has_bandwidth_count):
    layer_node_types = config["cloud_node_types"]
    min_single_core_score = config["min_max_cloud_node_single_core_score"][0]
    max_single_core_score = config["min_max_cloud_node_single_core_score"][1]
    base_single_core_score = config["base_node_single_core_score"]
    min_ingress_bandwidth_per_core = config["min_max_ingress_bandwidth_per_core"][0]
    max_ingress_bandwidth_per_core = config["min_max_ingress_bandwidth_per_core"][1]
    min_egress_bandwidth_per_core = config["min_max_egress_bandwidth_per_core"][0]
    max_egress_bandwidth_per_core = config["min_max_egress_bandwidth_per_core"][1]
    min_uptime_percentage_30_days = config["min_max_cloud_uptime_percentage_30_days"][0]
    max_uptime_percentage_30_days = config["min_max_cloud_uptime_percentage_30_days"][1]
    min_cost_per_core = config["min_max_cluster_node_cost_per_core"][0]
    max_cost_per_core = config["min_max_cluster_node_cost_per_core"][1]
    layer = "cloud"

    clusters = []
    with_bandwidth_nodes_left = has_bandwidth_count
    i = 0
    id = 0
    while i < nodes_count:
        cluster_size = random.randint(
            min_size,
            max_size
        )

        # random cluster would overflow nodes_count
        if i + cluster_size > nodes_count:
            # cluster is too small, break loop and use nodes_left strategy
            if nodes_count - i < min_size:
                break

            # try setting size to what is left
            cluster_size = nodes_count - i

        i += cluster_size

        # impossible to create another cluster, break loop and use nodes_left strategy
        if i > nodes_count:
            break

        cluster = []
        for j in range(0, cluster_size):
            has_bandwidth_specified = False
            if with_bandwidth_nodes_left >= 0:
                has_bandwidth_specified = True
                with_bandwidth_nodes_left -= 1

            cluster.append(create_node(
                layer=layer,
                location=f"cloud-location-{id}",
                layer_node_types=layer_node_types,
                min_single_core_score=min_single_core_score,
                max_single_core_score=max_single_core_score,
                base_single_core_score=base_single_core_score,
                has_bandwidth_specified=has_bandwidth_specified,
                min_ingress_bandwidth_per_core=min_ingress_bandwidth_per_core,
                max_ingress_bandwidth_per_core=max_ingress_bandwidth_per_core,
                min_egress_bandwidth_per_core=min_egress_bandwidth_per_core,
                max_egress_bandwidth_per_core=max_egress_bandwidth_per_core,
                min_uptime_percentage_30_days=min_uptime_percentage_30_days,
                max_uptime_percentage_30_days=max_uptime_percentage_30_days,
                min_cost_per_core=min_cost_per_core, max_cost_per_core=max_cost_per_core)
            )

        clusters.append(cluster)

        id += 1

    # add missing nodes to existing clusters that have space since a new cluster cannot be created
    nodes_left = nodes_count - i
    for cluster in clusters:
        if nodes_left <= 0:
            break

        if len(cluster) < max_size:
            space = max_size - len(cluster)
            for _ in range(0, space):
                has_bandwidth_specified = False
                if with_bandwidth_nodes_left >= 0:
                    has_bandwidth_specified = True
                    with_bandwidth_nodes_left -= 1

                cluster.append(create_node(
                    layer=layer,
                    location=cluster[0]["location"],
                    layer_node_types=layer_node_types,
                    min_single_core_score=min_single_core_score,
                    max_single_core_score=max_single_core_score,
                    base_single_core_score=base_single_core_score,
                    has_bandwidth_specified=has_bandwidth_specified,
                    min_ingress_bandwidth_per_core=min_ingress_bandwidth_per_core,
                    max_ingress_bandwidth_per_core=max_ingress_bandwidth_per_core,
                    min_egress_bandwidth_per_core=min_egress_bandwidth_per_core,
                    max_egress_bandwidth_per_core=max_egress_bandwidth_per_core,
                    min_uptime_percentage_30_days=min_uptime_percentage_30_days,
                    max_uptime_percentage_30_days=max_uptime_percentage_30_days,
                    min_cost_per_core=min_cost_per_core, max_cost_per_core=max_cost_per_core)
                )
            nodes_left -= space

    return clusters


def call_until_no_error(func, *args, **kwargs):
    while True:
        result = func(*args, **kwargs)
        try:
            assert sum(len(cluster) for cluster in result) == args[0]
            return result
        except Exception as e:
            print(e)



def create_latency_graph(cloud_clusters, fog_clusters):
    latencies = {}

    latencies["inter-cluster"] = {}
    cloud_cluster_names = [c[0]["location"] for c in cloud_clusters]
    fog_cluster_names = [c[0]["location"] for c in fog_clusters]
    cluster_names = cloud_cluster_names + fog_cluster_names

    inter_min_latency = config["min_max_inter_cluster_latencies"][0]
    inter_max_latency = config["min_max_inter_cluster_latencies"][1]

    for c1 in cluster_names:
        for c2 in cluster_names:
            if c1 == c2:  # same clusters, no measurement here
                continue

            if c1 > c2:
                continue  # we store only (c1, c2) measurement pairs where c1 < c2 since (c1, c2) == (c2, c1)

            if c1 not in latencies["inter-cluster"]:
                latencies["inter-cluster"][c1] = {}

            latency = random.randint(inter_min_latency, inter_max_latency)
            latencies["inter-cluster"][c1][c2] = latency

    latencies["intra-cluster"] = {}
    intra_min_latency = config["min_max_intra_cluster_latencies"][0]
    intra_max_latency = config["min_max_intra_cluster_latencies"][1]

    clusters = cloud_clusters + fog_clusters
    for cluster in clusters:
        cluster_name = cluster[0]["location"]
        for n1 in cluster:
            n1_hostname = n1["hostname"]
            for n2 in cluster:
                n2_hostname = n2["hostname"]

                if n1_hostname == n2_hostname:  # same node, no measurement here
                    continue

                if n1_hostname > n2_hostname:
                    continue  # we store only (n1, n2) measurement pairs where n1 < n2 since (n1, n2) == (n2, n1)

                if cluster_name not in latencies["intra-cluster"]:
                    latencies["intra-cluster"][cluster_name] = {}

                if n1_hostname not in latencies["intra-cluster"][cluster_name]:
                    latencies["intra-cluster"][cluster_name][n1_hostname] = {}

                latency = random.randint(intra_min_latency, intra_max_latency)
                latencies["intra-cluster"][cluster_name][n1_hostname][n2_hostname] = latency

    return latencies


def print_config(f):
    for key, value in config.items():
        f.write(f'# {key}: {value}\n')

    f.write("#\n")

def main():
    assert config["cloud_size_percentage"] + config["fog_size_percentage"] == 100

    cloud_nodes_count = math.floor(config["cloud_size_percentage"] / 100 * config["n"])
    fog_nodes_count = math.floor(config["fog_size_percentage"] / 100 * config["n"])

    if cloud_nodes_count + fog_nodes_count < config["n"]:
        fog_nodes_count += 1

    cloud_has_bandwidth_count = round(config["nodes_with_bandwidth_capacity_percentage"] / 100 * cloud_nodes_count)
    fog_has_bandwidth_count = round(config["nodes_with_bandwidth_capacity_percentage"] / 100 * fog_nodes_count)

    cloud_clusters = call_until_no_error(
        create_cloud_clusters,
        cloud_nodes_count,
        math.floor(config["min_max_cloud_cluster_size_percentage"][0] / 100 * config["n"]),
        math.floor(config["min_max_cloud_cluster_size_percentage"][1] / 100 * config["n"]),
        cloud_has_bandwidth_count
    )

    fog_clusters = call_until_no_error(
        create_fog_clusters,
        fog_nodes_count,
        math.floor(config["min_max_fog_cluster_size_percentage"][0] / 100 * config["n"]),
        math.floor(config["min_max_fog_cluster_size_percentage"][1] / 100 * config["n"]),
        fog_has_bandwidth_count,
    )

    nodes = list(itertools.chain.from_iterable(cloud_clusters)) + list(itertools.chain.from_iterable(fog_clusters))

    hostname = 0
    for node in nodes:
        node["hostname"] = f"{hostname}"
        hostname += 1

    latencies = create_latency_graph(cloud_clusters, fog_clusters)

    output_dir = "output"
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/nodes.csv", 'w', newline='') as f:
        f.write(f"# generated at: {datetime.now()}\n")
        f.write(f"#\n")
        f.write(f"#### Overview\n")
        f.write(f"# nodes: {config['n']}\n")
        f.write(f"# cloud clusters: {len(cloud_clusters)}\n")
        f.write(f"# \tmax size: {max([len(c) for c in cloud_clusters])}\n")
        f.write(f"# \tmin size: {min([len(c) for c in cloud_clusters])}\n")
        f.write(f"# fog clusters: {len(fog_clusters)}\n")
        f.write(f"# \tmax size: {max([len(c) for c in fog_clusters])}\n")
        f.write(f"# \tmin size: {min([len(c) for c in fog_clusters])}\n")
        f.write(f"# nodes with bandwidth specified: {fog_has_bandwidth_count + cloud_has_bandwidth_count}\n")
        f.write(f"# \tcloud: {cloud_has_bandwidth_count}\n")
        f.write(f"# \tfog: {fog_has_bandwidth_count}\n")
        f.write(f"# total CPU cores: {sum([n['cpu_cores'] for n in nodes])}\n")
        f.write(f"# total memory GiB: {sum([n['memory_GiB'] for n in nodes])}\n")
        ingress = sum(
            [float("0" if n['ingress_bandwidth_Mbps'] is None else n['ingress_bandwidth_Mbps']) for n in nodes])
        f.write(f"# total ingress Mbps: {ingress}\n")
        egress = sum([float("0" if n['egress_bandwidth_Mbps'] is None else n['egress_bandwidth_Mbps']) for n in nodes])
        f.write(f"# total egress Mbps: {egress}\n")
        f.write(f"#\n")
        f.write(f"#### Used Config\n")
        f.write(f"#\n")
        print_config(f)

        keys = nodes[0].keys()
        dc = csv.DictWriter(f, keys)
        dc.writeheader()
        dc.writerows(nodes)

    with open(f"{output_dir}/node-latencies.json", 'w', newline='') as f:
        f.write(json.dumps(latencies, indent=2))


if __name__ == '__main__':
    main()
