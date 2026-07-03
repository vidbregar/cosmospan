import numpy as np
from tqdm import tqdm


def isclose(a, b, rel_tol=1e-09, abs_tol=0.0):
    return abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)


def score_cpu_requests(nodes_df, pods_df, scheduled_df):
    non_ok = set()
    all_pods = set()

    print("starting cpu requests score")
    for _, node in nodes_df.iterrows():
        hostname = node["hostname"]
        cpu_capacity = node["cpu_cores"] * node["single_core_score"] / node["base_single_core_score"]

        pods_on_node = scheduled_df[scheduled_df["node_name"] == hostname]
        if pods_on_node.empty:
            continue

        all_pods.update(pods_on_node["pod_name"])

        requested_cpu_capacity = 0
        for pod_name in pods_on_node["pod_name"]:
            workload = pod_name.rsplit('-', 2)[0]
            pod_cpu_request = pods_df[pods_df["id"] == f"{workload}-replica-0"]["cpu_request_cores"].values[0]
            requested_cpu_capacity += pod_cpu_request

        if requested_cpu_capacity > cpu_capacity and not isclose(requested_cpu_capacity, cpu_capacity):
            non_ok.update(pods_on_node["pod_name"])

    print("finished cpu requests score")
    if not all_pods:
        return 100.0
    return 100 * (1 - len(non_ok) / len(all_pods))


def score_memory_requests():
    print("starting memory requests score")
    print("finished memory requests score")
    return 100.0


def score_uptime_requests(nodes_df, pods_df, scheduled_df):
    non_ok = set()
    all_pods = set()

    print("starting uptime requests score")
    for _, node in nodes_df.iterrows():
        hostname = node["hostname"]
        uptime = node["uptime_30d_percentage"]

        pods_on_node = scheduled_df[scheduled_df["node_name"] == hostname]
        for _, pod_row in pods_on_node.iterrows():
            pod_name = pod_row["pod_name"]
            workload = pod_name.rsplit('-', 2)[0]
            uptime_request = pods_df[pods_df["id"] == f"{workload}-replica-0"]["uptime_30d_percentage_request"].item()
            if not np.isnan(uptime_request):
                all_pods.add(pod_name)
                if uptime_request > uptime and not isclose(uptime_request, uptime):
                    non_ok.add(pod_name)

    print("finished uptime requests score")
    if not all_pods:
        return 100.0
    return 100 * (1 - len(non_ok) / len(all_pods))


def score_bandwidth_requests(nodes_df, pods_df, scheduled_df):
    non_ok = set()
    all_pods = set()

    print("starting bandwidth requests score")
    for _, node in nodes_df.iterrows():
        hostname = node["hostname"]

        ingress_capacity = node["ingress_bandwidth_Mbps"]
        if np.isnan(ingress_capacity):
            ingress_capacity = 0

        egress_capacity = node["egress_bandwidth_Mbps"]
        if np.isnan(egress_capacity):
            egress_capacity = 0

        requested_ingress = 0
        requested_egress = 0

        pods_on_node = scheduled_df[scheduled_df["node_name"] == hostname]
        pods_with_ingress_request = []
        pods_with_egress_request = []

        for pod_name in pods_on_node["pod_name"]:
            workload = pod_name.rsplit('-', 2)[0]

            pod_ingress_request = pods_df[pods_df["id"] == f"{workload}-replica-0"]["ingress_bandwidth_request_Mbps"].item()
            if not np.isnan(pod_ingress_request):
                pods_with_ingress_request.append(pod_name)
                requested_ingress += pod_ingress_request

            pod_egress_request = pods_df[pods_df["id"] == f"{workload}-replica-0"]["egress_bandwidth_request_Mbps"].item()
            if not np.isnan(pod_egress_request):
                pods_with_egress_request.append(pod_name)
                requested_egress += pod_egress_request

        all_pods.update(pods_with_ingress_request)
        all_pods.update(pods_with_egress_request)

        if requested_ingress > ingress_capacity and not isclose(requested_ingress, ingress_capacity):
            non_ok.update(pods_with_ingress_request)

        if requested_egress > egress_capacity and not isclose(requested_egress, egress_capacity):
            non_ok.update(pods_with_egress_request)

    print("finished bandwidth requests score")
    if not all_pods:
        return 100.0
    return 100 * (1 - len(non_ok) / len(all_pods))


def get_latency_between_nodes(n1_name, n2_name, nodes_df, node_latencies):
    if n1_name == n2_name:
        return 0

    n1 = nodes_df[nodes_df["hostname"] == n1_name]
    n1_cluster = n1["location"].item()

    n2 = nodes_df[nodes_df["hostname"] == n2_name]
    n2_cluster = n2["location"].item()

    if n1_cluster == n2_cluster:
        x, y = min(str(n1_name), str(n2_name)), max(str(n1_name), str(n2_name))
        return node_latencies["intra-cluster"][str(n1_cluster)][x][y]

    x, y = min(str(n1_cluster), str(n2_cluster)), max(str(n1_cluster), str(n2_cluster))
    return node_latencies["inter-cluster"][x][y]


