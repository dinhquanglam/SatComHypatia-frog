# The MIT License (MIT)
#
# Copyright (c) 2020 ETH Zurich
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import math
import re
import ephem
import networkx as nx

from .fstate_calculation import calculate_fstate_shortest_path_without_gs_relaying_with_dist
from ..distance_tools.distance_tools import geodetic2cartesian


def _parse_beta(dynamic_state_algorithm, default_beta):
    """
    Accept a few simple spellings:
      - algorithm_direction_aware_floyd_warshall
      - algorithm_direction_aware_floyd_warshall_beta0p2
      - algorithm_direction_aware_floyd_warshall_beta0.2
      - algorithm_direction_aware_floyd_warshall__beta=0.2
    """
    # Prefer the '0p2' style match over the plain integer match.
    m = re.search(r"beta(?:=|_)?([0-9]+p[0-9]+|[0-9]+(?:\\.[0-9]+)?)", dynamic_state_algorithm)
    if not m:
        return float(default_beta)
    s = m.group(1).replace("p", ".")
    return float(s)


def _sat_pos_ecef_m(sat, epoch_str, date):
    """
    Return an approximate Earth-fixed (ECEF-like) position vector (x,y,z) in meters.

    We rely on PyEphem's sublat/sublong/elevation (computed from TLE) and map it to
    Cartesian using the existing WGS72 ellipsoid helper.
    """
    sat.compute(date, epoch=epoch_str)
    lat_deg = math.degrees(sat.sublat)
    lon_deg = math.degrees(sat.sublong)
    ele_m = float(sat.elevation)
    return geodetic2cartesian(lat_deg, lon_deg, ele_m)


def _sat_vel_ecef_m_per_s(sat, epoch_str, date, dt_s, pos_now=None):
    """
    Approximate velocity via forward finite differences in the same coordinate system as _sat_pos_ecef_m.
    """
    if pos_now is None:
        pos_now = _sat_pos_ecef_m(sat, epoch_str, date)
    pos_next = _sat_pos_ecef_m(sat, epoch_str, ephem.Date(date) + dt_s * ephem.second)
    return (
        (pos_next[0] - pos_now[0]) / dt_s,
        (pos_next[1] - pos_now[1]) / dt_s,
        (pos_next[2] - pos_now[2]) / dt_s,
    )


def _cosine_similarity(a, b):
    ax, ay, az = a
    bx, by, bz = b
    na = math.sqrt(ax * ax + ay * ay + az * az)
    nb = math.sqrt(bx * bx + by * by + bz * bz)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return (ax * bx + ay * by + az * bz) / (na * nb)


def _build_direction_aware_digraph(sat_net_graph_undirected, satellites, epoch_str, date_str, beta, dt_s):
    """
    Convert the undirected ISL graph into a directed graph with per-direction weights.

    Effective edge cost:
        w = w0 * (1 + beta * f(alpha))
    where w0 is the baseline edge weight, alpha is cosine similarity between the
    link direction (i->j) and satellite i's velocity, and f(alpha) = -alpha.
    """
    date = ephem.Date(date_str)

    # Cache satellite positions/velocities once per time step.
    pos = [None] * len(satellites)
    vel = [None] * len(satellites)
    for i, sat in enumerate(satellites):
        p = _sat_pos_ecef_m(sat, epoch_str, date)
        pos[i] = p
        vel[i] = _sat_vel_ecef_m_per_s(sat, epoch_str, date, dt_s, pos_now=p)

    g = nx.DiGraph()
    g.add_nodes_from(sat_net_graph_undirected.nodes())

    for u, v, data in sat_net_graph_undirected.edges(data=True):
        w0 = float(data.get("weight", 1.0))

        duv = (pos[v][0] - pos[u][0], pos[v][1] - pos[u][1], pos[v][2] - pos[u][2])
        dvu = (-duv[0], -duv[1], -duv[2])

        alpha_uv = _cosine_similarity(vel[u], duv)
        alpha_vu = _cosine_similarity(vel[v], dvu)

        # f(alpha) = -alpha (bounded, monotonic decreasing)
        mult_uv = 1.0 + beta * (-alpha_uv)
        mult_vu = 1.0 + beta * (-alpha_vu)

        # Guard against negative/zero multiplier for extreme configs.
        mult_uv = max(mult_uv, 1e-6)
        mult_vu = max(mult_vu, 1e-6)

        g.add_edge(u, v, weight=w0 * mult_uv, base_weight=w0, alpha=alpha_uv, multiplier=mult_uv)
        g.add_edge(v, u, weight=w0 * mult_vu, base_weight=w0, alpha=alpha_vu, multiplier=mult_vu)

    return g


