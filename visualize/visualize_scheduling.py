import os
import json
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SCHEDULER_LABELS = {
    'cosmospan': 'Cosmospan',
    'network_aware': 'Network-Aware',
    'default': 'Default'
}
SCHEDULER_COLORS = {
    'cosmospan': '#059669',
    'network_aware': '#1E3A8A',
    'default': '#D97706'
}

SCORE_KEYS = [
    'cpu_requests',
    'memory_requests',
    'uptime_requests',
    'bandwidth_requests',
    'latency_requests',
    'fault_tolerance',
    'unscheduled_pods'
]
SCORE_LABELS = [
    'CPU' + chr(10) + 'Requests',
    'Memory' + chr(10) + 'Requests',
    'Node Uptime' + chr(10) + 'Requests',
    'Network Bandwidth' + chr(10) + 'Requests',
    'Latency' + chr(10) + 'Requests',
    'Fault' + chr(10) + 'Tolerance',
    'Unscheduled Workload' + chr(10) + 'Instances'
]


def get_cluster_counts(dataset_dir):
    nodes_path = os.path.join(dataset_dir, 'nodes.csv')
    if not os.path.exists(nodes_path):
        return None, None

    cloud_clusters = None
    fog_clusters = None

    try:
        with open(nodes_path, 'r') as f:
            for line in f:
                if line.startswith('#'):
                    if 'cloud clusters:' in line:
                        match = re.search(r'cloud clusters:\s*(\d+)', line)
                        if match:
                            cloud_clusters = int(match.group(1))
                    if 'fog clusters:' in line:
                        match = re.search(r'fog clusters:\s*(\d+)', line)
                        if match:
                            fog_clusters = int(match.group(1))
                if cloud_clusters is not None and fog_clusters is not None:
                    break
    except Exception:
        pass

    return cloud_clusters, fog_clusters


def get_total_pods(dataset_dir):
    pods_path = os.path.join(dataset_dir, 'pods.csv')
    if not os.path.exists(pods_path):
        return None

    try:
        with open(pods_path, 'r') as f:
            for line in f:
                if line.startswith('# total pods:'):
                    match = re.search(r'total pods:\s*(\d+)', line)
                    if match:
                        return int(match.group(1))
    except Exception:
        pass

    try:
        df = pd.read_csv(pods_path, comment='#')
        return len(df)
    except Exception:
        return 0


def get_scheduled_pods(results_dir, scheduler):
    csv_path = os.path.join(results_dir, f'pods_and_nodes_{scheduler}.csv')
    if not os.path.exists(csv_path):
        return 0
    try:
        df = pd.read_csv(csv_path, sep=r'\s+')
        scheduled_df = df[df['node_name'] != '<none>']
        return len(scheduled_df)
    except Exception:
        return 0


def get_scheduling_time(results_dir, scheduler):
    txt_path = os.path.join(results_dir, f'scheduling_time_seconds_{scheduler}.txt')
    if not os.path.exists(txt_path):
        return 0.0
    try:
        with open(txt_path, 'r') as f:
            return float(f.read().strip())
    except Exception:
        return 0.0


