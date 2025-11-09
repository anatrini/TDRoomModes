"""
Mesh Import and Repair Module

Handles importing 3D meshes from various formats (STL, OBJ, PLY, etc.)
and provides robust repair capabilities for real-world geometries.
"""

import numpy as np
import trimesh
import pymeshlab
from pathlib import Path
from typing import Union, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MeshImporter:
    """
    Import and process 3D meshes for acoustic FEM analysis.

    Supports:
    - Multiple file formats: STL, OBJ, PLY, OFF, etc.
    - Automatic mesh repair
    - Quality assessment
    - Adaptive refinement
    """

    def __init__(self, filepath: Union[str, Path]):
        """
        Initialize mesh importer.

        Args:
            filepath: Path to 3D mesh file
        """
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"Mesh file not found: {filepath}")

        self.mesh = None
        self.pymeshlab_mesh = None

    def import_mesh(self) -> trimesh.Trimesh:
        """
        Import mesh from file.

        Returns:
            Trimesh object
        """
        logger.info(f"Importing mesh from {self.filepath}")

        try:
            self.mesh = trimesh.load(self.filepath)
            logger.info(f"Successfully loaded mesh: "
                       f"{len(self.mesh.vertices)} vertices, "
                       f"{len(self.mesh.faces)} faces")
            return self.mesh

        except Exception as e:
            logger.error(f"Failed to import mesh: {e}")
            raise

    def check_mesh_quality(self) -> dict:
        """
        Assess mesh quality metrics.

        Returns:
            Dictionary with quality metrics
        """
        if self.mesh is None:
            raise ValueError("No mesh loaded. Call import_mesh() first.")

        metrics = {
            'vertices': len(self.mesh.vertices),
            'faces': len(self.mesh.faces),
            'edges': len(self.mesh.edges),
            'is_watertight': self.mesh.is_watertight,
            'is_winding_consistent': self.mesh.is_winding_consistent,
            'volume': self.mesh.volume if self.mesh.is_watertight else None,
            'bounds': self.mesh.bounds.tolist(),
            'extents': self.mesh.extents.tolist(),
        }

        # Check for holes
        if not self.mesh.is_watertight:
            logger.warning("Mesh is not watertight (contains holes)")
            metrics['needs_repair'] = True
        else:
            metrics['needs_repair'] = False

        # Check for degenerate faces
        face_areas = self.mesh.area_faces
        degenerate_faces = np.sum(face_areas < 1e-10)
        if degenerate_faces > 0:
            logger.warning(f"Found {degenerate_faces} degenerate faces")
            metrics['degenerate_faces'] = degenerate_faces

        # Check edge ratios (aspect ratio)
        edges = self.mesh.edges_unique_length
        if len(edges) > 0:
            metrics['edge_length_min'] = float(np.min(edges))
            metrics['edge_length_max'] = float(np.max(edges))
            metrics['edge_length_mean'] = float(np.mean(edges))
            metrics['edge_length_std'] = float(np.std(edges))

        logger.info(f"Mesh quality metrics: {metrics}")
        return metrics

    def repair_mesh(
        self,
        fix_holes: bool = True,
        remove_duplicates: bool = True,
        remove_degenerate: bool = True,
        smooth_iterations: int = 0,
        remesh: bool = False,
        target_edge_length: Optional[float] = None
    ) -> trimesh.Trimesh:
        """
        Repair mesh using PyMeshLab algorithms.

        Args:
            fix_holes: Close holes in mesh
            remove_duplicates: Remove duplicate vertices/faces
            remove_degenerate: Remove degenerate faces
            smooth_iterations: Number of Laplacian smoothing iterations
            remesh: Perform isotropic remeshing
            target_edge_length: Target edge length for remeshing

        Returns:
            Repaired Trimesh object
        """
        logger.info("Starting mesh repair...")

        # Convert to PyMeshLab format
        ms = pymeshlab.MeshSet()
        ms.add_mesh(pymeshlab.Mesh(
            vertex_matrix=self.mesh.vertices,
            face_matrix=self.mesh.faces
        ))

        # Remove duplicate vertices
        if remove_duplicates:
            logger.info("Removing duplicate vertices...")
            ms.meshing_remove_duplicate_vertices()

        # Remove unreferenced vertices
        logger.info("Removing unreferenced vertices...")
        ms.meshing_remove_unreferenced_vertices()

        # Remove duplicate faces
        if remove_duplicates:
            logger.info("Removing duplicate faces...")
            ms.meshing_remove_duplicate_faces()

        # Remove degenerate faces (zero area)
        if remove_degenerate:
            logger.info("Removing degenerate faces...")
            ms.meshing_remove_null_faces()

        # Fix non-manifold edges
        logger.info("Fixing non-manifold edges...")
        ms.meshing_repair_non_manifold_edges()

        # Close holes
        if fix_holes:
            logger.info("Closing holes...")
            ms.meshing_close_holes(maxholesize=30)

        # Smooth mesh
        if smooth_iterations > 0:
            logger.info(f"Smoothing mesh ({smooth_iterations} iterations)...")
            ms.apply_coord_laplacian_smoothing(stepsmoothnum=smooth_iterations)

        # Remesh to uniform edge length
        if remesh and target_edge_length is not None:
            logger.info(f"Remeshing to target edge length {target_edge_length}...")
            ms.meshing_isotropic_explicit_remeshing(
                targetlen=pymeshlab.AbsoluteValue(target_edge_length),
                iterations=10
            )

        # Convert back to Trimesh
        m = ms.current_mesh()
        self.mesh = trimesh.Trimesh(
            vertices=m.vertex_matrix(),
            faces=m.face_matrix()
        )

        logger.info(f"Repair complete: "
                   f"{len(self.mesh.vertices)} vertices, "
                   f"{len(self.mesh.faces)} faces")

        return self.mesh

    def compute_adaptive_mesh_size(
        self,
        max_frequency: float,
        speed_of_sound: float = 343.0,
        elements_per_wavelength: int = 6
    ) -> float:
        """
        Calculate appropriate element size for FEM based on maximum frequency.

        Rule of thumb: Need 6-10 elements per wavelength for accurate results.

        Args:
            max_frequency: Maximum frequency of interest [Hz]
            speed_of_sound: Speed of sound [m/s]
            elements_per_wavelength: Desired elements per wavelength

        Returns:
            Maximum element edge length [m]
        """
        wavelength = speed_of_sound / max_frequency
        element_size = wavelength / elements_per_wavelength

        logger.info(f"For f_max = {max_frequency} Hz:")
        logger.info(f"  Wavelength = {wavelength:.3f} m")
        logger.info(f"  Recommended element size ≤ {element_size:.3f} m")

        return element_size

    def refine_mesh_adaptive(
        self,
        max_frequency: float,
        speed_of_sound: float = 343.0,
        elements_per_wavelength: int = 6
    ) -> trimesh.Trimesh:
        """
        Refine mesh adaptively based on maximum frequency.

        Args:
            max_frequency: Maximum frequency [Hz]
            speed_of_sound: Speed of sound [m/s]
            elements_per_wavelength: Elements per wavelength

        Returns:
            Refined mesh
        """
        target_edge_length = self.compute_adaptive_mesh_size(
            max_frequency, speed_of_sound, elements_per_wavelength
        )

        logger.info(f"Refining mesh to edge length ≤ {target_edge_length:.3f} m")

        ms = pymeshlab.MeshSet()
        ms.add_mesh(pymeshlab.Mesh(
            vertex_matrix=self.mesh.vertices,
            face_matrix=self.mesh.faces
        ))

        # Isotropic remeshing
        ms.meshing_isotropic_explicit_remeshing(
            targetlen=pymeshlab.AbsoluteValue(target_edge_length),
            iterations=10,
            adaptive=True
        )

        m = ms.current_mesh()
        self.mesh = trimesh.Trimesh(
            vertices=m.vertex_matrix(),
            faces=m.face_matrix()
        )

        logger.info(f"Refinement complete: "
                   f"{len(self.mesh.vertices)} vertices, "
                   f"{len(self.mesh.faces)} faces")

        return self.mesh

    def export_mesh(self, output_path: Union[str, Path]) -> None:
        """
        Export mesh to file.

        Args:
            output_path: Output file path
        """
        if self.mesh is None:
            raise ValueError("No mesh to export")

        output_path = Path(output_path)
        self.mesh.export(output_path)
        logger.info(f"Exported mesh to {output_path}")

    def import_and_repair(
        self,
        fix_holes: bool = True,
        remove_duplicates: bool = True,
        max_frequency: Optional[float] = None,
        speed_of_sound: float = 343.0
    ) -> trimesh.Trimesh:
        """
        Convenience method: import, check, repair, and optionally refine mesh.

        Args:
            fix_holes: Close holes in mesh
            remove_duplicates: Remove duplicates
            max_frequency: If provided, refine mesh adaptively
            speed_of_sound: Speed of sound [m/s]

        Returns:
            Processed mesh
        """
        # Import
        self.import_mesh()

        # Check quality
        metrics = self.check_mesh_quality()

        # Repair if needed
        if metrics.get('needs_repair', False) or fix_holes or remove_duplicates:
            self.repair_mesh(
                fix_holes=fix_holes,
                remove_duplicates=remove_duplicates
            )

            # Re-check
            metrics = self.check_mesh_quality()

        # Adaptive refinement
        if max_frequency is not None:
            self.refine_mesh_adaptive(max_frequency, speed_of_sound)

        return self.mesh


