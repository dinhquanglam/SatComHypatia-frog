#!/usr/bin/env python3

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "papier2/ns3_experiments/traffic_matrix_load/data"
DEFAULT_DETAIL_CSV = REPO_ROOT / "report_artifacts/frog_k/traffic_matrix/frog_k_compare_detail.csv"
DEFAULT_SUMMARY_CSV = REPO_ROOT / "report_artifacts/frog_k/traffic_matrix/frog_k_compare_summary.csv"
DEFAULT_COMPARISON_CSV = REPO_ROOT / "report_artifacts/frog_k/traffic_matrix/frog_k_compare_vs_k1.csv"

ALGO_TO_K = {
    "algorithm_free_one_only_over_isls": "k=1",
    "algorithm_free_one_only_over_isls3": "k=3",
    "algorithm_free_one_only_over_isls5": "k=5",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Reuse step_3_generate_plots.py data/*.csv outputs to build explicit "
            "FROG k-labeled comparison tables."
        )
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(DEFAULT_DATA_DIR),
        help="Directory that contains step_3 outputs (run_dirs.csv and traffic_*.csv)",
    )
    parser.add_argument(
        "--detail-csv",
        type=str,
        default=str(DEFAULT_DETAIL_CSV),
        help="Output CSV path for k-labeled per-run table",
    )
    parser.add_argument(
        "--summary-csv",
        type=str,
        default=str(DEFAULT_SUMMARY_CSV),
        help="Output CSV path for mean metrics by protocol and k",
    )
    parser.add_argument(
        "--comparison-csv",
        type=str,
        default=str(DEFAULT_COMPARISON_CSV),
        help="Output CSV path for comparison against baseline k=1",
    )
    return parser.parse_args()


def read_single_column_csv(path):
    rows = []
    with open(path, "r", newline="") as f_in:
        for row in csv.reader(f_in):
            if not row:
                continue
            rows.append(row)
    return rows


def parse_run_dir(run_dir):
    name = Path(run_dir).name
    match = re.search(r"_for_(\d+)s_with_(tcp|udp)_(algorithm_.+)$", name)
    if not match:
        return None
    duration_s = float(match.group(1))
    protocol = match.group(2)
    algorithm = match.group(3)
    k = ALGO_TO_K.get(algorithm)
    return duration_s, protocol, algorithm, k


def collect_rows_from_step3(data_dir):
    data_path = Path(data_dir)
    run_dirs_path = data_path / "run_dirs.csv"
    rate_path = data_path / "traffic_goodput_rate_vs_slowdown.csv"
    totals_path = data_path / "traffic_goodput_total_data_sent_vs_runtime.csv"

    run_rows = read_single_column_csv(run_dirs_path)
    rate_rows = read_single_column_csv(rate_path)
    total_rows = read_single_column_csv(totals_path)

    if not (len(run_rows) == len(rate_rows) == len(total_rows)):
        raise RuntimeError(
            "step_3 data files have different row counts: "
            f"run_dirs={len(run_rows)}, rate_vs_slowdown={len(rate_rows)}, totals={len(total_rows)}"
        )

    rows = []
    for idx, (run_row, rate_row, total_row) in enumerate(zip(run_rows, rate_rows, total_rows)):
        run_dir = run_row[0].strip()
        parsed = parse_run_dir(run_dir)
        if parsed is None:
            continue
        duration_s, protocol, algorithm, k = parsed
        if k is None:
            continue

        if len(rate_row) < 3 or len(total_row) < 3:
            raise RuntimeError(f"Malformed data row at index {idx}")

        proto_rate = rate_row[0].strip()
        proto_total = total_row[0].strip()
        if proto_rate != protocol or proto_total != protocol:
            raise RuntimeError(
                f"Protocol mismatch at row {idx}: run_dir={protocol}, rate={proto_rate}, totals={proto_total}"
            )

        goodput_mbps = float(rate_row[1])
        slowdown = float(rate_row[2])
        total_sent_bytes = float(total_row[1])
        total_runtime_ns = float(total_row[2])

        rows.append(
            (
                protocol,
                algorithm,
                k,
                duration_s,
                total_sent_bytes,
                total_runtime_ns,
                goodput_mbps,
                slowdown,
                run_dir,
            )
        )
    return rows


def build_summary(rows):
    grouped = defaultdict(list)
    for proto, _, k, _, _, _, goodput_mbps, slowdown, _ in rows:
        grouped[(proto, k)].append((goodput_mbps, slowdown))

    summary = []
    for (proto, k), values in sorted(grouped.items()):
        mean_goodput = sum(v[0] for v in values) / float(len(values))
        mean_slowdown = sum(v[1] for v in values) / float(len(values))
        summary.append((proto, k, len(values), mean_goodput, mean_slowdown))
    return summary


def build_comparison_vs_k1(summary_rows):
    by_proto_k = {
        (proto, k): (mean_goodput, mean_slowdown)
        for proto, k, _, mean_goodput, mean_slowdown in summary_rows
    }
    comparison = []
    for proto in sorted({row[0] for row in summary_rows}):
        baseline = by_proto_k.get((proto, "k=1"))
        if baseline is None:
            continue
        base_goodput, base_slowdown = baseline
        for candidate_k in ["k=3", "k=5"]:
            candidate = by_proto_k.get((proto, candidate_k))
            if candidate is None:
                continue
            cand_goodput, cand_slowdown = candidate
            goodput_delta_pct = ((cand_goodput - base_goodput) / base_goodput * 100.0) if base_goodput else 0.0
            slowdown_delta_pct = ((cand_slowdown - base_slowdown) / base_slowdown * 100.0) if base_slowdown else 0.0
            comparison.append(
                (
                    proto,
                    "k=1",
                    candidate_k,
                    base_goodput,
                    cand_goodput,
                    goodput_delta_pct,
                    base_slowdown,
                    cand_slowdown,
                    slowdown_delta_pct,
                )
            )
    return comparison


def write_detail_csv(path, rows):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(
            [
                "protocol",
                "algorithm",
                "k",
                "duration_s",
                "total_sent_bytes",
                "total_runtime_ns",
                "goodput_mbps",
                "slowdown",
                "run_dir",
            ]
        )
        writer.writerows(rows)


def write_summary_csv(path, summary_rows):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["protocol", "k", "num_rows", "mean_goodput_mbps", "mean_slowdown"])
        writer.writerows(summary_rows)


def write_comparison_csv(path, rows):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(
            [
                "protocol",
                "baseline_k",
                "candidate_k",
                "baseline_goodput_mbps",
                "candidate_goodput_mbps",
                "goodput_delta_pct",
                "baseline_slowdown",
                "candidate_slowdown",
                "slowdown_delta_pct",
            ]
        )
        writer.writerows(rows)


def main():
    args = parse_args()
    rows = collect_rows_from_step3(args.data_dir)

    print("protocol,algorithm,k,duration_s,total_sent_bytes,total_runtime_ns,goodput_mbps,slowdown,run_dir")
    for row in rows:
        print(
            f"{row[0]},{row[1]},{row[2]},{row[3]:.0f},{row[4]:.6f},{row[5]:.6f},"
            f"{row[6]:.6f},{row[7]:.6f},{row[8]}"
        )

    summary_rows = build_summary(rows)
    print("\nprotocol,k,num_rows,mean_goodput_mbps,mean_slowdown")
    for proto, k, num_rows, mean_goodput, mean_slowdown in summary_rows:
        print(f"{proto},{k},{num_rows},{mean_goodput:.6f},{mean_slowdown:.6f}")

    comparison_rows = build_comparison_vs_k1(summary_rows)
    print(
        "\nprotocol,baseline_k,candidate_k,baseline_goodput_mbps,candidate_goodput_mbps,"
        "goodput_delta_pct,baseline_slowdown,candidate_slowdown,slowdown_delta_pct"
    )
    for row in comparison_rows:
        print(
            f"{row[0]},{row[1]},{row[2]},{row[3]:.6f},{row[4]:.6f},{row[5]:.6f},"
            f"{row[6]:.6f},{row[7]:.6f},{row[8]:.6f}"
        )

    if args.detail_csv:
        write_detail_csv(args.detail_csv, rows)
        print(f"\nWrote detail CSV: {args.detail_csv}")
    if args.summary_csv:
        write_summary_csv(args.summary_csv, summary_rows)
        print(f"Wrote summary CSV: {args.summary_csv}")
    if args.comparison_csv:
        write_comparison_csv(args.comparison_csv, comparison_rows)
        print(f"Wrote comparison CSV: {args.comparison_csv}")


if __name__ == "__main__":
    main()
