# Report: Reproducing and Explaining `papier2` and the FROG Extension

Date: 2026-03-26
Workspace: `/workspaces/SatComHypatia-frog`
Reference papers:

- `HAL.pdf`
- `W1_imc2020-hypatia.pdf`

## 1. Introduce about FROG

`papier2` is the extension layer built on top of the original Hypatia codebase to compare baseline shortest-path routing against FROG-based first-hop and last-hop optimization.

The comparison of interest is:

- `k=1`
  Baseline Hypatia routing using `algorithm_free_one_only_over_isls`
- `k=3`
  FROG variant using `algorithm_free_one_only_over_isls3`
- `k=5`
  FROG variant using `algorithm_free_one_only_over_isls5`

The key idea is simple: instead of always using the single nearest visible satellite for a ground station, FROG evaluates the `k` nearest visible satellites and chooses a better source and destination satellite pair before the route is forwarded through the inter-satellite network.

The heuristic implemented in this project follows three priorities:

1. common satellite
2. direct-neighbor source/destination satellite pair
3. fallback to the baseline-style shortest-path-compatible choice

This means FROG does not replace the whole forwarding engine. It changes the ground-station attachment decision so that the route entering and leaving the constellation is better aligned with the evolving network geometry.

### 1.1 How FROG is implemented on top of Hypatia

The implementation is split across dispatch, algorithm wrappers, and forwarding-state calculation.

#### Files added

- `satgenpy/satgen/dynamic_state/algorithm_free_one_only_over_isls3.py`
- `satgenpy/satgen/dynamic_state/algorithm_free_one_only_over_isls5.py`

What they do:

- expose two new dynamic-state algorithms to the rest of Hypatia
- keep the same interface as the baseline `algorithm_free_one_only_over_isls`
- delegate the real work to dedicated functions in `fstate_calculation.py`

#### Files modified

- `satgenpy/satgen/dynamic_state/fstate_calculation.py`
- `satgenpy/satgen/dynamic_state/generate_dynamic_state.py`
- `papier2/satellite_networks_state/main_helper.py`
- `papier2/paper2.sh`
- `papier2/ns3_experiments/traffic_matrix_load/step_1_generate_runs2.py`
- `papier2/satgenpy_analysis/perform_full_analysis.py`
- `papier2/ns3_experiments/traffic_matrix_load/runs_results.py`
- `papier2/ns3_experiments/traffic_matrix_load/runs_logs4.py`
- `papier2/ns3_experiments/traffic_matrix_load/hop_count.py`

#### What changed in each file

`fstate_calculation.py`

- adds the dedicated forwarding-state builders:
  - `calculate_fstate_shortest_path_without_gs_relaying3(...)`
  - `calculate_fstate_shortest_path_without_gs_relaying5(...)`
- `k=3` uses the first three satellite candidates in range
- `k=5` uses the first five satellite candidates in range
- writes `src_to_dst.txt` to record the chosen ingress/egress satellite pair
- for `k=5`, also writes `possibilities_5.txt` for debugging candidate selection

`generate_dynamic_state.py`

- registers the new algorithms so the generation pipeline can dispatch:
  - `algorithm_free_one_only_over_isls3`
  - `algorithm_free_one_only_over_isls5`

`main_helper.py`

- extends the list of supported dynamic-state algorithms so the Telesat scenario generator accepts:
  - `algorithm_free_one_only_over_isls3`
  - `algorithm_free_one_only_over_isls5`

`paper2.sh`

- defines the six experimental variants used by the extended routing study
- now supports `START_INDEX` and `END_INDEX` to rerun only part of the full workload set

`step_1_generate_runs2.py`

- builds run directories and schedules for the `papier2` traffic-matrix-load experiments
- writes the commodity list used later by the routing and analysis scripts

`perform_full_analysis.py`

- generates path and RTT analysis for the exact commodity pairs created by `papier2`

`runs_results.py`

- aggregates TCP and UDP totals over all commodities
- defaults to `_120` for the validated 120-second runs
- writes:
  - `results_tcp_10_Mbps_for_120s.txt`
  - `results_udp_10_Mbps_for_120s.txt`

`runs_logs4.py`

- overlays one selected TCP flow across algorithms
- writes:
  - `pdf/runs_logs4_tcp_overlay_120s_10mbps.pdf`
  - `pdf/runs_logs4_tcp_overlay_120s_10mbps.png`

`hop_count.py`

