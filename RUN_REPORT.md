# Hypatia Run Report (Workspace: SatComHypatia-frog)

Date: 2026-03-23

## Goal
Run the project end-to-end, regenerate figures/visualizations, and document reproducible commands plus bug fixes.

## Environment Used
- Host: macOS (Docker Desktop)
- Container: `hypatia-dev` (`ubuntu:22.04` based)
- Repo root in container: `/workspaces/SatComHypatia-frog`

## What Was Successfully Generated
- Paper figure PDFs: `62`
- Paper figure PNGs: `65`
- Satviz HTML files: `5`

Verified examples:
- `paper/figures/traffic_matrix_load_scalability/pdf/plot_goodput_rate_vs_slowdown.pdf`
- `paper/figures/a_b/multiple_rtt_matching/pdf/time_vs_multiple_rtt_pair_a.pdf`
- `paper/figures/a_b/tcp_cwnd/pdf/time_vs_tcp_cwnd_and_bdp_plus_queue_pair_a.pdf`
- `paper/figures/constellation_comparison/general_ecdfs/pdf/ecdf_max_rtt.pdf`
- `satviz/viz_output/kuiper_630_path_Paris_1180_Moskva-(Moscow)_1177_10000_isls.html`
- `satviz/viz_output/kuiper_630_path_158300.html`
- `satviz/viz_output/kuiper_630_path_wise_util_Chicago_1193_Zhengzhou_1243_10000_isls.html`
- `satviz/viz_output/kuiper_630_util_10000.html`
- `satviz/viz_output/Telesat.html`

## Recommended Repro Workflow

### 1) Build and start container
```bash
docker compose build
docker compose up -d hypatia-dev
```

### 2) Install dependencies (non-interactive)
```bash
docker compose exec -T hypatia-dev bash -lc 'cd /workspaces/SatComHypatia-frog && printf "y\n" | bash hypatia_install_dependencies.sh'
```

### 3) Build simulator stack
```bash
docker compose exec -T hypatia-dev bash -lc 'cd /workspaces/SatComHypatia-frog && bash hypatia_build.sh'
```

### 4) Fast paper-data restore (recommended for practical runtime)
```bash
curl -L --fail -o paper/hypatia_paper_temp_data.tar.gz \
  https://github.com/snkas/hypatia/releases/download/v1/hypatia_paper_temp_data.tar.gz
shasum -a 256 paper/hypatia_paper_temp_data.tar.gz
# expected:
# 18d761a28706723b57772e0636fbc40b7d57161f4c54069eede0c8ae740cbe2d

docker compose exec -T hypatia-dev bash -lc \
  'cd /workspaces/SatComHypatia-frog/paper && printf "yes\n" | python3 extract_temp_data.py'
```

### 5) Regenerate experiment plots from restored runs/data
```bash
docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/paper/ns3_experiments/a_b && python3 step_3_generate_plots.py
cd /workspaces/SatComHypatia-frog/paper/ns3_experiments/traffic_matrix && python3 step_3_generate_plots.py
cd /workspaces/SatComHypatia-frog/paper/ns3_experiments/traffic_matrix_load && python3 step_3_generate_plots.py
'
```

### 6) Generate all paper figure PDFs + PNGs
```bash
docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/paper/figures
python3 plot_all.py
python3 generate_pngs.py
'
```

### 7) Generate satviz HTML visualizations
```bash
docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/satviz
mkdir -p viz_output
cd scripts
python3 visualize_constellation.py
python3 visualize_path.py
python3 visualize_path_no_isl.py
python3 visualize_path_wise_utilization.py
python3 visualize_utilization.py
'
```

## Full From-Scratch Workflow (Very Slow)
To regenerate dynamic-state and ns-3 runs fully from zero (instead of using temp data):
```bash
docker compose exec -T hypatia-dev bash -lc \
  'cd /workspaces/SatComHypatia-frog/paper/satellite_networks_state && bash generate_all_local.sh'

docker compose exec -T hypatia-dev bash -lc \
  'cd /workspaces/SatComHypatia-frog/paper/satgenpy_analysis && python3 perform_full_analysis.py'

docker compose exec -T hypatia-dev bash -lc \
  'cd /workspaces/SatComHypatia-frog/paper/ns3_experiments/a_b && python3 step_1_generate_runs.py && python3 step_2_run.py && python3 step_3_generate_plots.py'

docker compose exec -T hypatia-dev bash -lc \
  'cd /workspaces/SatComHypatia-frog/paper/ns3_experiments/traffic_matrix && python3 step_1_generate_runs.py && python3 step_2_run.py && python3 step_3_generate_plots.py'

# traffic_matrix_load step_2 requires workload id split across 4 machines (0..3)
```
Observed in this workspace: `generate_all_local.sh` alone is multi-hour scale.

