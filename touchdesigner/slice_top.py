"""Script TOP callbacks: the sound field on a plane through the room.

Reads the weights from the modes Script CHOP. Set Common > Pixel Format to 32-bit float (RGBA).
See README.md in this folder.
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
    rt = runtime(scriptOp)
    par = scriptOp.par
    room = rt.load(par.Grid.eval())
    weights = np.array(par.Weights.eval()["weight"].vals)
    field = room.slice(weights, par.Axis.eval(), par.Position.eval())
    scriptOp.copyNumpyArray(rt.to_rgba(field, par.Colors.eval(), par.Gain.eval()))
