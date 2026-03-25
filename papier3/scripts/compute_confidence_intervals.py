#!/usr/bin/env python3

import argparse
import ast
import csv
import json
import math
from pathlib import Path

import numpy as np

import sys


SPEED_OF_LIGHT_M_PER_S = 299792458.0
Z_95 = 1.959963984540054


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute 95% confidence intervals for papier3 routing metrics"
    )
    parser.add_argument(
        "--config",
        default="papier3/config/experiment_config.json",
        help="Path to experiment config JSON"
    )
    parser.add_argument(
        "--output-csv",
        default="papier3/results/summary_metrics_ci.csv",
        help="Output CSV path"
    )
    parser.add_argument(
        "--output-json",
        default="papier3/results/summary_metrics_ci.json",
        help="Output JSON path"
    )
    return parser.parse_args()


def parse_description(description_path):
    values = {}
    with open(description_path, "r") as f_in:
        for line in f_in:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = float(value.strip())
    return values


def parse_commodities(commodities_file):
    with open(commodities_file, "r") as f_in:
        data = f_in.read().strip()
    parsed = ast.literal_eval(data)
    return [(int(src), int(dst), float(load)) for src, dst, load in parsed]


def get_constellation_base_name(main_script):
    stem = Path(main_script).stem
    if stem.startswith("main_"):
        return stem[len("main_"):]
    return stem


def get_constellation_name(
        constellation_base_name,
        isls_selection,
        gs_selection,
        dynamic_state_algorithm
):
    return "{}_{}_{}_{}".format(
        constellation_base_name,
        isls_selection,
        gs_selection,
        dynamic_state_algorithm
    )


def load_fstate_updates(fstate_file, fstate):
    updates = 0
    with open(fstate_file, "r") as f_in:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            current = int(parts[0])
            destination = int(parts[1])
            next_hop = int(parts[2])
            fstate[(current, destination)] = next_hop
            updates += 1
    return updates


def get_path(src, dst, forward_state):
    if (src, dst) not in forward_state:
        return None
    if forward_state[(src, dst)] == -1:
        return None
    path = [src]
    curr = src
    while curr != dst:
        if (curr, dst) not in forward_state:
            return None
        curr = forward_state[(curr, dst)]
        if curr == -1:
            return None
        path.append(curr)
        if len(path) > 10000:
            return None
    return path


def mean_ci_95(values):
    n = len(values)
    if n == 0:
        return None, None, None, n
    arr = np.array(values, dtype=float)
    mean = float(np.mean(arr))
    if n == 1:
        return mean, mean, mean, n
    std = float(np.std(arr, ddof=1))
    half_width = Z_95 * std / math.sqrt(n)
    return mean, mean - half_width, mean + half_width, n


def wilson_ci_95(successes, total):
    if total <= 0:
        return None, None, None, total
    p_hat = successes / float(total)
    z2 = Z_95 * Z_95
    denom = 1.0 + z2 / total
    center = (p_hat + z2 / (2.0 * total)) / denom
    margin = (Z_95 * math.sqrt((p_hat * (1.0 - p_hat) / total) + (z2 / (4.0 * total * total)))) / denom
    return p_hat, center - margin, center + margin, total