## Bugs Found and Fixes Applied

1. `git status` in container failed with `Resource deadlock avoided` / `Bus error` on iCloud-backed bind mount.
- Workaround (repo-local git config):
```bash
git config --local core.checkStat minimal
git config --local core.trustctime false
git config --local core.preloadIndex false
```

2. `hypatia_install_dependencies.sh` prompt blocked non-interactive runs.
- Workaround: pipe `y` (`printf "y\n" | bash hypatia_install_dependencies.sh`).

3. `ns3-sat-sim/build.sh` failed: `unzip: command not found`.
- Fix: add `unzip` to `Dockerfile` apt packages.

4. ARM build failed due x86 prebuilt `cgen` binary (`rosetta error... ld-linux-x86-64.so.2`).
- Fix: in `ns3-sat-sim/build.sh`, remove bundled `simulator/src/satellite/model/data/cgen` before waf build so native binary is regenerated.

5. Werror compile failure in `constants-gen.cc` (`case EOF` with char range warning).
- Fix: use `int c_int = in.peek(); if (c_int == EOF) return in;` and remove `case EOF` in switch.

6. Werror compile failure in `basic-simulation.cc` (`range-loop-construct`).
- Fix: change loop to `for (const auto& key_val : m_config)`.

7. `satgenpy` import errors due missing `gurobipy` in this branch.
- Fix: install `gurobipy`; added to Dockerfile pip install list.

8. `perform_full_analysis.py`/`step_2_run.py` depend on `screen`, but image lacked it.
- Fix: install `screen`; add to Dockerfile apt packages.

9. `generate_pngs.py` required `pdftoppm` not available.
- Fix: install `poppler-utils`; add to Dockerfile apt packages.

10. `paper/figures/plot_all.py` aborted if optional `two_compete` data missing.
- Fix: wrap gnuplot execution in `try/except`, warn and continue for missing optional inputs.

11. `satviz` scripts defaulted to local `papier2` paths and had one runtime bug.
- Fixes:
- repoint default input paths to valid `paper` data and ns3 runs.
- set stable Kuiper defaults in path/utilization scripts.
- fix `visualize_utilization.py` undefined `modif` (default `False`).
- make missing utilization samples default to `0.0` instead of `KeyError`.

12. Satviz pages loaded blank in browser (`localhost:8000`).
- Root causes:
- `satviz/static_html/top.html` referenced `https://cesiumjs.org/...`, which now redirects to HTML and breaks JS loading.
- Stamen tile endpoint `https://stamen-tiles.a.ssl.fastly.net/toner-background/` returned HTTP 503.
- Fixes:
- switch Cesium assets to `https://cesium.com/downloads/cesiumjs/releases/1.57/...`.
- switch imagery source to `https://tile.openstreetmap.org/`.
- regenerate all satviz HTML outputs so existing files include the new URLs.

13. `papier2` summary script defaulted to 20s filter and skipped 120s runs.
- Root cause:
- `papier2/ns3_experiments/traffic_matrix_load/runs_results.py` had `tps_simu = "_20"`.
- Fixes:
- default changed to `_120` for this workload.
- added env-based overrides (`PAPIER2_MBPS`, `PAPIER2_DURATION_TAG`).
- added TCP summary output file (`results_tcp_10_Mbps_for_120s.txt`) alongside UDP summary file.

14. `papier2` logs plotting script was interactive-only (`plt.show()`), unsafe for headless automation.
- Root cause:
- `papier2/ns3_experiments/traffic_matrix_load/runs_logs4.py` tried to open a GUI window in container execution flow.
- Fixes:
- save plot artifacts directly to:
- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.pdf`
- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.png`
- keep interactive display only when `DISPLAY` is set.

