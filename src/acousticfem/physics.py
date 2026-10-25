"""Room acoustic formulas.

Conventions used throughout the package:

- Pressure decays as exp(-delta * t); delta is the amplitude decay constant [1/s].
  Energy decays as exp(-2 * delta * t), so a 60 dB decay takes T60 = 3 ln(10) / delta.
- Air attenuation m is the energy attenuation coefficient [1/m], as in the Sabine
  term 4 m V (ISO 3382-2, ISO 354).

References:
    H. Kuttruff, Room Acoustics, 6th ed., CRC Press, 2016.
    ISO 9613-1:1993, Attenuation of sound during propagation outdoors, part 1.
"""

import numpy as np
from scipy.optimize import brentq

LN_1E6 = 6.0 * np.log(10.0)  # ln of the energy ratio of 60 dB
DB_PER_NEPER_ENERGY = 10.0 / np.log(10.0)  # 4.343: dB per unit of energy exponent


def speed_of_sound(temperature: float = 20.0) -> float:
    """Speed of sound in dry air [m/s] at `temperature` [°C]."""
    return 331.3 * np.sqrt(1.0 + temperature / 273.15)


def air_attenuation_db(frequency, temperature: float = 20.0, humidity: float = 50.0,
                       pressure: float = 101.325):
    """Atmospheric attenuation [dB/m] after ISO 9613-1:1993, equations (3)-(5) and annex B.

    Args:
        frequency: frequency or array of frequencies [Hz]
        temperature: air temperature [°C]
        humidity: relative humidity [%]
        pressure: atmospheric pressure [kPa]
    """
    f = np.asarray(frequency, dtype=float)
    T = temperature + 273.15
    T0, T01, pr = 293.15, 273.16, 101.325
    pa = pressure / pr

    # Molar concentration of water vapour [%] (annex B)
    C = -6.8346 * (T01 / T) ** 1.261 + 4.6151
    h = humidity * 10.0 ** C / pa

    # Relaxation frequencies of oxygen and nitrogen [Hz]
    fr_o = pa * (24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h))
    fr_n = pa * (T / T0) ** -0.5 * (9.0 + 280.0 * h * np.exp(-4.170 * ((T / T0) ** (-1.0 / 3.0) - 1.0)))

    return 8.686 * f ** 2 * (
        1.84e-11 / pa * (T / T0) ** 0.5
        + (T / T0) ** -2.5 * (
            0.01275 * np.exp(-2239.1 / T) / (fr_o + f ** 2 / fr_o)
            + 0.1068 * np.exp(-3352.0 / T) / (fr_n + f ** 2 / fr_n)
        )
    )


def air_attenuation(frequency, temperature: float = 20.0, humidity: float = 50.0,
                    pressure: float = 101.325):
    """Energy attenuation coefficient m [1/m] of air, the m of the Sabine term 4 m V."""
    return air_attenuation_db(frequency, temperature, humidity, pressure) / DB_PER_NEPER_ENERGY


def sabine_t60(volume: float, equivalent_area: float, air_m: float = 0.0, c: float = 343.0) -> float:
    """Sabine reverberation time [s]: T = 24 ln(10) V / (c (A + 4 m V)).

    Args:
        volume: room volume [m³]
        equivalent_area: equivalent absorption area A = sum(alpha_i S_i) [m²]
        air_m: energy attenuation coefficient of air [1/m]
        c: speed of sound [m/s]
    """
    total = equivalent_area + 4.0 * air_m * volume
    return np.inf if total <= 0 else 24.0 * np.log(10.0) * volume / (c * total)


def eyring_t60(volume: float, surface_area: float, alpha_mean: float, air_m: float = 0.0,
               c: float = 343.0) -> float:
    """Eyring reverberation time [s]: T = 24 ln(10) V / (c (-S ln(1 - alpha) + 4 m V))."""
    if not 0.0 <= alpha_mean < 1.0:
        raise ValueError(f"mean absorption coefficient must be in [0, 1), got {alpha_mean}")
    total = -surface_area * np.log1p(-alpha_mean) + 4.0 * air_m * volume
    return np.inf if total <= 0 else 24.0 * np.log(10.0) * volume / (c * total)


def schroeder_frequency(volume: float, t60: float) -> float:
    """Schroeder frequency [Hz]: f_s = 2000 sqrt(T60 / V) (Kuttruff, Room Acoustics, ch. 3)."""
    if volume <= 0 or t60 <= 0:
        raise ValueError("volume and T60 must be positive")
    return 2000.0 * np.sqrt(t60 / volume)


def critical_distance(equivalent_area: float, directivity: float = 1.0) -> float:
    """Critical distance [m]: r_c = sqrt(Q A / (16 pi)), A the equivalent absorption area."""
    return np.sqrt(directivity * equivalent_area / (16.0 * np.pi))


def t60_from_decay(delta):
    """T60 [s] from the amplitude decay constant delta [1/s]."""
    delta = np.asarray(delta, dtype=float)
    with np.errstate(divide="ignore"):
        return LN_1E6 / (2.0 * delta)


def mode_count(frequency: float, volume: float, surface_area: float, c: float = 343.0) -> float:
    """Expected number of modes below `frequency` in a room with rigid walls.

    Weyl's law with the first boundary correction for Neumann conditions
    (Kuttruff, Room Acoustics, ch. 3, without the edge term, which depends on the shape).
    """
    return (4.0 * np.pi * volume * frequency ** 3 / (3.0 * c ** 3)
            + np.pi * surface_area * frequency ** 2 / (4.0 * c ** 2))


def _statistical_absorption(zeta: float) -> float:
    """Random-incidence absorption of a locally reacting wall with real normalized impedance zeta
    (Paris formula for a real impedance, Kuttruff, Room Acoustics, ch. 2)."""
    return 8.0 / zeta * (1.0 + 1.0 / (1.0 + zeta) - 2.0 / zeta * np.log1p(zeta))


ZETA_AT_MAX_ALPHA = 1.567
MAX_STATISTICAL_ALPHA = _statistical_absorption(ZETA_AT_MAX_ALPHA)  # 0.951


def admittance_from_alpha(alpha):
    """Real normalized wall admittance beta = rho c / Z for a random-incidence absorption alpha.

    Inverts the Paris formula on the reflective branch (zeta > 1.567), the branch of real
    walls. For small alpha this gives beta ≈ alpha / 8. alpha is clipped to 0.95, the
    maximum a locally reacting wall with real impedance can reach.
    """
    alpha = np.atleast_1d(np.asarray(alpha, dtype=float))
    beta = np.zeros_like(alpha)
    for i, a in enumerate(alpha.flat):
        a = min(a, MAX_STATISTICAL_ALPHA - 1e-9)
        if a <= 0:
            continue
        zeta = brentq(lambda z: _statistical_absorption(z) - a, ZETA_AT_MAX_ALPHA, 1e12)
        beta.flat[i] = 1.0 / zeta
    return beta