def analyze_algorithm(
        satgen_modules,
        network_dir,
        duration_s,
        time_step_ms,
        commodities
):
    read_ground_stations_extended = satgen_modules["read_ground_stations_extended"]
    read_tles = satgen_modules["read_tles"]
    read_isls = satgen_modules["read_isls"]
    compute_path_length_without_graph = satgen_modules["compute_path_length_without_graph"]

    description = parse_description(network_dir / "description.txt")
    max_gsl_length_m = description["max_gsl_length_m"]
    max_isl_length_m = description["max_isl_length_m"]

    ground_stations = read_ground_stations_extended(str(network_dir / "ground_stations.txt"))
    tles = read_tles(str(network_dir / "tles.txt"))
    satellites = tles["satellites"]
    epoch = tles["epoch"]
    list_isls = read_isls(str(network_dir / "isls.txt"), len(satellites))

    dynamic_state_dir = network_dir / "dynamic_state_{}ms_for_{}s".format(time_step_ms, duration_s)
    time_step_ns = time_step_ms * 1000 * 1000
    simulation_end_ns = duration_s * 1000 * 1000 * 1000
    timesteps = list(range(0, simulation_end_ns, time_step_ns))

    fstate = {}
    previous_paths = {}
    route_changes = 0
    total_updates = 0
    total_reachable = 0
    total_samples = 0
    rtt_values_ms = []
    hop_values = []

    for t_index, t_ns in enumerate(timesteps):
        fstate_file = dynamic_state_dir / "fstate_{}.txt".format(t_ns)
        if not fstate_file.is_file():
            raise RuntimeError("Missing forwarding-state file: {}".format(fstate_file))
        total_updates += load_fstate_updates(fstate_file, fstate)

        for src_node_id, dst_node_id, _ in commodities:
            total_samples += 1
            path = get_path(src_node_id, dst_node_id, fstate)
            path_signature = None if path is None else tuple(path)
            pair_key = (src_node_id, dst_node_id)

            if t_index > 0 and pair_key in previous_paths and previous_paths[pair_key] != path_signature:
                route_changes += 1
            previous_paths[pair_key] = path_signature

            if path is None:
                continue
            total_reachable += 1
            hop_values.append(len(path) - 1)
            path_length_m = compute_path_length_without_graph(
                path,
                epoch,
                t_ns,
                satellites,
                ground_stations,
                list_isls,
                max_gsl_length_m,
                max_isl_length_m
            )
            rtt_values_ms.append((2.0 * path_length_m / SPEED_OF_LIGHT_M_PER_S) * 1e3)

    rtt_mean, rtt_lo, rtt_hi, rtt_n = mean_ci_95(rtt_values_ms)
    hop_mean, hop_lo, hop_hi, hop_n = mean_ci_95(hop_values)
    pdr_mean, pdr_lo, pdr_hi, pdr_n = wilson_ci_95(total_reachable, total_samples)

    change_denominator = max((len(timesteps) - 1) * len(commodities), 1)
    route_change_rate, route_change_lo, route_change_hi, _ = wilson_ci_95(route_changes, change_denominator)

    return {
        "samples_total": total_samples,
        "samples_reachable": total_reachable,
        "pdr_proxy": pdr_mean,
        "pdr_ci95_lower": pdr_lo,
        "pdr_ci95_upper": pdr_hi,
        "pdr_n": pdr_n,
        "avg_rtt_ms": rtt_mean,
        "rtt_ci95_lower_ms": rtt_lo,
        "rtt_ci95_upper_ms": rtt_hi,
        "rtt_n": rtt_n,
        "avg_hop_count": hop_mean,
        "hop_ci95_lower": hop_lo,
        "hop_ci95_upper": hop_hi,
        "hop_n": hop_n,
        "route_change_rate": route_change_rate,
        "route_change_ci95_lower": route_change_lo,
        "route_change_ci95_upper": route_change_hi,
        "route_change_events": route_changes,
        "route_change_opportunities": change_denominator,
        "avg_fstate_updates_per_step": total_updates / float(len(timesteps)) if timesteps else None,
        "num_time_steps": len(timesteps)
    }


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    config_path = (repo_root / args.config).resolve()
    with open(config_path, "r") as f_in:
        cfg = json.load(f_in)

    sys.path.insert(0, str((repo_root / "satgenpy").resolve()))
    from satgen.ground_stations import read_ground_stations_extended
    from satgen.tles import read_tles
    from satgen.isls import read_isls
    from satgen.post_analysis.graph_tools import compute_path_length_without_graph

    satgen_modules = {
        "read_ground_stations_extended": read_ground_stations_extended,
        "read_tles": read_tles,
        "read_isls": read_isls,
        "compute_path_length_without_graph": compute_path_length_without_graph
    }

    constellation_base_name = get_constellation_base_name(cfg["main_script"])
    gen_data_dir = (repo_root / cfg["satellite_networks_state_dir"] / "gen_data").resolve()
    commodities = parse_commodities((repo_root / cfg["commodities_file"]).resolve())

    rows = []
    for algo_entry in cfg["algorithms"]:
        label = algo_entry["label"]
        algorithm = algo_entry["dynamic_state_algorithm"]
        constellation_name = get_constellation_name(
            constellation_base_name,
            cfg["isls_selection"],
            cfg["ground_station_selection"],
            algorithm
        )
        network_dir = gen_data_dir / constellation_name
        if not network_dir.is_dir():
            raise RuntimeError("Missing network directory: {}".format(network_dir))

        computed = analyze_algorithm(
            satgen_modules,
            network_dir,
            cfg["duration_s"],
            cfg["time_step_ms"],
            commodities
        )

        row = {
            "label": label,
            "algorithm": algorithm,
            **computed
        }
        rows.append(row)

    output_csv_path = (repo_root / args.output_csv).resolve()
    output_json_path = (repo_root / args.output_json).resolve()
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "label",
        "algorithm",
        "avg_rtt_ms",
        "rtt_ci95_lower_ms",
        "rtt_ci95_upper_ms",
        "rtt_n",
        "avg_hop_count",
        "hop_ci95_lower",
        "hop_ci95_upper",
        "hop_n",
        "pdr_proxy",
        "pdr_ci95_lower",
        "pdr_ci95_upper",
        "pdr_n",
        "route_change_rate",
        "route_change_ci95_lower",
        "route_change_ci95_upper",
        "route_change_events",
        "route_change_opportunities",
        "avg_fstate_updates_per_step",
        "samples_total",
        "samples_reachable",
        "num_time_steps"
    ]
    with open(output_csv_path, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with open(output_json_path, "w") as f_out:
        json.dump(rows, f_out, indent=2)

    print("Wrote {}".format(output_csv_path))
    print("Wrote {}".format(output_json_path))


if __name__ == "__main__":
    main()
