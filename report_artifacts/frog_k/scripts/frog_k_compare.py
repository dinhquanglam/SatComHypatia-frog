#!/usr/bin/env python3

import argparse
import csv
import json
import random
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_BASE_DIR = REPO_ROOT / "papier2/satellite_networks_state/gen_data"
DEFAULT_OUT_DIR = REPO_ROOT / "report_artifacts/frog_k"
DEFAULT_HOP_COUNT_FILE = REPO_ROOT / "papier2/ns3_experiments/traffic_matrix_load/hop_count.txt"


def build_reciprocated_pairs(ground_station_nodes, seed):
    nodes = list(ground_station_nodes)
    if len(nodes) % 2 != 0:
        raise ValueError("Number of nodes for reciprocated pairing must be even")
    rnd = random.Random(seed)
    rnd.shuffle(nodes)
    pairs = []
    for i in range(0, len(nodes), 2):
        a = nodes[i]
        b = nodes[i + 1]
        pairs.append((a, b))
        pairs.append((b, a))
    return pairs


def read_fstate_delta(fstate_path, fstate):
    with open(fstate_path, "r") as f_in:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            spl = line.split(",")
            if len(spl) < 3:
                continue
            current = int(spl[0])
            destination = int(spl[1])
            next_hop = int(spl[2])
            fstate[(current, destination)] = next_hop


def hop_count(src, dst, fstate, max_hops):
    curr = src
    hops = 0
    visited = set()
    while curr != dst:
        key = (curr, dst)
        if key not in fstate:
            return None
        nxt = fstate[key]
        if nxt == -1:
            return None
        state = (curr, nxt)
        if state in visited:
            return None
        visited.add(state)
        curr = nxt
        hops += 1
        if hops > max_hops:
            return None
    return hops


def analyze_algorithm(dynamic_state_dir, times_ns, pairs, max_hops):
    fstate = {}
    hops_per_pair = {pair: [] for pair in pairs}
    unreachable_per_pair = {pair: 0 for pair in pairs}

    for t_ns in times_ns:
        fstate_file = dynamic_state_dir / f"fstate_{t_ns}.txt"
        if not fstate_file.exists():
            raise FileNotFoundError(f"Missing forwarding file: {fstate_file}")
        read_fstate_delta(fstate_file, fstate)

        for pair in pairs:
            src, dst = pair
            hops = hop_count(src, dst, fstate, max_hops)
            hops_per_pair[pair].append(hops)
            if hops is None:
                unreachable_per_pair[pair] += 1

    return {
        "hops_per_pair": hops_per_pair,
        "unreachable_per_pair": unreachable_per_pair,
    }


