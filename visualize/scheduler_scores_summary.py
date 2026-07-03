import os
import json
import numpy as np


def calculate_scores():
    results_dir = '../results'
    schedulers = ['cosmospan', 'network_aware', 'default']

    scores_to_average = {s: [] for s in schedulers}

    print(f"{'Dataset':<25} | {'Cosmospan':>12} | {'Network-Aware':>15} | {'Default':>10}")
    print("-" * 75)

    try:
        dir_items = sorted(os.listdir(results_dir))
    except FileNotFoundError:
        print(f"Error: Results directory not found at '{results_dir}'")
        return

    for item in dir_items:
        dataset_dir = os.path.join(results_dir, item)

        if os.path.isdir(dataset_dir) and '_nodes_' in item and '_util_' in item:
            try:
                num_nodes = int(item.split('_nodes_')[0])
                if num_nodes not in [100, 300, 900]:
                    continue
            except (ValueError, IndexError):
                continue

            scores_json_path = os.path.join(dataset_dir, 'scores.json')

            if not os.path.exists(scores_json_path):
                continue

            try:
                with open(scores_json_path, 'r') as f:
                    scores_data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Could not read or parse {scores_json_path}: {e}")
                continue

            print(f"{item:<25} |", end="")

            for scheduler in schedulers:
                score = scores_data.get(scheduler, {}).get('equal', {}).get('final_score')

                if score is not None:
                    print(f" {score:>11.2f} |", end="")
                    scores_to_average[scheduler].append(score)
                else:
                    print(f" {'N/A':>11} |", end="")

            print()

    print("\n" + "-" * 75)
    print("Average Scores and Standard Deviation Across All Datasets:")
    print("-" * 75)

    scheduler_labels = {
        'cosmospan': 'Cosmospan',
        'network_aware': 'Network-Aware',
        'default': 'Default Kubernetes'
    }

    print(f"{'Scheduler':<25} | {'Average Score':>15} | {'Standard Deviation':>20}")
    print("-" * 75)

    for scheduler in schedulers:
        scores = scores_to_average[scheduler]
        avg_score = np.mean(scores) if scores else 0.0
        std_dev = np.std(scores) if scores else 0.0
        scheduler_name = scheduler_labels[scheduler]
        print(f"{scheduler_name:<25} | {avg_score:>15.2f} | {std_dev:>20.2f}")


if __name__ == '__main__':
    calculate_scores()