def load_averaged_data(node_count, schedulers):
    runs = [1, 2, 3]

    indiv_scores_all = {s: {k: [] for k in SCORE_KEYS} for s in schedulers}
    summary_scores_all = {s: {p: [] for p in ['equal', 'latency_focused', 'bandwidth_focused', 'latency_50']} for s in schedulers}
    times_all = {s: [] for s in schedulers}
    pods_all = {s: [] for s in schedulers}
    cloud_clusters_all = []
    fog_clusters_all = []

    for run in runs:
        dataset_name = f'{node_count}_nodes_70_util_{run}'
        results_path = os.path.join('..', 'results', dataset_name)
        dataset_path = os.path.join('..', 'datasets', dataset_name)

        total_pods = get_total_pods(dataset_path)

        cloud_count, fog_count = get_cluster_counts(dataset_path)
        if cloud_count is not None:
            cloud_clusters_all.append(cloud_count)
        if fog_count is not None:
            fog_clusters_all.append(fog_count)

        scores_json_path = os.path.join(results_path, 'scores.json')
        if os.path.exists(scores_json_path):
            try:
                with open(scores_json_path, 'r') as f:
                    scores_data = json.load(f)
            except Exception:
                scores_data = {}
        else:
            scores_data = {}

        for s in schedulers:
            if s in scores_data:
                if 'equal' in scores_data[s] and 'individual_scores' in scores_data[s]['equal']:
                    indiv = scores_data[s]['equal']['individual_scores']
                    for k in SCORE_KEYS:
                        if k in indiv:
                            indiv_scores_all[s][k].append(indiv[k])

                for p in ['equal', 'latency_focused', 'bandwidth_focused', 'latency_50']:
                    if p in scores_data[s] and 'final_score' in scores_data[s][p]:
                        summary_scores_all[s][p].append(scores_data[s][p]['final_score'])

            time_val = get_scheduling_time(results_path, s)
            times_all[s].append(time_val)

            sched_pods = get_scheduled_pods(results_path, s)
            pods_all[s].append((sched_pods, total_pods))

    averaged_data = {
        'individual_scores': {},
        'summary_scores': {},
        'scheduling_time': {},
        'pods': {},
        'cloud_clusters': np.mean(cloud_clusters_all) if cloud_clusters_all else 0.0,
        'fog_clusters': np.mean(fog_clusters_all) if fog_clusters_all else 0.0,
    }

    for s in schedulers:
        averaged_data['individual_scores'][s] = {}
        for k in SCORE_KEYS:
            vals = indiv_scores_all[s][k]
            averaged_data['individual_scores'][s][k] = np.mean(vals) if vals else 0.0

        averaged_data['summary_scores'][s] = {}
        for p in ['equal', 'latency_focused', 'bandwidth_focused', 'latency_50']:
            vals = summary_scores_all[s][p]
            averaged_data['summary_scores'][s][p] = np.mean(vals) if vals else 0.0

        vals = times_all[s]
        averaged_data['scheduling_time'][s] = np.mean(vals) if vals else 0.0

        sched_vals = [p[0] for p in pods_all[s] if p[0] is not None]
        total_vals = [p[1] for p in pods_all[s] if p[1] is not None]

        avg_sched = np.mean(sched_vals) if sched_vals else 0.0
        avg_total = np.mean(total_vals) if total_vals else 0.0
        averaged_data['pods'][s] = (avg_sched, avg_total)

    return averaged_data


