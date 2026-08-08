# AcousticFEM Phase 0 Baseline and Test Harness Implementation Plan

> **Required execution skill:** Use `superpowers:executing-plans` to implement this plan task by task. Use `superpowers:test-driven-development` for every test/code change and `superpowers:verification-before-completion` before reporting Phase 0 complete.

**Goal:** Freeze the currently observed AcousticFEM behavior in reproducible tests, add a trustworthy rectangular-room analytical reference, and capture known defects as strict expected failures before replacing the engineering kernel.

**Completion standard:** The pinned Apple Silicon environment can run pytest; all environment/reference/baseline/CLI smoke tests pass; four current defects are reproduced as strict `xfail`; the complete Phase 0 verification command exits 0; no production solver behavior is changed.

**Scope boundary:** This plan does not implement Gmsh/OpenCASCADE geometry, boundary tags, impedance, forced response, source superposition, adaptive sweeps, or engineering reports. Those remain Phases 1–5 in the approved design specification.

**Architecture:** Add a thin pytest layer around the current public Python and CLI interfaces. Keep an independent closed-form rigid-box reference under `tests/reference`, store the already observed 8 m × 6 m × 3.5 m result as a golden snapshot, and isolate invalid current behavior in `tests/known_defects` with `xfail(strict=True)`. Pin the direct dependencies used to reproduce the baseline on `osx-arm64` while retaining the existing portable environment file.

**Tech stack:** Python 3.11, pytest 8.4, NumPy, pandas, trimesh, FEniCSx/DOLFINx 0.11, PETSc/SLEPc, MPICH, YAML/JSON.

**Source design:** [2026-08-08-private-cinema-engineering-fem-design.md](/Users/peterzhoumacmini/Desktop/AcousticFEM-main/docs/superpowers/specs/2026-08-08-private-cinema-engineering-fem-design.md)

**Repository note:** `/Users/peterzhoumacmini/Desktop/AcousticFEM-main` currently has no `.git` directory. Do not run `git init`. Each task therefore ends with a file/status verification checkpoint instead of a commit. If the user later supplies a proper clone, make one commit per task using the suggested commit message.

---

## Task 1: Pin the Phase 0 runtime and install the test harness

**Files:**

- Modify: `environment.yml`
- Create: `environment-phase0-osx-arm64.yml`
- Create: `pyproject.toml`
- Create: `tests/test_environment.py`

### Step 1: Write the failing environment smoke test

Create `tests/test_environment.py`:

```python
import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "dolfinx",
        "mpi4py",
        "petsc4py",
        "slepc4py",
        "numpy",
        "scipy",
        "pandas",
        "trimesh",
        "meshio",
        "pyvista",
        "plotly",
        "matplotlib",
        "yaml",
        "tqdm",
        "h5py",
        "pymeshlab",
    ],
)
def test_required_runtime_module_imports(module_name):
    assert importlib.import_module(module_name) is not None
```

### Step 2: Confirm the test runner is absent

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/test_environment.py -q
```

Expected: fail with `No module named pytest`.

### Step 3: Configure pytest

Create `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
addopts = "-ra --strict-markers"
markers = [
  "integration: invokes FEniCSx or the AcousticFEM CLI",
  "known_defect: executable specification for a confirmed current defect",
]
```

### Step 4: Add pytest to the portable environment

Append this direct dependency beneath `h5py>=3.8` in `environment.yml`:

```yaml
  # Test harness
  - pytest>=8,<9
```

Do not pin the other portable dependencies in this file; it remains the cross-platform authoring environment.

### Step 5: Add the reproducible Apple Silicon baseline environment

Create `environment-phase0-osx-arm64.yml`:

```yaml
name: acoustics-phase0
channels:
  - conda-forge
dependencies:
  - python=3.11.15
  - fenics-dolfinx=0.11.0
  - mpich=5.0.1
  - numpy=2.4.6
  - scipy=1.17.1
  - pandas=3.0.5
  - trimesh=5.0.0
  - meshio=5.3.5
  - pyvista=0.48.4
  - plotly=6.9.0
  - matplotlib=3.11.1
  - pyyaml=6.0.3
  - tqdm=4.70.0
  - h5py=3.16.0
  - pytest=8.4.2
  - pip
  - pip:
      - pymeshlab==2025.7.post1
