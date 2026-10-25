"""Complete analysis of a room: geometry, modes, decay, statistics, outputs."""

import json
import logging
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import export, geometry, modes as modes_, physics, plots, synth
from .statistics import room_statistics

logger = logging.getLogger(__name__)


@dataclass
class Analysis:
    room: geometry.Room
    modes: modes_.Modes
    statistics: dict
    source: np.ndarray
    receiver: np.ndarray
    seconds: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "room": self.room.summary(),
            "statistics": self.statistics,
            "modes": {**self.modes.info, "count": len(self.modes),
                      "lowest_hz": float(self.modes.frequencies[0]),
                      "highest_hz": float(self.modes.frequencies[-1]),
                      "speed_of_sound_ms": self.modes.c},
            "source_m": self.source.tolist(),
            "receiver_m": self.receiver.tolist(),
            "seconds": self.seconds,
        }

    def impulse_response(self, duration: float | None = None, sample_rate: int = 48000):
        """Modal part of the impulse response from source to receiver (see `synth`)."""
        phi = self.modes.evaluate([self.source, self.receiver])
        duration = duration or float(min(np.max(self.modes.t60), 10.0))
        return synth.impulse_response(duration, sample_rate, self.modes.frequencies, self.modes.decay,
                                      phi[0], phi[1], self.modes.c)

    def write(self, output, plots_: bool = True, grid_spacing: float | None = None,
              paraview: bool = False, wav: bool = True, slice_axis: str = "z",
              slice_position: float | None = None, gallery_modes: int = 12):
        """Write the results to the directory `output`.

        Files: summary.json, modes.csv, modes.npz and, as requested, spectrum.html,
        gallery.html, grid.npz (modes on a regular grid, for TouchDesigner), modes.vtu
        (ParaView) and impulse_response.wav.
        """
        start = time.perf_counter()
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)
        self.modes.save(out / "modes.npz")
        export.table(self.modes, out / "modes.csv", self.source, self.receiver)
        if grid_spacing:
            export.grid(self.modes, out / "grid.npz", grid_spacing)
        if paraview:
            export.paraview(self.modes, out / "modes.vtu")
        if wav:
            _write_wav(out / "impulse_response.wav", self.impulse_response(), 48000)
        if plots_:
            plots.spectrum(self.modes, self.source, self.receiver,
                           self.statistics["schroeder_frequency_hz"]).write_html(out / "spectrum.html")
            plots.gallery(self.modes, slice_axis, slice_position, gallery_modes).write_html(out / "gallery.html")
        self.seconds["output"] = time.perf_counter() - start
        (out / "summary.json").write_text(json.dumps(self.summary(), indent=2))
        return out


def analyze(geometry_, absorption=0.1, f_max: float | None = None, order: int = 2,
            h: float | None = None, temperature: float = 20.0, humidity: float = 50.0,
            c: float | None = None, up: str = "z", scale: float = 1.0, repair: bool = False,
            mesher: str = "auto", source=None, receiver=None, name: str | None = None) -> Analysis:
    """Mesh a room, compute its modes up to f_max and their decay.

    Args:
        geometry_: path to a closed surface (STL, OBJ, PLY, ...), a trimesh.Trimesh, or the
            dimensions (length, width, height) [m] of a rectangular room
        absorption: see `tdroommodes.materials`; surfaces are floor, ceiling and walls, or
            x0, x1, y0, y1, floor, ceiling for a rectangular room
        f_max: highest frequency [Hz]; by default the Schroeder frequency, above which
            single modes lose their meaning
        order: 2 (quadratic elements, recommended) or 1
        h: element size [m]; by default from f_max (`geometry.element_size`)
        temperature, humidity: air conditions [°C, %]
        c: speed of sound [m/s]; by default from the temperature
        up: vertical axis of the geometry
        scale: factor to metres, e.g. 0.001 for a model in millimetres
        repair, mesher: see `geometry.load_surface` and `geometry.from_surface`
        source, receiver: points [m]; by default two asymmetric points inside the room
            (the centre is a node of every mode of odd order in a symmetric room)
    """
    seconds = {}
    start = time.perf_counter()
    c = physics.speed_of_sound(temperature) if c is None else c

    is_box = isinstance(geometry_, (tuple, list)) and len(geometry_) == 3
    if is_box:
        L, W, H = map(float, geometry_)
        volume, extents = L * W * H, np.array([L, W, H])
        areas = {"x0": W * H, "x1": W * H, "y0": L * H, "y1": L * H, "floor": L * W, "ceiling": L * W}
        name = name or f"box {L:g} x {W:g} x {H:g} m"
    else:
        surface = geometry_
        if not hasattr(surface, "faces"):
            name = name or Path(surface).stem
            surface = geometry.load_surface(surface, scale=scale, repair=repair)
        volume, extents = surface.volume, surface.extents
        areas = geometry.surface_areas(surface, up)
        name = name or "room"

    if f_max is None:
        f_max = room_statistics(volume, areas, absorption, temperature, humidity, c)["schroeder_frequency_hz"]
        if not f_max:
            raise ValueError("no absorption, so no Schroeder frequency: give f_max")
        f_max = float(np.ceil(f_max))
        logger.info("f_max = Schroeder frequency = %.0f Hz", f_max)
    h = h or min(geometry.element_size(f_max, c, order), float(np.min(extents)) / 3)

    room = geometry.box(L, W, H, h, name) if is_box else geometry.from_surface(surface, h, up, name, mesher)
    seconds["mesh"] = time.perf_counter() - start

    modes = modes_.compute(room, f_max, c, order)
    modes.set_absorption(absorption, temperature, humidity)
    modes.info["element_size_m"] = h
    seconds["modes"] = time.perf_counter() - start - seconds["mesh"]

    statistics = room_statistics(room.volume, room.areas(), absorption, temperature, humidity, c)
    source = room.interior_point([0.3, 0.4, 0.35]) if source is None else np.asarray(source, dtype=float)
    receiver = room.interior_point([0.7, 0.65, 0.4]) if receiver is None else np.asarray(receiver, dtype=float)
    for label, point in (("source", source), ("receiver", receiver)):
        if np.isnan(modes.evaluate([point])[0, 0]):
            raise ValueError(f"the {label} {point.tolist()} is outside the room")
    return Analysis(room, modes, statistics, source, receiver, seconds)


def _write_wav(path, samples, sample_rate):
    data = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(data.tobytes())
