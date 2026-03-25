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
import ephem
import networkx as nx
import numpy as np
from astropy import units as u
from satgen.distance_tools import geodetic2cartesian


def _compute_satellite_positions_cartesian(satellites, epoch, time):
    observer = ephem.Observer()
    observer.epoch = str(epoch)
    observer.date = str(time)
    observer.lat = 0
    observer.lon = 0
    observer.elevation = 0

    positions = []
    for sat in satellites:
        sat.compute(observer)
        positions.append(
            np.array(
                geodetic2cartesian(
                    math.degrees(sat.sublat),
                    math.degrees(sat.sublong),
                    sat.elevation
                ),
                dtype=float
            )
        )
    return positions


def _compute_alignment_cosine(velocity_vector, link_vector):
    velocity_norm = np.linalg.norm(velocity_vector)
    link_norm = np.linalg.norm(link_vector)
    if velocity_norm <= 1e-12 or link_norm <= 1e-12:
        return 0.0
    alpha = float(np.dot(velocity_vector, link_vector) / (velocity_norm * link_norm))
    return max(-1.0, min(1.0, alpha))


def _compute_direction_aware_weight(baseline_weight, beta, alpha):
    weight = baseline_weight * (1.0 - beta * alpha)
    return max(weight, 1e-9)


def _build_direction_aware_directed_graph(
        satellites,
        epoch,
        time,
        sat_net_graph_only_satellites_with_isls,
        beta,
        velocity_sample_delta_ns
):
    positions_now = _compute_satellite_positions_cartesian(satellites, epoch, time)
    positions_next = _compute_satellite_positions_cartesian(
        satellites,
        epoch,
        time + velocity_sample_delta_ns * u.ns
    )
    velocities = [
        positions_next[sat_id] - positions_now[sat_id] for sat_id in range(len(satellites))
    ]

    direction_aware_graph = nx.DiGraph()
    direction_aware_graph.add_nodes_from(range(len(satellites)))

    for (a, b, data) in sat_net_graph_only_satellites_with_isls.edges(data=True):
        baseline_weight = data["weight"]

        link_vector_a_to_b = positions_now[b] - positions_now[a]
        alpha_a_to_b = _compute_alignment_cosine(velocities[a], link_vector_a_to_b)
        direction_aware_graph.add_edge(
            a,
            b,
            weight=_compute_direction_aware_weight(baseline_weight, beta, alpha_a_to_b)
        )

        link_vector_b_to_a = positions_now[a] - positions_now[b]
        alpha_b_to_a = _compute_alignment_cosine(velocities[b], link_vector_b_to_a)
        direction_aware_graph.add_edge(
            b,
            a,
            weight=_compute_direction_aware_weight(baseline_weight, beta, alpha_b_to_a)
        )

    return direction_aware_graph


