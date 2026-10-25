"""Script TOP callbacks: the sound field on a plane through the room.

Reads the weights from the modes Script CHOP. The image is 32-bit float RGBA.
See README.md in this folder.
"""

import importlib
import os
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
    from tdroommodes import runtime, synth

    # TouchDesigner keeps imported modules in memory: reload them when their files have changed
    # (or when it is unknown), so an update of TDRoomModes reaches a project that is already open
    for module in (synth, runtime):
        stamp = os.path.getmtime(module.__file__)
        if getattr(module, "_file_stamp", None) != stamp:
            module = importlib.reload(module)
            module._file_stamp = stamp
    rt = sys.modules["tdroommodes.runtime"]
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
    position.default = position.val = 0.5
    colors = page.appendMenu("Colors")[0]
    colors.menuNames = ["signed", "raw"]
    colors.menuLabels = ["Red + / blue -", "Raw value in RGB"]
    brightness = page.appendMenu("Brightness")[0]
    brightness.menuNames = ["auto", "physical"]
    brightness.menuLabels = ["Auto: every frame at full scale", "Physical: real level, shows the decay"]
    gain = page.appendFloat("Gain")[0]
    gain.default = gain.val = 1.0


def modes_chop(scriptOp):
    """The modes Script CHOP: the "Modes CHOP" parameter or, if empty, the Script CHOP next to
    this operator whose callbacks are synced to modes_chop.py."""
    chop = scriptOp.par.Weights.eval()
    if chop is None:
        for candidate in scriptOp.parent().findChildren(type=scriptCHOP, depth=1):
            callbacks = candidate.par.callbacks.eval()
            if callbacks is not None and str(callbacks.par.file.eval()).endswith("modes_chop.py"):
                chop = candidate
                break
    if chop is None or chop["weight"] is None:
        raise RuntimeError("Set 'Modes CHOP' to the Script CHOP that runs modes_chop.py")
    return chop


def onCook(scriptOp):
    rt, room = load(scriptOp)
    par = scriptOp.par
    weights = np.array(modes_chop(scriptOp)["weight"].vals)
    field = room.slice(weights, par.Axis.eval(), par.Position.eval())
    brightness = getattr(par, "Brightness", None)  # absent in operators set up before it existed
    if brightness is None or brightness.eval() == "auto":
        field = rt.auto_scale(field)
    scriptOp.copyNumpyArray(rt.to_rgba(field, par.Colors.eval(), par.Gain.eval()))
