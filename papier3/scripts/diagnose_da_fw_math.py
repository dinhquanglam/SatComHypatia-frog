#!/usr/bin/env python3

import csv
import json
import math
from pathlib import Path

import networkx as nx
import numpy as np

import sys


def _as_list(vector):
    return [float(x) for x in vector]


def run_vector_cases(da_mod, out_dir):
    beta = 0.2
    w0 = 1000.0
    eps = 1e-12

    # Deterministic cases with known hand-expected alpha values.
    cases = [
        {
            "case_id": "alpha_pos_1",
            "p_i": np.array([0.0, 0.0, 0.0]),
            "p_j": np.array([10.0, 0.0, 0.0]),
            "v_i": np.array([5.0, 0.0, 0.0]),
            "expected_alpha": 1.0
        },
        {
            "case_id": "alpha_zero",
            "p_i": np.array([0.0, 0.0, 0.0]),
            "p_j": np.array([0.0, 10.0, 0.0]),
            "v_i": np.array([5.0, 0.0, 0.0]),
            "expected_alpha": 0.0
        },
        {
            "case_id": "alpha_neg_1",
            "p_i": np.array([0.0, 0.0, 0.0]),
            "p_j": np.array([-10.0, 0.0, 0.0]),
            "v_i": np.array([5.0, 0.0, 0.0]),
            "expected_alpha": -1.0
        },
        {
            "case_id": "alpha_pos_03",
            "p_i": np.array([0.0, 0.0, 0.0]),
            "p_j": np.array([10.0, 0.0, 0.0]),
            "v_i": np.array([0.3, math.sqrt(1.0 - 0.3 * 0.3), 0.0]),
            "expected_alpha": 0.3
        },
        {
            "case_id": "alpha_pos_07",
            "p_i": np.array([0.0, 0.0, 0.0]),
            "p_j": np.array([10.0, 0.0, 0.0]),
            "v_i": np.array([0.7, math.sqrt(1.0 - 0.7 * 0.7), 0.0]),
            "expected_alpha": 0.7
        },
    ]

    rows = []
    for case in cases:
        p_i = case["p_i"]
        p_j = case["p_j"]
        v_i = case["v_i"]
        link_vector = p_j - p_i
        norm_link = np.linalg.norm(link_vector)
        if norm_link <= eps:
            raise RuntimeError("Invalid synthetic case with zero-length link")
        direction = link_vector / norm_link

        alpha = da_mod._compute_alignment_cosine(v_i, link_vector)
        w = da_mod._compute_direction_aware_weight(w0, beta, alpha)
        expected_alpha = case["expected_alpha"]
        expected_w = w0 * (1.0 - beta * expected_alpha)

        rows.append({
            "case_id": case["case_id"],
            "p_i": _as_list(p_i),
            "p_j": _as_list(p_j),
            "v_i": _as_list(v_i),
            "link_vector": _as_list(link_vector),
            "link_direction_d": _as_list(direction),
            "baseline_weight_w0": w0,
            "beta": beta,
            "expected_alpha_hand": expected_alpha,
            "computed_alpha_code": float(alpha),
            "alpha_abs_error": abs(alpha - expected_alpha),
            "expected_weight_hand": expected_w,
            "computed_weight_code": float(w),
            "weight_abs_error": abs(w - expected_w),
            "pass_alpha": abs(alpha - expected_alpha) < 1e-9,
            "pass_weight": abs(w - expected_w) < 1e-9
        })

    csv_path = out_dir / "math_vector_cases.csv"
    with open(csv_path, "w", newline="") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=[
                "case_id",
                "p_i",
                "p_j",
                "v_i",
                "link_vector",
                "link_direction_d",
                "baseline_weight_w0",
                "beta",
                "expected_alpha_hand",
                "computed_alpha_code",
                "alpha_abs_error",
                "expected_weight_hand",
                "computed_weight_code",
                "weight_abs_error",
                "pass_alpha",
                "pass_weight"
            ]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    json_path = out_dir / "math_vector_cases.json"
    with open(json_path, "w") as f_out:
        json.dump(rows, f_out, indent=2)

    return rows


def run_routing_flip_case(da_mod, out_dir):
    # Tiny deterministic routing example:
    # baseline shortest path: 0->2->3
    # DA-modified (beta=0.2, minus-sign) path: 0->1->3
    beta = 0.2

    baseline_edges = {
        (0, 1): 10.0,
        (1, 3): 10.0,
        (0, 2): 9.0,
        (2, 3): 9.0
    }
    alpha_by_edge = {
        (0, 1): 1.0,
        (1, 3): 1.0,
        (0, 2): -1.0,
        (2, 3): -1.0
    }

    g_base = nx.DiGraph()
    g_da = nx.DiGraph()
    g_base.add_nodes_from([0, 1, 2, 3])
    g_da.add_nodes_from([0, 1, 2, 3])
    for edge, w0 in baseline_edges.items():
        alpha = alpha_by_edge[edge]
        g_base.add_edge(edge[0], edge[1], weight=w0)
        g_da.add_edge(
            edge[0],
            edge[1],
            weight=da_mod._compute_direction_aware_weight(w0, beta, alpha)
        )

    base_path = nx.shortest_path(g_base, source=0, target=3, weight="weight")
    da_path = nx.shortest_path(g_da, source=0, target=3, weight="weight")

    def path_cost(graph, path):
        total = 0.0
        for i in range(len(path) - 1):
            total += graph[path[i]][path[i + 1]]["weight"]
        return total

    payload = {
        "beta": beta,
        "baseline_edges_w0": {str(k): v for k, v in baseline_edges.items()},
        "alpha_by_edge": {str(k): v for k, v in alpha_by_edge.items()},
        "baseline_shortest_path": base_path,
        "baseline_shortest_path_cost": path_cost(g_base, base_path),
        "da_shortest_path": da_path,
        "da_shortest_path_cost": path_cost(g_da, da_path),
        "expected_baseline_path": [0, 2, 3],
        "expected_da_path": [0, 1, 3],
        "pass_baseline_path": base_path == [0, 2, 3],
        "pass_da_path": da_path == [0, 1, 3]
    }

    out_path = out_dir / "math_routing_flip_case.json"
    with open(out_path, "w") as f_out:
        json.dump(payload, f_out, indent=2)
    return payload


def main():
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "papier3" / "results" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str((repo_root / "satgenpy").resolve()))
    import satgen.dynamic_state.algorithm_direction_aware_floyd_warshall as da_mod

    vector_rows = run_vector_cases(da_mod, out_dir)
    routing_payload = run_routing_flip_case(da_mod, out_dir)

    summary = {
        "vector_cases_all_pass": all(row["pass_alpha"] and row["pass_weight"] for row in vector_rows),
        "routing_flip_all_pass": bool(
            routing_payload["pass_baseline_path"] and routing_payload["pass_da_path"]
        )
    }
    with open(out_dir / "math_diagnostic_summary.json", "w") as f_out:
        json.dump(summary, f_out, indent=2)

    print("Wrote {}".format(out_dir / "math_vector_cases.csv"))
    print("Wrote {}".format(out_dir / "math_vector_cases.json"))
    print("Wrote {}".format(out_dir / "math_routing_flip_case.json"))
    print("Wrote {}".format(out_dir / "math_diagnostic_summary.json"))
    print("Summary:", summary)


if __name__ == "__main__":
    main()
