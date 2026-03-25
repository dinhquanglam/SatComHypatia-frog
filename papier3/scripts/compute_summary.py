#!/usr/bin/env python3

import argparse
import ast
import csv
import json
from pathlib import Path

import numpy as np

import sys


SPEED_OF_LIGHT_M_PER_S = 299792458.0


def parse_args():
    parser = argparse.ArgumentParser(description="Compute papier3 summary metrics")
    parser.add_argument(
        "--config",
        default="papier3/config/experiment_config.json",
        help="Path to experiment config JSON"
    )
    return parser.parse_args()


def get_constellation_base_name(main_script):
    stem = Path(main_script).stem
    if stem.startswith("main_"):
        return stem[len("main_"):]
    return stem


def get_constellation_name(constellation_base_name, isls_selection, gs_selection, dynamic_state_algorithm):
    return "{}_{}_{}_{}".format(
        constellation_base_name,
        isls_selection,
        gs_selection,
        dynamic_state_algorithm
    )


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


def parse_beta(dynamic_state_algorithm):
    prefix = "algorithm_direction_aware_floyd_warshall"
    if dynamic_state_algorithm == prefix:
        return 0.0
    beta_prefix = prefix + "_beta_"
    if not dynamic_state_algorithm.startswith(beta_prefix):
        return None
    token = dynamic_state_algorithm[len(beta_prefix):].replace("p", ".")
    if "." not in token and token.count("_") == 1:
        left, right = token.split("_")
        token = left + "." + right
    try:
        return float(token)
    except ValueError:
        return None


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


def parse_tcp_metrics(run_dir, duration_s):
    tcp_file = run_dir / "logs_ns3" / "tcp_flows.csv"
    if not tcp_file.is_file():
        return None, None

    delivered_bytes = 0.0
    finished_flows = 0
    total_flows = 0
    with open(tcp_file, "r") as f_in:
        reader = csv.reader(f_in)
        for row in reader:
            if len(row) < 9:
                continue
            delivered_bytes += float(row[7])
            total_flows += 1
            if row[8].strip() == "YES":
                finished_flows += 1

    if total_flows == 0:
        return None, None
    tcp_goodput_mbps = (delivered_bytes * 8.0) / (duration_s * 1e6)
    tcp_finish_ratio = finished_flows / float(total_flows)
    return tcp_goodput_mbps, tcp_finish_ratio


def parse_udp_metrics(run_dir, duration_s):
    outgoing_file = run_dir / "logs_ns3" / "udp_bursts_outgoing.csv"
    incoming_file = run_dir / "logs_ns3" / "udp_bursts_incoming.csv"
    if not outgoing_file.is_file() or not incoming_file.is_file():
        return None, None

    tx_bytes = 0.0
    rx_bytes = 0.0
    with open(outgoing_file, "r") as f_out:
        reader = csv.reader(f_out)
        for row in reader:
            if len(row) < 11:
                continue
            tx_bytes += float(row[10])
    with open(incoming_file, "r") as f_in:
        reader = csv.reader(f_in)
        for row in reader:
            if len(row) < 11:
                continue
            rx_bytes += float(row[10])

    if tx_bytes <= 0:
        return None, None
    udp_goodput_mbps = (rx_bytes * 8.0) / (duration_s * 1e6)
    udp_delivery_ratio = rx_bytes / tx_bytes
    return udp_goodput_mbps, udp_delivery_ratio


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
    return path


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

    denom_changes = max((len(timesteps) - 1) * len(commodities), 1)
    return {
        "samples_total": total_samples,
        "samples_reachable": total_reachable,
        "pdr_proxy": (total_reachable / float(total_samples)) if total_samples else None,
        "avg_rtt_ms": float(np.mean(rtt_values_ms)) if rtt_values_ms else None,
        "avg_hop_count": float(np.mean(hop_values)) if hop_values else None,
        "route_change_rate": route_changes / float(denom_changes),
        "avg_fstate_updates_per_step": total_updates / float(len(timesteps)) if timesteps else None,
        "num_time_steps": len(timesteps)
    }


def write_summary_markdown(rows, output_path):
    headers = [
        "label",
        "algorithm",
        "beta",
        "avg_rtt_ms",
        "avg_hop_count",
        "pdr_proxy",
        "route_change_rate",
        "avg_fstate_updates_per_step",
        "tcp_goodput_mbps",
        "tcp_flow_finish_ratio",
        "udp_goodput_mbps",
        "udp_delivery_ratio"
    ]
    with open(output_path, "w") as f_out:
        f_out.write("| " + " | ".join(headers) + " |\n")
        f_out.write("|" + "|".join(["---"] * len(headers)) + "|\n")
        for row in rows:
            values = []
            for key in headers:
                value = row.get(key)
                if value is None:
                    values.append("NA")
                elif isinstance(value, float):
                    values.append("{:.6f}".format(value))
                else:
                    values.append(str(value))
            f_out.write("| " + " | ".join(values) + " |\n")


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

    results_dir = (repo_root / cfg["results_dir"]).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    commodities = parse_commodities((repo_root / cfg["commodities_file"]).resolve())

    constellation_base_name = get_constellation_base_name(cfg["main_script"])
    gen_data_dir = (repo_root / cfg["satellite_networks_state_dir"] / "gen_data").resolve()
    ns3_runs_base = (repo_root / "papier2/ns3_experiments/traffic_matrix_load/runs").resolve()

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

        tcp_run_dir = ns3_runs_base / "run_loaded_tm_pairing_10_Mbps_for_{}s_with_tcp_{}".format(
            cfg["duration_s"],
            algorithm
        )
        udp_run_dir = ns3_runs_base / "run_loaded_tm_pairing_10_Mbps_for_{}s_with_udp_{}".format(
            cfg["duration_s"],
            algorithm
        )
        tcp_goodput_mbps, tcp_flow_finish_ratio = parse_tcp_metrics(tcp_run_dir, cfg["duration_s"])
        udp_goodput_mbps, udp_delivery_ratio = parse_udp_metrics(udp_run_dir, cfg["duration_s"])

        row = {
            "label": label,
            "algorithm": algorithm,
            "beta": parse_beta(algorithm),
            **computed,
            "tcp_goodput_mbps": tcp_goodput_mbps,
            "tcp_flow_finish_ratio": tcp_flow_finish_ratio,
            "udp_goodput_mbps": udp_goodput_mbps,
            "udp_delivery_ratio": udp_delivery_ratio
        }
        rows.append(row)

    csv_path = results_dir / "summary_metrics.csv"
    with open(csv_path, "w", newline="") as f_out:
        fieldnames = [
            "label",
            "algorithm",
            "beta",
            "samples_total",
            "samples_reachable",
            "pdr_proxy",
            "avg_rtt_ms",
            "avg_hop_count",
            "route_change_rate",
            "avg_fstate_updates_per_step",
            "num_time_steps",
            "tcp_goodput_mbps",
            "tcp_flow_finish_ratio",
            "udp_goodput_mbps",
            "udp_delivery_ratio"
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    markdown_path = results_dir / "summary_metrics.md"
    write_summary_markdown(rows, markdown_path)

    json_path = results_dir / "summary_metrics.json"
    with open(json_path, "w") as f_out:
        json.dump(rows, f_out, indent=2)

    print("Wrote {}".format(csv_path))
    print("Wrote {}".format(markdown_path))
    print("Wrote {}".format(json_path))


if __name__ == "__main__":
    main()
