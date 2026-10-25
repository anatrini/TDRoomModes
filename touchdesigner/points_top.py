"""Script TOP callbacks: points inside the room with their pressure, for instancing.

One pixel per point: RGB = x, y, z [m], A = pressure. Set Common > Pixel Format to 32-bit float
(RGBA). See README.md in this folder.
"""

import sys
from pathlib import Path

import numpy as np


def load(scriptOp):
    """tdroommodes.runtime and the modes of this operator's grid.npz (see modes_chop.py)."""
    def absolute(path):
        path = Path(path).expanduser()
        return path if path.is_absolute() else Path(project.folder) / path

    par = scriptOp.par
    if par.Repository.eval():
        repository = absolute(par.Repository.eval())
    else:
        synced = par.callbacks.eval().par.file.eval()
        if not synced:
            raise RuntimeError("Set File of the callbacks DAT to TDRoomModes/touchdesigner/"
                               "<callbacks>.py, or fill in 'TDRoomModes folder'")
        repository = absolute(synced).resolve().parents[1]
    src = str(repository / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from tdroommodes import runtime as rt
    grid = absolute(par.Grid.eval()) if par.Grid.eval() else repository / "examples" / "box" / "grid.npz"
    return rt, rt.load(grid)


def onSetupParameters(scriptOp):
    page = scriptOp.appendCustomPage("Room Modes")
    page.appendCHOP("Weights", label="Modes CHOP")
    page.appendFile("Grid", label="grid.npz (empty: example room)")
    page.appendFolder("Repository", label="TDRoomModes folder (optional)")
    gain = page.appendFloat("Gain")[0]
    gain.default = 1.0


def onCook(scriptOp):
    rt, room = load(scriptOp)
    par = scriptOp.par
    weights = np.array(par.Weights.eval()["weight"].vals)
    scriptOp.copyNumpyArray(rt.points_image(room, weights, par.Gain.eval()))