def create_rectangular_room(
    length: float,
    width: float,
    height: float,
    resolution: int = 20
) -> trimesh.Trimesh:
    """
    Create a simple rectangular room mesh.

    Useful for validation against analytical solutions.

    Args:
        length: Room length (x) [m]
        width: Room width (y) [m]
        height: Room height (z) [m]
        resolution: Mesh resolution per dimension

    Returns:
        Trimesh object
    """
    logger.info(f"Creating rectangular room: {length}×{width}×{height} m")

    # Create box mesh
    box = trimesh.creation.box(extents=[length, width, height])

    # Subdivide for better FEM resolution
    vertices, faces = trimesh.remesh.subdivide_to_size(
        box.vertices, box.faces, max_edge=min(length, width, height) / resolution
    )

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

    logger.info(f"Created mesh: {len(mesh.vertices)} vertices, "
               f"{len(mesh.faces)} faces")

    return mesh


if __name__ == "__main__":
    # Example usage
    print("=== Mesh Importer Example ===\n")

    # Example 1: Create simple rectangular room
    print("1. Creating rectangular room...")
    room = create_rectangular_room(length=5.0, width=4.0, height=3.0)
    print(f"   Volume: {room.volume:.2f} m³")
    print(f"   Is watertight: {room.is_watertight}\n")

    # Example 2: Import and repair external mesh (if file exists)
    # importer = MeshImporter("path/to/your/mesh.stl")
    # mesh = importer.import_and_repair(
    #     fix_holes=True,
    #     max_frequency=200.0
    # )
