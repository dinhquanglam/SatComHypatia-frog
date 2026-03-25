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

import os
import sys
import exputil


def _constellation_folder_name(params):
    # params: main_*.py duration_s timestep_ms isl_selection gs_selection algorithm num_threads
    return "_".join([params[0].lstrip("main_").rstrip(".py")] + params[3:-1])


def main():
    params = sys.argv[1:]
    if len(params) != 7:
        raise SystemExit(
            "Usage: python perform_full_analysis.py "
            "[main_constellation.py] [duration_s] [time_step_ms] [isls_*] [ground_stations_*] [algorithm_*] [num_threads]"
        )

    duration_s = int(params[1])
    update_interval_ms = int(params[2])
    constellation = _constellation_folder_name(params)

    # Layout: paper3/satgenpy_analysis/data, paper3/satellite_networks_state/gen_data/<constellation>
    output_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
    sat_net_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "satellite_networks_state", "gen_data", constellation))
    commodities_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "satellite_networks_state", "commodites.temp"))

    os.makedirs(os.path.join(output_data_dir, "command_logs"), exist_ok=True)
    local_shell = exputil.LocalShell()

    # Manual pair plotting (limit for runtime)
    manual_pairs_limit = int(os.environ.get("PAPER3_MANUAL_PAIRS_LIMIT", "1"))
    list_comms = []
    if os.path.isfile(commodities_path):
        with open(commodities_path, "r") as f:
            list_comms = eval(f.readline())

    # Core analyses (path, rtt, time-step stability)
    cmds = []
    cmds.append(
        "cd ../../satgenpy; "
        "python3 -m satgen.post_analysis.main_analyze_path "
        "../paper3/satgenpy_analysis/data ../paper3/satellite_networks_state/gen_data/%s %d %d "
        "> ../paper3/satgenpy_analysis/data/command_logs/analyze_path_%s.log 2>&1"
        % (constellation, update_interval_ms, duration_s, constellation)
    )
    cmds.append(
        "cd ../../satgenpy; "
        "python3 -m satgen.post_analysis.main_analyze_rtt "
        "../paper3/satgenpy_analysis/data ../paper3/satellite_networks_state/gen_data/%s %d %d "
        "> ../paper3/satgenpy_analysis/data/command_logs/analyze_rtt_%s.log 2>&1"
        % (constellation, update_interval_ms, duration_s, constellation)
    )
    cmds.append(
        "cd ../../satgenpy; "
        "python3 -m satgen.post_analysis.main_analyze_time_step_path "
        "../paper3/satgenpy_analysis/data ../paper3/satellite_networks_state/gen_data/%s %s %d "
        "> ../paper3/satgenpy_analysis/data/command_logs/analyze_time_step_path_%s.log 2>&1"
        % (constellation, str(update_interval_ms), duration_s, constellation)
    )

    # Optional: print routes/RTT for a small subset of pairs
    for (src, dst, _) in list_comms[:manual_pairs_limit]:
        suffix = "%s_%dto%d" % (constellation, src, dst)
        cmds.append(
            "cd ../../satgenpy; "
            "python3 -m satgen.post_analysis.main_print_routes_and_rtt "
            "../paper3/satgenpy_analysis/data ../paper3/satellite_networks_state/gen_data/%s %d %d %d %d "
            "> ../paper3/satgenpy_analysis/data/command_logs/print_routes_%s.log 2>&1"
            % (constellation, update_interval_ms, duration_s, src, dst, suffix)
        )
        cmds.append(
            "cd ../../satgenpy; "
            "python3 -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
            "../paper3/satgenpy_analysis/data ../paper3/satellite_networks_state/gen_data/%s %d %d %d %d "
            "> ../paper3/satgenpy_analysis/data/command_logs/print_graphical_routes_%s.log 2>&1"
            % (constellation, update_interval_ms, duration_s, src, dst, suffix)
        )

    for c in cmds:
        print("Running:", c)
        local_shell.perfect_exec(c, output_redirect=exputil.OutputRedirect.CONSOLE)

    print("Finished.")


if __name__ == "__main__":
    main()
