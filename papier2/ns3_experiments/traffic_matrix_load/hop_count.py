"""
Compute hop-count comparison summaries across available routing outputs.
"""

import os

#------------------------------------#
#        PARAMETERS TO MODIFY        #
#------------------------------------#
mbps = 10
tps_simu = 120
timestep_ms = 10000
nb_cities = 100
tab_isls = ["isls", "isls2", "isls3", "isls4", "isls5", "isls6"]
constellation = "telesat_1015"
#------------------------------------#


def read_hop_file(path):
    with open(path, "r") as f_in:
        first_line = f_in.readline().strip()
    if not first_line:
        return None
    parts = first_line.split(",")
    if len(parts) < 2:
        return None
    hop_count = parts[1].split("-")
    return len(hop_count) - 2


def compute_ratio(new_value, ref_value):
    if new_value is None or ref_value in (None, 0):
        return None
    return (new_value - ref_value) / ref_value


def average_or_none(values):
    if not values:
        return None
    return sum(values) / len(values)


def format_value(value):
    return "" if value is None else str(value)


def format_ratio(value):
    return "" if value is None else "{:.2f}".format(value)


doss = "../../satgenpy_analysis/data/"
interdoss1 = (
    str(constellation)
    + "_isls_plus_grid_ground_stations_top_"
    + str(nb_cities)
    + "_algorithm_free_one_only_over_"
)
interdoss2 = "/" + str(timestep_ms) + "ms_for_" + str(tps_simu) + "s/manual/data/"

datasets = {}
skipped_empty = {}
for algo in tab_isls:
    algo_dir = doss + interdoss1 + algo + interdoss2
    datasets[algo] = {}
    skipped_empty[algo] = 0
    if not os.path.isdir(algo_dir):
        continue
    for networkx in sorted(os.listdir(algo_dir)):
        if "path" not in networkx:
            continue
        path = algo_dir + networkx
        hop_count = read_hop_file(path)
        if hop_count is None:
            skipped_empty[algo] += 1
            continue
        datasets[algo][networkx] = hop_count

row_keys = sorted(datasets["isls"].keys())
if not row_keys:
    raise RuntimeError(
        "No valid baseline path files found in {}".format(
            doss + interdoss1 + "isls" + interdoss2
        )
    )

sp3_ratios = []
sp5_ratios = []
mcnf3_ratios = []
mcnf5_ratios = []
rows = []

for index, key in enumerate(row_keys):
    isls = datasets["isls"].get(key)
    isls2 = datasets["isls2"].get(key)
    isls3 = datasets["isls3"].get(key)
    isls4 = datasets["isls4"].get(key)
    isls5 = datasets["isls5"].get(key)
    isls6 = datasets["isls6"].get(key)

    ratio_sp3 = compute_ratio(isls3, isls)
    ratio_sp5 = compute_ratio(isls5, isls)
    ratio_mcnf3 = compute_ratio(isls4, isls2)
    ratio_mcnf5 = compute_ratio(isls6, isls2)

    if ratio_sp3 is not None:
        sp3_ratios.append(ratio_sp3)
    if ratio_sp5 is not None:
        sp5_ratios.append(ratio_sp5)
    if ratio_mcnf3 is not None:
        mcnf3_ratios.append(ratio_mcnf3)
    if ratio_mcnf5 is not None:
        mcnf5_ratios.append(ratio_mcnf5)

    rows.append(
        (
            index,
            isls,
            isls2,
            isls3,
            isls4,
            isls5,
            isls6,
            ratio_sp3,
            ratio_sp5,
            ratio_mcnf3,
            ratio_mcnf5,
        )
    )

avg_reduc_SP3 = average_or_none(sp3_ratios)
avg_reduc_SP5 = average_or_none(sp5_ratios)
avg_reduc_MCNF3 = average_or_none(mcnf3_ratios)
avg_reduc_MCNF5 = average_or_none(mcnf5_ratios)

file = "hop_count.txt"
with open(file, "w") as fhopcount:
    if avg_reduc_SP3 is None:
        fhopcount.write("AVERAGE DIFFERENCE SP 3: N/A\n")
    else:
        fhopcount.write("AVERAGE DIFFERENCE SP 3: {:.2f}%\n".format(avg_reduc_SP3 * 100))
    if avg_reduc_SP5 is None:
        fhopcount.write("AVERAGE DIFFERENCE SP 5: N/A\n")
    else:
        fhopcount.write("AVERAGE DIFFERENCE SP 5: {:.2f}%\n".format(avg_reduc_SP5 * 100))
    if avg_reduc_MCNF3 is None:
        fhopcount.write("AVERAGE DIFFERENCE MCNF 3: N/A\n")
    else:
        fhopcount.write("AVERAGE DIFFERENCE MCNF 3: {:.2f}%\n".format(avg_reduc_MCNF3 * 100))
    if avg_reduc_MCNF5 is None:
        fhopcount.write("AVERAGE DIFFERENCE MCNF 5: N/A\n")
    else:
        fhopcount.write("AVERAGE DIFFERENCE MCNF 5: {:.2f}%\n".format(avg_reduc_MCNF5 * 100))

    fhopcount.write("\n")
    fhopcount.write(
        "ID\tISLS\tISLS2\tISLS3\tISLS4\tISLS5\tISLS6\tISLS3/ISLS\tISLS5/ISLS\tISLS4/ISLS2\tISLS6/ISLS2\n"
    )
    for row in rows:
        fhopcount.write(
            "{}\t{}\t\t{}\t\t{}\t\t{}\t\t{}\t\t{}\t\t{}\t\t{}\t\t{}\t\t{}\n".format(
                row[0],
                format_value(row[1]),
                format_value(row[2]),
                format_value(row[3]),
                format_value(row[4]),
                format_value(row[5]),
                format_value(row[6]),
                format_ratio(row[7]),
                format_ratio(row[8]),
                format_ratio(row[9]),
                format_ratio(row[10]),
            )
        )

print("Hop_Count Results written in file : hop_count.txt")
for algo in tab_isls:
    print(
        "Valid {} files: {}, skipped empty/invalid: {}".format(
            algo,
            len(datasets[algo]),
            skipped_empty[algo],
        )
    )
