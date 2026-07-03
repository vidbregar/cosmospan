# CosmoSpan

This repository contains the source code for the `Toward Adaptive Workload Scheduling in Kubernetes Across the Edge-Cloud Continuum` research paper.
CosmoSpan is a Kubernetes-based platform that provides seamless integration between the cloud and fog layers.

## Repository Structure

The repository is organized as follows:

- **cosmospan-descheduler**: Proof of concept implementation of the CosmoSpan descheduler.
- **cosmospan-scheduler**: Proof of concept implementation of the CosmoSpan scheduler.
- **datasets**: Datasets used for the evaluations.
- **experiments**: Scripts to run the experiments and evaluations.
- **generate-datasets**: Scripts to generate the datasets.
- **infra**: Code for deploying the platform's underlying infrastructure.
- **kubernetes-default-scheduler**: Configuration for the default Kubernetes scheduler used in the evaluations.
- **network-aware-scheduler**: Configuration for the network-aware scheduler used in the evaluations.
- **results**: Results of the evaluations.
- **visualize**: Scripts to visualize the results.

## Dataset Structure

Each directory in `datasets/` contains a synthetic dataset defining an edge-cloud continuum multi-cluster topology and a list of workload instances to schedule.

### Dataset Directory Naming Convention

The dataset directories follow a specific naming pattern:

`<number_of_nodes>_nodes_<target_resource_utilization>_util_<id>`

For example, `100_nodes_50_util_1` signifies a dataset with:
- `100` nodes: The total number of compute nodes simulated in this environment.
- `50`% target resource utilization: The desired percentage of all available resources (CPU, memory, or bandwidth) that pods are intended to consume across the entire infrastructure.
- `1`st generated dataset of this type: A unique identifier for different instantiations of the same node count and target utilization.

### File Structure

Each dataset directory contains the following files:

- **`nodes.csv`**: Defines the simulated edge-cloud infrastructure topology. Columns include:
  - `hostname`: Identifier of the node.
  - `layer`: Node layer classification (`cloud` or `fog`).
  - `location`: Cluster location (e.g., `cloud-location-0`, `fog-location-1`).
  - `cpu_cores`: Number of CPU cores available on the node.
  - `single_core_score`: Benchmark score for single-core CPU performance, used to normalize heterogeneous cores.
  - `base_single_core_score`: Reference core score for normalization.
  - `memory_GiB`: Node's memory capacity in GiB.
  - `ingress_bandwidth_Mbps` & `egress_bandwidth_Mbps`: Node network bandwidth capacities (empty if not specified).
  - `uptime_30d_percentage`: Historical node uptime percentage over 30 days.
  - `cost`: Arbitrary node cost metric (can encode infra costs, environmental impact, etc.)
- **`pods.csv`**: Defines the workload instances (pods) to be scheduled. Columns include:
  - `id`: Unique identifier of the workload instance (pod).
  - `app_id`: Application identifier.
  - `app_type`: Application pattern (`api-composition` or `messaging`).
  - `workload_id` and `replica_id`: Workload and replica indices.
  - `layer`: Specified layer requirements (`fog`, `cloud`, or `edge-cloud`/any).
  - `cpu_request_cores` and `memory_request_GiB`: Compute resource requests.
  - `ingress_bandwidth_request_Mbps` and `egress_bandwidth_request_Mbps`: Bandwidth guarantees requested.
  - `uptime_30d_percentage_request`: Minimum historical node uptime required.
- **`node-latencies.json`**: This JSON file specifies network latencies. It includes inter-cluster latencies (network latencies between different clusters) and intra-cluster latencies (network latencies between individual nodes within the same cluster).
- **`workload-latency-requests.json`**: Describes dependency latency requests between specific workloads in milliseconds, representing microservice call chains or data locality constraints.

Synthetic datasets were generated using the [compute_nodes_random_graph_model.py](generate-datasets/compute_nodes_random_graph_model.py) and [workloads_random_graph_model.py](generate-datasets/workloads_random_graph_model.py) scripts.

