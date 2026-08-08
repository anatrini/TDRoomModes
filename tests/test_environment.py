import importlib
import importlib.metadata
from pathlib import Path
import platform
import re
import sys

from mpi4py import MPI
import pytest
import yaml


PROJECT_ROOT = Path(__file__).parents[1]
PHASE0_MANIFEST = PROJECT_ROOT / "environment-phase0-osx-arm64.yml"


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


def test_phase0_manifest_matches_osx_arm64_runtime():
    manifest = yaml.safe_load(PHASE0_MANIFEST.read_text())
    assert manifest["name"] == "acoustics-phase0"
    assert sys.platform == "darwin"
    assert platform.machine() == "arm64"
    assert Path(sys.executable).parents[1].name == manifest["name"]

    pinned = {}
    for dependency in manifest["dependencies"]:
        if isinstance(dependency, str) and "=" in dependency:
            name, version = dependency.split("=", 1)
            pinned[name] = version
        elif isinstance(dependency, dict):
            for pip_requirement in dependency.get("pip", []):
                name, version = pip_requirement.split("==", 1)
                pinned[name] = version

    distribution_names = {
        "fenics-dolfinx": "fenics-dolfinx",
        "numpy": "numpy",
        "scipy": "scipy",
        "pandas": "pandas",
        "trimesh": "trimesh",
        "meshio": "meshio",
        "pyvista": "pyvista",
        "plotly": "plotly",
        "matplotlib": "matplotlib",
        "pyyaml": "pyyaml",
        "tqdm": "tqdm",
        "h5py": "h5py",
        "pytest": "pytest",
        "pymeshlab": "pymeshlab",
    }
    assert set(pinned) == {"python", "mpich", *distribution_names}

    actual = {
        name: importlib.metadata.version(distribution)
        for name, distribution in distribution_names.items()
    }
    actual["python"] = platform.python_version()
    mpich_match = re.search(r"MPICH Version:\s+(\S+)", MPI.Get_library_version())
    assert mpich_match is not None
    actual["mpich"] = mpich_match.group(1)

    assert actual == pinned
