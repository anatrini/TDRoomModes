"""Script CHOP callbacks: the room modes and their current weights.

One sample per mode; channels "frequency" [Hz], "t60" [s] and "weight", the current amplitude
of each mode (the field stays within [-1, 1]). See README.md in this folder.
"""

import importlib
import os
import sys
from pathlib import Path


def load(scriptOp):
    """tdroommodes.runtime and the modes of this operator's grid.npz.

    The TDRoomModes folder is the "TDRoomModes folder" parameter if set, otherwise found from
    the file this callbacks DAT is synced to (TDRoomModes/touchdesigner/<file>.py). An empty
    grid.npz loads the example in TDRoomModes/examples/box.
    """
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
    page.appendFile("Grid", label="grid.npz (empty: example room)")
    page.appendFolder("Repository", label="TDRoomModes folder (optional)")
    excitation = page.appendMenu("Excitation")[0]
    excitation.menuNames = ["mode", "impulse", "sine"]
    excitation.menuLabels = ["Single mode", "Impulse at the source", "Sine at the source"]
    page.appendXYZ("Source", label="Source [m]")
    frequency = page.appendFloat("Frequency", label="Sine frequency [Hz]")[0]
    frequency.normMax = 200
    frequency.default = frequency.val = 50
    page.appendInt("Mode", label="Mode index")
    page.appendPulse("Trigger", label="Trigger impulse")
    page.appendFloat("Loop", label="Retrigger every [s] (0 = never)")
    speed = page.appendFloat("Speed", label="Speed (1 = real time)")[0]
    speed.default = speed.val = 0.05
    speed.normMax = 1.0


def onPulse(par):
    if par.name == "Trigger":
        par.owner.store("t0", absTime.seconds)


def onCook(scriptOp):
    _, room = load(scriptOp)
    par = scriptOp.par
    excitation = par.Excitation.eval()
    t = absTime.seconds
    if excitation == "impulse":
        if scriptOp.fetch("t0", None) is None:  # never triggered: the first impulse is now
            scriptOp.store("t0", t)
        t -= scriptOp.fetch("t0", t)
        if par.Loop.eval() > 0:
            t %= par.Loop.eval()
    # Modes oscillate at tens of hertz, faster than the frame rate: slow time down to watch them
    t *= par.Speed.eval()
    source = [par.Sourcex.eval(), par.Sourcey.eval(), par.Sourcez.eval()]
    weights = room.weights(excitation, t, source, par.Frequency.eval(), par.Mode.eval())

    scriptOp.clear()
    scriptOp.numSamples = room.n
    for name, values in (("frequency", room.frequencies), ("t60", room.t60), ("weight", weights)):
        scriptOp.appendChan(name).vals = [float(v) for v in values]
