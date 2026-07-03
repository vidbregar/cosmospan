import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


def load_scores(json_path):
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Scores file not found: {json_path}")

    with open(json_path, 'r') as f:
        data = json.load(f)

    records = []
    for key, val in data.items():
        parts = key.split('_')
        if len(parts) != 2:
            continue
        run_type, env_change_str = parts
        try:
            env_change = int(env_change_str)
        except ValueError:
            continue

        final_score = val.get('equal', {}).get('final_score')
        if final_score is not None:
            records.append({
                'environmental_change': env_change,
                'type': run_type,
                'score': final_score
            })

    df = pd.DataFrame(records)
    if df.empty:
        raise ValueError("No valid scores could be parsed from the JSON file.")

    df_pivot = df.pivot(index='environmental_change', columns='type', values='score')
    df_pivot = df_pivot.sort_index()

    if 'baseline' not in df_pivot.columns:
        df_pivot['baseline'] = None
    if 'proposed' not in df_pivot.columns:
        df_pivot['proposed'] = None

    return df_pivot


def load_percentages(csv_path):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Percentages file not found: {csv_path}")

    df = pd.read_csv(csv_path, comment='#')
    df = df.rename(columns={'mutation': 'environmental_change', 'percentage': 'percentage_descheduled'})
    df = df.sort_values('environmental_change')
    return df


