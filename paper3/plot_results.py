#!/usr/bin/env python3

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _load_rows(path):
    with open(path, "r") as f:
        r = csv.DictReader(f)
        rows = []
        for row in r:
            rows.append(row)
        return rows


def _to_float(x):
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "none":
        return None
    return float(s)


def _short_label(variant):
    if variant.endswith("algorithm_free_one_only_over_isls"):
        return "k=1 (FW)"
    if variant.endswith("algorithm_free_one_only_over_isls3"):
        return "FROG k=3"
    if variant.endswith("algorithm_free_one_only_over_isls5"):
        return "FROG k=5"
    if "algorithm_direction_aware_floyd_warshall" in variant:
        # Extract beta token
        if "beta" in variant:
            beta = variant.split("beta", 1)[1]
            beta = beta.replace("0p", "0.").replace("p", ".")
            return "DA-FW beta=" + beta
        return "DA-FW"
    return variant


def plot(paper3_dir):
    paper3_dir = os.path.abspath(paper3_dir)
    res_dir = os.path.join(paper3_dir, "results")
    out_dir = os.path.join(res_dir, "plots")
    os.makedirs(out_dir, exist_ok=True)

    summary_csv = os.path.join(res_dir, "summary.csv")
    rows = _load_rows(summary_csv)

    labels = [_short_label(r["variant"]) for r in rows]
    mean_hops = [_to_float(r["mean_hop_count"]) for r in rows]
    reach = [_to_float(r["reachability_ratio"]) for r in rows]
    stability = [_to_float(r["mean_path_changes_per_pair_per_step"]) for r in rows]
    median_min_rtt = [_to_float(r["median_min_rtt_ms"]) for r in rows]
    median_max_rtt = [_to_float(r["median_max_rtt_ms"]) for r in rows]

    def _bar(values, title, ylabel, filename):
        fig = plt.figure(figsize=(10, 4), dpi=140)
        ax = fig.add_subplot(1, 1, 1)
        xs = list(range(len(labels)))
        ax.bar(xs, [v if v is not None else 0.0 for v in values])
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=20, ha="right")
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        fig.tight_layout()
        out = os.path.join(out_dir, filename)
        fig.savefig(out)
        plt.close(fig)
        print("Wrote:", out)

    _bar(mean_hops, "Mean Hop Count (Reachable Commodities Only)", "hops", "mean_hop_count.png")
    _bar(reach, "Reachability Ratio", "ratio", "reachability_ratio.png")
    _bar(stability, "Mean Path Changes Per Pair Per Step", "changes/step", "path_change_rate.png")
    _bar(median_min_rtt, "Median Min RTT (If RTT Analysis Ran)", "ms", "median_min_rtt_ms.png")
    _bar(median_max_rtt, "Median Max RTT (If RTT Analysis Ran)", "ms", "median_max_rtt_ms.png")


if __name__ == "__main__":
    plot(os.path.join(os.path.dirname(__file__)))