def score_latency_requests(scheduled_df, nodes_df, workload_latency_requests, node_latencies):
    non_ok = set()
    all_pods = set()
    print("started latency requests score")

    for w1 in tqdm(workload_latency_requests):
        w1_pods = scheduled_df[scheduled_df["pod_name"].str.startswith(f'{w1}-')]
        w1_pods = w1_pods[w1_pods["node_name"] != "<none>"]

        depWorkloads = workload_latency_requests[w1]
        for w2 in depWorkloads:
            w2_pods = scheduled_df[scheduled_df["pod_name"].str.startswith(f'{w2}-')]
            w2_pods = w2_pods[w2_pods["node_name"] != "<none>"]

            latency_request = depWorkloads[w2]

            for _, w1_pod in w1_pods.iterrows():
                w1_pod_node = w1_pod["node_name"]
                w1_pod_name = w1_pod["pod_name"]
                all_pods.add(w1_pod_name)

                for _, w2_pod in w2_pods.iterrows():
                    w2_pod_node = w2_pod["node_name"]
                    w2_pod_name = w2_pod["pod_name"]
                    all_pods.add(w2_pod_name)

                    if w1_pod_node == w2_pod_node:
                        continue

                    h = get_latency_between_nodes(w1_pod_node, w2_pod_node, nodes_df, node_latencies)
                    if h > latency_request and not isclose(h, latency_request):
                        non_ok.add(w1_pod_name)
                        non_ok.add(w2_pod_name)

    print("finished latency requests score")
    if not all_pods:
        return 100.0
    return 100 * (1 - len(non_ok) / len(all_pods))


def score_unscheduled_pods(scheduled_df):
    print("starting unschedulable pods score")
    if scheduled_df.empty:
        return 100.0
    unscheduled = len(scheduled_df[scheduled_df["node_name"] == "<none>"])

    print("finished unschedulable pods score")
    return 100 * (1 - unscheduled / len(scheduled_df))


def score_fault_tolerance(scheduled_df):
    # Precondition: each workload has >= 2 replicas
    print("starting fault tolerance score")
    if scheduled_df.empty:
        return 100.0

    def get_workload_from_pod_name(pod_name):
        return pod_name.rsplit('-', 2)[0]

    df = scheduled_df.copy()
    df['workload'] = df['pod_name'].apply(get_workload_from_pod_name)

    scheduled_pods = df[df["node_name"] != "<none>"]

    workload_node_counts = scheduled_pods.groupby('workload')['node_name'].nunique()

    total_scheduled_workloads = len(workload_node_counts)
    if total_scheduled_workloads == 0:
        print("finished fault tolerance score")
        return 100.0

    non_ok = (workload_node_counts < 2).sum()

    print("finished fault tolerance score")
    return 100 * (1 - non_ok / total_scheduled_workloads)


def calculate_weighted_score(scores, weights):
    total_score = 0
    total_weight = 0
    for score_name, value in scores.items():
        total_score += value * weights[score_name]
        total_weight += weights[score_name]

    return total_score / total_weight if total_weight > 0 else 0


def calculate_individual_scores(scheduled_df, nodes_df, pods_df, node_latencies, workload_latency_requests, scheduler_name):
    print(f"Calculating scores for {scheduler_name}...")

    required_scheduled_cols = ['pod_name', 'node_name']
    if not all(col in scheduled_df.columns for col in required_scheduled_cols):
        print(f"Error: Missing required columns in scheduled data for {scheduler_name}")
        return None

    required_nodes_cols = ['hostname', 'cpu_cores', 'single_core_score', 'base_single_core_score', 'uptime_30d_percentage',
                           'ingress_bandwidth_Mbps', 'egress_bandwidth_Mbps', 'location']
    if not all(col in nodes_df.columns for col in required_nodes_cols):
        print("Error: Missing required columns in nodes.csv")
        return None

    required_pods_cols = ['id', 'cpu_request_cores', 'uptime_30d_percentage_request', 'ingress_bandwidth_request_Mbps',
                          'egress_bandwidth_request_Mbps']
    if not all(col in pods_df.columns for col in required_pods_cols):
        print("Error: Missing required columns in pods.csv")
        return None

    scores = {
        'cpu_requests': score_cpu_requests(nodes_df, pods_df, scheduled_df),
        'memory_requests': score_memory_requests(),
        'uptime_requests': score_uptime_requests(nodes_df, pods_df, scheduled_df),
        'bandwidth_requests': score_bandwidth_requests(nodes_df, pods_df, scheduled_df),
        'latency_requests': score_latency_requests(scheduled_df, nodes_df, workload_latency_requests, node_latencies),
        'fault_tolerance': score_fault_tolerance(scheduled_df),
        'unscheduled_pods': score_unscheduled_pods(scheduled_df),
    }

    return scores
