"""Statistical room acoustics: reverberation time, Schroeder frequency, critical distance.

These quantities assume a diffuse sound field, which holds above the Schroeder frequency;
below it the room behaves as a set of separate modes (`acousticfem.modes`).
"""

import numpy as np

from . import materials, physics


def room_statistics(volume: float, areas: dict, absorption, temperature: float = 20.0,
                    humidity: float = 50.0, c: float | None = None) -> dict:
    """Reverberation times per octave band, Schroeder frequency and critical distance.

    Args:
        volume: room volume [m³]
        areas: surface name -> area [m²], e.g. `Room.areas()` or `geometry.surface_areas`
        absorption: see `acousticfem.materials`

    The Schroeder frequency uses the Sabine reverberation time of the 125 Hz band, the band
    nearest to the modal range.
    """
    c = physics.speed_of_sound(temperature) if c is None else c
    bands = materials.resolve(absorption, areas)
    S, V = sum(areas.values()), volume

    per_band = []
    for i, f in enumerate(materials.OCTAVE_BANDS):
        A = sum(bands[name][i] * areas[name] for name in areas)
        m = float(physics.air_attenuation(f, temperature, humidity))
        per_band.append({
            "frequency_hz": float(f),
            "alpha_mean": A / S,
            "equivalent_area_m2": A,
            "t60_sabine_s": physics.sabine_t60(V, A, m, c),
            "t60_eyring_s": physics.eyring_t60(V, S, min(A / S, 0.99), m, c),
            "critical_distance_m": physics.critical_distance(A + 4 * m * V),
        })

    t125 = per_band[0]["t60_sabine_s"]
    return {
        "volume_m3": V,
        "surface_area_m2": S,
        "surfaces_m2": dict(areas),
        "speed_of_sound_ms": c,
        "schroeder_frequency_hz": physics.schroeder_frequency(V, t125) if np.isfinite(t125) else 0.0,
        "octave_bands": per_band,
    }