def compare_against_baseline(baseline_data, candidate_data, pairs):
    pair_rows = []
    total_valid_samples = 0
    total_baseline_hops = 0.0
    total_candidate_hops = 0.0
    improved_steps = 0
    worse_steps = 0
    equal_steps = 0
    pairs_mean_improved = 0
    pairs_any_improved = 0

    for pair in pairs:
        baseline_series = baseline_data["hops_per_pair"][pair]
        candidate_series = candidate_data["hops_per_pair"][pair]
        valid = []
        for b, c in zip(baseline_series, candidate_series):
            if b is None or c is None:
                continue
            valid.append((b, c))
            if c < b:
                improved_steps += 1
            elif c > b:
                worse_steps += 1
            else:
                equal_steps += 1

        if not valid:
            row = {
                "src": pair[0],
                "dst": pair[1],
                "valid_steps": 0,
                "baseline_mean_hops": None,
                "candidate_mean_hops": None,
                "mean_delta_hops": None,
                "mean_reduction_pct": None,
                "any_step_improved": False,
            }
            pair_rows.append(row)
            continue

        baseline_mean = sum([v[0] for v in valid]) / float(len(valid))
        candidate_mean = sum([v[1] for v in valid]) / float(len(valid))
        delta_hops = baseline_mean - candidate_mean
        reduction_pct = (delta_hops / baseline_mean) * 100.0 if baseline_mean > 0 else 0.0
        any_improved = any([c < b for b, c in valid])
        if any_improved:
            pairs_any_improved += 1
        if candidate_mean < baseline_mean:
            pairs_mean_improved += 1

        total_valid_samples += len(valid)
        total_baseline_hops += sum([v[0] for v in valid])
        total_candidate_hops += sum([v[1] for v in valid])

        row = {
            "src": pair[0],
            "dst": pair[1],
            "valid_steps": len(valid),
            "baseline_mean_hops": baseline_mean,
            "candidate_mean_hops": candidate_mean,
            "mean_delta_hops": delta_hops,
            "mean_reduction_pct": reduction_pct,
            "any_step_improved": any_improved,
        }
        pair_rows.append(row)

    overall_baseline_mean = (
        total_baseline_hops / float(total_valid_samples) if total_valid_samples else None
    )
    overall_candidate_mean = (
        total_candidate_hops / float(total_valid_samples) if total_valid_samples else None
    )
    overall_delta_hops = (
        overall_baseline_mean - overall_candidate_mean
        if overall_baseline_mean is not None and overall_candidate_mean is not None
        else None
    )
    overall_reduction_pct = (
        (overall_delta_hops / overall_baseline_mean) * 100.0
        if overall_baseline_mean not in [None, 0]
        else None
    )

    summary = {
        "pairs_count": len(pairs),
        "pairs_mean_improved": pairs_mean_improved,
        "pairs_any_improved": pairs_any_improved,
        "total_valid_samples": total_valid_samples,
        "overall_baseline_mean_hops": overall_baseline_mean,
        "overall_candidate_mean_hops": overall_candidate_mean,
        "overall_delta_hops": overall_delta_hops,
        "overall_reduction_pct": overall_reduction_pct,
        "improved_steps": improved_steps,
        "worse_steps": worse_steps,
        "equal_steps": equal_steps,
    }
    return summary, pair_rows