15. `papier2` FROG/MCNF routing variants (`...over_isls2`, `...over_isls4`, `...over_isls6`) failed in dynamic-state generation.
- Root cause:
- Gurobi optimization exceeded free/size-limited license capacity:
- `gurobipy._exception.GurobiError: Model too large for size-limited license`
- Impact:
- no `fstate_0.txt` generated for these variants, causing ns-3 runtime abort for those run directories.
- Workaround:
- use an unrestricted/academic Gurobi license, then re-run failed indices only with `START_INDEX`/`END_INDEX`.

16. `runs_results.py` wrote unreadable summary text with a space between every character.
- Root cause:
- `f.write(" ".join(<already formatted string>))` joined characters instead of joining lines.
- Fix:
- write formatted strings directly (`f.write("...\\n".format(...))`).

## Papier2 (FROG / HAL) Reproduction

Command used for full run:
```bash
docker compose exec -T hypatia-dev bash -lc \
  'cd /workspaces/SatComHypatia-frog/papier2 && bash paper2.sh' \
  |& tee repro_logs/13_papier2_paper2_full_run.log
```

What this run executes:
- `6` routing variants listed in `papier2/paper2.sh` (`algorithm_free_one_only_over_isls`, `...2`, `...3`, `...4`, `...5`, `...6`)
- per variant: dynamic-state generation + satgenpy analysis + ns-3 TCP + ns-3 UDP
- final post-processing: `runs_logs4.py` and `runs_results.py`

Runtime observation (current workspace):
- first ns-3 TCP run started and is actively progressing (log snapshot at 2026-03-23 16:07 shows `16.08%` simulation time).
- expected total runtime for all 6 variants is multi-hour scale.
- latest run ended on `2026-03-23 19:34 CET` with partial completion (details below).

Papier2 completion status in this workspace:
- completed (dynamic state + ns3 TCP/UDP data): `algorithm_free_one_only_over_isls`, `algorithm_free_one_only_over_isls3`, `algorithm_free_one_only_over_isls5`
- failed to generate usable forwarding state (`fstate_0.txt` missing): `algorithm_free_one_only_over_isls2`, `algorithm_free_one_only_over_isls4`, `algorithm_free_one_only_over_isls6`
- root cause from traceback: `gurobipy._exception.GurobiError: Model too large for size-limited license`

Primary output locations:
- `papier2/satellite_networks_state/gen_data/`
- `papier2/satgenpy_analysis/data/`
- `papier2/ns3_experiments/traffic_matrix_load/runs/`
- `papier2/ns3_experiments/traffic_matrix_load/pdf/`

Available aggregate outputs generated from completed runs:
- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.pdf`
- `papier2/ns3_experiments/traffic_matrix_load/pdf/runs_logs4_tcp_overlay_120s_10mbps.png`
- `papier2/ns3_experiments/traffic_matrix_load/results_tcp_10_Mbps_for_120s.txt`
- `papier2/ns3_experiments/traffic_matrix_load/results_udp_10_Mbps_for_120s.txt`

Monitoring commands:
```bash
tail -f repro_logs/13_papier2_paper2_full_run.log
docker compose exec -T hypatia-dev bash -lc "ps -eo pid,etime,%cpu,cmd | grep main_satnet | grep -v grep"
```

Resume/partial-run support added to `papier2/paper2.sh`:
```bash
# run only one algorithm index (example: index 3)
docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/papier2
START_INDEX=3 END_INDEX=3 bash paper2.sh
'

# resume from algorithm index 1 to the end
docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/papier2
START_INDEX=1 END_INDEX=5 bash paper2.sh
'
```

Standalone post-processing (after runs are complete):
```bash
docker compose exec -T hypatia-dev bash -lc '
cd /workspaces/SatComHypatia-frog/papier2/ns3_experiments/traffic_matrix_load
python3 runs_logs4.py
python3 runs_results.py
'
```

## Known Non-Blocking Notes
- `hypatia_run_tests.sh` currently reports failing satgenpy tests in this branch (notably around changed routing/function signatures). This did not block figure regeneration using restored paper temp data.
- `paper/ns3_experiments/two_compete` is not part of the paper temp-data bundle and is treated as optional in plotting.

## Logs Collected
All execution logs are under `repro_logs/`, including:
- dependency/install/build logs (`01*`, `02*`, `03*`)
- paper data download/extract (`04a`, `04b`, `04c`, `08a`)
- analysis/plots/figures (`06`, `07`, `09a`)
- satviz generation (`10*`)
- artifact verification (`11_artifact_verification.log`)
- papier2 full pipeline run (`13_papier2_paper2_full_run.log`)
