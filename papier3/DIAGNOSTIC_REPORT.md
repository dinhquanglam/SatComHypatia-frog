# DA-FW Diagnostic Report

Date: 2026-03-25  
Branch: `applyDAD`

## 1) Code-Path Explanation

### 1.1 Dispatch path
- DA-FW is registered in [generate_dynamic_state.py:49](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/generate_dynamic_state.py:49).
- Beta parsing from algorithm name is implemented in [generate_dynamic_state.py:52](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/generate_dynamic_state.py:52).
- Runtime dispatch into DA-FW happens at [generate_dynamic_state.py:444](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/generate_dynamic_state.py:444).

### 1.2 Where each DA quantity is computed
- Satellite Cartesian position vectors: [_compute_satellite_positions_cartesian():31](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:31)
- Velocity vectors: finite difference at [_build_direction_aware_directed_graph():77-85](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:77)
- Directed link vectors:
  - `a->b` at line [93](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:93)
  - `b->a` at line [101](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:101)
- Alpha (`cos(v, d)`): [_compute_alignment_cosine():55-61](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:55)
- Modified edge weight `w = w0 * (1 - beta * alpha)`: [_compute_direction_aware_weight():64-66](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:64)
- Floyd–Warshall on modified graph: [_calculate_fstate...():128](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:128)
- Forwarding-state generation from that distance matrix: [_calculate_fstate...():139-221](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:139)

### 1.3 Coordinate frame used
- Coordinates are built from `(sublat, sublong, elevation)` and converted via `geodetic2cartesian(...)` in [_compute_satellite_positions_cartesian():44-48](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/satgenpy/satgen/dynamic_state/algorithm_direction_aware_floyd_warshall.py:44).
- This is an Earth-fixed geodetic-to-Cartesian frame.
- Velocity is computed in the same frame (`pos(t+1s)-pos(t)`), so alpha uses self-consistent vectors.

### 1.4 Plain-English logic summary
- For each timestep, DA-FW computes satellite positions and approximate velocities.
- Each undirected ISL is expanded into two directed edges.
- For each direction, alpha is the cosine between transmitter velocity and link direction.
- ISL weight is scaled by `1 - beta*alpha`.
- Floyd–Warshall computes all-pairs shortest distances over this directed weighted ISL graph.
- Existing forwarding logic then produces `fstate` updates using those DA distances (GSL behavior unchanged).

## 2) Mathematical Sanity Checks

Artifacts:
- [math_vector_cases.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/math_vector_cases.csv)
- [math_routing_flip_case.json](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/math_routing_flip_case.json)
- [math_diagnostic_summary.json](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/math_diagnostic_summary.json)

Results:
- Deterministic alpha cases `1, 0, -1, 0.3, 0.7`: all computed alpha values match hand expectations (numerical tolerance only).
- Modified weights exactly match hand calculations.
- Tiny two-path routing toy case confirms path flips exactly when DA-modified costs make alternate path better.

Conclusion for Section 2: DA math implementation (alpha and `w`) is correct on deterministic controlled inputs.

## 3) Beta=0 Exact Equivalence

Artifacts:
- [beta0_semantic_equivalence_per_timestep.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/beta0_semantic_equivalence_per_timestep.csv)
- [beta0_sample_route_comparison.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/beta0_sample_route_comparison.csv)
- [beta0_equivalence_summary.json](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/beta0_equivalence_summary.json)

Results:
- Semantic forwarding-state equivalence baseline vs DA-beta0: exact (`diff_entries=0`) at all 12 timesteps.
- Sampled route equivalence baseline vs DA-beta0: exact (0 mismatches over 240 sampled pair-time checks).

Conclusion for Section 3: DA with `beta=0` truly reproduces baseline routing state behavior, not just similar aggregate metrics.

## 4) Alpha / Multiplier Distributions

Artifacts:
- [alpha_summary.json](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/alpha_summary.json)
- [alpha_histogram.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/alpha_histogram.csv)
- [multiplier_stats.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/multiplier_stats.csv)
- [multiplier_histograms.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/multiplier_histograms.csv)

Key numbers:
- Alpha count: `16848` directed ISL samples.
- Alpha min/mean/max: `-0.9946 / 0.000099 / 0.9997`.
- Fraction `alpha>0`: `0.5`; `alpha<0`: `0.5`.
- Multipliers (`w/w0`) range:
  - beta `0.1`: `0.9000 .. 1.0995`
  - beta `0.2`: `0.8001 .. 1.1989`
  - beta `0.3`: `0.7001 .. 1.2984`