def _calculate_fstate_shortest_path_without_gs_relaying_direction_aware(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        num_satellites,
        num_ground_stations,
        sat_net_graph_direction_aware_directed,
        num_isls_per_sat,
        gid_to_sat_gsl_if_idx,
        ground_station_satellites_in_range_candidates,
        sat_neighbor_to_if,
        prev_fstate,
        enable_verbose_logs,
        is_last
):
    if enable_verbose_logs:
        print("  > Calculating direction-aware Floyd-Warshall for directed graph without ground-station relays")
    dist_sat_net_without_gs = nx.floyd_warshall_numpy(sat_net_graph_direction_aware_directed)

    fstate = {}
    output_filename = output_dynamic_state_dir + "/fstate_" + str(time_since_epoch_ns) + ".txt"
    if enable_verbose_logs:
        print("  > Writing forwarding state to: " + output_filename)
    with open(output_filename, "w+") as f_out:

        # Satellites to ground stations
        # Keep source/destination satellite selection behavior aligned with baseline shortest-path workflow.
        dist_satellite_to_ground_station = {}
        for curr in range(num_satellites):
            for dst_gid in range(num_ground_stations):
                dst_gs_node_id = num_satellites + dst_gid

                possible_dst_sats = ground_station_satellites_in_range_candidates[dst_gid]
                possibilities = []
                for b in possible_dst_sats:
                    if not math.isinf(dist_sat_net_without_gs[(curr, b[1])]):
                        possibilities.append((dist_sat_net_without_gs[(curr, b[1])] + b[0], b[1]))
                possibilities = list(sorted(ground_station_satellites_in_range_candidates[dst_gid]))

                next_hop_decision = (-1, -1, -1)
                distance_to_ground_station_m = float("inf")
                if len(possibilities) > 0:
                    dst_sat = possibilities[0][1]
                    distance_to_ground_station_m = possibilities[0][0]

                    if curr != dst_sat:
                        best_distance_m = 1000000000000000
                        for neighbor_id in sat_net_graph_direction_aware_directed.successors(curr):
                            distance_m = (
                                    sat_net_graph_direction_aware_directed.edges[(curr, neighbor_id)]["weight"]
                                    + dist_sat_net_without_gs[(neighbor_id, dst_sat)]
                            )
                            if distance_m < best_distance_m:
                                next_hop_decision = (
                                    neighbor_id,
                                    sat_neighbor_to_if[(curr, neighbor_id)],
                                    sat_neighbor_to_if[(neighbor_id, curr)]
                                )
                                best_distance_m = distance_m
                    else:
                        next_hop_decision = (
                            dst_gs_node_id,
                            num_isls_per_sat[dst_sat] + gid_to_sat_gsl_if_idx[dst_gid],
                            0
                        )

                dist_satellite_to_ground_station[(curr, dst_gs_node_id)] = distance_to_ground_station_m

                if not prev_fstate or prev_fstate[(curr, dst_gs_node_id)] != next_hop_decision:
                    f_out.write("%d,%d,%d,%d,%d\n" % (
                        curr,
                        dst_gs_node_id,
                        next_hop_decision[0],
                        next_hop_decision[1],
                        next_hop_decision[2]
                    ))
                fstate[(curr, dst_gs_node_id)] = next_hop_decision

        # Ground stations to ground stations
        for src_gid in range(num_ground_stations):
            for dst_gid in range(num_ground_stations):
                if src_gid != dst_gid:
                    src_gs_node_id = num_satellites + src_gid
                    dst_gs_node_id = num_satellites + dst_gid

                    possible_src_sats = ground_station_satellites_in_range_candidates[src_gid]
                    possibilities = []
                    for a in possible_src_sats:
                        best_distance_offered_m = dist_satellite_to_ground_station[(a[1], dst_gs_node_id)]
                        if not math.isinf(best_distance_offered_m):
                            possibilities.append((a[0] + best_distance_offered_m, a[1]))
                    possibilities = sorted(possible_src_sats)

                    next_hop_decision = (-1, -1, -1)
                    if len(possibilities) > 0:
                        src_sat_id = possibilities[0][1]
                        next_hop_decision = (
                            src_sat_id,
                            0,
                            num_isls_per_sat[src_sat_id] + gid_to_sat_gsl_if_idx[src_gid]
                        )

                    if not prev_fstate or prev_fstate[(src_gs_node_id, dst_gs_node_id)] != next_hop_decision:
                        f_out.write("%d,%d,%d,%d,%d\n" % (
                            src_gs_node_id,
                            dst_gs_node_id,
                            next_hop_decision[0],
                            next_hop_decision[1],
                            next_hop_decision[2]
                        ))
                    fstate[(src_gs_node_id, dst_gs_node_id)] = next_hop_decision

    if is_last:
        with open(output_filename + ".temp", "w+") as f_out:
            f_out.write(str(fstate))

    return fstate


def algorithm_direction_aware_floyd_warshall(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        epoch,
        time,
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
        beta
):
    if enable_verbose_logs:
        print("\nALGORITHM: DIRECTION-AWARE FLOYD-WARSHALL (beta=%.3f)" % beta)

    if sat_net_graph_only_satellites_with_isls.number_of_nodes() != len(satellites):
        raise ValueError("Number of nodes in the graph does not match the number of satellites")
    for sid in range(len(satellites)):
        for n in sat_net_graph_only_satellites_with_isls.neighbors(sid):
            if n >= len(satellites):
                raise ValueError("Graph cannot contain satellite-to-ground-station links")

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

    prev_fstate = None
    if prev_output is not None:
        prev_fstate = prev_output["fstate"]

    gid_to_sat_gsl_if_idx = [0] * len(ground_stations)

    sat_net_graph_direction_aware_directed = _build_direction_aware_directed_graph(
        satellites,
        epoch,
        time,
        sat_net_graph_only_satellites_with_isls,
        beta,
        velocity_sample_delta_ns=1000000000
    )

    fstate = _calculate_fstate_shortest_path_without_gs_relaying_direction_aware(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        len(satellites),
        len(ground_stations),
        sat_net_graph_direction_aware_directed,
        num_isls_per_sat,
        gid_to_sat_gsl_if_idx,
        ground_station_satellites_in_range,
        sat_neighbor_to_if,
        prev_fstate,
        enable_verbose_logs,
        is_last
    )

    if enable_verbose_logs:
        print("")

    return {
        "fstate": fstate
    }
