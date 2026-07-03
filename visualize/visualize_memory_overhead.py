import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

DISPLAY_NAME_MAP = {
    'cloud-k3s-master1': 'Cloud Master 1',
    'cloud-k3s-master2': 'Cloud Master 2',
    'cloud-k3s-master3': 'Cloud Master 3',
    'cloud-k3s-pool-workers-worker1': 'Cloud Worker 1',
    'cloud-k3s-pool-workers-worker2': 'Cloud Worker 2',
    'cloud-k3s-pool-workers-worker3': 'Cloud Worker 3',
    'cloud-k3s-pool-workers-worker4': 'Cloud Worker 4',
    'cloud-k3s-pool-workers-worker5': 'Cloud Worker 5',
    'cloud-k3s-pool-workers-worker6': 'Cloud Worker 6',
    'fog-k3s-master1': 'Fog Master 1',
    'fog-k3s-master2': 'Fog Master 2',
    'fog-k3s-master3': 'Fog Master 3',
    'fog-k0s': 'Fog k0s Node'
}

ORDERED_NODES = [
    'cloud-k3s-master1',
    'cloud-k3s-master2',
    'cloud-k3s-master3',
    'cloud-k3s-pool-workers-worker1',
    'cloud-k3s-pool-workers-worker2',
    'cloud-k3s-pool-workers-worker3',
    'cloud-k3s-pool-workers-worker4',
    'cloud-k3s-pool-workers-worker5',
    'cloud-k3s-pool-workers-worker6',
    'fog-k3s-master1',
    'fog-k3s-master2',
    'fog-k3s-master3',
    'fog-k0s'
]


def read_sar_csv(file_path):
    with open(file_path, 'r') as f:
        header_line = f.readline().strip()

    if header_line.startswith('#'):
        header_line = header_line.lstrip('#').strip()

    columns = [col.strip() for col in header_line.split(',')]
    df = pd.read_csv(file_path, comment='#', names=columns)
    return df


def get_node_data(base_dir, metric):
    data_map = {}
    search_path = os.path.join(base_dir, metric, '*.csv')
    files = glob.glob(search_path)
    for file_path in files:
        try:
            df = read_sar_csv(file_path)
            if not df.empty:
                hostname = df['hostname'].iloc[0].strip()
                data_map[hostname] = df
        except Exception as e:
            print(f"Warning: Failed to load {file_path}: {e}")
    return data_map


def plot_memory_overhead(baseline_data, proposed_data, output_pdf):
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
        'font.size': 11,
        'axes.labelsize': 12.5,
        'axes.titlesize': 13,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'legend.fontsize': 10.5,
        'grid.color': '#CBD5E1',
        'grid.linestyle': '--',
        'grid.linewidth': 0.6,
    })

    baseline_vals = []
    proposed_values = []
    node_labels = []

    for node in ORDERED_NODES:
        if node in baseline_data:
            df_base = baseline_data[node]
            mem_series = pd.to_numeric(df_base['kbmemused'], errors='coerce').dropna()
            baseline_val = (mem_series.mean() / 1024.0) if not mem_series.empty else 0.0
        else:
            baseline_val = np.nan

        if node in proposed_data:
            df_prop = proposed_data[node]
            mem_series = pd.to_numeric(df_prop['kbmemused'], errors='coerce').dropna()
            proposed_val = (mem_series.mean() / 1024.0) if not mem_series.empty else 0.0
        else:
            proposed_val = np.nan

        baseline_vals.append(baseline_val)
        proposed_values.append(proposed_val)
        node_labels.append(DISPLAY_NAME_MAP.get(node, node))

    x = np.arange(len(node_labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10.5, 3.8), dpi=300)

    rects1 = ax.bar(x - width / 2, baseline_vals, width, label='Baseline', color='#1E3A8A', edgecolor='none')
    rects2 = ax.bar(x + width / 2, proposed_values, width, label='Proposed', color='#059669', edgecolor='none')

    ax.set_ylabel('Avg. Memory Usage (MB)', fontweight='bold', labelpad=10, color='#1E293B')
    ax.set_xticks(x)
    ax.set_xticklabels(node_labels, rotation=30, ha='right', fontweight='semibold', color='#334155')
    ax.grid(True, which='both', axis='y', zorder=0)
    ax.grid(False, axis='x')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#64748B')
    ax.spines['bottom'].set_color('#64748B')

    ax.set_axisbelow(True)

    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            if not np.isnan(height):
                ax.annotate(
                    f'{height:.1f}',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(4, 3),
                    textcoords="offset points",
                    ha='right', va='bottom',
                    rotation=-45,
                    fontsize=8, fontweight='bold', color='#1E293B'
                )

    autolabel(rects1)
    autolabel(rects2)

    ax.legend(
        loc='upper center',
        bbox_to_anchor=(0.5, -0.34),
        ncol=2,
        fontsize=10.5,
        frameon=True,
        facecolor='white',
        edgecolor='#94A3B8',
        framealpha=0.95
    )

    fig.subplots_adjust(left=0.10, right=0.98, top=0.90, bottom=0.28)
    plt.savefig(output_pdf, format='pdf', bbox_inches='tight', pad_inches=0.15)
    plt.close(fig)
    print(f"Successfully generated Memory overhead visualization PDF: {output_pdf}")


def main():
    benchmark_dir = '../results/resources-overhead-benchmark'
    baseline_dir = os.path.join(benchmark_dir, 'baseline')
    proposed_dir = os.path.join(benchmark_dir, 'proposed')
    output_pdf = 'visualize_memory_overhead.pdf'

    print("Loading Memory baseline data...")
    baseline_data = get_node_data(baseline_dir, 'memory')

    print("Loading Memory proposed data...")
    proposed_data = get_node_data(proposed_dir, 'memory')

    print("Generating Memory overhead visualization...")
    plot_memory_overhead(baseline_data, proposed_data, output_pdf)


if __name__ == '__main__':
    main()
