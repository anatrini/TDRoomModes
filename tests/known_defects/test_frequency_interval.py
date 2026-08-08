import numpy as np
import pytest

from analysis.modes import AcousticAnalyzer
from mesh.converter import create_box_mesh
from tests.reference.rectangular_room import analytical_rigid_box_modes


class IntervalMidpointTargetDefect(AssertionError):
    """The current midpoint-target solve returns only 73 of 89 modes."""


@pytest.mark.integration
@pytest.mark.known_defect
@pytest.mark.xfail(
    raises=IntervalMidpointTargetDefect,
    strict=True,
    reason="solver targets the interval midpoint and returns N nearby modes",
)
def test_frequency_range_matches_all_89_rigid_box_modes():
    reference = [
        mode["frequency_hz"]
        for mode in analytical_rigid_box_modes(8.0, 6.0, 3.5, 343.0, 150.0)
        if mode["frequency_hz"] >= 20.0
    ]
    assert len(reference) == 89

    domain = create_box_mesh(8.0, 6.0, 3.5, 15, 12, 8)
    analyzer = AcousticAnalyzer(domain, speed_of_sound=343.0)
    computed = analyzer.compute_modes(num_modes=len(reference), freq_range=(20.0, 150.0))
    computed_frequencies = np.array([mode.frequency for mode in computed])

    assert len(computed_frequencies) > 0
    assert np.isfinite(computed_frequencies).all()
    assert np.all(np.diff(computed_frequencies) >= 0.0)
    assert np.all((20.0 <= computed_frequencies) & (computed_frequencies <= 150.0))
    if (
        len(computed_frequencies) == 73
        and computed_frequencies[0] == pytest.approx(21.4760113702, abs=1e-6)
        and computed_frequencies[-1] == pytest.approx(149.887073525, abs=1e-6)
    ):
        raise IntervalMidpointTargetDefect(
            "midpoint-target extraction returned 73 of 89 interval modes"
        )

    assert len(computed_frequencies) == len(reference)
    # This coarse P1 mesh is allowed 3% relative plus 0.25 Hz absolute error.
    # Every sorted frequency is compared one-to-one, so returning the first mode
    # plus 88 arbitrary in-range values cannot satisfy the specification.
    np.testing.assert_allclose(
        computed_frequencies,
        np.array(reference),
        rtol=0.03,
        atol=0.25,
    )
