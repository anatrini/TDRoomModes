from math import ceil, sqrt


def analytical_rigid_box_modes(
    length_m: float,
    width_m: float,
    height_m: float,
    speed_of_sound_m_s: float,
    max_frequency_hz: float,
) -> list[dict]:
    dimensions = (length_m, width_m, height_m)
    if any(value <= 0 for value in dimensions):
        raise ValueError("Room dimensions must be positive")
    if speed_of_sound_m_s <= 0 or max_frequency_hz <= 0:
        raise ValueError("Speed of sound and maximum frequency must be positive")

    limits = [
        ceil(2.0 * max_frequency_hz * dimension / speed_of_sound_m_s)
        for dimension in dimensions
    ]
    modes = []
    for nx in range(limits[0] + 1):
        for ny in range(limits[1] + 1):
            for nz in range(limits[2] + 1):
                if (nx, ny, nz) == (0, 0, 0):
                    continue
                frequency = 0.5 * speed_of_sound_m_s * sqrt(
                    (nx / length_m) ** 2
                    + (ny / width_m) ** 2
                    + (nz / height_m) ** 2
                )
                if frequency <= max_frequency_hz:
                    modes.append(
                        {
                            "indices": (nx, ny, nz),
                            "frequency_hz": frequency,
                        }
                    )

    return sorted(
        modes,
        key=lambda mode: (mode["frequency_hz"], mode["indices"]),
    )