Datasets consisting of 300 nodes additionally include a `mutations` folder which contains the baseline `nodes_0` and `node-latencies_0.json` files,
and 10 mutations (environmental changes) used for the descheduler evaluations. Mutations were generated using the [generate_mutations.py](generate-datasets/generate_mutations.py) script.

## Result Structure

Each directory in `results/` corresponds to a dataset and contains the scheduling outcome files produced during evaluations:

- **`pods_and_nodes_<scheduler>.csv`** (where `<scheduler>` is `cosmospan`, `default`, or `network_aware`): Tab-separated mapping files detailing the mapping of scheduled pod names to host node IDs.
- **`scheduling_time_seconds_<scheduler>.txt`**: Text file containing a single numeric value representing the total scheduler execution time in seconds.
- **`scores.json`**: Contains the computed placement scores (e.g., CPU, Memory, Node Uptime, Network Bandwidth, Latency, Fault Tolerance, Unscheduled Workload Instances) for each scheduler on this dataset. It outputs scores across three distinct weighting profiles:
  - `equal`: Equally weighted criteria.
  - `latency_focused`: Prioritizes latency-related criteria.
  - `bandwidth_focused`: Prioritizes network bandwidth criteria.

Datasets consisting of 300 nodes additionally include a `descheduling` folder which includes the baseline `pods_and_nodes_baseline_0.csv` results as well as 10 results for each mutation (environmental change) in the dataset for the descheduler evaluations.
Additionally, `percentage_descheduled.csv` is used to track a percentage of workload instances that were descheduled for each mutation.

Results for the resource and latency overhead benchmarks available in the [latency-benchmark](results/latency-benchmark) and [resources-overhead-benchmark](results/resources-overhead-benchmark) folders.

## Usage

### Requirements

- docker
- uv
- kubectl

### Running the evaluations

Spin up 3 schedulers, default, network aware, cosmospan. The simulator will be available here: http://localhost:3000/

#### Scheduler evaluations

```bash
export KUBECONFIG=$(pwd)/kubeconfig.yaml
cd experiments
./run_scheduler_experiment.sh ../datasets/10000_nodes_70_util_1 cosmospan-scheduler
./run_scheduler_experiment.sh ../datasets/300_nodes_50_util_1 network-aware-scheduler
./run_scheduler_experiment.sh ../datasets/10000_nodes_70_util_2 kubernetes-default-scheduler

./run_scheduler_experiment.sh ../datasets/300_nodes_50_util_2 cosmospan-scheduler
./run_scheduler_experiment.sh ../datasets/300_nodes_50_util_2 network-aware-scheduler
./run_scheduler_experiment.sh ../datasets/300_nodes_50_util_2 kubernetes-default-scheduler

...

uv run placement_score_scheduler.py --dataset-name 10000_nodes_70_util_2 --results-dir ../results --datasets-dir ../datasets
```

Repeat for all schedulers and datasets.

#### Descheduler evaluations
```bash
export KUBECONFIG=$(pwd)/kubeconfig.yaml
cd experiments
./run_descheduler_experiment.sh ../datasets/300_nodes_50_util_1

...

uv run placement_score_descheduler.py --dataset-name 300_nodes_70_util_3 --results-dir ../results --datasets-dir ../datasets
```

#### Infra resource and latency overhead evaluations

Read instructions in [infra/README.md](infra/README.md).

## Citation

If you use this work, please cite it using the following BibTeX entry:

```bibtex
@unpublished{bregar2025toward,
  author = {Bregar, Vid and Juri{\v{c}}, Matja{\v{z}} B.},
  title = {Toward Adaptive Workload Scheduling in Kubernetes Across the Edge-Cloud Continuum},
  year = {2025},
  month = {sep},
  note = {Research Square Preprint (Version 1)},
  doi = {10.21203/rs.3.rs-7555016/v1},
  url = {https://doi.org/10.21203/rs.3.rs-7555016/v1}
}
```

You can also use the [`CITATION.cff`](CITATION.cff) file or refer to [`citation.bib`](citation.bib).
