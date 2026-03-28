# MIT License
#
# Copyright (c) 2020 Debopam Bhattacherjee
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

try:
    from . import util
except (ImportError, SystemError):
    import util


# Generate static visualizations for shell 0 of Starlink, Telesat, and Kuiper.

EARTH_RADIUS = 6378135.0  # WGS72 value

# CONSTELLATION GENERATION GENERAL CONSTANTS
ECCENTRICITY = 0.0000001  # pyephem does not permit exactly 0
ARG_OF_PERIGEE_DEGREE = 0.0
PHASE_DIFF = True
EPOCH = "2000-01-01 00:00:00"

CONSTELLATIONS = [
    {
        "name": "Starlink S1",
        "output_file": "starlink_first_shell.html",
        "color": "CRIMSON",
        "shells": [
            {
                "mean_motion_rev_per_day": 15.19,
                "altitude_m": 550000,
                "num_orbits": 72,
                "num_sats_per_orbit": 22,
                "inclination_degree": 53,
            }
        ],
    },
    {
        "name": "Kuiper K1",
        "output_file": "kuiper_first_shell.html",
        "color": "DODGERBLUE",
        "shells": [
            {
                "mean_motion_rev_per_day": 14.80,
                "altitude_m": 630000,
                "num_orbits": 34,
                "num_sats_per_orbit": 34,
                "inclination_degree": 51.9,
            }
        ],
    },
    {
        "name": "Telesat T1",
        "output_file": "telesat_first_shell.html",
        "color": "FORESTGREEN",
        "shells": [
            {
                "mean_motion_rev_per_day": 13.66,
                "altitude_m": 1015000,
                "num_orbits": 27,
                "num_sats_per_orbit": 13,
                "inclination_degree": 98.98,
            }
        ],
    },
]

# General files needed to generate visualizations; Do not change for different simulations
TOP_FILE = "../static_html/top.html"
BOTTOM_FILE = "../static_html/bottom.html"

# Output directory for creating visualization html files
OUT_DIR = "../viz_output/"
def generate_satellite_trajectories(constellation):
    """
    Generates and adds satellite orbits to visualization.
    :return: viz_string
    """
    viz_string = ""
    for shell in constellation["shells"]:
        sat_objs = util.generate_sat_obj_list(
            shell["num_orbits"],
            shell["num_sats_per_orbit"],
            EPOCH,
            PHASE_DIFF,
            shell["inclination_degree"],
            ECCENTRICITY,
            ARG_OF_PERIGEE_DEGREE,
            shell["mean_motion_rev_per_day"],
            shell["altitude_m"],
        )
        for sat in sat_objs:
            sat["sat_obj"].compute(EPOCH)
            viz_string += (
                "viewer.entities.add({name : '"
                + constellation["name"]
                + "', position: Cesium.Cartesian3.fromDegrees("
                + str(math.degrees(sat["sat_obj"].sublong))
                + ", "
                + str(math.degrees(sat["sat_obj"].sublat))
                + ", "
                + str(sat["alt_km"] * 1000)
                + "), ellipsoid : {radii : new Cesium.Cartesian3(30000.0, 30000.0, 30000.0), "
                + "material : Cesium.Color."
                + constellation["color"]
                + ".withAlpha(0.9),}});\n"
            )

        orbit_links = util.find_orbit_links(
            sat_objs,
            shell["num_orbits"],
            shell["num_sats_per_orbit"],
        )

        for key in orbit_links:
            sat1 = orbit_links[key]["sat1"]
            sat2 = orbit_links[key]["sat2"]
            viz_string += (
                "viewer.entities.add({name : '"
                + constellation["name"]
                + "', polyline: { positions: Cesium.Cartesian3.fromDegreesArrayHeights(["
                + str(math.degrees(sat_objs[sat1]["sat_obj"].sublong))
                + ","
                + str(math.degrees(sat_objs[sat1]["sat_obj"].sublat))
                + ","
                + str(sat_objs[sat1]["alt_km"] * 1000)
                + ","
                + str(math.degrees(sat_objs[sat2]["sat_obj"].sublong))
                + ","
                + str(math.degrees(sat_objs[sat2]["sat_obj"].sublat))
                + ","
                + str(sat_objs[sat2]["alt_km"] * 1000)
                + "]), width: 0.5, arcType: Cesium.ArcType.NONE, "
                + "material: new Cesium.PolylineOutlineMaterialProperty({ "
                + "color: Cesium.Color."
                + constellation["color"]
                + ".withAlpha(0.4), outlineWidth: 0, outlineColor: Cesium.Color.BLACK})}});"
            )

    return viz_string


def write_viz_file(viz_string, out_html_file):
    """
    Writes HTML file to the output folder
    :param viz_string: generated Cesium entity string
    :return: None
    """
    with open(out_html_file, "w") as writer_html:
        with open(TOP_FILE, "r") as fi:
            writer_html.write(fi.read())
        writer_html.write(viz_string)
        with open(BOTTOM_FILE, "r") as fb:
            writer_html.write(fb.read())


for constellation in CONSTELLATIONS:
    viz_string = generate_satellite_trajectories(constellation)
    write_viz_file(viz_string, OUT_DIR + constellation["output_file"])