```

This is a direct-dependency reproduction manifest, not a transitive package lock and not a claim of cross-platform reproducibility.

### Step 6: Update the existing environment and run the test

Run:

```bash
/Users/peterzhoumacmini/.local/bin/micromamba install -r /Users/peterzhoumacmini/.micromamba -n acoustics -c conda-forge 'pytest=8.4.2' -y
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/test_environment.py -q
```

Expected: `16 passed`.

### Step 7: Verify the checkpoint

Run:

```bash
rg -n "pytest|fenics-dolfinx|pymeshlab" environment.yml environment-phase0-osx-arm64.yml pyproject.toml
```

Expected: pytest appears in both manifests/configuration; all Phase 0 direct dependency pins are visible.

Suggested commit if a valid Git checkout is restored: `test: add phase0 runtime harness`

---

## Task 2: Add an independent analytical rigid-box reference

**Files:**

- Create: `tests/reference/__init__.py`
- Create: `tests/reference/rectangular_room.py`
- Create: `tests/unit/test_rectangular_reference.py`

### Step 1: Write the failing reference tests

Create `tests/unit/test_rectangular_reference.py`:

```python
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
```

Create an empty `tests/reference/__init__.py` so the helper has an explicit package boundary.

### Step 2: Run the test to verify it fails

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/unit/test_rectangular_reference.py -q
```

Expected: fail during collection because `tests.reference.rectangular_room` does not exist.

### Step 3: Implement the minimal analytical helper

Create `tests/reference/rectangular_room.py`:

```python
from math import ceil, sqrt


def analytical_rigid_box_modes(
    length_m: float,
    width_m: float,
    height_m: float,
    speed_of_sound_m_s: float,
    max_frequency_hz: float,
) -> list[dict]:
    dimensions = (length_m, width_m, height_m)
    if any(value <= 0 for value in dimensions):
        raise ValueError("Room dimensions must be positive")
    if speed_of_sound_m_s <= 0 or max_frequency_hz <= 0:
        raise ValueError("Speed of sound and maximum frequency must be positive")

    limits = [
        ceil(2.0 * max_frequency_hz * dimension / speed_of_sound_m_s)
        for dimension in dimensions
    ]
    modes = []
    for nx in range(limits[0] + 1):
        for ny in range(limits[1] + 1):
            for nz in range(limits[2] + 1):
                if (nx, ny, nz) == (0, 0, 0):
                    continue
                frequency = 0.5 * speed_of_sound_m_s * sqrt(
                    (nx / length_m) ** 2
                    + (ny / width_m) ** 2
                    + (nz / height_m) ** 2
                )
                if frequency <= max_frequency_hz:
                    modes.append(
                        {
                            "indices": (nx, ny, nz),
                            "frequency_hz": frequency,
                        }
                    )

    return sorted(
        modes,
        key=lambda mode: (mode["frequency_hz"], mode["indices"]),
    )
```

### Step 4: Run the unit test

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/unit/test_rectangular_reference.py -q
```

Expected: `4 passed`.

### Step 5: Verify the checkpoint

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/unit -q
```

Expected: all unit tests pass.

Suggested commit if a valid Git checkout is restored: `test: add analytical rigid box reference`

---

## Task 3: Freeze the observed 8 m × 6 m × 3.5 m FEM baseline

**Files:**

- Create: `tests/golden/box_8x6x3_5_baseline.json`
- Create: `tests/integration/test_current_box_baseline.py`

### Step 1: Add the golden snapshot

Create `tests/golden/box_8x6x3_5_baseline.json`:

```json
{
  "provenance": {
    "captured_on": "2026-08-08",
    "platform": "macOS osx-arm64",
    "fenics_dolfinx": "0.11.0",
    "python": "3.11.15",
    "status": "current_behavior_baseline_not_engineering_validation"
  },
  "mesh": {
    "length_m": 8.0,
    "width_m": 6.0,
    "height_m": 3.5,
    "nx": 15,
    "ny": 12,
    "nz": 8
  },
  "analysis": {
    "speed_of_sound_m_s": 343.0,
    "temperature_c": 20.0,
    "relative_humidity_percent": 50.0,
    "frequency_range_hz": [20.0, 150.0],
    "requested_modes": 30,
    "average_absorption": 0.15,
    "t60_method": "eyring"
  },
  "geometry": {
    "volume_m3": 168.0,
    "surface_area_m2": 194.0
  },
  "room_metrics": {
    "schroeder_frequency_hz": 142.91901269488,
    "critical_distance_m": 0.30748317027115485,
    "t60_at_1khz_s": 0.8578854559665294
  },
  "frequencies_hz": [
    54.04626754846856,
    57.42676040492077,
    57.828280480759084,
    61.60287452370839,
    62.06817310454263,
    65.31045762517104,
    66.46505689622666,
    71.87687195888071,
    72.84713924615788,
    73.62582448590595,
    77.21124935495824,
    80.60347109621667,
    83.39908147939894,
    87.88346522794855,
    88.23394472906999,
    88.67681334399832,
    89.16957006738409,
    90.46497962965279,
    91.02991396192486,
    93.87290262991662,
    100.00799429693946,
    100.44443824717685,
    102.75671860678224,
    102.96174911770669,
    103.45480020273028,
    103.94715751279531,
    105.36379567658243,
    105.6277360427017,
    107.65172701234331,
    108.06403928879361
  ]
}
```

