"""Real-time sound fields from precomputed room modes, for TouchDesigner.

Imports only numpy (and the numpy-only `synth`), so TouchDesigner's own Python can use it.
The callbacks in the `touchdesigner/` folder of the repository are thin wrappers around it.

The input is the `grid.npz` written by `tdroommodes ROOM --grid SPACING`: the mode shapes
on a regular grid. A field is the sum of the shapes with one weight per mode; `RoomModes.weights`
gives the weights of three excitations, all normalized so that the field stays within [-1, 1]:

- "impulse": a click at the source, then each mode rings and decays at its own rate;
- "sine": the source plays a steady sine, which excites most the modes near its frequency;
- "mode": a single mode oscillating on its own, without decay.
"""

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np

from . import synth

EXCITATIONS = ("impulse", "sine", "mode")
AXES = {"x": 0, "y": 1, "z": 2}

_cache = {}


def load(path) -> "RoomModes":
    """The modes in a grid.npz file, cached until the file changes."""
    path = os.path.abspath(path)
    stamp = os.path.getmtime(path)
    cached = _cache.get(path)
    if cached is None or cached[0] != stamp:
        cached = (stamp, RoomModes(synth.load(path)))
        _cache[path] = cached
    return cached[1]


class RoomModes:
    """Mode shapes on a regular grid, with what is needed to animate them."""

    def __init__(self, data: dict):
        self.x, self.y, self.z = data["x"], data["y"], data["z"]
        self.shapes = np.asarray(data["shapes"], dtype=np.float32)  # (nx, ny, nz, n)
        self.inside = np.asarray(data["inside"], dtype=bool)
        self.frequencies = np.asarray(data["frequencies"], dtype=float)
        self.decay = np.asarray(data["decay"], dtype=float)
        self.c = float(data["c"])
        self._points = None
        self._scales = {}

    @property
    def n(self) -> int:
        return len(self.frequencies)

    @property
    def t60(self) -> np.ndarray:
        return 3.0 * np.log(10.0) / self.decay

    @property
    def bounds(self) -> np.ndarray:
        return np.array([[self.x[0], self.y[0], self.z[0]], [self.x[-1], self.y[-1], self.z[-1]]])

    # Values at a point

    def shape_at(self, point) -> np.ndarray:
        """Mode shapes at a point, by trilinear interpolation of the grid (zero outside the room)."""
        index = []
        for axis, value in zip((self.x, self.y, self.z), point):
            i = int(np.clip(np.searchsorted(axis, value) - 1, 0, len(axis) - 2))
            index.append((i, float(np.clip((value - axis[i]) / (axis[i + 1] - axis[i]), 0, 1))))
        (i, u), (j, v), (k, w) = index
        cube = self.shapes[i:i + 2, j:j + 2, k:k + 2]
        weights = np.einsum("a,b,c->abc", [1 - u, u], [1 - v, v], [1 - w, w])
        weights = weights * self.inside[i:i + 2, j:j + 2, k:k + 2]
        total = weights.sum()
        return np.zeros(self.n) if total == 0 else np.einsum("abc,abcn->n", weights / total, cube)

    # Weights

    def weights(self, excitation: str, t: float, source=None, frequency: float = 0.0,
                mode: int = 0) -> np.ndarray:
        """Weight of each mode at time t [s], normalized so the field stays within [-1, 1].

        Args:
            excitation: "impulse" (t is the time since the click), "sine" or "mode"
            source: source position [m] for "impulse" and "sine"; default the room centre
            frequency: sine frequency [Hz] for "sine"
            mode: mode index for "mode"
        """
        if excitation == "mode":
            w = np.zeros(self.n)
            mode = int(np.clip(mode, 0, self.n - 1))
            w[mode] = np.cos(2 * np.pi * self.frequencies[mode] * t)
            return w / self._scale(("mode", mode), lambda: np.abs(self.shapes[..., mode]).max())

        source = self.bounds.mean(axis=0) if source is None else np.asarray(source, dtype=float)
        phi = self.shape_at(source)
        key = (excitation, tuple(np.round(source, 6)), round(float(frequency), 6))
        if excitation == "impulse":
            a = synth.point_source_weights(phi, self.frequencies, self.c)
            w = synth.free_decay(t, np.eye(self.n), self.frequencies, self.decay, a)
            return w / self._scale(key, lambda: np.abs(self.shapes @ a).max())
        if excitation == "sine":
            coefficients = synth.steady_state(frequency, np.eye(self.n), self.frequencies, self.decay, phi, self.c)
            w = synth.steady_state_frame(coefficients, frequency, t)
            return w / self._scale(key, lambda: np.abs(self.shapes @ coefficients).max())
        raise ValueError(f"excitation must be one of {EXCITATIONS}, got {excitation!r}")

    def _scale(self, key, compute) -> float:
        if key not in self._scales:
            self._scales[key] = float(compute()) or 1.0
        return self._scales[key]

    # Fields

    def slice(self, weights, axis: str = "z", position: float = 0.5) -> np.ndarray:
        """Field on a plane perpendicular to `axis` at `position` (0 to 1 across the room).

        Returns:
            (rows, columns) array; rows run along the second remaining axis (y for a z plane),
            columns along the first; NaN outside the room
        """
        k = AXES[axis]
        index = int(round(np.clip(position, 0, 1) * (self.shapes.shape[k] - 1)))
        plane = np.take(self.shapes, index, axis=k) @ np.asarray(weights, dtype=np.float32)
        plane[~np.take(self.inside, index, axis=k)] = np.nan
        return plane.T

    def points(self) -> np.ndarray:
        """Positions (n_points, 3) of the grid points inside the room."""
        if self._points is None:
            X, Y, Z = np.meshgrid(self.x, self.y, self.z, indexing="ij")
            self._points = np.column_stack([X[self.inside], Y[self.inside], Z[self.inside]])
            self._point_shapes = self.shapes[self.inside]
        return self._points

    def point_field(self, weights) -> np.ndarray:
        """Field at `points()`."""
        self.points()
        return self._point_shapes @ np.asarray(weights, dtype=np.float32)


