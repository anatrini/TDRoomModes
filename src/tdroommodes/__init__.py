"""Room modes for TouchDesigner: computed with the finite element method, played in real time.

    import tdroommodes as trm
    result = trm.analyze("room.stl", absorption={"floor": "wood_floor", "walls": 0.05, "ceiling": 0.1})
    result.write("results/room", grid_spacing=0.25)

The computing side needs scikit-fem, gmsh and SciPy. `tdroommodes.runtime` and
`tdroommodes.synth` need only numpy, so TouchDesigner can import them: the names below are
loaded on first use, and importing the package itself loads nothing else.
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # for editors and type checkers; at run time names load on first use
    from .analysis import Analysis, analyze
    from .geometry import Room, box, element_size, from_surface, load_surface
    from .materials import list_materials
    from .modes import Modes, compute
    from .statistics import room_statistics

__version__ = "1.0.0"

_EXPORTS = {
    "Analysis": "analysis", "analyze": "analysis",
    "Room": "geometry", "box": "geometry", "element_size": "geometry",
    "from_surface": "geometry", "load_surface": "geometry",
    "list_materials": "materials",
    "Modes": "modes", "compute": "modes",
    "room_statistics": "statistics",
}

__all__ = ["Analysis", "Modes", "Room", "analyze", "box", "compute", "element_size", "from_surface",
           "list_materials", "load_surface", "room_statistics"]


def __getattr__(name):
    if name in _EXPORTS:
        return getattr(importlib.import_module(f".{_EXPORTS[name]}", __name__), name)
    try:
        return importlib.import_module(f".{name}", __name__)
    except ModuleNotFoundError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
