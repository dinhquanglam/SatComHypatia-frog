#!/usr/bin/env python3

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_RUNS_DIR = REPO_ROOT / "papier2/ns3_experiments/traffic_matrix_load/runs"
DEFAULT_OUT_DIR = REPO_ROOT / "report_artifacts/frog_k/tcp_performance"

ALGORITHMS = [
    ("algorithm_free_one_only_over_isls", "k=1"),
    ("algorithm_free_one_only_over_isls3", "k=3"),
    ("algorithm_free_one_only_over_isls5", "k=5"),
]

COLORS = {
    "k=1": "#1f77b4",
    "k=3": "#2ca02c",
    "k=5": "#d62728",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate paper-style TCP cwnd/RTT/progress|rate plots for FROG k=1,3,5."
    )
    parser.add_argument("--runs-dir", type=str, default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--duration-s", type=int, default=120)
    parser.add_argument("--flow-ids", type=str, default="68", help="Comma-separated TCP flow ids (e.g., 68,91)")
    parser.add_argument(
        "--bottom-metric",
        choices=["progress", "rate"],
        default="rate",
        help="Bottom subplot metric. 'progress' matches original runs_logs4.py behavior.",
    )
    parser.add_argument(
        "--bin-s",
        type=float,
        default=0.25,
        help="Smoothing bin size in seconds for plotting clarity.",
    )
    return parser.parse_args()


def read_series_samples(csv_path):
    samples = []
    with open(csv_path, "r", newline="") as f_in:
        reader = csv.reader(f_in)
        for row in reader:
            if len(row) < 3:
                continue
            t_s = int(row[1]) / 1e9
            value = float(row[2])
            samples.append((t_s, value))
    return samples


def sort_and_dedup(samples):
    if not samples:
        return [], []
    samples = sorted(samples, key=lambda x: x[0])
    times = []
    values = []
    i = 0
    n = len(samples)
    while i < n:
        t = samples[i][0]
        j = i
        vals = []
        while j < n and samples[j][0] == t:
            vals.append(samples[j][1])
            j += 1
        times.append(t)
        values.append(sum(vals) / len(vals))
        i = j
    return times, values


def monotonic_envelope(values):
    out = []
    current = -math.inf
    for v in values:
        if v > current:
            current = v
        out.append(current)
    return out


def bin_average(times, values, bin_s):
    if not times:
        return [], []
    if bin_s <= 0:
        return times, values

    binned = {}
    for t, v in zip(times, values):
        b = int(t / bin_s)
        if b not in binned:
            binned[b] = [0.0, 0]
        binned[b][0] += v
        binned[b][1] += 1

    out_t = []
    out_v = []
    for b in sorted(binned):
        s, c = binned[b]
        out_t.append((b + 0.5) * bin_s)
        out_v.append(s / c)
    return out_t, out_v


def to_rate_mbps(times, progress_bytes):
    if len(times) < 2:
        return times, [0.0 for _ in times]

    out_t = [times[0]]
    out_r = [0.0]
    for i in range(1, len(times)):
        dt = times[i] - times[i - 1]
        if dt <= 0:
            continue
        dbytes = progress_bytes[i] - progress_bytes[i - 1]
        if dbytes < 0:
            dbytes = 0
        rate_mbps = (dbytes * 8.0) / (dt * 1e6)
        out_t.append(times[i])
        out_r.append(rate_mbps)
    return out_t, out_r


def build_run_dir(runs_dir, duration_s, algorithm):
    return Path(runs_dir) / f"run_loaded_tm_pairing_10_Mbps_for_{duration_s}s_with_tcp_{algorithm}"


def load_flow_data(run_dir, flow_id, bin_s):
    logs = run_dir / "logs_ns3"
    cwnd = logs / f"tcp_flow_{flow_id}_cwnd.csv"
    rtt = logs / f"tcp_flow_{flow_id}_rtt.csv"
    progress = logs / f"tcp_flow_{flow_id}_progress.csv"

    if not (cwnd.exists() and rtt.exists() and progress.exists()):
        return None

    t_cwnd, cwnd_bytes = sort_and_dedup(read_series_samples(cwnd))
    t_rtt, rtt_ns = sort_and_dedup(read_series_samples(rtt))
    t_prog, prog_bytes = sort_and_dedup(read_series_samples(progress))

    prog_bytes = monotonic_envelope(prog_bytes)

    t_cwnd, cwnd_bytes = bin_average(t_cwnd, cwnd_bytes, bin_s)
    t_rtt, rtt_ns = bin_average(t_rtt, rtt_ns, bin_s)
    t_prog, prog_bytes = bin_average(t_prog, prog_bytes, bin_s)

    return {
        "t_cwnd": t_cwnd,
        "cwnd_bytes": cwnd_bytes,
        "t_rtt": t_rtt,
        "rtt_ms": [x / 1e6 for x in rtt_ns],
        "t_prog": t_prog,
        "progress_bytes": prog_bytes,
    }


def plot_flow(flow_id, output_dir, runs_dir, duration_s, bottom_metric, bin_s):
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=False)
    any_data = False

    for algorithm, k_label in ALGORITHMS:
        run_dir = build_run_dir(runs_dir, duration_s, algorithm)
        data = load_flow_data(run_dir, flow_id, bin_s)
        if data is None:
            print(f"WARN missing logs for flow {flow_id} in {run_dir}")
            continue

        any_data = True
        color = COLORS.get(k_label)

        axes[0].plot(data["t_cwnd"], data["cwnd_bytes"], label=k_label, color=color)
        axes[1].plot(data["t_rtt"], data["rtt_ms"], label=k_label, color=color)

        if bottom_metric == "progress":
            axes[2].plot(data["t_prog"], data["progress_bytes"], label=k_label, color=color)
        else:
            t_rate, rate_mbps = to_rate_mbps(data["t_prog"], data["progress_bytes"])
            t_rate, rate_mbps = bin_average(t_rate, rate_mbps, bin_s)
            axes[2].plot(t_rate, rate_mbps, label=k_label, color=color)

    if not any_data:
        print(f"WARN no available data for flow {flow_id}; skipping figure")
        plt.close(fig)
        return None

    axes[0].set_title(f"TCP flow {flow_id}: congestion window")
    axes[0].set_xlabel("Simulation time (s)")
    axes[0].set_ylabel("cwnd (bytes)")
    axes[0].legend(loc="upper left")

    axes[1].set_title(f"TCP flow {flow_id}: RTT")
    axes[1].set_xlabel("Simulation time (s)")
    axes[1].set_ylabel("RTT (ms)")
    axes[1].legend(loc="upper left")

    if bottom_metric == "progress":
        axes[2].set_title(f"TCP flow {flow_id}: transmitted data progress")
        axes[2].set_ylabel("Progress (bytes)")
    else:
        axes[2].set_title(f"TCP flow {flow_id}: instantaneous data rate")
        axes[2].set_ylabel("Rate (Mbit/s)")
    axes[2].set_xlabel("Simulation time (s)")
    axes[2].legend(loc="upper left")

    fig.tight_layout()

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / f"flow_{flow_id}_{bottom_metric}"
    png_path = stem.with_suffix(".png")
    pdf_path = stem.with_suffix(".pdf")
    fig.savefig(png_path, dpi=180)
    fig.savefig(pdf_path)
    plt.close(fig)
    return png_path, pdf_path


def main():
    args = parse_args()
    runs_dir = Path(args.runs_dir)
    output_dir = Path(args.output_dir)

    flow_ids = [f.strip() for f in args.flow_ids.split(",") if f.strip()]
    if not flow_ids:
        raise ValueError("No flow id provided")

    print("Generating TCP performance figures for:")
    print(f"  runs_dir={runs_dir}")
    print(f"  output_dir={output_dir}")
    print(f"  flow_ids={flow_ids}")
    print(f"  bottom_metric={args.bottom_metric}")
    print(f"  bin_s={args.bin_s}")

    for flow_id in flow_ids:
        result = plot_flow(flow_id, output_dir, runs_dir, args.duration_s, args.bottom_metric, args.bin_s)
        if result is None:
            continue
        png_path, pdf_path = result
        print(f"Wrote: {png_path}")
        print(f"Wrote: {pdf_path}")


if __name__ == "__main__":
    main()
