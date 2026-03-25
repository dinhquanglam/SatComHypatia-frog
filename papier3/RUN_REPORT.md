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
- `papier3/scripts/plot_results.py` (new)
  - Comparison and DA-beta plots
- `papier3/scripts/run_all.sh` (new)
  - Single-command wrapper
- `papier3/RUN_REPORT.md` (new)

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

4. Optional force full regeneration (ignore cached dynamic-state directories):
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
- Run manifest:
  - `papier3/results/run_manifest.json`
- Plots:
  - `papier3/results/plots/*.png`
  - `papier3/results/plots/*.pdf`

Dynamic-state regeneration:

- Smoke (`20s`, `10000ms`):
  - baseline `k=1`
  - FROG `k=3`
  - FROG `k=5`
  - DA-FW `beta=0.1`
- Full (`120s`, `10000ms`) generated for DA-FW:
  - `beta=0.0`, `0.1`, `0.2`, `0.3`

## 7) Cached / Temp Reuse

- Reused existing full dynamic-state directories for:
  - baseline `k=1`
  - FROG `k=3`
  - FROG `k=5`
- Newly generated full dynamic-state directories for all DA-FW beta variants.

## 8) Result Interpretation (This Practical Run)

From `papier3/results/summary_metrics.csv`:

- `beta=0.0` DA-FW matches baseline exactly (as expected):
  - same RTT, hop count, path-change rate, forwarding-state update rate
- In this scenario, increasing DA beta (`0.1 -> 0.3`) increased:
  - average RTT
  - average hop count
  - forwarding-state updates per step
- Reachability proxy (`pdr_proxy`) remained `1.0` for all tested variants.
- Existing FROG variants (`k=3`, `k=5`) outperformed baseline and DA-FW on RTT/hop-count in this run.

## 9) Limitations / Caveats

- Throughput/goodput for DA-FW variants is not present in this run (NS-3 traffic runs were not regenerated for DA-FW); those fields are `NA`.
- `pdr_proxy` is forwarding-state reachability, not packet-level NS-3 delivery ratio.
- Velocity vector is approximated by finite difference of satellite positions with a 1-second delta in the new DA-FW implementation.
- No confidence intervals were computed in this practical subset run.
