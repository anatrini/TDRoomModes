"""
Mesh Conversion Module - Modern FEniCSx version

Converts between Trimesh and FEniCSx (dolfinx) mesh formats.
"""

import numpy as np
import trimesh
from typing import Tuple
import logging

try:
    from dolfinx import mesh
    from mpi4py import MPI
    FENICSX_AVAILABLE = True
except ImportError:
    FENICSX_AVAILABLE = False
    logging.warning("FEniCSx not available. Install with: conda install -c conda-forge fenics-dolfinx mpich")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def trimesh_to_fenicsx(trimesh_obj: trimesh.Trimesh) -> 'mesh.Mesh':
    """
    Convert Trimesh to FEniCSx mesh.

    Note: Creates a surface mesh. For volumetric FEM, we create a box mesh
    matching the bounding box dimensions.

    Args:
        trimesh_obj: Trimesh object (must be watertight)

    Returns:
        FEniCSx mesh object
    """
    if not FENICSX_AVAILABLE:
        raise ImportError("FEniCSx required. Install with: conda install -c conda-forge fenics-dolfinx mpich")

    if not trimesh_obj.is_watertight:
        raise ValueError("Mesh must be watertight for FEM analysis. Use MeshImporter.repair_mesh()")

    logger.info("Converting Trimesh to FEniCSx...")

    # Get bounding box
    bounds = trimesh_obj.bounds
    p0 = bounds[0]  # min corner
    p1 = bounds[1]  # max corner

    # Calculate dimensions
    dims = p1 - p0
    volume = trimesh_obj.volume

    logger.info(f"Mesh bounds: {p0} to {p1}")
    logger.info(f"Dimensions: {dims}")
    logger.info(f"Volume: {volume:.2f} m³")

    # Estimate appropriate mesh resolution
    # Rule: ~10 elements per meter for good accuracy
    nx = max(5, int(dims[0] * 10))
    ny = max(5, int(dims[1] * 10))
    nz = max(5, int(dims[2] * 10))

    # Limit to reasonable size
    nx = min(nx, 50)
    ny = min(ny, 50)
    nz = min(nz, 50)

    logger.info(f"Creating FEniCSx mesh with resolution: {nx}×{ny}×{nz}")

    # Create box mesh with same dimensions
    domain = mesh.create_box(
        MPI.COMM_WORLD,
        [p0.tolist(), p1.tolist()],
        [nx, ny, nz],
        cell_type=mesh.CellType.tetrahedron
    )

    logger.info(f"FEniCSx mesh created: {domain.topology.index_map(0).size_global} vertices, "
               f"{domain.topology.index_map(3).size_global} cells")

    return domain


def create_box_mesh(
    length: float,
    width: float,
    height: float,
    nx: int = 20,
    ny: int = 20,
    nz: int = 20
) -> 'mesh.Mesh':
    """
    Create rectangular box mesh using FEniCSx.

    Args:
        length: Length (x direction) [m]
        width: Width (y direction) [m]
        height: Height (z direction) [m]
        nx, ny, nz: Number of elements per dimension

    Returns:
        FEniCSx mesh
    """
    if not FENICSX_AVAILABLE:
        raise ImportError("FEniCSx required")

    logger.info(f"Creating box mesh: {length}×{width}×{height} m")
    logger.info(f"Resolution: {nx}×{ny}×{nz} = {nx*ny*nz*6} tetrahedra")

    domain = mesh.create_box(
        MPI.COMM_WORLD,
        [[0.0, 0.0, 0.0], [length, width, height]],
        [nx, ny, nz],
        cell_type=mesh.CellType.tetrahedron
    )

    logger.info(f"Created: {domain.topology.index_map(0).size_global} vertices, "
               f"{domain.topology.index_map(3).size_global} cells")

    return domain


if __name__ == "__main__":
    print("=== Mesh Converter Test (FEniCSx) ===\n")

    if FENICSX_AVAILABLE:
        # Test: Create box mesh
        print("Creating box mesh...")
        domain = create_box_mesh(5.0, 4.0, 3.0, nx=10, ny=8, nz=6)
        print(f"✓ Created: {domain.topology.index_map(0).size_global} vertices\n")

        # Test: Convert from Trimesh
        print("Converting Trimesh to FEniCSx...")
        from mesh.importer import create_rectangular_room
        tmesh = create_rectangular_room(5.0, 4.0, 3.0, resolution=10)
        print(f"Trimesh: {len(tmesh.vertices)} vertices")

        fmesh = trimesh_to_fenicsx(tmesh)
        print(f"FEniCSx: {fmesh.topology.index_map(0).size_global} vertices")
    else:
        print("FEniCSx not available. Install with:")
        print("  conda install -c conda-forge fenics-dolfinx mpich")