def plot_subplot(ax, data, schedulers):
    x = np.arange(len(SCORE_KEYS))

    num_schedulers = len(schedulers)
    width = 0.8 / num_schedulers
    total_width = width * num_schedulers

    offsets = {}
    for i, s in enumerate(schedulers):
        offsets[s] = -total_width / 2 + (i + 0.5) * width

    rects = {}
    for s in schedulers:
        scores = [data['individual_scores'][s][k] for k in SCORE_KEYS]
        rects[s] = ax.bar(
            x + offsets[s],
            scores,
            width,
            label=SCHEDULER_LABELS[s],
            color=SCHEDULER_COLORS[s],
            edgecolor='none',
            zorder=3
        )

        for rect in rects[s]:
            height = rect.get_height()
            ax.annotate(
                f'{height:.1f}',
                xy=(rect.get_x() + rect.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha='center', va='bottom',
                fontsize=8.0, fontweight='bold',
                color='#1E293B',
                rotation=45
            )

    ax.set_ylabel('Average Placement Score', fontweight='semibold', labelpad=10)
    ax.set_xticks(x)
    ax.set_xticklabels(SCORE_LABELS, fontweight='semibold', fontsize=10.5)
    ax.set_xlim(-0.5, len(SCORE_KEYS) - 0.5)
    ax.set_ylim(0, 110)

    ax.grid(True, which='both', axis='y', zorder=0)
    ax.grid(False, axis='x')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#64748B')
    ax.spines['bottom'].set_color('#64748B')

    col_labels = ['Metric'] + [SCHEDULER_LABELS[s] for s in schedulers]

    cell_text = []

    row_labels_and_keys = [
        ('Equally Weighted Total Score', 'equal'),
        ('Latency-Focused Total Score', 'latency_focused'),
        ('Bandwidth-Focused Total Score', 'bandwidth_focused'),
        ('Latency-50% Total Score', 'latency_50'),
    ]

    for label, key in row_labels_and_keys:
        row = [label] + [f"{data['summary_scores'][s][key]:.1f}" for s in schedulers]
        cell_text.append(row)

    time_row = ['Avg Scheduling Time'] + [f"~{int(round(data['scheduling_time'][s]))}s" for s in schedulers]
    cell_text.append(time_row)

    pods_row = ['Avg Total Workload Instances'] + [f"~{int(round(data['pods'][s][1]))}" for s in schedulers]
    cell_text.append(pods_row)

    cloud_clusters_row = ['Avg Cloud Clusters'] + [f"~{int(round(data['cloud_clusters']))}" for _ in schedulers]
    cell_text.append(cloud_clusters_row)

    fog_clusters_row = ['Avg Fog Clusters'] + [f"~{int(round(data['fog_clusters']))}" for _ in schedulers]
    cell_text.append(fog_clusters_row)

    col_widths = [0.34] + [0.22] * len(schedulers)

    table = ax.table(
        cellText=cell_text,
        colLabels=col_labels,
        loc='bottom',
        cellLoc='center',
        bbox=[0.0, -0.6, 1.0, 0.42],
        colWidths=col_widths
    )

    table.set_fontsize(10)
    table.scale(1.0, 1.4)

    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight='bold', color='#1E293B')
            cell.set_facecolor('#F1F5F9')
            cell.set_edgecolor('#CBD5E1')
        elif col == 0:
            cell.set_text_props(weight='semibold', color='#0F172A', ha='left')
            cell.set_facecolor('#F8FAFC')
            cell.set_edgecolor('#CBD5E1')
        else:
            cell.set_edgecolor('#E2E8F0')
            if col == 1:
                cell.set_facecolor('#ECFDF5')
                cell.set_text_props(weight='bold', color='#065F46')

    return rects


def main():
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
        'font.size': 11,
        'axes.labelsize': 12,
        'axes.titlesize': 13,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'legend.fontsize': 11,
        'grid.color': '#CBD5E1',
        'grid.linestyle': '--',
        'grid.linewidth': 0.6,
    })

    schedulers_standard = ['cosmospan', 'network_aware', 'default']
    schedulers_10000 = ['cosmospan', 'default']

    node_counts = [(100, schedulers_standard), (900, schedulers_standard), (10000, schedulers_10000)]

    for node_count, schedulers in node_counts:
        print(f"Loading and averaging {node_count}-node datasets...")
        data = load_averaged_data(node_count, schedulers)

        print(f"Plotting {node_count}-node visualization...")
        fig, ax = plt.subplots(figsize=(11.0, 7.0), dpi=300)
        rects = plot_subplot(ax, data, schedulers)

        handles = [rects[s] for s in schedulers]
        labels = [SCHEDULER_LABELS[s] for s in schedulers]
        ax.legend(
            handles,
            labels,
            loc='upper center',
            bbox_to_anchor=(0.5, 1.14),
            ncol=len(schedulers),
            fontsize=11.5,
            frameon=True,
            facecolor='white',
            edgecolor='#94A3B8',
            framealpha=0.95
        )

        fig.subplots_adjust(bottom=0.35, left=0.06, right=0.96, top=0.86)
        output_pdf = f"scheduling_visualization_{node_count}.pdf"
        fig.savefig(output_pdf, format='pdf', bbox_inches='tight', pad_inches=0.15)
        plt.close(fig)
        print(f"Successfully generated {node_count}-node visualization PDF: {output_pdf}")


if __name__ == '__main__':
    main()
