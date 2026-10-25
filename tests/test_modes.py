"""Modes of a rectangular room against the analytical solution
f = c/2 sqrt((nx/L)² + (ny/W)² + (nz/H)²)."""

import itertools

import numpy as np
import pytest

import tdroommodes as trm

C = 343.2
L, W, H = 5.0, 4.0, 3.0


def analytical(f_max):
    f = [C / 2 * np.sqrt((a / L) ** 2 + (b / W) ** 2 + (d / H) ** 2)
         for a, b, d in itertools.product(range(20), repeat=3)]
    return np.sort([x for x in f if 0 < x <= f_max])


@pytest.mark.parametrize("order", [1, 2])
def test_frequencies_within_one_percent(order):
    f_max = 120.0
    room = trm.box(L, W, H, trm.element_size(f_max, C, order))
    modes = trm.compute(room, f_max, C, order)
    exact = analytical(f_max)
    # The FEM overestimates frequencies slightly, so a mode just below f_max can fall above it
    assert len(exact) - 2 <= len(modes) <= len(exact)
    n = len(modes)
    error = np.abs(modes.frequencies - exact[:n]) / exact[:n]
    assert error.max() < 0.01


def test_shapes_are_normalized_and_evaluated_correctly():
    room = trm.box(L, W, H, 0.4)
    modes = trm.compute(room, 60.0, C)
    first = modes.frequencies[0]
    assert first == pytest.approx(C / (2 * L), rel=1e-3)  # axial mode (1, 0, 0)
    points = np.array([[0.5, 2.0, 1.5], [2.0, 1.0, 0.2], [4.9, 3.9, 2.9]])
    values = modes.evaluate(points)[:, 0]
    exact = np.sqrt(2 / room.volume) * np.cos(np.pi * points[:, 0] / L)
    # Same up to the sign of the eigenvector
    assert np.allclose(np.abs(values), np.abs(exact), atol=2e-3)
    assert np.all(np.sign(values) == np.sign(exact)) or np.all(np.sign(values) == -np.sign(exact))


def test_points_outside_are_nan():
    modes = trm.compute(trm.box(L, W, H, 0.6), 50.0, C)
    values = modes.evaluate([[-1.0, 1.0, 1.0], [1.0, 1.0, 1.0]])
    assert np.isnan(values[0]).all() and not np.isnan(values[1]).any()


def test_oblique_mode_decay_matches_sabine():
    """For uniform small absorption, a mode with all three indices non-zero has the decay of
    the Sabine formula: δ = c α S / (8 V)."""
    alpha = 0.02
    modes = trm.compute(trm.box(L, W, H, 0.4), 110.0, C).set_absorption(alpha, humidity=0, temperature=20)
    from tdroommodes import physics
    air = C * physics.air_attenuation(modes.frequencies, 20, 0) / 2
    room = modes.room
    sabine = C * alpha * room.surface_area() / (8 * room.volume)
    # mode (1, 1, 1)
    f111 = C / 2 * np.sqrt(1 / L ** 2 + 1 / W ** 2 + 1 / H ** 2)
    i = np.argmin(np.abs(modes.frequencies - f111))
    assert (modes.decay[i] - air[i]) == pytest.approx(sabine, rel=0.03)


def test_save_and_load(tmp_path):
    modes = trm.compute(trm.box(L, W, H, 0.8), 60.0, C).set_absorption(0.1)
    modes.save(tmp_path / "modes.npz")
    loaded = trm.Modes.load(tmp_path / "modes.npz")
    assert np.allclose(loaded.frequencies, modes.frequencies)
    p = [[1.0, 1.0, 1.0]]
    assert np.allclose(loaded.evaluate(p), modes.evaluate(p), atol=1e-6)
