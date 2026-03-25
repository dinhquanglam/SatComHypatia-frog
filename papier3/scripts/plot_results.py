#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Plot papier3 summary metrics")
    parser.add_argument(
        "--config",
        default="papier3/config/experiment_config.json",
        help="Path to experiment config JSON"
    )
    return parser.parse_args()


def to_float(value):
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_rows(summary_csv_path):
    rows = []
    with open(summary_csv_path, "r") as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            rows.append({
                **row,
                "beta": to_float(row.get("beta")),
                "avg_rtt_ms": to_float(row.get("avg_rtt_ms")),
                "avg_hop_count": to_float(row.get("avg_hop_count")),
                "pdr_proxy": to_float(row.get("pdr_proxy")),
                "route_change_rate": to_float(row.get("route_change_rate")),
                "avg_fstate_updates_per_step": to_float(row.get("avg_fstate_updates_per_step")),
                "tcp_goodput_mbps": to_float(row.get("tcp_goodput_mbps")),
                "udp_goodput_mbps": to_float(row.get("udp_goodput_mbps")),
                "udp_delivery_ratio": to_float(row.get("udp_delivery_ratio"))
            })
    return rows


def save_bar_plot(rows, metric_key, title, ylabel, output_dir):
    labels = [row["label"] for row in rows]
    values = [row[metric_key] if row[metric_key] is not None else np.nan for row in rows]

    plt.figure(figsize=(12, 5))
    plt.bar(labels, values)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    png_path = output_dir / "{}.png".format(metric_key)
    pdf_path = output_dir / "{}.pdf".format(metric_key)
    plt.savefig(png_path, dpi=200)
    plt.savefig(pdf_path)
    plt.close()
    return str(png_path), str(pdf_path)


def save_da_line_plot(rows, metric_key, title, ylabel, output_dir):
    da_rows = [row for row in rows if row["beta"] is not None and row[metric_key] is not None]
    if not da_rows:
        return None, None
    da_rows = sorted(da_rows, key=lambda x: x["beta"])
    betas = [row["beta"] for row in da_rows]
    values = [row[metric_key] for row in da_rows]

    plt.figure(figsize=(8, 4))
    plt.plot(betas, values, marker="o")
    plt.title(title)
    plt.xlabel("beta")
    plt.ylabel(ylabel)
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    png_path = output_dir / "da_{}.png".format(metric_key)
    pdf_path = output_dir / "da_{}.pdf".format(metric_key)
    plt.savefig(png_path, dpi=200)
    plt.savefig(pdf_path)
    plt.close()
    return str(png_path), str(pdf_path)


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    config_path = (repo_root / args.config).resolve()
    with open(config_path, "r") as f_in:
        cfg = json.load(f_in)

    results_dir = (repo_root / cfg["results_dir"]).resolve()
    summary_csv_path = results_dir / "summary_metrics.csv"
    if not summary_csv_path.is_file():
        raise RuntimeError("Missing summary CSV: {}".format(summary_csv_path))

    plots_dir = results_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(summary_csv_path)
    outputs = []
    outputs.extend(save_bar_plot(rows, "avg_rtt_ms", "Average RTT Comparison", "RTT (ms)", plots_dir))
    outputs.extend(save_bar_plot(rows, "avg_hop_count", "Average Hop Count Comparison", "Hop count", plots_dir))
    outputs.extend(save_bar_plot(rows, "pdr_proxy", "Reachability (PDR Proxy) Comparison", "Reachability ratio", plots_dir))
    outputs.extend(save_bar_plot(rows, "route_change_rate", "Route Change Rate Comparison", "Path change rate", plots_dir))
    outputs.extend(save_bar_plot(rows, "avg_fstate_updates_per_step", "Forwarding-State Updates per Step", "Updates / step", plots_dir))

    da_outputs = []
    for metric_key, title, ylabel in [
        ("avg_rtt_ms", "DA-FW: RTT vs beta", "RTT (ms)"),
        ("avg_hop_count", "DA-FW: Hop Count vs beta", "Hop count"),
        ("pdr_proxy", "DA-FW: Reachability vs beta", "Reachability ratio"),
        ("route_change_rate", "DA-FW: Route Change Rate vs beta", "Path change rate")
    ]:
        png, pdf = save_da_line_plot(rows, metric_key, title, ylabel, plots_dir)
        if png is not None:
            da_outputs.append(png)
            da_outputs.append(pdf)

    print("Generated plot files:")
    for output in outputs:
        if output:
            print(" - {}".format(output))
    for output in da_outputs:
        if output:
            print(" - {}".format(output))


if __name__ == "__main__":
    main()
