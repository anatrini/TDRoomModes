from pathlib import Path
import re
import subprocess
import sys

import pytest
import trimesh


PROJECT_ROOT = Path(__file__).parents[2]


class ResolutionIgnoredDefect(AssertionError):
    """The current CLI produces 1,331 DOFs for both resolutions."""


def run_with_resolution(mesh_path, output_dir, resolution):
    return subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "acoustic_analysis.py"),
            str(mesh_path),
            "--resolution",
            str(resolution),
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


@pytest.mark.integration
@pytest.mark.known_defect
@pytest.mark.xfail(
    raises=ResolutionIgnoredDefect,
    strict=True,
    reason="--resolution is parsed but never passed to mesh conversion",
)
def test_cli_resolution_changes_fem_degrees_of_freedom(tmp_path):
    mesh_path = tmp_path / "cube.stl"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(mesh_path)
    coarse = run_with_resolution(mesh_path, tmp_path / "coarse", 5)
    fine = run_with_resolution(mesh_path, tmp_path / "fine", 20)

    assert coarse.returncode == 0, coarse.stdout + coarse.stderr
    assert fine.returncode == 0, fine.stdout + fine.stderr
    pattern = re.compile(r"FEM mesh created:\s+([\d,]+) DOFs")
    coarse_match = pattern.search(coarse.stdout)
    fine_match = pattern.search(fine.stdout)
    assert coarse_match is not None, coarse.stdout + coarse.stderr
    assert fine_match is not None, fine.stdout + fine.stderr
    coarse_dofs = int(coarse_match.group(1).replace(",", ""))
    fine_dofs = int(fine_match.group(1).replace(",", ""))
    assert coarse_dofs > 0
    assert fine_dofs > 0
    if coarse_dofs == fine_dofs == 1331:
        raise ResolutionIgnoredDefect(
            "--resolution 5 and 20 both produced the current 1,331 DOFs"
        )

    assert fine_dofs > coarse_dofs
