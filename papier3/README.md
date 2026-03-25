# Papier3 Run Report (Direction-Aware Floyd–Warshall)

Date: 2026-03-25  
Branch used: `applyDAD`

## 1) What Was Implemented

- Added a new dynamic-state routing algorithm:
  - `algorithm_direction_aware_floyd_warshall`
  - Direction-aware ISL cost for directed link `i -> j`:
    - `alpha = cos(velocity(i), link_direction(i->j))`
    - `w = w0 * (1 - beta * alpha)` (default `f(alpha)=-alpha`)
- Added directed all-pairs shortest-path computation via Floyd–Warshall for the new mode.
- Kept baseline (`k=1`) and existing FROG (`k=3`, `k=5`) logic unchanged.
- Added reproducible `papier3/` experiment scripts:
  - smoke verification (`k=1`, `k=3`, `k=5`, DA-FW)
  - full 7-variant comparison run
  - summary table generation
  - confidence interval table generation
  - plot generation

## 2) Files Changed

- `satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py` (new)
  - New DA-FW algorithm implementation
- `satgenpy/satgen/dynamic_state/generate_dynamic_state.py`
  - Registered DA-FW mode
  - Added beta parsing from algorithm name suffix
- `papier2/satellite_networks_state/main_helper.py`
  - Accepted `algorithm_direction_aware_floyd_warshall*` in one-interface GSL branch
- `papier3/config/experiment_config.json` (new)
  - Reproducible experiment matrix config
- `papier3/scripts/run_experiments.py` (new)
  - End-to-end smoke + generation + analysis + plotting orchestrator
- `papier3/scripts/compute_summary.py` (new)
  - Metric extraction and summary table generation
- `papier3/scripts/compute_confidence_intervals.py` (new)
  - 95% CI computation for task-4.2 metrics from raw sampled routes
- `papier3/scripts/plot_results.py` (new)
  - Comparison and DA-beta plots
- `papier3/scripts/run_all.sh` (new)
  - Single-command wrapper
- `papier3/README.md`

## 3) Commands To Reproduce

From repo root:

1. Dependency required in this environment:
```bash
python3 -m pip install --user gurobipy
```

2. Run smoke checks + full experiment matrix + tables + plots:
```bash
python3 papier3/scripts/run_experiments.py --config papier3/config/experiment_config.json
```

3. Optional rerun analysis/plots only (no regeneration):
```bash
python3 papier3/scripts/run_experiments.py --config papier3/config/experiment_config.json --skip-generation --skip-smoke
```

4. Compute task-4.2 confidence intervals from raw samples:
```bash
python3 papier3/scripts/compute_confidence_intervals.py --config papier3/config/experiment_config.json
```

5. Optional force full regeneration (ignore cached dynamic-state directories):
```bash
python3 papier3/scripts/run_experiments.py --config papier3/config/experiment_config.json --force-regenerate
```

## 4) Dependencies / Setup Notes

- Python 3
- Python packages used by this run:
  - `numpy`, `networkx`, `astropy`, `ephem`, `matplotlib`, `gurobipy`
- Existing generated topology/data under:
  - `papier2/satellite_networks_state/gen_data/`
- Commodity list source:
  - `papier2/satellite_networks_state/commodites.temp`

## 5) Bugs Encountered And Fixes

1. `satgen` import failed due missing `gurobipy`.
   - Fix applied in environment: `python3 -m pip install --user gurobipy`
2. FROG debug side-effect files were touched during smoke run (`src_to_dst.txt`, `possibilities_5.txt`).
   - Fix applied: restored tracked file and removed generated temporary file.

## 6) Outputs Regenerated

Main outputs:

- Summary tables:
  - `papier3/results/summary_metrics.csv`
  - `papier3/results/summary_metrics.md`
  - `papier3/results/summary_metrics.json`
  - `papier3/results/summary_metrics_ci.csv`
  - `papier3/results/summary_metrics_ci.json`
- Run manifest:
  - `papier3/results/run_manifest.json`
- Plots:
  - `papier3/results/plots/*.png`
  - `papier3/results/plots/*.pdf`

Dynamic-state regeneration for this report:

- Full (`20s`, `100ms`) generated for all 7 algorithms:
  - baseline `k=1`
  - FROG `k=3`
  - FROG `k=5`
  - DA-FW `beta=0.0`
  - DA-FW `beta=0.1`
  - DA-FW `beta=0.2`
  - DA-FW `beta=0.3`

Plot regeneration:

- Summary and CI tables were regenerated successfully.
- Plot regeneration was attempted in this environment, but Matplotlib/font cache issues prevented a clean rerun of the plots.

## 7) Cached / Temp Reuse

- No `20s` / `100ms` dynamic-state directories were reused for this report run.
- The `20s` / `100ms` forwarding-state outputs used in the final tables were regenerated for all 7 algorithms.

## 8) Result Interpretation (20s Simulation, 100ms Timestep)

Data sources:

- `papier3/results/summary_metrics.csv`
- `papier3/results/summary_metrics_ci.csv`

### 8.1) Experimental Methodology: Scenarios Actually Covered In This Run

This practical run matches the task requirements in the following way:

- Different values of the directional bias parameter `beta` were evaluated with DA-FW at `0.0`, `0.1`, `0.2`, and `0.3`.
- Multiple source-destination pairs were evaluated through the existing commodity list in `papier2/satellite_networks_state/commodites.temp`.
- The run produced `200` timesteps per algorithm (`20s` at `100ms`) and `20,000` route samples per algorithm.
- Communication was ground-to-ground via the satellite network.
- The practical run used one constellation/orbital configuration already present in the repository: `telesat_1015`, `isls_plus_grid`, `ground_stations_top_100`.
- Statistical confidence is reported from the observed samples using 95% confidence intervals.

