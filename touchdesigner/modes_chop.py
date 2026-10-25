"""Script CHOP callbacks: the room modes and their current weights.

One sample per mode; channels "frequency" [Hz], "t60" [s] and "weight", the current amplitude
of each mode (the field stays within [-1, 1]). See README.md in this folder.
"""

import sys
from pathlib import Path


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
    excitation = page.appendMenu("Excitation")[0]
    excitation.menuNames = ["impulse", "sine", "mode"]
    excitation.menuLabels = ["Impulse at the source", "Sine at the source", "Single mode"]
    page.appendXYZ("Source", label="Source [m]")
    frequency = page.appendFloat("Frequency", label="Sine frequency [Hz]")[0]
    frequency.normMax = 200
    frequency.default = 50
    page.appendInt("Mode", label="Mode index")
    page.appendPulse("Trigger", label="Trigger impulse")
    page.appendFloat("Loop", label="Retrigger every [s] (0 = never)")


def onPulse(par):
    if par.name == "Trigger":
        par.owner.store("t0", absTime.seconds)


def onCook(scriptOp):
    rt = runtime(scriptOp)
    room = rt.load(scriptOp.par.Grid.eval())
    par = scriptOp.par
    excitation = par.Excitation.eval()
    t = absTime.seconds
    if excitation == "impulse":
        t -= scriptOp.fetch("t0", 0.0)
        if par.Loop.eval() > 0:
            t %= par.Loop.eval()
    source = [par.Sourcex.eval(), par.Sourcey.eval(), par.Sourcez.eval()]
    weights = room.weights(excitation, t, source, par.Frequency.eval(), par.Mode.eval())

    scriptOp.clear()
    scriptOp.numSamples = room.n
    for name, values in (("frequency", room.frequencies), ("t60", room.t60), ("weight", weights)):
        scriptOp.appendChan(name).vals = [float(v) for v in values]
