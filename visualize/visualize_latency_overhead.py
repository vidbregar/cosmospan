import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

DISPLAY_NAME_MAP = {
    'cloud-k3s-pool-workers-worker1': 'Cloud k3s Worker 1',
    'cloud-k3s-pool-workers-worker2': 'Cloud k3s Worker 2',
    'cloud-k3s-pool-workers-worker3': 'Cloud k3s Worker 3',
    'cloud-k3s-pool-workers-worker4': 'Cloud k3s Worker 4',
    'cloud-k3s-pool-workers-worker5': 'Cloud k3s Worker 5',
    'cloud-k3s-pool-workers-worker6': 'Cloud k3s Worker 6',
    'fog-k0s': 'Fog k0s Node',
    'fog-k3s-master1': 'Fog k3s Node 1',
    'fog-k3s-master2': 'Fog k3s Node 2',
    'fog-k3s-master3': 'Fog k3s Node 3'
}

ORDERED_NODES = [
    'fog-k3s-master1',
    'fog-k3s-master2',
    'fog-k3s-master3',
    'fog-k0s',
    'cloud-k3s-pool-workers-worker1',
    'cloud-k3s-pool-workers-worker2',
    'cloud-k3s-pool-workers-worker3',
    'cloud-k3s-pool-workers-worker4',
    'cloud-k3s-pool-workers-worker5',
    'cloud-k3s-pool-workers-worker6'
]


def load_node_ip_mapping(csv_path):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Mapping file not found: {csv_path}")
    df = pd.read_csv(csv_path)
    df['ip'] = df['ip'].str.strip()
    df['node'] = df['node'].str.strip()
    return dict(zip(df['ip'], df['node']))


def load_latency_data(directory, file_pattern):
    search_path = os.path.join(directory, file_pattern)
    files = glob.glob(search_path)
    if not files:
        raise FileNotFoundError(f"No latency files found matching pattern: {search_path}")

    latency_map = {}
    for filepath in files:
        df = pd.read_csv(filepath)
        for _, row in df.iterrows():
            src = str(row['source_ip']).strip()
            dst = str(row['destination_ip']).strip()
            val = float(row['average_latency_s'])
            latency_map[(src, dst)] = val

    return latency_map


def build_latency_matrix(latency_map, ip_to_name, ordered_nodes):
    name_to_ip = {name: ip for ip, name in ip_to_name.items()}

    n = len(ordered_nodes)
    matrix = np.zeros((n, n))

    for i, src_name in enumerate(ordered_nodes):
        for j, dst_name in enumerate(ordered_nodes):
            if i == j:
                matrix[i][j] = np.nan
                continue

            src_ip = name_to_ip.get(src_name)
            dst_ip = name_to_ip.get(dst_name)

            if src_ip and dst_ip:
                matrix[i][j] = latency_map.get((src_ip, dst_ip), np.nan)
            else:
                matrix[i][j] = np.nan

    return matrix


def plot_overhead_heatmap(overhead_matrix, ordered_nodes, output_pdf):
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
        'font.size': 7.5,
        'axes.labelsize': 8.5,
        'xtick.labelsize': 7.0,
        'ytick.labelsize': 7.0,
        'legend.fontsize': 7.5,
    })

    display_names = [DISPLAY_NAME_MAP.get(node, node) for node in ordered_nodes]

    fig, ax = plt.subplots(figsize=(4.2, 3.5), dpi=300)

    masked_matrix = np.ma.masked_invalid(overhead_matrix.T)

    cmap = plt.colormaps.get_cmap('YlGnBu').copy()
    cmap.set_bad(color='#F1F5F9')

    im = ax.imshow(masked_matrix, cmap=cmap, aspect='equal', origin='lower')

    ax.set_xticks(np.arange(len(ordered_nodes)) - 0.5, minor=True)
    ax.set_yticks(np.arange(len(ordered_nodes)) - 0.5, minor=True)
    ax.grid(which="minor", color="white", linestyle='-', linewidth=1.2)
    ax.tick_params(which="minor", size=0)

    n = len(ordered_nodes)
    for i in range(n):
        for j in range(n):
            if i == j:
                ax.text(j, i, '-', ha='center', va='center', color='#94A3B8', fontweight='semibold', fontsize=7.5)
                continue

            val = overhead_matrix.T[i][j]
            if not np.isnan(val):
                text_color = '#FFFFFF' if val > 6.0 else '#0F172A'
                ax.text(j, i, f"{val:.1f}", ha='center', va='center', color=text_color, fontweight='semibold',
                        fontsize=6.0)

    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels(display_names, rotation=45, ha='right', fontweight='semibold', color='#334155')
    ax.set_yticklabels(display_names, fontweight='semibold', color='#334155')

    ax.set_xlabel('Source Node', fontweight='bold', labelpad=6, color='#1E293B')
    ax.set_ylabel('Destination Node', fontweight='bold', labelpad=6, color='#1E293B')

    for edge, spine in ax.spines.items():
        spine.set_color('#CBD5E1')
        spine.set_linewidth(1.0)

    cbar = fig.colorbar(im, ax=ax, shrink=0.82, pad=0.04)
    cbar.outline.set_edgecolor('#CBD5E1')
    cbar.outline.set_linewidth(1.0)
    cbar.set_label('Average Latency Overhead (ms)', fontweight='bold', labelpad=6, color='#1E293B')
    cbar.ax.tick_params(labelsize=7, colors='#334155')

    fig.subplots_adjust(left=0.25, right=0.90, top=0.97, bottom=0.25)

    fig.savefig(output_pdf, format='pdf', bbox_inches='tight', pad_inches=0.08)
    plt.close(fig)
    print(f"Successfully generated 10x10 latency overhead heatmap PDF: {output_pdf}")


def main():
    latency_dir = '../results/latency-benchmark'
    node_ip_file = os.path.join(latency_dir, 'node_name_ip.csv')
    output_pdf = 'latency_overhead_visualization.pdf'

    print("Loading Node name IP mapping...")
    ip_to_name = load_node_ip_mapping(node_ip_file)

    print("Loading Pod network latency measurements...")
    pod_latencies = load_latency_data(latency_dir, 'pod-results-*.csv')

    print("Loading VM network latency baseline measurements...")
    vm_latencies = load_latency_data(latency_dir, 'vm-results-*.csv')

    print("Building average latency matrices...")
    pod_matrix = build_latency_matrix(pod_latencies, ip_to_name, ORDERED_NODES)
    vm_matrix = build_latency_matrix(vm_latencies, ip_to_name, ORDERED_NODES)

    print("Calculating latency overhead (Pod minus VM baseline) in milliseconds...")
    overhead_matrix = (pod_matrix - vm_matrix) * 1000.0

    print("Plotting overhead heatmap...")
    plot_overhead_heatmap(overhead_matrix, ORDERED_NODES, output_pdf)


if __name__ == '__main__':
    main()