- compares hop counts across all six routing variants
- writes the summary table in:
  - `papier2/ns3_experiments/traffic_matrix_load/hop_count.txt`

## 2. Workflow

This workflow is written for someone who knows nothing about the project and wants to reproduce everything `papier2` can generate.

### 2.1 Base installation

`papier2` depends on the same root environment as the original Hypatia project.

Commands:

```bash
git clone <your-repo-url> SatComHypatia-frog
cd SatComHypatia-frog
git submodule update --init --recursive
docker compose build
docker compose up -d hypatia-dev
docker compose exec -T hypatia-dev bash -lc 'cd /workspaces/SatComHypatia-frog && printf "y\n" | bash hypatia_install_dependencies.sh'
docker compose exec -T hypatia-dev bash -lc 'cd /workspaces/SatComHypatia-frog && bash hypatia_build.sh'
```

Required tools/libraries:

- everything needed by the original Hypatia stack
- `gurobipy`
- Gurobi Optimizer if you want to run MCNF-based variants without license failure

Important distinction:

- `k=1`, `k=3`, and `k=5` shortest-path based comparisons are reproducible without the large MCNF solve
- `...over_isls2`, `...over_isls4`, `...over_isls6` depend on Gurobi optimization capacity and failed in this workspace with the free size-limited license

### 2.2 Main orchestration script

The full `papier2` pipeline is launched through:

```bash
docker compose exec -T hypatia-dev bash -lc 'cd /workspaces/SatComHypatia-frog/papier2 && bash paper2.sh'
```

What `paper2.sh` does for each configured algorithm:

1. writes `debitISL.temp`
2. runs `step_1_generate_runs2.py`
3. runs `perform_full_analysis.py`
4. runs `step_2_run.py`
5. finally runs `runs_logs4.py` and `runs_results.py`

Parameters hard-coded in the validated configuration:

- constellation: `main_telesat_1015.py`
- duration: `120`
- time step: `10000 ms`
- ISL mode: `isls_plus_grid`
- ground stations: `ground_stations_top_100`
- threads: `4`
- ISL rate: `10 Mbps`

### 2.3 Recommended reproduction path for the FROG comparison

The full script tries to run six variants:

- `algorithm_free_one_only_over_isls`
- `algorithm_free_one_only_over_isls2`
- `algorithm_free_one_only_over_isls3`
- `algorithm_free_one_only_over_isls4`
- `algorithm_free_one_only_over_isls5`
- `algorithm_free_one_only_over_isls6`

If the goal is specifically the FROG-vs-baseline comparison, run only:

- index `0` for `k=1`
- index `2` for `k=3`
- index `4` for `k=5`

Commands:

```bash
docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/papier2
START_INDEX=0 END_INDEX=0 bash paper2.sh
'

docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/papier2
START_INDEX=2 END_INDEX=2 bash paper2.sh
'

docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/papier2
START_INDEX=4 END_INDEX=4 bash paper2.sh
'
```

Why this is the correct practical workflow:

- it reproduces the comparison relevant to HAL
- it avoids blocking on the large MCNF variants that exceeded the Gurobi free license

### 2.4 What each `papier2` stage generates

#### Stage A: dynamic state and run configuration

Command executed by `paper2.sh`:

```bash
python step_1_generate_runs2.py <debitISL> <constellation> <duration> <timestep> <isls> <ground_stations> <algorithm> <threads>
```

Purpose:

- creates ns-3 run directories
- writes TCP and UDP schedules
- writes commodity lists
- triggers the routing-state generation in `papier2/satellite_networks_state`

Generated artifacts:

- `papier2/ns3_experiments/traffic_matrix_load/runs/...`
- `papier2/satellite_networks_state/commodites.temp`
- `papier2/satellite_networks_state/debitISL.temp`
- `papier2/satellite_networks_state/gen_data/...`

#### Stage B: theoretical path and RTT analysis

Command executed by `paper2.sh`:

```bash
python perform_full_analysis.py <same arguments>
```

Purpose:

- computes path traces and RTT traces for all generated commodity pairs
- stores manual path/RTT outputs used later for debugging and analysis

Generated artifacts:

- `papier2/satgenpy_analysis/data/.../manual/data/networkx_path_*.txt`
- `papier2/satgenpy_analysis/data/.../manual/data/networkx_rtt_*.txt`
- `papier2/satgenpy_analysis/data/.../manual/pdf/*.pdf`

