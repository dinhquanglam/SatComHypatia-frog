#!/usr/bin/env python3

import csv
import glob
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Variant:
    name: str
    constellation_dir: str
    duration_s: int
    update_interval_ms: int


def _read_commodities(commodities_path: str) -> List[Tuple[int, int, float]]:
    with open(commodities_path, "r") as f:
        return list(eval(f.readline()))


def _load_fstate_file(path: str) -> Dict[Tuple[int, int], int]:
    """
    Parse fstate_<t>.txt which contains delta updates (not necessarily full table).
    Caller is expected to keep a persistent map and update it.
    """
    updates = {}
    with open(path, "r") as f:
        for line in f:
            spl = line.strip().split(",")
            if len(spl) < 3:
                continue
            current = int(spl[0])
            destination = int(spl[1])
            next_hop = int(spl[2])
            updates[(current, destination)] = next_hop
    return updates


def _get_path(src: int, dst: int, fstate_next: Dict[Tuple[int, int], int], max_hops: int = 10000):
    """
    Build a path by following next-hop pointers (as in satgen post_analysis).
    Returns list of node ids including src and dst, or None if unreachable/loop.
    """
    path = [src]
    cur = src
    seen = set([src])
    for _ in range(max_hops):
        if cur == dst:
            return path
        nh = fstate_next.get((cur, dst))
        if nh is None or nh < 0:
            return None
        if nh in seen:
            return None
        path.append(nh)
        seen.add(nh)
        cur = nh
    return None


def _median_from_ecdf(ecdf_path: str):
    """
    ECDF files are (x,y) lines. Return the smallest x with y>=0.5.
    """
    if not os.path.isfile(ecdf_path):
        return None
    xs = []
    ys = []
    with open(ecdf_path, "r") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            x, y = s.split(",")
            xs.append(float(x))
            ys.append(float(y))
    for x, y in zip(xs, ys):
        if y >= 0.5:
            return x
    return xs[-1] if xs else None


def _variant_from_satnet_dir(satnet_dir: str) -> Variant:
    # satnet_dir: paper3/satellite_networks_state/gen_data/<constellation_name>
    name = os.path.basename(satnet_dir)
    # Parse duration/update interval from existing dynamic_state_* folder names.
    dyn_dirs = [p for p in glob.glob(os.path.join(satnet_dir, "dynamic_state_*ms_for_*s")) if os.path.isdir(p)]
    if not dyn_dirs:
        raise RuntimeError(f"No dynamic_state_* folder found in {satnet_dir}")

    # Prefer an explicitly requested run config if provided.
    want_dur = os.environ.get("PAPER3_DURATION_S")
    want_ms = os.environ.get("PAPER3_UPDATE_INTERVAL_MS")
    if want_dur and want_ms:
        wanted = os.path.join(satnet_dir, f"dynamic_state_{int(want_ms)}ms_for_{int(want_dur)}s")
        if os.path.isdir(wanted):
            dd = os.path.basename(wanted)
        else:
            # Fallback: choose the most recently modified folder.
            dd = os.path.basename(max(dyn_dirs, key=lambda p: os.path.getmtime(p)))
    else:
        # Default behavior: use most recently modified folder.
        dd = os.path.basename(max(dyn_dirs, key=lambda p: os.path.getmtime(p)))
    # dynamic_state_2000ms_for_20s
    parts = dd.split("_")
    update_interval_ms = int(parts[2].removesuffix("ms"))
    duration_s = int(parts[4].removesuffix("s"))
    return Variant(name=name, constellation_dir=satnet_dir, duration_s=duration_s, update_interval_ms=update_interval_ms)


def summarize(paper3_dir: str):
    paper3_dir = os.path.abspath(paper3_dir)
    sat_state_dir = os.path.join(paper3_dir, "satellite_networks_state")
    gen_data_dir = os.path.join(sat_state_dir, "gen_data")
    commodities_path = os.path.join(sat_state_dir, "commodites.temp")
    out_dir = os.path.join(paper3_dir, "results")
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isfile(commodities_path):
        raise FileNotFoundError(f"Missing commodities file: {commodities_path}")
    commodities = _read_commodities(commodities_path)

    satnet_dirs = sorted([p for p in glob.glob(os.path.join(gen_data_dir, "*")) if os.path.isdir(p)])
    variants = [_variant_from_satnet_dir(p) for p in satnet_dirs]

    rows = []
    for v in variants:
        dyn_dir = os.path.join(v.constellation_dir, f"dynamic_state_{v.update_interval_ms}ms_for_{v.duration_s}s")
        fstate_files = sorted(glob.glob(os.path.join(dyn_dir, "fstate_*.txt")))
        if not fstate_files:
            continue

        # Persistent fstate mapping updated by delta files.
        fstate = {}
        sum_hops = 0
        sum_reachable = 0
        sum_paths = 0
        sum_path_changes = 0
        prev_paths = {}

        for fp in fstate_files:
            fstate.update(_load_fstate_file(fp))

            for (src, dst, _) in commodities:
                p = _get_path(src, dst, fstate)
                sum_paths += 1
                if p is None:
                    continue
                sum_reachable += 1
                sum_hops += (len(p) - 1)
                prev = prev_paths.get((src, dst))
                if prev is not None and prev != p:
                    sum_path_changes += 1
                prev_paths[(src, dst)] = p

        reach_ratio = (sum_reachable / sum_paths) if sum_paths else None
        mean_hops = (sum_hops / sum_reachable) if sum_reachable else None
        mean_path_changes_per_pair_per_step = (sum_path_changes / (len(commodities) * max(1, len(fstate_files) - 1))) if commodities else None

        # Read RTT median from satgenpy analysis if present
        analysis_base = os.path.join(paper3_dir, "satgenpy_analysis", "data", v.name, f"{v.update_interval_ms}ms_for_{v.duration_s}s", "rtt", "data")
        median_min_rtt_ns = _median_from_ecdf(os.path.join(analysis_base, "ecdf_pairs_min_rtt_ns.txt"))
        median_max_rtt_ns = _median_from_ecdf(os.path.join(analysis_base, "ecdf_pairs_max_rtt_ns.txt"))

        rows.append({
            "variant": v.name,
            "duration_s": v.duration_s,
            "update_interval_ms": v.update_interval_ms,
            "reachability_ratio": reach_ratio,
            "mean_hop_count": mean_hops,
            "mean_path_changes_per_pair_per_step": mean_path_changes_per_pair_per_step,
            "median_min_rtt_ms": (median_min_rtt_ns / 1e6) if median_min_rtt_ns is not None else None,
            "median_max_rtt_ms": (median_max_rtt_ns / 1e6) if median_max_rtt_ns is not None else None,
        })

    out_csv = os.path.join(out_dir, "summary.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print("Wrote:", out_csv)


if __name__ == "__main__":
    summarize(os.path.join(os.path.dirname(__file__)))
