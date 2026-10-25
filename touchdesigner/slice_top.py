"""Script TOP callbacks: the sound field on a plane through the room.

Reads the weights from the modes Script CHOP. Set Common > Pixel Format to 32-bit float (RGBA).
See README.md in this folder.
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
    axis = page.appendMenu("Axis", label="Plane normal")[0]
    axis.menuNames = axis.menuLabels = ["z", "y", "x"]
    position = page.appendFloat("Position", label="Plane position (0-1)")[0]
    position.default = 0.5
    colors = page.appendMenu("Colors")[0]
    colors.menuNames = ["signed", "raw"]
    colors.menuLabels = ["Red + / blue -", "Raw value in RGB"]
    gain = page.appendFloat("Gain")[0]
    gain.default = 1.0


def onCook(scriptOp):
    rt, room = load(scriptOp)
    par = scriptOp.par
    weights = np.array(par.Weights.eval()["weight"].vals)
    field = room.slice(weights, par.Axis.eval(), par.Position.eval())
    scriptOp.copyNumpyArray(rt.to_rgba(field, par.Colors.eval(), par.Gain.eval()))