#### Stage C: ns-3 traffic-matrix-load simulation

Command executed by `paper2.sh`:

```bash
python step_2_run.py 0 <debitISL> <duration> <algorithm>
```

Purpose:

- executes one TCP and one UDP ns-3 run for the selected routing algorithm
- records timing, flow completion, burst delivery, utilization, and per-flow logs

Generated artifacts:

- `papier2/ns3_experiments/traffic_matrix_load/runs/.../logs_ns3/*`

#### Stage D: aggregate post-processing

Commands:

```bash
python runs_logs4.py
python runs_results.py
python hop_count.py
python step_3_generate_plots.py
```

Purpose:

- `runs_logs4.py`
  overlays TCP `cwnd`, RTT, and progress for one logged flow
- `runs_results.py`
  computes aggregate TCP and UDP totals
- `hop_count.py`
  compares path length across routing variants
- `step_3_generate_plots.py`
  generates simulator runtime/goodput scaling plots

Generated artifacts:

- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.pdf`
- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.png`
- `papier2/ns3_experiments/traffic_matrix_load/hop_count.txt`
- `papier2/ns3_experiments/traffic_matrix_load/pdf/*`
- `papier2/ns3_experiments/traffic_matrix_load/data/*`

### 2.5 Bugs and how to fix them

The validated issues below come from [RUN_REPORT.md](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/RUN_REPORT.md).

#### Bug A: container missing runtime tools

Symptoms:

- build failures
- figure conversion failures
- analysis scripts depending on tools not present in the image

Fix:

- add the following to `Dockerfile` if absent:
  - `unzip`
  - `screen`
  - `poppler-utils`
  - packages needed by `openmpi`

#### Bug B: `gurobipy` missing

Symptoms:

- import failure from `satgenpy`

Fix:

- ensure `gurobipy` is installed in the container environment

#### Bug C: size-limited Gurobi license fails on MCNF variants

Symptom:

```text
gurobipy._exception.GurobiError: Model too large for size-limited license
```

Impact:

- `algorithm_free_one_only_over_isls2`
- `algorithm_free_one_only_over_isls4`
- `algorithm_free_one_only_over_isls6`

did not generate valid `fstate_0.txt`, so the related ns-3 runs abort.

Fix/workaround:

1. use an unrestricted or academic Gurobi license, or
2. reproduce only indices `0`, `2`, and `4` for the baseline-vs-FROG report

#### Bug D: `runs_results.py` ignored 120-second runs

Root cause:

- default tag was `_20`

Fix:

- change the default to:

```python
tps_simu = os.environ.get("PAPIER2_DURATION_TAG", "_120")
```

#### Bug E: `runs_results.py` wrote malformed output

Root cause:

- string joining was done at the character level

Fix:

- write formatted lines directly with `f.write("...\n".format(...))`

#### Bug F: `runs_logs4.py` used interactive plotting by default

Symptom:

- unsafe in headless container execution

Fix:

- save outputs directly to `pdf/`
- only display interactively if `DISPLAY` is set

#### Bug G: satviz blank output in browser

If you also want `satviz` visualizations for the `papier2` analysis, the same Cesium and imagery fixes from the original Hypatia reproduction apply:

- update [satviz/static_html/top.html](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satviz/static_html/top.html)
- use Cesium `1.57` assets from `cesium.com`
- use OpenStreetMap imagery

## 3. Result and analysis about the result

### 3.1 Validated environment and experiment parameters

Validated setup from this workspace:

- environment:
  macOS host, Ubuntu 22.04 container
- constellation:
  `telesat_1015`
- routing update interval:
  `10000 ms`
- simulation duration:
  `120 s`
- number of ground stations:
  `100`
- traffic style:
  random reciprocal permutation pairing
- link rate:
  `10 Mbps`

The completed runs in this workspace were:

- `algorithm_free_one_only_over_isls`
- `algorithm_free_one_only_over_isls3`
- `algorithm_free_one_only_over_isls5`

### 3.2 Path Length Evaluation

Primary artifact:

- `papier2/ns3_experiments/traffic_matrix_load/hop_count.txt`

Meaning of this file:

- it compares the initial path length for each of the 100 commodity pairs across all six routing variants
- for the shortest-path family, the important columns are:
  - `ISLS`
  - `ISLS3`
  - `ISLS5`
- the summary values at the top of the file are:
  - `AVERAGE DIFFERENCE SP 3: -10.57%`
  - `AVERAGE DIFFERENCE SP 5 -19.05%`