# Images for TouchDesigner (Script TOP: scriptOp.copyNumpyArray)

def to_rgba(field: np.ndarray, colors: str = "signed", gain: float = 1.0) -> np.ndarray:
    """RGBA float32 image of a field in [-1, 1].

    colors: "signed" puts positive pressure in red and negative in blue; "raw" puts the value
    in R, G and B, for further processing. Alpha is 0 outside the room.
    """
    inside = ~np.isnan(field)
    value = np.where(inside, field * gain, 0.0).astype(np.float32)
    rgba = np.zeros((*field.shape, 4), dtype=np.float32)
    if colors == "signed":
        rgba[..., 0] = np.clip(value, 0, 1)
        rgba[..., 2] = np.clip(-value, 0, 1)
    else:
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = value
    rgba[..., 3] = inside
    return rgba


def auto_scale(field: np.ndarray) -> np.ndarray:
    """The field divided by its own peak, so every frame uses the full range [-1, 1].

    The weights of `RoomModes.weights` keep the physical level: after an impulse the field fades
    as the room does, and around a source it peaks next to the source. Auto scale shows the
    shape of the field whatever its level. Below `SILENCE` (a field on a nodal plane, or long
    after an impulse) it is left alone, so numerical noise is not blown up to full scale."""
    peak = np.nanmax(np.abs(field)) if np.any(~np.isnan(field)) else 0.0
    return field / peak if peak > SILENCE else field


SILENCE = 1e-4  # relative to the loudest point of the room


def points_image(room: RoomModes, weights, gain: float = 1.0, auto: bool = False) -> np.ndarray:
    """Positions and field of the points in one RGBA float32 image, for instancing:
    RGB = x, y, z [m], A = pressure (see `auto_scale` for `auto`). Spare pixels at the end
    repeat the first point with zero pressure."""
    points = room.points()
    values = room.point_field(weights)
    values = (auto_scale(values) if auto else values) * gain
    n = len(points)
    width = int(np.ceil(np.sqrt(n)))
    height = int(np.ceil(n / width))
    image = np.zeros((height * width, 4), dtype=np.float32)
    image[:, :3] = points[0]
    image[:n, :3] = points
    image[:n, 3] = values
    return image.reshape(height, width, 4)


# Computing modes from TouchDesigner

def compute(repository, geometry, output, grid_spacing: float = 0.5, extra_args=()):
    """Start `tdroommodes` in the background with uv; returns the subprocess.Popen.

    TouchDesigner keeps running: poll the returned process (`.poll()` is None while it runs)
    and load output/grid.npz when it has finished. The log goes to output/compute.log.
    """
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    command = [uv, "run", "--project", str(repository), "tdroommodes", str(geometry),
               "-o", str(output), "--grid", str(grid_spacing), *extra_args]
    log = open(output / "compute.log", "w")
    return subprocess.Popen(command, cwd=str(repository), stdout=log, stderr=subprocess.STDOUT)
