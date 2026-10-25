"""Sound fields from precomputed modes, with numpy only.

This module does not import scikit-fem, gmsh or SciPy, so it also runs inside environments
such as TouchDesigner, given the arrays saved by `Modes.save` or `export.grid`.

Below the Schroeder frequency the pressure in a room is the sum of its modes:

    p(x, t) = Σ_n a_n φ_n(x) e^{-δ_n t} cos(ω'_n t + θ_n),   ω'_n = sqrt(ω_n² - δ_n²)

The shapes φ_n are computed once; everything here is a weighted sum of them, cheap enough
to evaluate per frame. Mode shapes are normalized so that ∫ φ_n² dV = 1, and a point source
of volume velocity q at x_s excites mode n in proportion to c² φ_n(x_s).
"""

import numpy as np


def load(path) -> dict:
    """Arrays saved by `Modes.save` or `export.grid` (a .npz file)."""
    with np.load(path) as data:
        return {k: data[k] for k in data.files}


def _damped(omega, delta):
    return np.sqrt(np.maximum(omega ** 2 - delta ** 2, 0.0))


def transfer_function(frequencies, mode_frequencies, decay, phi_source, phi_receiver,
                      c: float = 343.2, rho: float = 1.204):
    """Complex pressure at the receiver per unit volume velocity of the source [Pa s/m³].

    p(ω) = iωρc² Σ_n φ_n(x_s) φ_n(x_r) / (ω_n² - ω² + 2iδ_n ω)

    Args:
        frequencies: frequencies to evaluate [Hz]
        mode_frequencies, decay: modal frequencies [Hz] and decay constants [1/s]
        phi_source, phi_receiver: mode shapes at source and receiver
    """
    w = 2 * np.pi * np.asarray(frequencies, dtype=float)[:, None]
    wn = 2 * np.pi * np.asarray(mode_frequencies)[None, :]
    terms = phi_source * phi_receiver / (wn ** 2 - w ** 2 + 2j * np.asarray(decay) * w)
    return 1j * w[:, 0] * rho * c ** 2 * terms.sum(axis=1)


def impulse_response(duration: float, sample_rate: int, mode_frequencies, decay, phi_source,
                     phi_receiver, c: float = 343.2, normalize: bool = True):
    """Modal part of the room impulse response at the receiver, as audio samples.

    Response to an impulse of volume acceleration at the source:
    h(t) = c² Σ_n φ_n(x_s) φ_n(x_r) e^{-δ_n t} sin(ω'_n t) / ω'_n.
    It contains only the modes, so only frequencies up to the highest computed mode.
    """
    t = np.arange(int(duration * sample_rate)) / sample_rate
    wn = 2 * np.pi * np.asarray(mode_frequencies)
    wd = _damped(wn, np.asarray(decay))
    h = np.zeros_like(t)
    for a, d, w in zip(c ** 2 * phi_source * phi_receiver, decay, wd):
        h += a * np.exp(-d * t) * np.sin(w * t) / w
    if normalize and np.abs(h).max() > 0:
        h /= np.abs(h).max()
    return h


def free_decay(t: float, shapes, mode_frequencies, decay, weights, phases=None):
    """Field at time t after an excitation that set mode n to amplitude weights[n].

    Args:
        t: time [s]
        shapes: mode shapes at the points, array (..., n_modes)
        weights: amplitude of each mode at t = 0, e.g. `point_source_weights`
        phases: phase of each mode [rad], zero by default

    Returns:
        array (...) of pressures
    """
    wn = 2 * np.pi * np.asarray(mode_frequencies)
    phases = 0.0 if phases is None else phases
    a = weights * np.exp(-np.asarray(decay) * t) * np.cos(_damped(wn, np.asarray(decay)) * t + phases)
    return shapes @ a


def point_source_weights(phi_source, mode_frequencies, c: float = 343.2):
    """Mode amplitudes after an impulse at the source: c² φ_n(x_s) / ω_n."""
    return c ** 2 * np.asarray(phi_source) / (2 * np.pi * np.asarray(mode_frequencies))


def steady_state(frequency: float, shapes, mode_frequencies, decay, phi_source, c: float = 343.2):
    """Complex field of a source playing a sine at `frequency`: every point oscillates as
    Re(P e^{iωt}). Use `steady_state_frame` for the pressure at a given time."""
    w = 2 * np.pi * frequency
    wn = 2 * np.pi * np.asarray(mode_frequencies)
    coefficients = c ** 2 * np.asarray(phi_source) / (wn ** 2 - w ** 2 + 2j * np.asarray(decay) * w)
    return shapes @ coefficients


def steady_state_frame(field, frequency: float, t: float):
    """Real pressure at time t of a complex steady-state field."""
    return np.real(field * np.exp(2j * np.pi * frequency * t))
