# The MIT License (MIT)
#
# Copyright (c) 2020 ETH Zurich
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
  

#### README ##############################
# Workload format:
#   constellation_file duration[s] timestep[ms] isls? ground_stations? algorithm num_threads
#
# This paper3 suite compares:
#   1) baseline shortest-path (FW) / k=1: algorithm_free_one_only_over_isls
#   2) FROG variants: k=3 and k=5: algorithm_free_one_only_over_isls3/5
#   3) Direction-aware Floyd–Warshall: algorithm_direction_aware_floyd_warshall_beta{...}
#
# Tunables (override via env):
#   CONSTELLATION_MAIN, DURATION_S, TIME_STEP_MS, ISL_SELECTION, GS_SELECTION, NUM_THREADS, DEBIT_ISL_MBPS
##########################################

CONSTELLATION_MAIN="${CONSTELLATION_MAIN:-main_telesat_1015.py}"
DURATION_S="${DURATION_S:-20}"
TIME_STEP_MS="${TIME_STEP_MS:-2000}"
ISL_SELECTION="${ISL_SELECTION:-isls_plus_grid}"
GS_SELECTION="${GS_SELECTION:-ground_stations_top_100}"
NUM_THREADS="${NUM_THREADS:-4}"
DEBIT_ISL_MBPS="${DEBIT_ISL_MBPS:-10}"

liste_arguments=(
  "${CONSTELLATION_MAIN} ${DURATION_S} ${TIME_STEP_MS} ${ISL_SELECTION} ${GS_SELECTION} algorithm_free_one_only_over_isls ${NUM_THREADS}"
  "${CONSTELLATION_MAIN} ${DURATION_S} ${TIME_STEP_MS} ${ISL_SELECTION} ${GS_SELECTION} algorithm_free_one_only_over_isls3 ${NUM_THREADS}"
  "${CONSTELLATION_MAIN} ${DURATION_S} ${TIME_STEP_MS} ${ISL_SELECTION} ${GS_SELECTION} algorithm_free_one_only_over_isls5 ${NUM_THREADS}"
  "${CONSTELLATION_MAIN} ${DURATION_S} ${TIME_STEP_MS} ${ISL_SELECTION} ${GS_SELECTION} algorithm_direction_aware_floyd_warshall_beta0p2 ${NUM_THREADS}"
  "${CONSTELLATION_MAIN} ${DURATION_S} ${TIME_STEP_MS} ${ISL_SELECTION} ${GS_SELECTION} algorithm_direction_aware_floyd_warshall_beta0p4 ${NUM_THREADS}"
  "${CONSTELLATION_MAIN} ${DURATION_S} ${TIME_STEP_MS} ${ISL_SELECTION} ${GS_SELECTION} algorithm_direction_aware_floyd_warshall_beta0p6 ${NUM_THREADS}"
)

liste_debitISL=(
  "${DEBIT_ISL_MBPS}"
  "${DEBIT_ISL_MBPS}"
  "${DEBIT_ISL_MBPS}"
  "${DEBIT_ISL_MBPS}"
  "${DEBIT_ISL_MBPS}"
  "${DEBIT_ISL_MBPS}"
)

if (( ${#liste_debitISL[@]} != ${#liste_arguments[@]} )); then
	echo liste_debitISL ${#liste_debitISL[@]} and liste_arguments ${#liste_arguments[@]} must have the same size
	exit 1
fi

start_index="${START_INDEX:-0}"
end_index="${END_INDEX:-$(( ${#liste_arguments[@]} - 1 ))}"

if (( start_index < 0 || end_index < start_index || end_index >= ${#liste_arguments[@]} )); then
	echo "Invalid START_INDEX/END_INDEX: START_INDEX=${start_index} END_INDEX=${end_index} (valid range 0..$(( ${#liste_arguments[@]} - 1 )))"
	exit 1
fi

echo "Running paper2 workloads from index ${start_index} to ${end_index}"

	for ((i=start_index; i<=end_index; ++i )) ; do
		debitISL="${liste_debitISL[$i]}"
		read -a arguments <<< "${liste_arguments[$i]}"
	
		#save debitISL in a simple place for graph generation. Used by mcnf
		echo $debitISL > satellite_networks_state/debitISL.temp
	
	### Create routing tables and generate constellation
		cd ns3_experiments || exit 1
		cd traffic_matrix_load || exit 1
		python3 step_1_generate_runs2.py $debitISL ${arguments[*]} || exit 1
		cd ../.. || exit 1

		### SATGENPY ANALYSIS
		# analysis  of path and rtt based on networkx.
		# edit variables 'satgenpy_generated_constellation', 'duration_s' 
		# and 'list_update_interval_ms' in perform_full_analysis according to `liste_arguments`
		if [ "${SKIP_ANALYSIS:-0}" != "1" ]; then
			cd satgenpy_analysis || exit 1
			python3 perform_full_analysis.py ${arguments[*]} || exit 1
			cd .. || exit 1
		fi

		# NS-3 EXPERIMENTS
		if [ "${SKIP_NS3:-0}" != "1" ]; then
			cd ns3_experiments || exit 1
			cd traffic_matrix_load || exit 1
			python3 step_2_run.py 0 $debitISL ${arguments[1]} ${arguments[5]} || exit 1
			cd ..
			cd .. || exit 1
		fi

	unset debitISL
	unset arguments
done;

if [ "${SKIP_NS3:-0}" != "1" ]; then
	# global simulation plots
	cd ns3_experiments || exit 1
	cd traffic_matrix_load || exit 1
	# python3 step_3_generate_plots.py || exit 1

	# below scripts help to analyse simulation results.
	echo " "
	echo " run logs analysis "
	python3 runs_logs4.py
	echo "final results"
	python3 runs_results.py
	cd ..
	cd .. || exit 1
fi
