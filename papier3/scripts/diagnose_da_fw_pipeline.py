#!/usr/bin/env python3

import argparse
import ast
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import networkx as nx
import numpy as np
from astropy import units as u

import sys


SPEED_OF_LIGHT_M_PER_S = 299792458.0
EPS_ALPHA_ZERO = 1e-6


def parse_args():
    parser = argparse.ArgumentParser(description="Pipeline diagnostics for DA-FW implementation")
    parser.add_argument(
        "--config",
        default="papier3/config/experiment_config.json",
        help="Path to experiment config JSON"
    )
    parser.add_argument(
        "--sample-pairs",
        type=int,
        default=20,
        help="Number of commodity pairs to use in path-difference table"
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


def beta_to_algorithm(beta):
    if abs(beta) < 1e-12:
        return "algorithm_direction_aware_floyd_warshall_beta_0_0"
    token = "{:.2f}".format(beta).rstrip("0").rstrip(".")
    token = token.replace(".", "_")
    return "algorithm_direction_aware_floyd_warshall_beta_{}".format(token)


def parse_commodities(path):
    with open(path, "r") as f_in:
        data = f_in.read().strip()
    parsed = ast.literal_eval(data)
    return [(int(src), int(dst), float(load)) for src, dst, load in parsed]


def parse_description(path):
    values = {}
    with open(path, "r") as f_in:
        for line in f_in:
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = float(v.strip())
    return values


def get_timesteps(duration_s, time_step_ms):
    time_step_ns = time_step_ms * 1000 * 1000
    simulation_end_ns = duration_s * 1000 * 1000 * 1000
    return list(range(0, simulation_end_ns, time_step_ns))


def load_fstate_delta_file(path, state):
    updates = 0
    with open(path, "r") as f_in:
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
            state[(current, destination)] = next_hop
            updates += 1
    return updates


def load_semantic_states(dynamic_state_dir, timesteps):
    states = {}
    updates_per_timestep = {}
    current_state = {}
    for t_ns in timesteps:
        file_path = dynamic_state_dir / "fstate_{}.txt".format(t_ns)
        if not file_path.is_file():
            raise RuntimeError("Missing forwarding-state file: {}".format(file_path))
        updates_per_timestep[t_ns] = load_fstate_delta_file(file_path, current_state)
        states[t_ns] = dict(current_state)
    return states, updates_per_timestep


def get_path_from_state(state, src, dst):
    if (src, dst) not in state:
        return None
    if state[(src, dst)] == -1:
        return None
    path = [src]
    seen = {src}
    current = src
    while current != dst:
        if (current, dst) not in state:
            return None
        next_hop = state[(current, dst)]
        if next_hop == -1:
            return None
        path.append(next_hop)
        if next_hop in seen and next_hop != dst:
            return None
        seen.add(next_hop)
        current = next_hop
    return path


def serialize_path(path):
    if path is None:
        return "UNREACHABLE"
    return "->".join(str(x) for x in path)


def build_sat_neighbor_to_if(list_isls):
    sat_neighbor_to_if = {}
    num_isls_per_sat = defaultdict(int)
    for a, b in list_isls:
        sat_neighbor_to_if[(a, b)] = num_isls_per_sat[a]
        sat_neighbor_to_if[(b, a)] = num_isls_per_sat[b]
        num_isls_per_sat[a] += 1
        num_isls_per_sat[b] += 1
    return sat_neighbor_to_if, dict(num_isls_per_sat)


def compute_timestep_contexts(
        timesteps,
        epoch,
        satellites,
        ground_stations,
        list_isls,
        max_gsl_length_m,
        da_mod,
        distance_m_between_satellites,
        distance_m_ground_station_to_satellite
):
    contexts = {}

    for t_ns in timesteps:
        time = epoch + t_ns * u.ns
        positions_now = da_mod._compute_satellite_positions_cartesian(satellites, epoch, time)
        positions_next = da_mod._compute_satellite_positions_cartesian(satellites, epoch, time + 1000000000 * u.ns)
        velocities = [positions_next[sid] - positions_now[sid] for sid in range(len(satellites))]
        speeds_mps = [float(np.linalg.norm(v)) for v in velocities]  # delta t = 1 s

        sat_w0 = {}
        sat_alpha = {}
        euclid_vs_distance = []
        for a, b in list_isls:
            w0 = distance_m_between_satellites(satellites[a], satellites[b], str(epoch), str(time))
            sat_w0[(a, b)] = w0
            sat_w0[(b, a)] = w0

            link_ab = positions_now[b] - positions_now[a]
            link_ba = positions_now[a] - positions_now[b]
            sat_alpha[(a, b)] = da_mod._compute_alignment_cosine(velocities[a], link_ab)
            sat_alpha[(b, a)] = da_mod._compute_alignment_cosine(velocities[b], link_ba)

            euclid_d = float(np.linalg.norm(positions_now[b] - positions_now[a]))
            euclid_vs_distance.append((w0, euclid_d, abs(w0 - euclid_d), abs(w0 - euclid_d) / max(w0, 1e-12)))

        gs_sat_distance = {}
        nearest_sat_by_gid = {}
        for gs in ground_stations:
            gs_node = len(satellites) + gs["gid"]
            candidates = []
            for sid in range(len(satellites)):
                d = distance_m_ground_station_to_satellite(gs, satellites[sid], str(epoch), str(time))
                if d <= max_gsl_length_m:
                    gs_sat_distance[(gs_node, sid)] = d
                    gs_sat_distance[(sid, gs_node)] = d
                    candidates.append((d, sid))
            candidates.sort()
            nearest_sat_by_gid[gs["gid"]] = candidates[0][1] if candidates else None

        contexts[t_ns] = {
            "time": time,
            "positions_now": positions_now,
            "velocities": velocities,
            "speeds_mps": speeds_mps,
            "sat_w0": sat_w0,
            "sat_alpha": sat_alpha,
            "gs_sat_distance": gs_sat_distance,
            "nearest_sat_by_gid": nearest_sat_by_gid,
            "euclid_vs_distance": euclid_vs_distance
        }

    return contexts


def path_cost_m(path, context, beta=None, sign="minus"):
    if path is None:
        return None
    total = 0.0
    sat_w0 = context["sat_w0"]
    sat_alpha = context["sat_alpha"]
    gs_sat_distance = context["gs_sat_distance"]
    for i in range(len(path) - 1):
        u = path[i]
        v = path[i + 1]
        if (u, v) in sat_w0:
            w0 = sat_w0[(u, v)]
            if beta is None:
                total += w0
            else:
                alpha = sat_alpha[(u, v)]
                if sign == "minus":
                    total += w0 * (1.0 - beta * alpha)
                elif sign == "plus":
                    total += w0 * (1.0 + beta * alpha)
                else:
                    raise RuntimeError("Unknown sign: {}".format(sign))
        elif (u, v) in gs_sat_distance:
            total += gs_sat_distance[(u, v)]
        else:
            return None
    return total


def compute_metrics_from_states(states, contexts, timesteps, commodities, beta_for_da_cost=None):
    total_samples = 0
    total_reachable = 0
    hops = []
    rtts_ms = []
    path_changes = 0
    previous_paths = {}

    for t_idx, t_ns in enumerate(timesteps):
        state = states[t_ns]
        context = contexts[t_ns]
        for src, dst, _ in commodities:
            total_samples += 1
            path = get_path_from_state(state, src, dst)
            signature = None if path is None else tuple(path)
            pair = (src, dst)
            if t_idx > 0 and pair in previous_paths and previous_paths[pair] != signature:
                path_changes += 1
            previous_paths[pair] = signature

            if path is None:
                continue
            total_reachable += 1
            hops.append(len(path) - 1)
            physical_length_m = path_cost_m(path, context, beta=None)
            if physical_length_m is not None:
                rtts_ms.append((2.0 * physical_length_m / SPEED_OF_LIGHT_M_PER_S) * 1e3)

    denom_changes = max((len(timesteps) - 1) * len(commodities), 1)
    return {
        "samples_total": total_samples,
        "samples_reachable": total_reachable,
        "reachability_ratio": total_reachable / float(total_samples) if total_samples else None,
        "avg_hop_count": float(np.mean(hops)) if hops else None,
        "avg_rtt_ms": float(np.mean(rtts_ms)) if rtts_ms else None,
        "path_changes_total": path_changes,
        "route_change_rate": path_changes / float(denom_changes)
    }


def create_da_directed_graph(context, list_isls, beta, sign):
    g = nx.DiGraph()
    for a, b in list_isls:
        w0 = context["sat_w0"][(a, b)]
        alpha_ab = context["sat_alpha"][(a, b)]
        alpha_ba = context["sat_alpha"][(b, a)]
        if sign == "minus":
            w_ab = w0 * (1.0 - beta * alpha_ab)
            w_ba = w0 * (1.0 - beta * alpha_ba)
        elif sign == "plus":
            w_ab = w0 * (1.0 + beta * alpha_ab)
            w_ba = w0 * (1.0 + beta * alpha_ba)
        else:
            raise RuntimeError("Unknown sign: {}".format(sign))
        g.add_edge(a, b, weight=max(w_ab, 1e-9))
        g.add_edge(b, a, weight=max(w_ba, 1e-9))
    return g


def simulate_sign_metrics(
        contexts,
        timesteps,
        commodities,
        ground_station_count,
        sat_count,
        list_isls,
        beta,
        sign
):
    total_samples = 0
    total_reachable = 0
    hops = []
    rtts_ms = []
    path_changes = 0
    previous_paths = {}

    for t_idx, t_ns in enumerate(timesteps):
        context = contexts[t_ns]
        g_da = create_da_directed_graph(context, list_isls, beta, sign)
        for src, dst, _ in commodities:
            src_gid = src - sat_count
            dst_gid = dst - sat_count
            src_sat = context["nearest_sat_by_gid"].get(src_gid)
            dst_sat = context["nearest_sat_by_gid"].get(dst_gid)
            total_samples += 1
            path = None
            if src_sat is not None and dst_sat is not None:
                try:
                    sat_path = nx.shortest_path(g_da, source=src_sat, target=dst_sat, weight="weight")
                    path = [src] + sat_path + [dst]
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    path = None

            signature = None if path is None else tuple(path)
            pair = (src, dst)
            if t_idx > 0 and pair in previous_paths and previous_paths[pair] != signature:
                path_changes += 1
            previous_paths[pair] = signature

            if path is None:
                continue
            total_reachable += 1
            hops.append(len(path) - 1)
            physical_m = path_cost_m(path, context, beta=None)
            if physical_m is not None:
                rtts_ms.append((2.0 * physical_m / SPEED_OF_LIGHT_M_PER_S) * 1e3)

    denom_changes = max((len(timesteps) - 1) * len(commodities), 1)
    return {
        "sign": sign,
        "beta": beta,
        "samples_total": total_samples,
        "samples_reachable": total_reachable,
        "reachability_ratio": total_reachable / float(total_samples) if total_samples else None,
        "avg_hop_count": float(np.mean(hops)) if hops else None,
        "avg_rtt_ms": float(np.mean(rtts_ms)) if rtts_ms else None,
        "path_changes_total": path_changes,
        "route_change_rate": path_changes / float(denom_changes)
    }


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    config_path = (repo_root / args.config).resolve()
    with open(config_path, "r") as f_in:
        cfg = json.load(f_in)

    diagnostics_dir = repo_root / "papier3" / "results" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str((repo_root / "satgenpy").resolve()))
    from satgen.ground_stations import read_ground_stations_extended
    from satgen.tles import read_tles
    from satgen.isls import read_isls
    from satgen.distance_tools import distance_m_between_satellites, distance_m_ground_station_to_satellite
    import satgen.dynamic_state.algorithm_direction_aware_floyd_warshall as da_mod

    constellation_base = get_constellation_base_name(cfg["main_script"])
    gen_data_dir = (repo_root / cfg["satellite_networks_state_dir"] / "gen_data").resolve()
    commodities = parse_commodities((repo_root / cfg["commodities_file"]).resolve())
    sample_pairs = commodities[:args.sample_pairs]
    timesteps = get_timesteps(cfg["duration_s"], cfg["time_step_ms"])

    baseline_algorithm = "algorithm_free_one_only_over_isls"
    da_algorithms = {
        0.0: "algorithm_direction_aware_floyd_warshall_beta_0_0",
        0.01: "algorithm_direction_aware_floyd_warshall_beta_0_01",
        0.02: "algorithm_direction_aware_floyd_warshall_beta_0_02",
        0.05: "algorithm_direction_aware_floyd_warshall_beta_0_05",
        0.1: "algorithm_direction_aware_floyd_warshall_beta_0_1",
        0.2: "algorithm_direction_aware_floyd_warshall_beta_0_2",
        0.3: "algorithm_direction_aware_floyd_warshall_beta_0_3"
    }
    frog_algorithms = {
        "frog_k3": "algorithm_free_one_only_over_isls3",
        "frog_k5": "algorithm_free_one_only_over_isls5"
    }

    baseline_constellation = get_constellation_name(
        constellation_base, cfg["isls_selection"], cfg["ground_station_selection"], baseline_algorithm
    )
    baseline_dir = gen_data_dir / baseline_constellation
    if not baseline_dir.is_dir():
        raise RuntimeError("Missing baseline network dir: {}".format(baseline_dir))

    baseline_dynamic_state_dir = baseline_dir / "dynamic_state_{}ms_for_{}s".format(
        cfg["time_step_ms"], cfg["duration_s"]
    )

    description = parse_description(baseline_dir / "description.txt")
    max_gsl_length_m = description["max_gsl_length_m"]

    ground_stations = read_ground_stations_extended(str(baseline_dir / "ground_stations.txt"))
    tles = read_tles(str(baseline_dir / "tles.txt"))
    satellites = tles["satellites"]
    epoch = tles["epoch"]
    list_isls = read_isls(str(baseline_dir / "isls.txt"), len(satellites))
    sat_neighbor_to_if, num_isls_per_sat = build_sat_neighbor_to_if(list_isls)

    # 1) Build timestep contexts used by multiple diagnostics.
    contexts = compute_timestep_contexts(
        timesteps,
        epoch,
        satellites,
        ground_stations,
        list_isls,
        max_gsl_length_m,
        da_mod,
        distance_m_between_satellites,
        distance_m_ground_station_to_satellite
    )

    # 2) Load semantic states.
    all_states = {}
    all_updates = {}
    algorithm_to_dir = {
        baseline_algorithm: baseline_dynamic_state_dir,
        **{
            algo_name: gen_data_dir
            / get_constellation_name(
                constellation_base,
                cfg["isls_selection"],
                cfg["ground_station_selection"],
                algo_name
            )
            / "dynamic_state_{}ms_for_{}s".format(cfg["time_step_ms"], cfg["duration_s"])
            for algo_name in da_algorithms.values()
        },
        **{
            algo_name: gen_data_dir
            / get_constellation_name(
                constellation_base,
                cfg["isls_selection"],
                cfg["ground_station_selection"],
                algo_name
            )
            / "dynamic_state_{}ms_for_{}s".format(cfg["time_step_ms"], cfg["duration_s"])
            for algo_name in frog_algorithms.values()
        }
    }

    missing_algorithms = []
    for algo_name, dynamic_state_dir in algorithm_to_dir.items():
        if not dynamic_state_dir.is_dir():
            missing_algorithms.append(algo_name)
            continue
        states, updates = load_semantic_states(dynamic_state_dir, timesteps)
        all_states[algo_name] = states
        all_updates[algo_name] = updates

    with open(diagnostics_dir / "missing_algorithms.json", "w") as f_out:
        json.dump({"missing_algorithms": missing_algorithms}, f_out, indent=2)

    # 3) beta=0 semantic equivalence.
    beta0_algo = da_algorithms[0.0]
    if baseline_algorithm not in all_states or beta0_algo not in all_states:
        raise RuntimeError("Need baseline and DA beta=0 states for equivalence diagnostics")
    baseline_states = all_states[baseline_algorithm]
    beta0_states = all_states[beta0_algo]

    eq_rows = []
    all_equal = True
    for t_ns in timesteps:
        a = baseline_states[t_ns]
        b = beta0_states[t_ns]
        all_keys = set(a.keys()) | set(b.keys())
        diff_entries = 0
        for key in all_keys:
            if a.get(key, None) != b.get(key, None):
                diff_entries += 1
        if diff_entries != 0:
            all_equal = False
        eq_rows.append({
            "timestep_ns": t_ns,
            "num_entries_baseline": len(a),
            "num_entries_da_beta0": len(b),
            "diff_entries": diff_entries
        })

    with open(diagnostics_dir / "beta0_semantic_equivalence_per_timestep.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=["timestep_ns", "num_entries_baseline", "num_entries_da_beta0", "diff_entries"]
        )
        writer.writeheader()
        writer.writerows(eq_rows)

    sample_route_rows = []
    route_all_equal = True
    for t_ns in timesteps:
        for src, dst, _ in sample_pairs:
            p_base = get_path_from_state(baseline_states[t_ns], src, dst)
            p_da0 = get_path_from_state(beta0_states[t_ns], src, dst)
            equal = p_base == p_da0
            route_all_equal = route_all_equal and equal
            sample_route_rows.append({
                "timestep_ns": t_ns,
                "src": src,
                "dst": dst,
                "baseline_path": serialize_path(p_base),
                "da_beta0_path": serialize_path(p_da0),
                "equal": equal
            })

    with open(diagnostics_dir / "beta0_sample_route_comparison.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=["timestep_ns", "src", "dst", "baseline_path", "da_beta0_path", "equal"]
        )
        writer.writeheader()
        writer.writerows(sample_route_rows)

    with open(diagnostics_dir / "beta0_equivalence_summary.json", "w") as f_out:
        json.dump(
            {
                "semantic_equivalence_all_timesteps": all_equal,
                "sample_route_equivalence": route_all_equal
            },
            f_out,
            indent=2
        )

    # 4) Alpha and multiplier distribution.
    all_alphas = []
    alpha_rows = []
    speed_values = []
    consistency_rows = []
    for t_ns in timesteps:
        context = contexts[t_ns]
        speed_values.extend(context["speeds_mps"])
        for w0, euclid, abs_err, rel_err in context["euclid_vs_distance"]:
            consistency_rows.append({
                "timestep_ns": t_ns,
                "distance_w0_m": w0,
                "euclidean_from_positions_m": euclid,
                "abs_error_m": abs_err,
                "rel_error": rel_err
            })
        for (a, b), alpha in context["sat_alpha"].items():
            all_alphas.append(alpha)
            alpha_rows.append({
                "timestep_ns": t_ns,
                "from_sat": a,
                "to_sat": b,
                "alpha": alpha
            })

    with open(diagnostics_dir / "alpha_values.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=["timestep_ns", "from_sat", "to_sat", "alpha"])
        writer.writeheader()
        writer.writerows(alpha_rows)

    alpha_hist_counts, alpha_hist_edges = np.histogram(all_alphas, bins=np.linspace(-1.0, 1.0, 41))
    alpha_hist_rows = []
    for i in range(len(alpha_hist_counts)):
        alpha_hist_rows.append({
            "bin_left": float(alpha_hist_edges[i]),
            "bin_right": float(alpha_hist_edges[i + 1]),
            "count": int(alpha_hist_counts[i]),
            "fraction": float(alpha_hist_counts[i] / max(len(all_alphas), 1))
        })
    with open(diagnostics_dir / "alpha_histogram.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=["bin_left", "bin_right", "count", "fraction"])
        writer.writeheader()
        writer.writerows(alpha_hist_rows)

    alpha_summary = {
        "count": len(all_alphas),
        "min": float(np.min(all_alphas)),
        "mean": float(np.mean(all_alphas)),
        "max": float(np.max(all_alphas)),
        "fraction_alpha_gt_0": float(np.mean(np.array(all_alphas) > EPS_ALPHA_ZERO)),
        "fraction_alpha_lt_0": float(np.mean(np.array(all_alphas) < -EPS_ALPHA_ZERO)),
        "fraction_alpha_approx_0": float(np.mean(np.abs(np.array(all_alphas)) <= EPS_ALPHA_ZERO))
    }

    multiplier_stats_rows = []
    multiplier_hist_rows = []
    for beta in [0.01, 0.02, 0.05, 0.1, 0.2, 0.3]:
        multipliers = [1.0 - beta * alpha for alpha in all_alphas]
        multiplier_stats_rows.append({
            "beta": beta,
            "min_multiplier": float(np.min(multipliers)),
            "mean_multiplier": float(np.mean(multipliers)),
            "max_multiplier": float(np.max(multipliers))
        })

        hist_counts, hist_edges = np.histogram(multipliers, bins=40)
        for i in range(len(hist_counts)):
            multiplier_hist_rows.append({
                "beta": beta,
                "bin_left": float(hist_edges[i]),
                "bin_right": float(hist_edges[i + 1]),
                "count": int(hist_counts[i]),
                "fraction": float(hist_counts[i] / max(len(multipliers), 1))
            })

    with open(diagnostics_dir / "multiplier_stats.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=["beta", "min_multiplier", "mean_multiplier", "max_multiplier"])
        writer.writeheader()
        writer.writerows(multiplier_stats_rows)

    with open(diagnostics_dir / "multiplier_histograms.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=["beta", "bin_left", "bin_right", "count", "fraction"])
        writer.writeheader()
        writer.writerows(multiplier_hist_rows)

    speed_summary = {
        "count": len(speed_values),
        "min_mps": float(np.min(speed_values)),
        "mean_mps": float(np.mean(speed_values)),
        "max_mps": float(np.max(speed_values))
    }
    with open(diagnostics_dir / "velocity_summary.json", "w") as f_out:
        json.dump(speed_summary, f_out, indent=2)

    with open(diagnostics_dir / "distance_consistency.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=["timestep_ns", "distance_w0_m", "euclidean_from_positions_m", "abs_error_m", "rel_error"]
        )
        writer.writeheader()
        writer.writerows(consistency_rows)

    consistency_arr = np.array([row["rel_error"] for row in consistency_rows], dtype=float)
    with open(diagnostics_dir / "distance_consistency_summary.json", "w") as f_out:
        json.dump(
            {
                "count": int(len(consistency_arr)),
                "rel_error_min": float(np.min(consistency_arr)),
                "rel_error_mean": float(np.mean(consistency_arr)),
                "rel_error_max": float(np.max(consistency_arr))
            },
            f_out,
            indent=2
        )

    with open(diagnostics_dir / "alpha_summary.json", "w") as f_out:
        json.dump(alpha_summary, f_out, indent=2)

    # 5) Path-difference diagnostics for DA betas.
    path_diff_rows = []
    for beta, algo_name in da_algorithms.items():
        if beta == 0.0:
            continue
        if algo_name not in all_states:
            continue
        da_states = all_states[algo_name]
        for t_ns in timesteps:
            context = contexts[t_ns]
            for src, dst, _ in sample_pairs:
                p_base = get_path_from_state(baseline_states[t_ns], src, dst)
                p_da = get_path_from_state(da_states[t_ns], src, dst)
                base_hop = None if p_base is None else len(p_base) - 1
                da_hop = None if p_da is None else len(p_da) - 1
                base_cost_baseline_m = path_cost_m(p_base, context, beta=None)
                da_cost_modified_m = path_cost_m(p_da, context, beta=beta, sign="minus")
                base_cost_modified_m = path_cost_m(p_base, context, beta=beta, sign="minus")
                da_cost_baseline_m = path_cost_m(p_da, context, beta=None)
                path_diff_rows.append({
                    "beta": beta,
                    "timestep_ns": t_ns,
                    "src": src,
                    "dst": dst,
                    "baseline_path": serialize_path(p_base),
                    "da_path": serialize_path(p_da),
                    "path_changed": p_base != p_da,
                    "baseline_hop_count": base_hop,
                    "da_hop_count": da_hop,
                    "baseline_total_cost_m": base_cost_baseline_m,
                    "da_modified_total_cost_m": da_cost_modified_m,
                    "baseline_path_da_modified_cost_m": base_cost_modified_m,
                    "da_path_baseline_cost_m": da_cost_baseline_m,
                    "baseline_physical_rtt_ms": None if base_cost_baseline_m is None else (2.0 * base_cost_baseline_m / SPEED_OF_LIGHT_M_PER_S) * 1e3,
                    "da_physical_rtt_ms": None if da_cost_baseline_m is None else (2.0 * da_cost_baseline_m / SPEED_OF_LIGHT_M_PER_S) * 1e3
                })

    with open(diagnostics_dir / "path_difference_samples.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=[
                "beta",
                "timestep_ns",
                "src",
                "dst",
                "baseline_path",
                "da_path",
                "path_changed",
                "baseline_hop_count",
                "da_hop_count",
                "baseline_total_cost_m",
                "da_modified_total_cost_m",
                "baseline_path_da_modified_cost_m",
                "da_path_baseline_cost_m",
                "baseline_physical_rtt_ms",
                "da_physical_rtt_ms"
            ]
        )
        writer.writeheader()
        writer.writerows(path_diff_rows)

    # 6) Route-stability diagnostics.
    route_stability_rows = []
    fstate_diff_rows = []

    algorithms_for_stability = [baseline_algorithm] + list(frog_algorithms.values()) + list(da_algorithms.values())
    for algo_name in algorithms_for_stability:
        if algo_name not in all_states:
            continue
        metrics = compute_metrics_from_states(
            all_states[algo_name], contexts, timesteps, commodities
        )
        avg_updates = float(np.mean(list(all_updates[algo_name].values())))
        route_stability_rows.append({
            "algorithm": algo_name,
            "avg_rtt_ms": metrics["avg_rtt_ms"],
            "avg_hop_count": metrics["avg_hop_count"],
            "reachability_ratio": metrics["reachability_ratio"],
            "path_changes_total": metrics["path_changes_total"],
            "route_change_rate": metrics["route_change_rate"],
            "avg_fstate_updates_per_step": avg_updates
        })

    for algo_name in algorithms_for_stability:
        if algo_name not in all_states or algo_name == baseline_algorithm:
            continue
        for t_ns in timesteps:
            base = baseline_states[t_ns]
            other = all_states[algo_name][t_ns]
            all_keys = set(base.keys()) | set(other.keys())
            diff = 0
            for key in all_keys:
                if base.get(key, None) != other.get(key, None):
                    diff += 1
            fstate_diff_rows.append({
                "algorithm": algo_name,
                "timestep_ns": t_ns,
                "fstate_entry_diff_vs_baseline": diff
            })

    with open(diagnostics_dir / "route_stability_metrics.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=[
                "algorithm",
                "avg_rtt_ms",
                "avg_hop_count",
                "reachability_ratio",
                "path_changes_total",
                "route_change_rate",
                "avg_fstate_updates_per_step"
            ]
        )
        writer.writeheader()
        writer.writerows(route_stability_rows)

    with open(diagnostics_dir / "fstate_diff_vs_baseline_per_timestep.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=["algorithm", "timestep_ns", "fstate_entry_diff_vs_baseline"]
        )
        writer.writeheader()
        writer.writerows(fstate_diff_rows)

    # 7) Sign and beta sensitivity (diagnostic-only simulation + validation against actual minus-sign runs).
    sign_beta_rows = []
    for sign in ["minus", "plus"]:
        for beta in [0.01, 0.02, 0.05, 0.1, 0.2, 0.3]:
            sign_beta_rows.append(
                simulate_sign_metrics(
                    contexts,
                    timesteps,
                    commodities,
                    len(ground_stations),
                    len(satellites),
                    list_isls,
                    beta,
                    sign
                )
            )

    with open(diagnostics_dir / "sign_beta_sensitivity_simulated.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=[
                "sign",
                "beta",
                "samples_total",
                "samples_reachable",
                "reachability_ratio",
                "avg_hop_count",
                "avg_rtt_ms",
                "path_changes_total",
                "route_change_rate"
            ]
        )
        writer.writeheader()
        writer.writerows(sign_beta_rows)

    # Validate the simulated minus-sign metric model against actual DA runs (for available betas).
    validation_rows = []
    actual_by_beta = {}
    for beta, algo_name in da_algorithms.items():
        if algo_name not in all_states:
            continue
        actual_by_beta[beta] = compute_metrics_from_states(
            all_states[algo_name], contexts, timesteps, commodities
        )
    simulated_minus_by_beta = {
        row["beta"]: row for row in sign_beta_rows if row["sign"] == "minus"
    }
    for beta, actual in sorted(actual_by_beta.items()):
        if beta not in simulated_minus_by_beta:
            continue
        sim = simulated_minus_by_beta[beta]
        validation_rows.append({
            "beta": beta,
            "actual_avg_rtt_ms": actual["avg_rtt_ms"],
            "sim_avg_rtt_ms": sim["avg_rtt_ms"],
            "abs_error_avg_rtt_ms": None if (actual["avg_rtt_ms"] is None or sim["avg_rtt_ms"] is None) else abs(actual["avg_rtt_ms"] - sim["avg_rtt_ms"]),
            "actual_avg_hop_count": actual["avg_hop_count"],
            "sim_avg_hop_count": sim["avg_hop_count"],
            "abs_error_avg_hop_count": None if (actual["avg_hop_count"] is None or sim["avg_hop_count"] is None) else abs(actual["avg_hop_count"] - sim["avg_hop_count"]),
            "actual_route_change_rate": actual["route_change_rate"],
            "sim_route_change_rate": sim["route_change_rate"],
            "abs_error_route_change_rate": abs(actual["route_change_rate"] - sim["route_change_rate"])
        })

    with open(diagnostics_dir / "sign_model_validation.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=[
                "beta",
                "actual_avg_rtt_ms",
                "sim_avg_rtt_ms",
                "abs_error_avg_rtt_ms",
                "actual_avg_hop_count",
                "sim_avg_hop_count",
                "abs_error_avg_hop_count",
                "actual_route_change_rate",
                "sim_route_change_rate",
                "abs_error_route_change_rate"
            ]
        )
        writer.writeheader()
        writer.writerows(validation_rows)

    # 8) Directed-graph assumption checks.
    directed_rows = []
    expected_directed_edges = 2 * len(list_isls)
    for t_ns in timesteps:
        context = contexts[t_ns]
        g = create_da_directed_graph(context, list_isls, beta=0.3, sign="minus")
        missing_if_mapping = 0
        for u, v in g.edges():
            if (u, v) not in sat_neighbor_to_if or (v, u) not in sat_neighbor_to_if:
                missing_if_mapping += 1
        out_degrees = [g.out_degree(n) for n in g.nodes()]
        directed_rows.append({
            "timestep_ns": t_ns,
            "directed_edge_count": g.number_of_edges(),
            "expected_directed_edge_count": expected_directed_edges,
            "edge_count_match": g.number_of_edges() == expected_directed_edges,
            "is_strongly_connected": nx.is_strongly_connected(g),
            "min_out_degree": int(min(out_degrees)),
            "max_out_degree": int(max(out_degrees)),
            "missing_if_mapping_edges": missing_if_mapping
        })

    with open(diagnostics_dir / "directed_graph_checks.csv", "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=[
                "timestep_ns",
                "directed_edge_count",
                "expected_directed_edge_count",
                "edge_count_match",
                "is_strongly_connected",
                "min_out_degree",
                "max_out_degree",
                "missing_if_mapping_edges"
            ]
        )
        writer.writeheader()
        writer.writerows(directed_rows)

    # 9) Write a compact machine-readable summary.
    summary = {
        "beta0_semantic_equivalence_all_timesteps": all_equal,
        "beta0_sample_routes_equal": route_all_equal,
        "alpha_summary": alpha_summary,
        "velocity_summary": speed_summary,
        "missing_algorithms": missing_algorithms
    }
    with open(diagnostics_dir / "pipeline_diagnostic_summary.json", "w") as f_out:
        json.dump(summary, f_out, indent=2)

    print("Wrote diagnostics to {}".format(diagnostics_dir))
    print("Summary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
