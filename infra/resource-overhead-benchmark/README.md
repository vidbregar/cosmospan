# Resource Overhead Benchmark

Benchmark must be performed twice, once with the proposed platform installed and once with the same VM specs, but
without anything installed (just whatever OS etc. is installed by Hetzner).
We benchmark CPU, memory, network througput, and disk I/O using `sysstat` suite. Samples are collected 1 second by
default, and we run the benchmark for 1 hour in total.

On the proposed platform:
- `ansible-playbook 01-prepare.yml`
- `ansible-playbook 02-run-benchmark.yml -e "benchmark_duration_seconds=3600"`
- `ansible-playbook 03-collect-results.yml -e "phase=proposed"`
- `ansible-playbook 04-cleanup.yml`

On the empty VMs:
- `ansible-playbook 01-prepare.yml`
- `ansible-playbook 02-run-benchmark.yml -e "benchmark_duration_seconds=3600"`
- `ansible-playbook 03-collect-results.yml -e "phase=baseline"`
- `ansible-playbook 04-cleanup.yml`
