#!/usr/bin/env bash
set -euo pipefail

# Contribution script (relocated under report_artifacts):
# Reproducible FROG k-comparison pipeline on top of Hypatia, restricted to:
#   k=1 (algorithm_free_one_only_over_isls)
#   k=3 (algorithm_free_one_only_over_isls3)
#   k=5 (algorithm_free_one_only_over_isls5)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PAPIER2_DIR="$REPO_ROOT/papier2"

cd "$PAPIER2_DIR"

CONSTELLATION="main_telesat_1015.py"
DURATION_S="120"
STEP_MS="10000"
ISL_SELECTION="isls_plus_grid"
GS_SELECTION="ground_stations_top_100"
THREADS="4"
DEBIT_ISL="10"

ALGORITHMS=(
  "algorithm_free_one_only_over_isls"
  "algorithm_free_one_only_over_isls3"
  "algorithm_free_one_only_over_isls5"
)

echo "Running FROG k-only pipeline with paper parameters (k=1,3,5)."

for algo in "${ALGORITHMS[@]}"; do
  echo ""
  echo "=== Algorithm: ${algo} ==="

  echo "$DEBIT_ISL" > satellite_networks_state/debitISL.temp

  echo "[1/3] Generate runs and inputs"
  cd ns3_experiments/traffic_matrix_load
  python3 step_1_generate_runs2.py \
    "$DEBIT_ISL" \
    "$CONSTELLATION" "$DURATION_S" "$STEP_MS" \
    "$ISL_SELECTION" "$GS_SELECTION" "$algo" "$THREADS"
  cd ../..

  echo "[2/3] Run satgenpy analysis"
  cd satgenpy_analysis
  python3 perform_full_analysis.py \
    "$CONSTELLATION" "$DURATION_S" "$STEP_MS" \
    "$ISL_SELECTION" "$GS_SELECTION" "$algo" "$THREADS"
  cd ..

  echo "[3/3] Run ns-3 simulation"
  cd ns3_experiments/traffic_matrix_load
  python3 step_2_run.py 0 "$DEBIT_ISL" "$DURATION_S" "$algo"
  cd ../..
done

echo ""
echo "Done. Generate contribution outputs with:"
echo "  python3 $REPO_ROOT/report_artifacts/frog_k/scripts/frog_k_compare.py --duration-s 120 --step-ms 10000"
echo "  python3 $REPO_ROOT/report_artifacts/frog_k/scripts/frog_k_traffic_matrix_compare.py"
echo "  python3 $REPO_ROOT/report_artifacts/frog_k/scripts/compute_paper_style_avg_throughput.py"
