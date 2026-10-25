"""Absorption of the room surfaces.

An absorption specification is either

- a number: the same frequency-independent coefficient on every surface, or
- a dict, surface name -> number, material name (see `list_materials`) or a list of six
  coefficients at the octave bands 125, 250, 500, 1000, 2000 and 4000 Hz.

Between bands the coefficient is interpolated linearly in log frequency; below 125 Hz,
where most room modes are, the 125 Hz value is used, and above 4000 Hz the 4000 Hz value.
"""

from functools import lru_cache
from importlib.resources import files

import numpy as np
import yaml

OCTAVE_BANDS = np.array([125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0])


@lru_cache(maxsize=1)
def _database() -> dict:
    return yaml.safe_load(files("tdroommodes").joinpath("materials.yaml").read_text())


def list_materials() -> dict:
    """Material name -> description."""
    return {k: v["name"] for k, v in _database()["materials"].items()}


def material(name: str) -> np.ndarray:
    """Octave-band absorption coefficients of a material."""
    try:
        return np.array(_database()["materials"][name]["absorption"], dtype=float)
    except KeyError:
        raise ValueError(f"unknown material {name!r}; see tdroommodes.materials.list_materials()") from None


def _bands(value) -> np.ndarray:
    if isinstance(value, str):
        return material(value)
    bands = np.broadcast_to(np.asarray(value, dtype=float), OCTAVE_BANDS.shape).copy()
    if np.any(bands < 0) or np.any(bands > 1):
        raise ValueError(f"absorption coefficients must be in [0, 1], got {value}")
    return bands


def resolve(spec, surfaces) -> dict:
    """Octave-band coefficients for each surface name in `surfaces`."""
    if not isinstance(spec, dict):
        return {name: _bands(spec) for name in surfaces}
    missing = set(surfaces) - set(spec)
    unknown = set(spec) - set(surfaces)
    if unknown:
        raise ValueError(f"no surface named {sorted(unknown)}; the room has {sorted(surfaces)}")
    if missing:
        raise ValueError(f"no absorption given for {sorted(missing)}")
    return {name: _bands(spec[name]) for name in surfaces}


def at_frequency(bands: np.ndarray, frequency) -> np.ndarray:
    """Coefficient at arbitrary frequencies from octave-band values."""
    f = np.clip(np.asarray(frequency, dtype=float), OCTAVE_BANDS[0], OCTAVE_BANDS[-1])
    return np.interp(np.log(f), np.log(OCTAVE_BANDS), bands)
