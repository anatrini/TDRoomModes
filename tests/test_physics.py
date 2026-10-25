import numpy as np
import pytest

from tdroommodes import materials, physics


@pytest.mark.parametrize("frequency, db_per_km", [
    (125, 0.44), (250, 1.31), (500, 2.73), (1000, 4.66), (2000, 9.89), (4000, 29.7),
])
def test_air_attenuation_iso_9613_1(frequency, db_per_km):
    """ISO 9613-1:1993, table 1, 20 °C, 50 % relative humidity, 101.325 kPa."""
    assert physics.air_attenuation_db(frequency, 20, 50) * 1000 == pytest.approx(db_per_km, rel=0.01)


def test_sabine_constant():
    # T = 0.161 V / A at c = 343 m/s
    assert physics.sabine_t60(100.0, 10.0, c=343.0) == pytest.approx(0.161 * 100 / 10, rel=2e-3)


def test_eyring_tends_to_sabine_for_small_absorption():
    V, S = 200.0, 220.0
    assert physics.eyring_t60(V, S, 0.01) == pytest.approx(physics.sabine_t60(V, 0.01 * S), rel=0.01)


def test_critical_distance():
    # r_c = 0.057 sqrt(V / T) with Sabine's T is the same as sqrt(A / 16π)
    V, A = 500.0, 60.0
    T = physics.sabine_t60(V, A, c=343.0)
    assert physics.critical_distance(A) == pytest.approx(0.057 * np.sqrt(V / T), rel=0.01)


def test_t60_and_decay():
    # 60 dB of energy decay at T60
    delta = 3.0
    T = physics.t60_from_decay(delta)
    assert 20 * np.log10(np.exp(-delta * T)) == pytest.approx(-60)


def test_admittance_small_absorption():
    assert physics.admittance_from_alpha(0.01)[0] == pytest.approx(0.01 / 8, rel=0.03)


def test_admittance_inverts_paris_formula():
    for a in (0.05, 0.3, 0.7, 0.9):
        beta = physics.admittance_from_alpha(a)[0]
        assert physics._statistical_absorption(1 / beta) == pytest.approx(a, rel=1e-6)


def test_materials():
    assert len(materials.list_materials()) >= 20
    bands = materials.resolve({"floor": "wood_floor", "walls": 0.1, "ceiling": [0.2] * 6},
                              ["floor", "walls", "ceiling"])
    assert materials.at_frequency(bands["floor"], 50.0) == bands["floor"][0]  # below 125 Hz
    mid = materials.at_frequency(bands["floor"], np.sqrt(125 * 250))
    assert mid == pytest.approx((bands["floor"][0] + bands["floor"][1]) / 2)
    with pytest.raises(ValueError):
        materials.resolve({"floor": 0.1}, ["floor", "walls"])