def algorithm_direction_aware_floyd_warshall(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        satellites,
        ground_stations,
        sat_net_graph_only_satellites_with_isls,
        ground_station_satellites_in_range,
        num_isls_per_sat,
        sat_neighbor_to_if,
        list_gsl_interfaces_info,
        prev_output,
        enable_verbose_logs,
        is_last,
        *,
        epoch_str,
        date_str,
        dynamic_state_algorithm,
        default_beta=0.4,
        dt_s=1.0,
        fw_max_n=2000
):
    """
    Direction-aware variant of the Floyd–Warshall shortest-path routing.

    This keeps the existing forwarding-state generation flow intact by:
      1) building a directed ISL graph with direction-aware per-edge weights
      2) calling the standard FW-based forwarding-state calculation on that graph

    Notes/assumptions:
      - Positions/velocities are approximated in an Earth-fixed (ECEF-like) frame
        derived from PyEphem sublat/sublong/elevation.
      - Velocity is estimated by forward finite difference with step dt_s.
    """
    beta = _parse_beta(dynamic_state_algorithm, default_beta)
    use_dijkstra_fallback = ("_dijkstra" in dynamic_state_algorithm) or (len(satellites) > fw_max_n)

    if enable_verbose_logs:
        method = "dijkstra-fallback" if use_dijkstra_fallback else "floyd-warshall"
        print("\nALGORITHM: DIRECTION-AWARE FLOYD-WARSHALL (beta=%.3f, method=%s)" % (beta, method))

    if sat_net_graph_only_satellites_with_isls.number_of_nodes() != len(satellites):
        raise ValueError("Number of nodes in the graph does not match the number of satellites")
    for sid in range(len(satellites)):
        for n in sat_net_graph_only_satellites_with_isls.neighbors(sid):
            if n >= len(satellites):
                raise ValueError("Graph cannot contain satellite-to-ground-station links")

    # BANDWIDTH STATE (same behavior as algorithm_free_one_only_over_isls)
    output_filename = output_dynamic_state_dir + "/gsl_if_bandwidth_" + str(time_since_epoch_ns) + ".txt"
    if enable_verbose_logs:
        print("  > Writing interface bandwidth state to: " + output_filename)
    with open(output_filename, "w+") as f_out:
        if time_since_epoch_ns == 0:
            for node_id in range(len(satellites)):
                f_out.write("%d,%d,%f\n"
                            % (node_id, num_isls_per_sat[node_id],
                               list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"]))
            for node_id in range(len(satellites), len(satellites) + len(ground_stations)):
                f_out.write("%d,%d,%f\n"
                            % (node_id, 0, list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"]))

    # FORWARDING STATE
    prev_fstate = None
    if prev_output is not None:
        prev_fstate = prev_output["fstate"]

    gid_to_sat_gsl_if_idx = [0] * len(ground_stations)

    # Build directed graph with direction-aware weights.
    digraph = _build_direction_aware_digraph(
        sat_net_graph_only_satellites_with_isls,
        satellites,
        epoch_str,
        date_str,
        beta,
        dt_s,
    )

    # Optional: quick stats
    if enable_verbose_logs and digraph.number_of_edges() > 0:
        mults = [digraph.edges[e].get("multiplier", 1.0) for e in digraph.edges]
        alphas = [digraph.edges[e].get("alpha", 0.0) for e in digraph.edges]
        print("  > Direction-aware edge multipliers: min=%.3f mean=%.3f max=%.3f" % (
            min(mults), sum(mults) / len(mults), max(mults)
        ))
        print("  > Alignment alpha values:          min=%.3f mean=%.3f max=%.3f" % (
            min(alphas), sum(alphas) / len(alphas), max(alphas)
        ))

    # Compute all-pairs distances (FW default, Dijkstra fallback if requested/needed)
    if use_dijkstra_fallback:
        import numpy as np
        dist = np.full((len(satellites), len(satellites)), float("inf"), dtype=float)
        for i in range(len(satellites)):
            dist[(i, i)] = 0.0
        for src in range(len(satellites)):
            lengths = nx.single_source_dijkstra_path_length(digraph, src, weight="weight")
            for dst, d in lengths.items():
                dist[(src, dst)] = float(d)
    else:
        dist = nx.floyd_warshall_numpy(digraph)

    fstate = calculate_fstate_shortest_path_without_gs_relaying_with_dist(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        len(satellites),
        len(ground_stations),
        digraph,
        dist,
        num_isls_per_sat,
        gid_to_sat_gsl_if_idx,
        ground_station_satellites_in_range,
        sat_neighbor_to_if,
        prev_fstate,
        enable_verbose_logs,
        is_last,
    )

    if enable_verbose_logs:
        print("")

    return {"fstate": fstate}
