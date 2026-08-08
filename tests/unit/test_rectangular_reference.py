import pytest

from tests.reference.rectangular_room import analytical_rigid_box_modes


def test_first_axis_modes_for_8_by_6_by_3_5_room():
    modes = analytical_rigid_box_modes(8.0, 6.0, 3.5, 343.0, 50.0)
    by_index = {mode["indices"]: mode["frequency_hz"] for mode in modes}

    assert by_index[(1, 0, 0)] == pytest.approx(21.4375)
    assert by_index[(0, 1, 0)] == pytest.approx(28.583333333333332)
    assert by_index[(0, 0, 1)] == pytest.approx(49.0)


def test_reference_excludes_zero_mode_and_sorts_deterministically():
    modes = analytical_rigid_box_modes(2.0, 2.0, 2.0, 343.0, 200.0)

    assert (0, 0, 0) not in [mode["indices"] for mode in modes]
    assert modes == sorted(
        modes,
        key=lambda mode: (mode["frequency_hz"], mode["indices"]),
    )


@pytest.mark.parametrize("dimension", [0.0, -1.0])
def test_reference_rejects_non_positive_dimensions(dimension):
    with pytest.raises(ValueError, match="Room dimensions must be positive"):
        analytical_rigid_box_modes(dimension, 6.0, 3.5, 343.0, 150.0)