def visualize_descheduling(dataset_dirs, output_pdf_path):
    baseline_all_runs = {i: [] for i in range(11)}
    proposed_all_runs = {i: [] for i in range(11)}
    pct_all_runs = {i: [] for i in range(11)}

    for d in dataset_dirs:
        scores_file = os.path.join(d, "descheduling", "scores.json")
        percentages_file = os.path.join(d, "descheduling", "percentage_descheduled.csv")
        
        try:
            df_scores = load_scores(scores_file)
            df_pct = load_percentages(percentages_file)
        except Exception as e:
            print(f"Warning: Failed to load data from {os.path.basename(d)}: {e}")
            continue
            
        for i in range(11):
            if i in df_scores.index:
                if 'baseline' in df_scores.columns:
                    val = df_scores.loc[i, 'baseline']
                    if pd.notna(val) and val is not None:
                        baseline_all_runs[i].append(val)
                if 'proposed' in df_scores.columns:
                    val = df_scores.loc[i, 'proposed']
                    if pd.notna(val) and val is not None:
                        proposed_all_runs[i].append(val)
                        
            pct_row = df_pct[df_pct['environmental_change'] == i]
            if not pct_row.empty:
                val = pct_row.iloc[0]['percentage_descheduled']
                if pd.notna(val) and val is not None:
                    pct_all_runs[i].append(val)

    print("\nProposed scores across datasets - Mean & Standard Deviation per Environmental Change:")
    print(f"{'Env Change':<12} {'Mean':<12} {'Std Dev':<12}")
    print("-" * 38)
    for i in range(11):
        vals = proposed_all_runs[i]
        if vals:
            mean_val = np.mean(vals)
            std_val = np.std(vals)
            print(f"{i:<12} {mean_val:<12.4f} {std_val:<12.4f}")
        else:
            print(f"{i:<12} {'N/A':<12} {'N/A':<12}")
    print()

    x = np.arange(11)

    baseline_scores = [np.mean(baseline_all_runs[i]) if baseline_all_runs[i] else None for i in x]
    proposed_scores = [np.mean(proposed_all_runs[i]) if proposed_all_runs[i] else None for i in x]
    descheduled_percentages = [np.mean(pct_all_runs[i]) if pct_all_runs[i] else 0.0 for i in x]

    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
        'font.size': 12,
        'axes.labelsize': 13.5,
        'axes.titlesize': 14,
        'xtick.labelsize': 11,
        'ytick.labelsize': 11,
        'legend.fontsize': 11.5,
        'grid.color': '#CBD5E1',
        'grid.linestyle': '--',
        'grid.linewidth': 0.6,
    })

    fig, ax1 = plt.subplots(figsize=(8.2, 5.4), dpi=300)

    ax2 = ax1.twinx()

    bar_width = 0.55
    bars = ax2.bar(
        x,
        descheduled_percentages,
        width=bar_width,
        color='#FEF3C7',
        edgecolor='#D97706',
        linewidth=1.2,
        label='Descheduled\nworkload instances',
        alpha=0.9,
        zorder=1
    )

    line_baseline, = ax1.plot(
        x,
        baseline_scores,
        color='#1E3A8A',
        marker='o',
        markersize=8,
        linewidth=2.5,
        linestyle='--',
        label='Baseline\nscores',
        zorder=3
    )
    line_proposed, = ax1.plot(
        x,
        proposed_scores,
        color='#059669',
        marker='s',
        markersize=8,
        linewidth=3.0,
        linestyle='-',
        label='Proposed\nscores',
        zorder=4
    )

    ax1.set_xlabel('Environmental Change', fontweight='semibold', labelpad=10)
    ax1.set_ylabel('Avg. Equally Weighted\nPlacement Score', color='#0F172A', fontweight='semibold', labelpad=12)
    ax2.set_ylabel('Avg. Percentage Descheduled', color='#0F172A', fontweight='semibold', labelpad=10)

    ax1.set_xticks(x)
    ax1.set_xlim(-0.6, 10.6)

    max_pct = max(descheduled_percentages) if descheduled_percentages else 0.0
    y2_max = max(6.0, np.ceil(max_pct + 1.0))
    ax2.set_ylim(0.0, y2_max)
    ax2.set_yticks(np.arange(0.0, y2_max + 0.1, 1.0))
    ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f%%'))

    valid_scores = [s for s in baseline_scores + proposed_scores if s is not None]
    min_score = min(valid_scores) if valid_scores else 90.0

    l_min = float(np.floor(min_score - 10.0))
    l_min = max(0.0, l_min)

    ax1.set_ylim(l_min, 100.0)

    next_mult_5 = int(np.ceil(l_min / 5.0) * 5.0)
    left_ticks = [l_min] + list(range(next_mult_5, 101, 5))
    left_ticks = sorted(list(set(left_ticks)))
    ax1.set_yticks(left_ticks)

    ax1.grid(True, which='both', axis='y', zorder=0)
    ax1.grid(False, axis='x')
    ax2.grid(False)

    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax2.annotate(
                f'{height:.2f}%',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 4),  # 4 points vertical offset
                textcoords="offset points",
                ha='center',
                va='bottom',
                fontsize=9.5,
                color='#1E293B',
                fontweight='bold'
            )

    all_elements = [line_baseline, line_proposed, bars]
    all_labels = [elem.get_label() for elem in all_elements]
    ax1.legend(
        all_elements,
        all_labels,
        loc='upper center',
        bbox_to_anchor=(0.5, -0.18),
        ncol=3,
        fontsize=10,
        frameon=True,
        facecolor='white',
        edgecolor='#94A3B8',
        framealpha=0.95
    )

    ax1.spines['top'].set_visible(False)
    ax2.spines['top'].set_visible(False)
    ax1.spines['left'].set_color('#64748B')
    ax1.spines['bottom'].set_color('#64748B')
    ax2.spines['right'].set_color('#64748B')
    ax1.spines['right'].set_visible(False)
    ax2.spines['left'].set_visible(False)

    fig.subplots_adjust(left=0.18, right=0.85, top=0.92, bottom=0.22)
    plt.savefig(output_pdf_path, format='pdf', bbox_inches='tight', pad_inches=0.15)
    plt.close()
    print(f"Successfully generated visualization PDF at: {output_pdf_path}")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, "../results")

    # Find all directories starting with "300_nodes_"
    dataset_dirs = []
    if os.path.exists(results_dir):
        for name in os.listdir(results_dir):
            if name.startswith("300_nodes_") and os.path.isdir(os.path.join(results_dir, name)):
                dataset_dirs.append(os.path.join(results_dir, name))

    dataset_dirs.sort()

    valid_dataset_dirs = []
    for d in dataset_dirs:
        scores_file = os.path.join(d, "descheduling", "scores.json")
        percentages_file = os.path.join(d, "descheduling", "percentage_descheduled.csv")
        if os.path.exists(scores_file) and os.path.exists(percentages_file):
            valid_dataset_dirs.append(d)

    if not valid_dataset_dirs:
        print(f"Error: No valid 300_nodes_* datasets with descheduling results found in {results_dir}")
    else:
        output_pdf = os.path.join(script_dir, "descheduling_visualization.pdf")
        visualize_descheduling(valid_dataset_dirs, output_pdf)
