from .interfaces import *
from .ground_stations import *
from .tles import *
from .isls import *
from .dynamic_state import *
from .description import *
from .post_analysis import *
from .distance_tools import *

"""
Package export surface.

Note: Some research/MCNF components depend on optional solver deps (e.g. gurobipy).
We keep the rest of satgen usable when those are not installed.
"""

# Optional: MCNF / column-generation research code (may require gurobipy)
try:
    from .dynamic_mcnf_paper_code import (  # type: ignore
        instance_mcnf,
        interface,
        k_shortest_path,
        launch_dataset_dynamic,
        mcnf_dynamic_column_generation,
        mcnf_dynamic_continuous,
        mcnf_dynamic,
    )
except ModuleNotFoundError as e:
    # Keep base satgen usable without optional solver deps.
    if getattr(e, "name", None) == "gurobipy":
        pass
    else:
        raise
