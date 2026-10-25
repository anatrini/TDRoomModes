"""Room acoustic modes with the finite element method.

    import acousticfem as af
    result = af.analyze("room.stl", absorption={"floor": "wood_floor", "walls": 0.05, "ceiling": 0.1})
    result.write("results/room", grid_spacing=0.25)

`acousticfem.synth` turns the saved modes into sound fields with numpy alone.
"""

__version__ = "3.0.0"

from .analysis import Analysis, analyze
from .geometry import Room, box, element_size, from_surface, load_surface
from .materials import list_materials
from .modes import Modes, compute
from .statistics import room_statistics

__all__ = ["Analysis", "Modes", "Room", "analyze", "box", "compute", "element_size", "from_surface",
           "list_materials", "load_surface", "room_statistics"]
