import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest
import trimesh


PROJECT_ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_cli_writes_json_and_csv_for_watertight_cube(tmp_path):
    mesh_path = tmp_path / "cube.stl"
    output_dir = tmp_path / "results"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(mesh_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "acoustic_analysis.py"),
            str(mesh_path),
            "--modes",
            "5",
            "--freq-range",
            "100",
            "500",
            "--source-position",
            "0",
            "0",
            "0",
            "--no-visualizations",
            "--output",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    mode_data = json.loads((output_dir / "mode_data.json").read_text())
    summary = pd.read_csv(output_dir / "modes_summary.csv")
    assert len(mode_data["modes"]) == 5
    assert len(summary) == 5
    assert not (output_dir / "frequency_spectrum.html").exists()
    assert not (output_dir / "mode_gallery.html").exists()