### Step 2: Write the integration test

Create `tests/integration/test_current_box_baseline.py`:

```python
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
```

### Step 3: Prove the test detects drift

Temporarily change the first golden frequency locally from `54.04626754846856` to `55.0`, run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/integration/test_current_box_baseline.py -q
```

Expected: one numerical mismatch failure. Revert only that temporary test-data edit using `apply_patch`.

### Step 4: Run against the authentic snapshot

Run the same pytest command again.

Expected: `1 passed`.

### Step 5: Verify the checkpoint

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/test_environment.py tests/unit tests/integration/test_current_box_baseline.py -q
```

Expected: all tests pass.

Suggested commit if a valid Git checkout is restored: `test: freeze current rectangular room baseline`

---

## Task 4: Add an end-to-end CLI smoke test

**Files:**

- Create: `tests/integration/test_cli_smoke.py`

### Step 1: Write the CLI smoke test

Create `tests/integration/test_cli_smoke.py`:

```python
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
```

### Step 2: Run the new test

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/integration/test_cli_smoke.py -q
```

Expected: `1 passed` and no files are written outside pytest's temporary directory.

### Step 3: Verify the complete passing integration baseline

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/integration -q
```

Expected: `2 passed`.

Suggested commit if a valid Git checkout is restored: `test: add acoustic analysis cli smoke coverage`

---

## Task 5: Capture four confirmed defects as strict expected failures

**Files:**

- Create: `tests/known_defects/test_geometry_conversion.py`
- Create: `tests/known_defects/test_cli_repair.py`
- Create: `tests/known_defects/test_frequency_interval.py`
- Create: `tests/known_defects/test_resolution_option.py`

These tests must describe the required behavior, not encode the defective behavior. `strict=True` ensures pytest reports an unexpected pass as a failure so the test cannot silently remain marked after a fix.

### Step 1: Specify preservation of non-box geometry

Create `tests/known_defects/test_geometry_conversion.py`:

```python
import numpy as np
import pytest
import trimesh

from mesh.converter import trimesh_to_fenicsx


@pytest.mark.integration
@pytest.mark.known_defect
@pytest.mark.xfail(
    strict=True,
    reason="trimesh_to_fenicsx currently replaces input geometry with its bounding box",
)
def test_sphere_conversion_does_not_create_box_corner_vertices():
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    domain = trimesh_to_fenicsx(sphere)

    maximum_radius = np.linalg.norm(domain.geometry.x, axis=1).max()
    assert maximum_radius <= 1.01
```

### Step 2: Specify a functional `--repair` path

Create `tests/known_defects/test_cli_repair.py`:

```python
from pathlib import Path
import subprocess
import sys

import pytest
import trimesh


PROJECT_ROOT = Path(__file__).parents[2]


@pytest.mark.integration
@pytest.mark.known_defect
@pytest.mark.xfail(
    strict=True,
    reason="CLI passes unsupported max_frequency to MeshImporter.repair_mesh",
)
def test_cli_repair_completes_for_watertight_cube(tmp_path):
    mesh_path = tmp_path / "cube.stl"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(mesh_path)
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
            str(tmp_path / "results"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
```

### Step 3: Specify interval-complete modal extraction

Create `tests/known_defects/test_frequency_interval.py`:

```python
import pytest

from analysis.modes import AcousticAnalyzer
from mesh.converter import create_box_mesh
from tests.reference.rectangular_room import analytical_rigid_box_modes


@pytest.mark.integration
@pytest.mark.known_defect
@pytest.mark.xfail(
    strict=True,
    reason="solver targets the interval midpoint and returns N nearby modes",
)
def test_frequency_range_includes_the_first_rigid_box_mode():
    domain = create_box_mesh(8.0, 6.0, 3.5, 15, 12, 8)
    analyzer = AcousticAnalyzer(domain, speed_of_sound=343.0)
    computed = analyzer.compute_modes(num_modes=30, freq_range=(20.0, 150.0))
    reference = analytical_rigid_box_modes(8.0, 6.0, 3.5, 343.0, 150.0)
    first_reference_hz = reference[0]["frequency_hz"]

    assert computed[0].frequency == pytest.approx(first_reference_hz, rel=0.05)
```

### Step 4: Specify that `--resolution` controls discretization

