import json
from pathlib import Path

import numpy as np
import pytest

from analysis.modes import AcousticAnalyzer
from mesh.converter import create_box_mesh


GOLDEN_PATH = (
    Path(__file__).parents[1] / "golden" / "box_8x6x3_5_baseline.json"
)


@pytest.mark.integration
def test_current_box_modal_and_room_metric_baseline():
    expected = json.loads(GOLDEN_PATH.read_text())
    mesh_spec = expected["mesh"]
    analysis_spec = expected["analysis"]
    domain = create_box_mesh(
        mesh_spec["length_m"],
        mesh_spec["width_m"],
        mesh_spec["height_m"],
        mesh_spec["nx"],
        mesh_spec["ny"],
        mesh_spec["nz"],
    )
    analyzer = AcousticAnalyzer(
        domain,
        speed_of_sound=analysis_spec["speed_of_sound_m_s"],
        temperature=analysis_spec["temperature_c"],
        humidity=analysis_spec["relative_humidity_percent"],
    )

    modes = analyzer.compute_modes(
        num_modes=analysis_spec["requested_modes"],
        freq_range=tuple(analysis_spec["frequency_range_hz"]),
    )
    analyzer.calculate_t60(
        alpha_avg=analysis_spec["average_absorption"],
        method=analysis_spec["t60_method"],
    )

    assert analyzer.volume == pytest.approx(expected["geometry"]["volume_m3"])
    assert analyzer.surface_area == pytest.approx(
        expected["geometry"]["surface_area_m2"]
    )
    np.testing.assert_allclose(
        [mode.frequency for mode in modes],
        expected["frequencies_hz"],
        rtol=5e-6,
        atol=1e-4,
    )
    metrics = expected["room_metrics"]
    assert analyzer.room_properties.schroeder_freq() == pytest.approx(
        metrics["schroeder_frequency_hz"], rel=1e-10
    )
    assert analyzer.room_properties.critical_dist() == pytest.approx(
        metrics["critical_distance_m"], rel=1e-10
    )
    assert analyzer.room_properties.t60(1000) == pytest.approx(
        metrics["t60_at_1khz_s"], rel=1e-10
    )
