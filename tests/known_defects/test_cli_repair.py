from pathlib import Path
import json
import subprocess
import sys

import pytest
import trimesh


PROJECT_ROOT = Path(__file__).parents[2]


class RepairKeywordDefect(AssertionError):
    """The CLI passes the current unsupported repair keyword."""


@pytest.mark.integration
@pytest.mark.known_defect
@pytest.mark.xfail(
    raises=RepairKeywordDefect,
    strict=True,
    reason="CLI passes unsupported max_frequency to MeshImporter.repair_mesh",
)
def test_cli_repair_closes_non_watertight_cube_and_writes_results(tmp_path):
    mesh_path = tmp_path / "open-cube.stl"
    output_dir = tmp_path / "results"
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    open_cube = trimesh.Trimesh(
        vertices=cube.vertices.copy(), faces=cube.faces[:-2].copy(), process=False
    )
    assert not open_cube.is_watertight
    open_cube.export(mesh_path)
    assert not trimesh.load_mesh(mesh_path, process=False).is_watertight

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "acoustic_analysis.py"),
            str(mesh_path),
            "--repair",
            "--modes",
            "1",
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

    combined_output = completed.stdout + completed.stderr
    assert "Watertight: ✗ No" in completed.stdout
    assert "Repairing mesh..." in completed.stdout
    current_error = (
        "MeshImporter.repair_mesh() got an unexpected keyword argument "
        "'max_frequency'"
    )
    if completed.returncode == 1 and current_error in combined_output:
        raise RepairKeywordDefect(current_error)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "✓ Mesh repaired:" in completed.stdout
    assert "watertight: True" in completed.stdout
    mode_data = json.loads((output_dir / "mode_data.json").read_text())
    assert len(mode_data["modes"]) == 1
    assert (output_dir / "modes_summary.csv").is_file()
