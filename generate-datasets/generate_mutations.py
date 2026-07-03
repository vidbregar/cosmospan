import shutil
import random
import numpy as np
import pandas as pd
import json
import argparse
import os
import copy


def mutate(nodes_df, node_latencies, improve: bool):
    # Create copies to avoid modifying the originals
    nodes_df_mutated = nodes_df.copy()
    node_latencies_mutated = copy.deepcopy(node_latencies)

    # Mutate inter-cluster latencies
    clusters = list(node_latencies_mutated["inter-cluster"].keys())
    selected_clusters = random.sample(clusters, max(1, int(len(clusters) * (10 / 100))))

    for cluster in selected_clusters:
        for neighbor_cluster in node_latencies_mutated["inter-cluster"][cluster].keys():
            if improve:
                node_latencies_mutated["inter-cluster"][cluster][neighbor_cluster] = int(
                    round(node_latencies_mutated["inter-cluster"][cluster][neighbor_cluster] * (1 / 2)))
            else:
                node_latencies_mutated["inter-cluster"][cluster][neighbor_cluster] = int(
                    round(node_latencies_mutated["inter-cluster"][cluster][neighbor_cluster] * 2))

    # Mutate node properties
    selected_df = nodes_df_mutated.sample(frac=0.10)

    for i, node in selected_df.iterrows():
        # uptime
        if "uptime_30d_percentage" in nodes_df_mutated.columns and not pd.isna(node["uptime_30d_percentage"]):
            node_uptime = node["uptime_30d_percentage"]
            if improve:
                new_node_uptime = min(node_uptime + 2, 100)
            else:
                new_node_uptime = max(node_uptime - 2, 0)
            nodes_df_mutated.loc[i, "uptime_30d_percentage"] = new_node_uptime

        # bandwidth
        max_ingress_to_add = 0
        max_egress_to_add = 0
        for i, node in selected_df.iterrows():
            if not np.isnan(node["ingress_bandwidth_Mbps"]) and node["ingress_bandwidth_Mbps"] > 0:
                max_ingress_to_add += 1
            if not np.isnan(node["egress_bandwidth_Mbps"]) and node["egress_bandwidth_Mbps"] > 0:
                max_egress_to_add += 1

        if "ingress_bandwidth_Mbps" in nodes_df_mutated.columns and "egress_bandwidth_Mbps" in nodes_df_mutated.columns and "cpu_cores" in nodes_df_mutated.columns:
            if not pd.isna(node["ingress_bandwidth_Mbps"]) and node["ingress_bandwidth_Mbps"] > 0:
                nodes_df_mutated.loc[i, "ingress_bandwidth_Mbps"] = np.nan
            elif max_ingress_to_add > 0:
                cpu_cores = node["cpu_cores"]
                ingress_bandwidth = random.uniform(10, 1500) * cpu_cores
                nodes_df_mutated.loc[i, "ingress_bandwidth_Mbps"] = ingress_bandwidth
                max_ingress_to_add -= 1

            if not pd.isna(node["egress_bandwidth_Mbps"]) and node["egress_bandwidth_Mbps"] > 0:
                nodes_df_mutated.loc[i, "egress_bandwidth_Mbps"] = np.nan
            elif max_egress_to_add:
                cpu_cores = node["cpu_cores"]
                egress_bandwidth = random.uniform(10, 1500) * cpu_cores
                nodes_df_mutated.loc[i, "egress_bandwidth_Mbps"] = egress_bandwidth
                max_egress_to_add -= 1

    return nodes_df_mutated, node_latencies_mutated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to the dataset directory")
    args = parser.parse_args()

    output_dir = "output"
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    # Read baseline dataset
    nodes_csv_path = os.path.join(args.dataset, "nodes.csv")
    node_latencies_json_path = os.path.join(args.dataset, "node-latencies.json")

    nodes_df = pd.read_csv(nodes_csv_path, comment='#')
    with open(node_latencies_json_path, 'r') as f:
        node_latencies = json.load(f)

    # Save baseline (mutation 0)
    nodes_df.to_csv(os.path.join(output_dir, "nodes_0.csv"), index=False)
    with open(os.path.join(output_dir, "node-latencies_0.json"), 'w') as f:
        json.dump(node_latencies, f, indent=2)

    # Generate and save 10 mutations
    mutated_node_latencies = node_latencies
    mutated_nodes_df = nodes_df
    for i in range(1, 11):
        mutated_nodes_df, mutated_node_latencies = mutate(mutated_nodes_df, mutated_node_latencies, improve=True)
        mutated_nodes_df, mutated_node_latencies = mutate(mutated_nodes_df, mutated_node_latencies, improve=False)

        mutated_nodes_df.to_csv(os.path.join(output_dir, f"nodes_{i}.csv"), index=False)
        with open(os.path.join(output_dir, f"node-latencies_{i}.json"), 'w') as f:
            json.dump(mutated_node_latencies, f, indent=2)

        print(f"Generated mutation {i}")


if __name__ == '__main__':
    random.seed(42)
    np.random.seed(42)
    main()