Create `tests/known_defects/test_resolution_option.py`:

```python
from pathlib import Path
import re
import subprocess
import sys

import pytest
import trimesh


PROJECT_ROOT = Path(__file__).parents[2]


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
    coarse_dofs = int(pattern.search(coarse.stdout).group(1).replace(",", ""))
    fine_dofs = int(pattern.search(fine.stdout).group(1).replace(",", ""))
    assert fine_dofs > coarse_dofs
```

### Step 5: Run the defect specifications

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest tests/known_defects -q
```

Expected: `4 xfailed`, exit code 0. Any ordinary failure means the defect was not captured correctly; any `XPASS(strict)` means remove the marker only after verifying the implementation that fixed it.

### Step 6: Verify normal tests remain green

Run:

```bash
/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python -m pytest -m 'not known_defect' -q
```

Expected: all selected tests pass.

Suggested commit if a valid Git checkout is restored: `test: characterize confirmed acousticfem defects`

---

## Task 6: Add the Phase 0 verification entry point and baseline record

**Files:**

- Create: `scripts/verify_phase0.sh`
- Create: `docs/baselines/phase0-current-behavior.md`

### Step 1: Add the verification script

Create `scripts/verify_phase0.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${ACOUSTICFEM_PYTHON:-/Users/peterzhoumacmini/.micromamba/envs/acoustics/bin/python}"

cd "$project_dir"
"$python_bin" -m pytest -m 'not known_defect' -q
"$python_bin" -m pytest tests/known_defects -q
```

Do not make the script depend on shell activation. It permits an alternate interpreter only through the task-specific `ACOUSTICFEM_PYTHON` variable.

### Step 2: Add the baseline record

Create `docs/baselines/phase0-current-behavior.md` with these sections and facts:

```markdown
# Phase 0 Current-Behavior Baseline

Captured: 2026-08-08 on macOS Apple Silicon.

## What is verified

- The pinned direct dependency set imports successfully.
- The existing 8 m × 6 m × 3.5 m box calculation reproduces 30 stored modal frequencies and its current statistical room metrics within stated tolerances.
- The CLI processes a watertight cube and writes JSON/CSV output.
- The independent rigid-box helper reproduces closed-form axis-mode frequencies.

## Confirmed known defects

- Arbitrary imported geometry is replaced with its axis-aligned bounding box.
- `--repair` raises a `TypeError` because the CLI passes an unsupported keyword.
- `--freq-range` targets the midpoint and does not enumerate the complete interval.
- `--resolution` is parsed but does not change the FEM mesh.

Each item is represented by a strict expected-failure test under `tests/known_defects`.

## Reproduction

```bash
bash scripts/verify_phase0.sh
```

Expected result: all normal tests pass and exactly four known-defect tests are reported as xfailed.

## Engineering status

This baseline proves repeatability of the current software behavior only. It does not validate complex geometry, material boundary conditions, absolute SPL, subwoofer frequency response, convergence, project calibration, standards compliance, or production readiness.
```

When creating the actual Markdown file, use a four-tilde outer fence around the displayed content or omit the outer fence so the embedded reproduction fence remains valid.

### Step 3: Run the complete Phase 0 verification

Run:

```bash
bash scripts/verify_phase0.sh
```

Expected:

- environment, analytical reference, golden baseline, and CLI smoke tests all pass;
- exactly four tests are reported as `XFAIL`;
- overall exit code is 0.

### Step 4: Confirm no solver implementation changed

Run:

```bash
find src -type f -newer docs/superpowers/plans/2026-08-08-phase0-baseline-and-test-harness.md -print
```

Expected: no files. If filesystem timestamps are unreliable, inspect `src/` and confirm no implementation file was edited during Phase 0.

### Step 5: Verify the final artifact set

Run:

```bash
find tests scripts docs/baselines -type f | sort
```

Expected: the files named in Tasks 1–6 are present; pytest cache files may also appear and should remain untracked/ignored when a valid Git checkout is restored.

Suggested commit if a valid Git checkout is restored: `docs: record verified phase0 baseline`

---

## Phase 0 handoff gate

Do not begin Phase 1 until all of the following are true:

1. `bash scripts/verify_phase0.sh` exits 0.
2. Normal tests have no skips, failures, or errors.
3. The known-defect suite reports exactly four strict xfails.
4. No file under `src/` or `acoustic_analysis.py` changed.
5. The baseline record explicitly retains the non-engineering-validation disclaimer.

Once this gate passes, create a separate Phase 1 plan for the parametric `ProjectSpec`, OpenCASCADE/Gmsh air-volume construction, stable Physical Groups, DOLFINx cell/facet tag import, and hard geometry/mesh gates.
