"""Script TOP callbacks: points inside the room with their pressure, for instancing.

One pixel per point: RGB = x, y, z [m], A = pressure. Set Common > Pixel Format to 32-bit float
(RGBA). See README.md in this folder.
"""

import sys
from pathlib import Path

import numpy as np


def runtime(scriptOp):
    src = str(Path(scriptOp.par.Repository.eval()).expanduser() / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from tdroommodes import runtime as rt
    return rt


def onSetupParameters(scriptOp):
    page = scriptOp.appendCustomPage("Room Modes")
    page.appendFolder("Repository", label="TDRoomModes folder")
    page.appendFile("Grid", label="grid.npz")
    page.appendCHOP("Weights", label="Modes CHOP")
    gain = page.appendFloat("Gain")[0]
    gain.default = 1.0


def onCook(scriptOp):
    rt = runtime(scriptOp)
    par = scriptOp.par
    room = rt.load(par.Grid.eval())
    weights = np.array(par.Weights.eval()["weight"].vals)
    scriptOp.copyNumpyArray(rt.points_image(room, weights, par.Gain.eval()))