def write_pair_details(csv_path, pair_rows):
    with open(csv_path, "w", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow([
            "src",
            "dst",
            "valid_steps",
            "baseline_mean_hops",
            "candidate_mean_hops",
            "mean_delta_hops",
            "mean_reduction_pct",
            "any_step_improved",
        ])
        for row in pair_rows:
            writer.writerow([
                row["src"],
                row["dst"],
                row["valid_steps"],
                row["baseline_mean_hops"],
                row["candidate_mean_hops"],
                row["mean_delta_hops"],
                row["mean_reduction_pct"],
                int(row["any_step_improved"]),
            ])


def parse_hop_count_table(hop_count_file, pair_limit):
    with open(hop_count_file, "r") as f_in:
        lines = [ln.rstrip("\n") for ln in f_in]

    header_indices = [i for i, line in enumerate(lines) if line.strip().startswith("ID")]
    if not header_indices:
        raise ValueError(f"Could not find table header in: {hop_count_file}")

    def extract_rows_from(header_idx):
        rows = []
        for line in lines[header_idx + 1:]:
            s = line.strip()
            if not s:
                break
            if not s[0].isdigit():
                break
            parts = re.split(r"\s+", s)
            if len(parts) < 6:
                continue
            try:
                row = {
                    "id": int(parts[0]),
                    "isls": float(parts[1]),
                    "isls2": float(parts[2]),
                    "isls3": float(parts[3]),
                    "isls4": float(parts[4]),
                    "isls5": float(parts[5]),
                }
            except ValueError:
                continue
            rows.append(row)
        return rows

    rows = []
    for header_idx in reversed(header_indices):
        rows = extract_rows_from(header_idx)
        if rows:
            break

    if not rows:
        raise ValueError(f"No parsable hop-count rows found in: {hop_count_file}")

    if pair_limit and pair_limit > 0:
        rows = rows[:pair_limit]
    return rows


def summarize_from_hop_count_rows(rows):
    def summarize(candidate_key):
        baseline_vals = [r["isls"] for r in rows]
        candidate_vals = [r[candidate_key] for r in rows]
        shorter = sum(1 for b, c in zip(baseline_vals, candidate_vals) if c < b)
        worse = sum(1 for b, c in zip(baseline_vals, candidate_vals) if c > b)
        equal = sum(1 for b, c in zip(baseline_vals, candidate_vals) if c == b)
        baseline_mean = sum(baseline_vals) / float(len(baseline_vals))
        candidate_mean = sum(candidate_vals) / float(len(candidate_vals))
        delta_hops = baseline_mean - candidate_mean
        reduction_pct = (delta_hops / baseline_mean) * 100.0 if baseline_mean else 0.0
        return {
            "pairs_count": len(rows),
            "pairs_shorter_paths": shorter,
            "pairs_worse_paths": worse,
            "pairs_equal_paths": equal,
            "overall_baseline_mean_hops": baseline_mean,
            "overall_candidate_mean_hops": candidate_mean,
            "overall_delta_hops": delta_hops,
            "overall_reduction_pct": reduction_pct,
        }

    return {
        "k3_vs_k1": summarize("isls3"),
        "k5_vs_k1": summarize("isls5"),
    }


def write_hop_count_summary_csv(csv_path, summary):
    with open(csv_path, "w", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow([
            "comparison",
            "pairs_count",
            "pairs_shorter_paths",
            "pairs_worse_paths",
            "pairs_equal_paths",
            "overall_baseline_mean_hops",
            "overall_candidate_mean_hops",
            "overall_delta_hops",
            "overall_reduction_pct",
        ])
        for tag in ["k3_vs_k1", "k5_vs_k1"]:
            data = summary[tag]
            writer.writerow([
                tag,
                data["pairs_count"],
                data["pairs_shorter_paths"],
                data["pairs_worse_paths"],
                data["pairs_equal_paths"],
                data["overall_baseline_mean_hops"],
                data["overall_candidate_mean_hops"],
                data["overall_delta_hops"],
                data["overall_reduction_pct"],
            ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-s", type=int, default=30)
    parser.add_argument("--step-ms", type=int, default=100)
    parser.add_argument("--num-satellites", type=int, default=351)
    parser.add_argument("--num-ground-stations", type=int, default=100)
    parser.add_argument("--pair-seed", type=int, default=123456789)
    parser.add_argument(
        "--base-dir",
        type=str,
        default=str(DEFAULT_BASE_DIR),
        help="Base directory that contains the telesat_* generated folders",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=str(DEFAULT_OUT_DIR),
        help="Output directory for comparison CSV and JSON files",
    )
    parser.add_argument(
        "--hop-count-file",
        type=str,
        default=str(DEFAULT_HOP_COUNT_FILE),
        help=(
            "If provided, parse hop_count.txt and generate summary outputs from it "
            "instead of reconstructing from fstate files."
        ),
    )
    parser.add_argument(
        "--pair-limit",
        type=int,
        default=100,
        help="Number of hop_count table rows (pairs) to use when --hop-count-file is set",
    )
    args = parser.parse_args()

    base = Path(args.base_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if args.hop_count_file:
        rows = parse_hop_count_table(args.hop_count_file, args.pair_limit)
        summary_core = summarize_from_hop_count_rows(rows)
        summary = {
            "config": {
                "source": "hop_count.txt",
                "hop_count_file": str(args.hop_count_file),
                "pairs_count_used": len(rows),
                "pair_limit": args.pair_limit,
            },
            "k3_vs_k1": summary_core["k3_vs_k1"],
            "k5_vs_k1": summary_core["k5_vs_k1"],
        }
        with open(out / "frog_k_summary.json", "w") as f_out:
            json.dump(summary, f_out, indent=2)
        write_hop_count_summary_csv(out / "frog_k_summary.csv", summary_core)
        print("Wrote summary JSON:", out / "frog_k_summary.json")
        print("Wrote summary CSV:", out / "frog_k_summary.csv")
        return

    dir_k1 = base / "telesat_1015_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls" / f"dynamic_state_{args.step_ms}ms_for_{args.duration_s}s"
    dir_k3_candidates = [
        base / "telesat_1015_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls_k3" / f"dynamic_state_{args.step_ms}ms_for_{args.duration_s}s",
        base / "telesat_1015_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls3" / f"dynamic_state_{args.step_ms}ms_for_{args.duration_s}s",
    ]
    dir_k5_candidates = [
        base / "telesat_1015_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls_k5" / f"dynamic_state_{args.step_ms}ms_for_{args.duration_s}s",
        base / "telesat_1015_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls5" / f"dynamic_state_{args.step_ms}ms_for_{args.duration_s}s",
    ]

    def pick_existing(candidates, label):
        for cand in candidates:
            if cand.exists():
                return cand
        raise FileNotFoundError(
            f"No candidate {label} directory exists. Tried: {', '.join([str(x) for x in candidates])}"
        )

    dir_k3 = pick_existing(dir_k3_candidates, "k=3")
    dir_k5 = pick_existing(dir_k5_candidates, "k=5")

    times_ns = [
        t * args.step_ms * 1000 * 1000
        for t in range(int((args.duration_s * 1000) / args.step_ms))
    ]

    gs_nodes = list(range(args.num_satellites, args.num_satellites + args.num_ground_stations))
    pairs = build_reciprocated_pairs(gs_nodes, args.pair_seed)
    max_hops = args.num_satellites + args.num_ground_stations + 5

    print(f"Analyzing baseline k=1 from: {dir_k1}")
    baseline = analyze_algorithm(dir_k1, times_ns, pairs, max_hops)
    print(f"Analyzing candidate k=3 from: {dir_k3}")
    cand_k3 = analyze_algorithm(dir_k3, times_ns, pairs, max_hops)
    print(f"Analyzing candidate k=5 from: {dir_k5}")
    cand_k5 = analyze_algorithm(dir_k5, times_ns, pairs, max_hops)

    summary_k3, pairs_k3 = compare_against_baseline(baseline, cand_k3, pairs)
    summary_k5, pairs_k5 = compare_against_baseline(baseline, cand_k5, pairs)

    summary = {
        "config": {
            "duration_s": args.duration_s,
            "step_ms": args.step_ms,
            "num_satellites": args.num_satellites,
            "num_ground_stations": args.num_ground_stations,
            "pair_seed": args.pair_seed,
            "pairs_count": len(pairs),
        },
        "k3_vs_k1": summary_k3,
        "k5_vs_k1": summary_k5,
    }

    with open(out / "frog_k_summary.json", "w") as f_out:
        json.dump(summary, f_out, indent=2)
    write_pair_details(out / "pair_details_k3_vs_k1.csv", pairs_k3)
    write_pair_details(out / "pair_details_k5_vs_k1.csv", pairs_k5)

    with open(out / "frog_k_summary.csv", "w", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow([
            "comparison",
            "pairs_count",
            "pairs_mean_improved",
            "pairs_any_improved",
            "overall_baseline_mean_hops",
            "overall_candidate_mean_hops",
            "overall_delta_hops",
            "overall_reduction_pct",
            "improved_steps",
            "worse_steps",
            "equal_steps",
        ])
        for tag, data in [("k3_vs_k1", summary_k3), ("k5_vs_k1", summary_k5)]:
            writer.writerow([
                tag,
                data["pairs_count"],
                data["pairs_mean_improved"],
                data["pairs_any_improved"],
                data["overall_baseline_mean_hops"],
                data["overall_candidate_mean_hops"],
                data["overall_delta_hops"],
                data["overall_reduction_pct"],
                data["improved_steps"],
                data["worse_steps"],
                data["equal_steps"],
            ])

    print("Wrote summary JSON:", out / "frog_k_summary.json")
    print("Wrote summary CSV:", out / "frog_k_summary.csv")
    print("Wrote pair details:", out / "pair_details_k3_vs_k1.csv")
    print("Wrote pair details:", out / "pair_details_k5_vs_k1.csv")


if __name__ == "__main__":
    main()
