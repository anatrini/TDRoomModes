"""The TouchDesigner side: runtime module and Script operator callbacks, with stand-ins for the
TouchDesigner objects they use (scriptOp, its parameters, absTime)."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import tdroommodes as trm
from tdroommodes import export, runtime, synth

REPO = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def grid_file(tmp_path_factory):
    modes = trm.compute(trm.box(4.0, 3.0, 2.5, 0.5), 90.0).set_absorption(0.1)
    path = tmp_path_factory.mktemp("grid") / "grid.npz"
    export.grid(modes, path, 0.25)
    return path


def test_runtime_imports_only_numpy():
    code = ("import sys; sys.path.insert(0, 'src'); import tdroommodes.runtime; "
            "heavy = {'scipy', 'skfem', 'gmsh', 'trimesh', 'plotly', 'pytetwild'} & set(sys.modules); "
            "print(sorted(heavy))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


@pytest.mark.parametrize("excitation", ["impulse", "sine", "mode"])
def test_weights_keep_the_field_within_one(grid_file, excitation):
    room = runtime.load(grid_file)
    source = [1.0, 0.8, 0.7]
    peak = max(np.nanmax(np.abs(room.point_field(room.weights(excitation, t, source, 60.0, 2))))
               for t in np.linspace(0, 0.1, 50))
    assert 0.3 < peak <= 1.0 + 1e-6


def test_sine_field_matches_synth(grid_file):
    room = runtime.load(grid_file)
    source, f, t = [1.0, 0.8, 0.7], 55.0, 0.013
    phi = room.shape_at(source)
    room.points()
    exact = synth.steady_state_frame(
        synth.steady_state(f, room._point_shapes, room.frequencies, room.decay, phi, room.c), f, t)
    field = room.point_field(room.weights("sine", t, source, f))
    assert np.allclose(field / np.abs(field).max(), exact / np.abs(exact).max(), atol=1e-5)


def test_shape_at_matches_fem(grid_file):
    modes = trm.compute(trm.box(4.0, 3.0, 2.5, 0.5), 90.0)
    room = runtime.load(grid_file)
    point = [1.1, 0.9, 0.6]
    assert np.allclose(np.abs(room.shape_at(point)), np.abs(modes.evaluate([point])[0]), atol=0.02)


def test_images(grid_file):
    room = runtime.load(grid_file)
    w = room.weights("mode", 0.0, mode=1)
    image = runtime.to_rgba(room.slice(w, "z", 0.5))
    assert image.dtype == np.float32 and image.shape == (len(room.y), len(room.x), 4)
    points = runtime.points_image(room, w)
    assert points.shape[0] * points.shape[1] >= len(room.points())
    assert np.allclose(points.reshape(-1, 4)[: len(room.points()), :3], room.points())


# Stand-ins for TouchDesigner

class Par:
    def __init__(self, name, value=None, owner=None):
        self.name, self.value, self.owner = name, value, owner

    def eval(self):
        return self.value


class Chan:
    vals = None


class ScriptOp:
    def __init__(self, siblings=(), **pars):
        self.par = SimpleNamespace(**{k: Par(k, v, self) for k, v in pars.items()})
        self.channels, self.storage, self.image = {}, {}, None
        self.siblings = list(siblings)

    def parent(self):
        siblings = self.siblings
        return SimpleNamespace(findChildren=lambda type, depth: [s for s in siblings if isinstance(s, type)])

    def clear(self):
        self.channels = {}

    def appendChan(self, name):
        self.channels[name] = Chan()
        return self.channels[name]

    def store(self, key, value):
        self.storage[key] = value

    def fetch(self, key, default=None):
        return self.storage.get(key, default)

    def copyNumpyArray(self, array):
        self.image = array

    def __getitem__(self, name):
        return self.channels.get(name)  # TouchDesigner returns None for a missing channel


def callbacks(name, seconds, project_folder=REPO):
    spec = importlib.util.spec_from_file_location(name, REPO / "touchdesigner" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.absTime = SimpleNamespace(seconds=seconds)
    module.project = SimpleNamespace(folder=str(project_folder))
    module.scriptCHOP = ScriptOp
    return module


def callbacks_dat(file):
    """The callbacks Text DAT, synced to `file`."""
    return SimpleNamespace(par=SimpleNamespace(file=Par("file", file)))


def test_callbacks_find_the_repository_and_the_example(tmp_path):
    """With every parameter empty: the folder comes from the synced callbacks file, the
    modes from examples/box/grid.npz."""
    chop = ScriptOp(Repository="", Grid="", Excitation="mode", Sourcex=0.0, Sourcey=0.0, Sourcez=0.0,
                    Frequency=50.0, Mode=0, Loop=0.0, Speed=1.0,
                    callbacks=callbacks_dat(str(REPO / "touchdesigner" / "modes_chop.py")))
    callbacks("modes_chop", 0.0, project_folder=tmp_path).onCook(chop)
    assert chop["frequency"].vals[0] == pytest.approx(343.2 / 16, rel=1e-3)  # 8 m axial mode

    # A path relative to the project folder, as TouchDesigner stores it
    relative = ScriptOp(Repository="", Grid="", Excitation="mode", Sourcex=0.0, Sourcey=0.0,
                        Sourcez=0.0, Frequency=50.0, Mode=0, Loop=0.0, Speed=1.0,
                        callbacks=callbacks_dat("TDRoomModes/touchdesigner/modes_chop.py"))
    callbacks("modes_chop", 0.0, project_folder=REPO.parent).onCook(relative)
    assert relative["frequency"].vals == chop["frequency"].vals

    unsynced = ScriptOp(Repository="", Grid="", callbacks=callbacks_dat(""))
    with pytest.raises(RuntimeError, match="callbacks DAT"):
        callbacks("modes_chop", 0.0).onCook(unsynced)


def test_callbacks_end_to_end(grid_file):
    chop = ScriptOp(Repository=str(REPO), Grid=str(grid_file), Excitation="impulse", Sourcex=1.0,
                    Sourcey=0.8, Sourcez=0.7, Frequency=50.0, Mode=0, Loop=0.0, Speed=0.5)
    modes_chop = callbacks("modes_chop", seconds=10.0)
    modes_chop.onPulse(Par("Trigger", None, chop))  # the impulse starts at 10 s
    modes_chop.absTime.seconds = 10.1
    modes_chop.onCook(chop)
    room = runtime.load(grid_file)
    assert set(chop.channels) == {"frequency", "t60", "weight"}
    assert np.allclose(chop["frequency"].vals, room.frequencies)
    # 0.1 s after the trigger at half speed
    assert np.allclose(chop["weight"].vals, room.weights("impulse", 0.05, [1.0, 0.8, 0.7]))

    top = ScriptOp(Repository=str(REPO), Grid=str(grid_file), Weights=chop, Axis="z", Position=0.5,
                   Colors="signed", Gain=1.0)
    callbacks("slice_top", 10.05).onCook(top)
    assert top.image.shape == (len(room.y), len(room.x), 4)

    points = ScriptOp(Repository=str(REPO), Grid=str(grid_file), Weights=chop, Gain=1.0)
    callbacks("points_top", 10.05).onCook(points)
    assert points.image.shape[2] == 4


def test_tops_find_the_modes_chop_when_the_parameter_is_empty(grid_file):
    chop = ScriptOp(Repository=str(REPO), Grid=str(grid_file), Excitation="mode", Sourcex=0.0,
                    Sourcey=0.0, Sourcez=0.0, Frequency=50.0, Mode=1, Loop=0.0, Speed=1.0,
                    callbacks=callbacks_dat(str(REPO / "touchdesigner" / "modes_chop.py")))
    callbacks("modes_chop", 0.0).onCook(chop)
    other = ScriptOp(callbacks=callbacks_dat("somewhere/else.py"))

    top = ScriptOp(siblings=[other, chop], Repository=str(REPO), Grid=str(grid_file), Weights=None,
                   Axis="z", Position=0.5, Colors="signed", Gain=1.0)
    callbacks("slice_top", 0.0).onCook(top)
    assert top.image is not None

    lonely = ScriptOp(siblings=[other], Repository=str(REPO), Grid=str(grid_file), Weights=None, Gain=1.0)
    with pytest.raises(RuntimeError, match="Modes CHOP"):
        callbacks("points_top", 0.0).onCook(lonely)


def test_auto_scale(grid_file):
    room = runtime.load(grid_file)
    source = [1.0, 0.8, 0.7]
    faded = room.slice(room.weights("impulse", 0.2, source))
    assert 0.01 < np.nanmax(np.abs(faded)) < 0.5  # quieter than at the start, still audible
    assert np.nanmax(np.abs(runtime.auto_scale(faded))) == pytest.approx(1.0)
    silent = room.slice(room.weights("impulse", 1.5, source))
    assert np.nanmax(np.abs(runtime.auto_scale(silent))) < runtime.SILENCE  # not blown up
