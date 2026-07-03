# Latency Benchmarks

Runs benchmarks with [hey](https://github.com/rakyll/hey).
Baseline is running `hey` directly on each VM against each other VM running nginx container.
Proposed (what workloads will experience running on Cosmospan) is `hey` running in a pod on each node against each other
node running nginx pod.

`hey` is configured to perform 1 request per second and we run all benchmarks in parallel for 1 hour.

Steps to run the benchmark:

- Update inventory.yml file
- `ansible-playbook 01-prepare.yml`
- `ansible-playbook 02-k8s-setup.yml`
- `ansible-playbook 03-run-benchmarks.yml --extra-vars "benchmark_duration_seconds=3600"`
- `ansible-playbook 04-collect-results.yml`
- `ansible-playbook 05-cleanup.yml`
