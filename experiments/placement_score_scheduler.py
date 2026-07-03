import argparse
import json
import os
import re
from glob import glob
from placement_scores import *

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Calculate placement scores for scheduler experiments.")
    parser.add_argument("--dataset-name", type=str, required=True,
                        help="Name of the dataset directory (e.g., '1000_nodes_50_util_1').")
    parser.add_argument("--results-dir", type=str, required=True, help="Base directory for results.")
    parser.add_argument("--datasets-dir", type=str, required=True, help="Base directory for datasets.")

    args = parser.parse_args()

    weight_profiles = {
        "equal": {
            "cpu_requests": 1.0,
            "memory_requests": 1.0,
            "uptime_requests": 1.0,
            "bandwidth_requests": 1.0,
            "latency_requests": 1.0,
            "fault_tolerance": 1.0,
            "unscheduled_pods": 1.0,
        },
        "latency_focused": {
            "cpu_requests": 0.8/3,
            "memory_requests": 0.8/3,
            "latency_requests": 0.8/3,
            "uptime_requests": 0.2/4,
            "bandwidth_requests": 0.2/4,
            "fault_tolerance": 0.2/4,
            "unscheduled_pods": 0.2/4,
        },
        "bandwidth_focused": {
            "cpu_requests": 0.8/3,
            "memory_requests": 0.8/3,
            "bandwidth_requests": 0.8/3,
            "uptime_requests": 0.2/4,
            "latency_requests": 0.2/4,
            "fault_tolerance": 0.2/4,
            "unscheduled_pods": 0.2/4,
        },
        "latency_50": {
            "cpu_requests": 1/12,
            "memory_requests": 1/12,
            "bandwidth_requests": 1/12,
            "uptime_requests": 1/12,
            "latency_requests": 1/2,
            "fault_tolerance": 1/12,
            "unscheduled_pods": 1/12,
        }
    }

    results_path = os.path.join(args.results_dir, args.dataset_name)
    dataset_path = os.path.join(args.datasets_dir, args.dataset_name)

    if not os.path.isdir(results_path):
        print(f"Error: Results directory not found at {results_path}")
        return

    if not os.path.isdir(dataset_path):
        print(f"Error: Dataset directory not found at {dataset_path}")
        return

    try:
        nodes_df = pd.read_csv(os.path.join(dataset_path, "nodes.csv"), comment='#')
        nodes_df["hostname"] = nodes_df["hostname"].astype(str)
        pods_df = pd.read_csv(os.path.join(dataset_path, "pods.csv"), comment='#')
        with open(os.path.join(dataset_path, "node-latencies.json"), 'r') as f:
            node_latencies = json.load(f)
        with open(os.path.join(dataset_path, "workload-latency-requests.json"), 'r') as f:
            workload_latency_requests = json.load(f)
    except FileNotFoundError as e:
        print(f"Error reading dataset files: {e}")
        return

    scheduler_files = glob(os.path.join(results_path, "pods_and_nodes_*.csv"))
    all_scores = {}

    for scheduler_file in scheduler_files:
        match = re.search(r"pods_and_nodes_(.+)\.csv", os.path.basename(scheduler_file))
        if not match:
            continue

        scheduler_name = match.group(1)
        all_scores[scheduler_name] = {}

        try:
            scheduled_df = pd.read_csv(scheduler_file, sep='\\s+')
            scheduled_df["node_name"] = scheduled_df["node_name"].astype(str)
        except FileNotFoundError:
            print(f"Error: Scheduler result file not found at {scheduler_file}")
            continue

        individual_scores = calculate_individual_scores(scheduled_df, nodes_df, pods_df, node_latencies,
                                                        workload_latency_requests, scheduler_name)

        for weight_profile_name, weights in weight_profiles.items():
            print(f"Calculating scores for scheduler '{scheduler_name}' with weight profile '{weight_profile_name}'...")

            final_score = calculate_weighted_score(individual_scores, weights)

            all_scores[scheduler_name][weight_profile_name] = {
                "individual_scores": individual_scores,
                "final_score": final_score
            }

    output_path = os.path.join(results_path, "scores.json")
    with open(output_path, 'w') as f:
        json.dump(all_scores, f, indent=4)

    print(f"Scores successfully written to {output_path}")


if __name__ == '__main__':
    main()