Interpretation:
- The directional signal is strong (alpha often near ±1), not near-zero numerical noise.
- At larger beta values, ISL cost scaling becomes large enough to strongly reorder shortest paths.

## 5) Sampled Path-Difference Analysis

Artifacts:
- [path_difference_samples.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/path_difference_samples.csv)
- [path_difference_summary.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/path_difference_summary.csv)
- [path_difference_alpha_reasoning_summary.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/path_difference_alpha_reasoning_summary.csv)

Summary (20 commodity pairs x 12 timesteps per beta):
- beta `0.01/0.02/0.05`: no sampled path changes vs baseline.
- beta `0.1`: 33/240 changed (`13.75%`).
- beta `0.2`: 39/240 changed (`16.25%`).
- beta `0.3`: 45/240 changed (`18.75%`).

For every changed sampled case at beta `>=0.1`:
- DA-chosen path has lower **DA-modified** path cost than baseline path.
- DA-chosen path has higher **physical RTT** than baseline path.

So path changes are mathematically consistent with the implemented DA objective, but unfavorable for physical-delay RTT.

## 6) Route-Stability Analysis

Artifacts:
- [route_stability_metrics.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/route_stability_metrics.csv)
- [fstate_diff_vs_baseline_per_timestep.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/fstate_diff_vs_baseline_per_timestep.csv)

Key DA findings:
- beta `0.0`: identical to baseline (`route_change_rate=0.1`).
- beta `0.01/0.02`: still identical path metrics to baseline.
- beta `0.05`: near-baseline, tiny shift.
- beta `0.1/0.2/0.3`: RTT and hop-count rise, route-change-rate slightly increases, and forwarding-state differences vs baseline become large.

## 7) Failure-Mode Hypotheses

### 7.1 Sign hypothesis (`1 - beta*alpha` vs `1 + beta*alpha`)
Artifacts:
- [sign_beta_sensitivity_simulated.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/sign_beta_sensitivity_simulated.csv)
- [sign_comparison_summary.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/sign_comparison_summary.csv)
- [sign_model_validation.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/sign_model_validation.csv)

Results:
- Diagnostic simulator matches actual minus-sign DA runs exactly (zero metric error in validation file).
- Opposite sign (`+`) does **not** improve RTT; it is slightly worse or nearly equal in this scenario.

Conclusion: performance degradation is not explained by an obvious sign inversion bug.

### 7.2 Scale hypothesis (beta magnitude)
Artifacts:
- [scale_sensitivity_actual.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/scale_sensitivity_actual.csv)

Results:
- `0.01`, `0.02`: effectively baseline-equivalent.
- `0.05`: almost baseline.
- degradation becomes visible at `0.1` and worsens by `0.3`.

Conclusion: currently used beta values (`0.1+`) are strong enough to move routing away from RTT-optimal behavior.

### 7.3 Coordinate/velocity hypothesis
Artifacts:
- [velocity_summary.json](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/velocity_summary.json)
- [distance_consistency_summary.json](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/distance_consistency_summary.json)

Results:
- Velocity magnitude range: ~`7405 .. 7471` m/s (physically plausible LEO orbital speed scale).
- Position-derived ISL Euclidean distances vs baseline distance function differ by ~`0.31%` mean relative error (`0.57%` max), acceptable for this diagnostic purpose.
- Same coordinate frame is used for position, velocity, and link vectors in alpha.

Conclusion: no evidence of frame/unit inconsistency bug in alpha computation.

### 7.4 Directed-graph hypothesis
Artifact:
- [directed_graph_checks.csv](/Users/dinhquanglam/Desktop/France/M2SAR/1ProjectSatCom/Hyptia/SatComHypatia-frog/papier3/results/diagnostics/directed_graph_checks.csv)

Results:
- Directed edge count always exactly `2 * |ISL| = 1404`.
- Out-degree remains exactly 4 for all satellites.
- Graph is strongly connected at all timesteps.
- No missing interface mappings for directed edges.

Conclusion: directed conversion does not appear to break downstream forwarding assumptions.

## 8) Final Conclusion

**implementation appears correct but heuristic underperforms**

Evidence basis:
- Controlled math checks pass.
- `beta=0` is semantically identical to baseline forwarding state.
- No unit/frame/directed-graph correctness failure detected.
- Degradation appears when beta is large enough to cause path changes that reduce DA objective cost but increase physical RTT/hops.