Interpretation:

- negative percentages mean fewer satellite hops than the baseline shortest-path attachment choice
- `k=3` reduces hop count on average by about `10.57%`
- `k=5` reduces hop count on average by about `19.05%`

This is the clearest structural result of the FROG heuristic in this repository: better entry/exit satellite selection often produces shorter end-to-end satellite paths before TCP behavior is even considered.

### 3.3 Throughput Evaluation

Primary artifacts:

- `papier2/ns3_experiments/traffic_matrix_load/plots/plot_goodput_total_data_sent_vs_runtime.plt`
- `papier2/ns3_experiments/traffic_matrix_load/plots/plot_goodput_rate_vs_slowdown.plt`
- generated PDFs under `papier2/ns3_experiments/traffic_matrix_load/pdf/`

What these plots represent:

- total application data transmitted versus simulator runtime
- goodput rate versus simulation slowdown

What they are used for:

- evaluating how much traffic the system successfully transfers
- comparing routing variants at fixed experiment settings
- checking simulator scaling and processing cost

Aggregate throughput values recorded in [RUN_REPORT.md](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/RUN_REPORT.md) for the validated `120s`, `10 Mbps` workload:

- UDP received volume
  - `k=1`: `11768.90 Mb`
  - `k=3`: `11838.71 Mb`
  - `k=5`: `11862.88 Mb`

Interpretation:

- FROG improves received UDP traffic modestly
- `k=5` performs best among the three compared shortest-path variants
- the improvement is smaller than the hop-count improvement because end-to-end throughput is constrained by many additional factors beyond route length alone

### 3.4 TCP Performance Evaluation

Primary artifact:

- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.png`

What this figure shows:

- one selected TCP commodity plotted over time
- three stacked views:
  - congestion window
  - RTT
  - progress in bytes

Why it matters:

- it shows how routing choice changes real TCP behavior, not just theoretical path length

Aggregate TCP results recorded in [RUN_REPORT.md](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/RUN_REPORT.md):

- transferred TCP data
  - `k=1`: `19952.83 Mb`
  - `k=3`: `20667.38 Mb`
  - `k=5`: `21083.73 Mb`
- finished TCP flows out of `100`
  - `k=1`: `53`
  - `k=3`: `61`
  - `k=5`: `66`

Interpretation:

- `k=3` improves over baseline in both total data transferred and number of completed flows
- `k=5` is the best result in this workspace
- the TCP overlay figure is the behavior-level explanation of those totals:
  better routing decisions reduce long and unstable paths, which helps TCP progress further during the fixed 120-second experiment window

### 3.5 Additional generated FROG figures

Validated artifacts present in this branch:

- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.pdf`
- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.png`
- `papier2/ns3_experiments/traffic_matrix_load/pdf/path_rtt_k_comparison_432_to_446.pdf`
- `papier2/ns3_experiments/traffic_matrix_load/pdf/path_rtt_k_comparison_432_to_446.png`

These pair-specific RTT comparison figures are useful to show concrete examples where the FROG variants avoid poor baseline attachment choices.

## 4. Conclusion

`papier2` is a targeted extension of Hypatia that inserts the FROG heuristic into the dynamic-state generation stage while keeping the original Hypatia experiment stack intact.

The main conclusions supported by this workspace are:

1. FROG is implemented as an extension, not a rewrite.
   The original Hypatia architecture remains the same, while new routing variants are introduced through `satgenpy` dynamic-state functions and `papier2` experiment scripts.
2. The strongest structural improvement is path length reduction.
   `hop_count.txt` shows that `k=3` and `k=5` reduce average path length relative to the baseline shortest-path attachment rule.
3. These structural gains carry into TCP behavior.
   The validated aggregate results show higher transferred data and more finished TCP flows for `k=3` and especially `k=5`.
4. The full six-algorithm study is limited by Gurobi licensing.
   For a clean baseline-vs-FROG reproduction, the practical and correct subset is `k=1`, `k=3`, and `k=5`.

For a reader who wants to reproduce the project successfully, the right target is:

- build the common Hypatia environment
- run `papier2` for indices `0`, `2`, and `4`
- regenerate `runs_logs4`, `hop_count`, and `step_3_generate_plots`
- use the resulting figures and summaries to compare `k=1`, `k=3`, and `k=5`

That is the most direct path to reproducing the FROG contribution described in this project.