Practical limitation of this run:

- This report does not include a sweep over multiple constellation sizes or orbital parameters.
- It therefore satisfies the comparison across routing algorithms and `beta` values, but not a multi-constellation sensitivity study.

### 8.2) Performance Metrics: Averages And 95% Confidence Intervals

| Algorithm | End-to-end latency (ms) | Packet delivery ratio | Average hop count | Path stability (route-change rate) |
|---|---:|---:|---:|---:|
| baseline_k1 | 165.315 [164.300, 166.330] | 1.0000 [0.9998, 1.0000] | 11.158 [11.089, 11.227] | 0.001106 [0.000730, 0.001673] |
| frog_k3 | 147.978 [146.930, 149.026] | 1.0000 [0.9998, 1.0000] | 9.969 [9.900, 10.038] | 0.001055 [0.000690, 0.001613] |
| frog_k5 | 134.016 [132.957, 135.076] | 1.0000 [0.9998, 1.0000] | 8.963 [8.895, 9.031] | 0.001256 [0.000851, 0.001854] |
| da_fw_beta_0_0 | 165.315 [164.300, 166.330] | 1.0000 [0.9998, 1.0000] | 11.158 [11.089, 11.227] | 0.001106 [0.000730, 0.001673] |
| da_fw_beta_0_1 | 167.297 [166.254, 168.341] | 1.0000 [0.9998, 1.0000] | 11.228 [11.159, 11.297] | 0.001106 [0.000730, 0.001673] |
| da_fw_beta_0_2 | 167.502 [166.454, 168.551] | 1.0000 [0.9998, 1.0000] | 11.258 [11.188, 11.328] | 0.001156 [0.000770, 0.001734] |
| da_fw_beta_0_3 | 172.905 [171.762, 174.047] | 1.0000 [0.9998, 1.0000] | 11.482 [11.409, 11.556] | 0.001156 [0.000770, 0.001734] |

### 8.3) Expected Outcomes: Interpretation Of Observed Trends

1. Identify scenarios where direction-aware routing outperforms standard Dijkstra:
- In this practical `20s` / `100ms` Telesat-1015 scenario, no DA-FW setting with `beta > 0` outperformed baseline `k=1`.
- `da_fw_beta_0_0` matched baseline exactly, which is the expected equivalence check.
- The observed DA-FW trend in this scenario is therefore "correct but not beneficial" rather than "better than baseline".

2. Analyze sensitivity to the parameter `beta`:
- The DA-FW results worsen monotonically as `beta` increases.
- RTT rises from `165.315 ms` at baseline / `beta=0.0` to `167.297 ms` at `beta=0.1`, `167.502 ms` at `beta=0.2`, and `172.905 ms` at `beta=0.3`.
- Hop count follows the same direction, from `11.158` to `11.228`, `11.258`, and `11.482`.
- This indicates that the directional penalty is strong enough in this scenario to steer routes onto physically longer paths without compensating benefit.

3. Discuss trade-offs between latency reduction and path stability:
- DA-FW does not provide a favorable latency-stability trade-off here.
- `beta=0.1` keeps the same measured route-change rate as baseline but still increases latency and hop count.
- `beta=0.2` and `beta=0.3` slightly worsen both latency and route-change rate.
- In short, the DA-FW variants do not buy stability improvements in exchange for latency loss in this run.

4. When and why mobility-aware routing outperforms standard Dijkstra:
- In this practical run, the clear mobility-aware gains come from the existing FROG family, not from DA-FW.
- `frog_k3` reduces RTT from `165.315 ms` to `147.978 ms` and hop count from `11.158` to `9.969`, while also slightly reducing route-change rate from `0.001106` to `0.001055`.
- `frog_k5` further reduces RTT to `134.016 ms` and hop count to `8.963`, but with a modest increase in route-change rate to `0.001256`.
- The observed reason is that FROG's multi-candidate routing explores more path alternatives and finds shorter routes through the evolving topology, whereas the DA-FW directional edge reweighting does not translate into better end-to-end path choices in this scenario.

5. Scenarios where FROG routing performs better:
- In this exact `20s` / `100ms` top-100-ground-station scenario, both FROG variants outperform baseline and all DA-FW variants on latency and hop count.
- `frog_k3` is the most balanced option in this run because it improves latency and hop count while also being marginally more stable than baseline.
- `frog_k5` is the best pure-latency option, but it pays for that with slightly more route churn than both baseline and `frog_k3`.

6. Trade-offs between latency optimization and route stability:
- `frog_k3` gives a favorable trade-off in this run: lower latency, lower hop count, and slightly better path stability.
- `frog_k5` gives the strongest latency optimization, but route-change rate rises from `0.001106` to `0.001256`.
- DA-FW does not show a useful trade-off here because increasing `beta` degrades latency and hop count without producing a compensating reduction in route changes.

### 8.4) Main Conclusion For This Practical Run

- The baseline equivalence check passed: `da_fw_beta_0_0` reproduced baseline `k=1` exactly in all reported metrics.
- In this scenario, DA-FW with positive `beta` values did not outperform baseline `k=1`.
- The strongest improvements came from the existing FROG methods, especially `frog_k5` for minimum latency and `frog_k3` for the best overall balance.
- The practical conclusion is that predictable mobility can clearly be exploited in this repository, but in this tested scenario the benefit is captured by FROG rather than by the current DA-FW heuristic.
