"""Room geometry: volumetric tetrahedral meshes of real rooms.

A `Room` holds a scikit-fem tetrahedral mesh of the air volume and the boundary facets
grouped into surfaces (floor, ceiling, walls, or the six faces of a box), so that each
surface can get its own material.
"""

import contextlib
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh
from skfem import MeshTet

logger = logging.getLogger(__name__)

AXES = {"x": 0, "y": 1, "z": 2}


@dataclass
class Room:
    """Tetrahedral mesh of a room and its boundary surfaces.

    Attributes:
        mesh: scikit-fem tetrahedral mesh, coordinates in metres
        surfaces: surface name -> indices of the boundary facets of `mesh`
        name: label used in outputs
    """
    mesh: MeshTet
    surfaces: dict = field(default_factory=dict)
    name: str = "room"

    @property
    def volume(self) -> float:
        """Volume of the air in the room [m³], summed over the tetrahedra."""
        p, t = self.mesh.p, self.mesh.t
        a, b, c, d = (p[:, t[i]] for i in range(4))
        return float(np.abs(np.einsum("ij,ij->j", b - a, np.cross(c - a, d - a, axis=0))).sum() / 6.0)

    def surface_area(self, name: str | None = None) -> float:
        """Area [m²] of one surface, or of the whole boundary."""
        facets = self.mesh.boundary_facets() if name is None else self.surfaces[name]
        return float(_facet_areas(self.mesh, facets).sum())

    def areas(self) -> dict:
        """Surface name -> area [m²]."""
        return {name: self.surface_area(name) for name in self.surfaces}

    def interior_point(self, fraction) -> np.ndarray:
        """A point inside the room near lo + fraction * (hi - lo) of the bounding box:
        the centroid of the nearest tetrahedron."""
        lo, hi = self.bounds
        target = lo + np.asarray(fraction, dtype=float) * (hi - lo)
        centroids = self.mesh.p[:, self.mesh.t].mean(axis=1)
        return centroids[:, np.argmin(np.linalg.norm(centroids.T - target, axis=1))]

    @property
    def bounds(self) -> np.ndarray:
        """[[xmin, ymin, zmin], [xmax, ymax, zmax]]."""
        return np.array([self.mesh.p.min(axis=1), self.mesh.p.max(axis=1)])

    def summary(self) -> dict:
        return {
            "name": self.name,
            "volume_m3": self.volume,
            "surface_area_m2": self.surface_area(),
            "surfaces_m2": {k: self.surface_area(k) for k in self.surfaces},
            "bounds_m": self.bounds.tolist(),
            "vertices": int(self.mesh.p.shape[1]),
            "tetrahedra": int(self.mesh.t.shape[1]),
        }


def element_size(f_max: float, c: float = 343.0, order: int = 2) -> float:
    """Element size [m] that keeps the error of the modal frequencies below about 1% up to f_max.

    Quadratic elements (order 2) need about 4 elements per wavelength, linear elements about
    16, with three times as many unknowns: quadratic elements are the better choice. The
    values come from the convergence test in tests/test_modes.py.
    """
    per_wavelength = {1: 16.0, 2: 4.0}[order]
    return c / f_max / per_wavelength


def box(length: float, width: float, height: float, h: float, name: str = "box") -> Room:
    """Rectangular room with a corner at the origin, meshed with element size about `h`.

    Surfaces: x0, x1, y0, y1 (walls), floor (z = 0) and ceiling.
    """
    n = [max(2, int(np.ceil(s / h))) for s in (length, width, height)]
    mesh = MeshTet.init_tensor(*(np.linspace(0, s, k + 1) for s, k in zip((length, width, height), n)))
    names = {(0, 0): "x0", (0, 1): "x1", (1, 0): "y0", (1, 1): "y1", (2, 0): "floor", (2, 1): "ceiling"}
    mid = mesh.p[:, mesh.facets[:, mesh.boundary_facets()]].mean(axis=1)
    bf = mesh.boundary_facets()
    surfaces = {}
    for (axis, side), label in names.items():
        target = (length, width, height)[axis] * side
        surfaces[label] = bf[np.isclose(mid[axis], target)]
    return Room(mesh, surfaces, name)


def load_surface(path, scale: float = 1.0, repair: bool = False,
                 min_part_fraction: float = 1e-3) -> trimesh.Trimesh:
    """Load a closed surface (STL, OBJ, PLY, ...) that bounds the air of a room.

    Separate parts smaller than `min_part_fraction` of the largest one (scan debris) are
    dropped. Larger extra parts are kept only if closed; they become obstacles inside
    the room. Normals are oriented outwards.
    """
    surface = trimesh.load(path, force="mesh")
    if scale != 1.0:
        surface.apply_scale(scale)
    surface.merge_vertices()

    if repair:
        surface.update_faces(surface.nondegenerate_faces())
        surface.update_faces(surface.unique_faces())
        surface.remove_unreferenced_vertices()
        trimesh.repair.fill_holes(surface)
        trimesh.repair.fix_normals(surface, multibody=True)

    with np.errstate(invalid="ignore", divide="ignore"):  # flat debris has zero volume
        parts = sorted(surface.split(only_watertight=False), key=lambda m: -abs(m.volume))
    keep = [parts[0]]
    for part in parts[1:]:
        if abs(part.volume) < min_part_fraction * abs(parts[0].volume):
            logger.warning("Dropped a separate part of %.3g m³ (scan debris)", abs(part.volume))
        elif part.is_watertight:
            keep.append(part)
        else:
            logger.warning("Dropped an open separate part of %.3g m³", abs(part.volume))
    surface = trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]

    if not surface.is_watertight:
        raise ValueError(
            f"{Path(path).name} is not a closed surface, so it does not bound a volume. "
            "Try repair=True (--repair), or close it in a mesh editor.")
    if parts[0].volume < 0:
        surface.invert()
    return surface


def from_surface(surface, h: float, up: str = "z", name: str = "room", mesher: str = "auto",
                 verbose: bool = False) -> Room:
    """Mesh the volume bounded by a closed surface with tetrahedra of size about `h`.

    Args:
        surface: path to a mesh file or a trimesh.Trimesh (closed, in metres)
        h: target element size [m], see `element_size`
        up: vertical axis, used to split the boundary into floor, ceiling and walls
        mesher: "gmsh" rebuilds the surface with elements of size h and fills it with
            tetrahedra: best quality, but it needs a clean surface. "tetwild" (fTetWild)
            accepts self-intersecting surfaces, as photogrammetry scans often are, and
            keeps the boundary within 0.2% of the room size from the original. "auto"
            tries gmsh and falls back to fTetWild.
        verbose: print mesher output
    """
    if not isinstance(surface, trimesh.Trimesh):
        surface = load_surface(surface)
    if mesher not in ("auto", "gmsh", "tetwild"):
        raise ValueError(f"unknown mesher {mesher!r}")

    p = t = None
    if mesher in ("auto", "gmsh"):
        try:
            p, t = _gmsh_volume(surface, h, verbose)
        except Exception as error:
            if mesher == "gmsh":
                raise
            logger.warning("gmsh could not mesh the surface (%s); using fTetWild", error)
    if p is None:
        p, t = _tetwild_volume(surface, h, verbose)

    mesh = MeshTet(p, t)
    room = Room(mesh, {}, name)
    room.surfaces = _split_by_orientation(mesh, AXES[up])
    return room


def _tetwild_volume(surface: trimesh.Trimesh, h: float, verbose: bool):
    import pytetwild

    # fTetWild writes a working file to the current directory
    with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
        p, t = pytetwild.tetrahedralize(np.asarray(surface.vertices, dtype=np.float64),
                                        np.asarray(surface.faces, dtype=np.int32),
                                        edge_length_abs=h, epsilon=2e-3, quiet=not verbose)
    return np.ascontiguousarray(p.T), np.ascontiguousarray(t.T.astype(np.int64))


def _gmsh_volume(surface: trimesh.Trimesh, h: float, verbose: bool):
    import gmsh

    with tempfile.TemporaryDirectory() as tmp:
        stl = str(Path(tmp) / "surface.stl")
        surface.export(stl)
        gmsh.initialize(interruptible=False)
        try:
            gmsh.option.setNumber("General.Terminal", int(verbose))
            return _gmsh_generate(gmsh, stl, h)
        finally:
            gmsh.finalize()


def _gmsh_generate(gmsh, stl: str, h: float):
    gmsh.merge(stl)
    # Rebuild the surface: scans have many tiny triangles that would force a needlessly fine
    # volume mesh, and details much smaller than the wavelength do not change the modes.
    gmsh.model.mesh.classifySurfaces(np.radians(40), True, True, np.radians(180))
    gmsh.model.mesh.createGeometry()
    surfaces = [tag for _, tag in gmsh.model.getEntities(2)]
    loop = gmsh.model.geo.addSurfaceLoop(surfaces)
    gmsh.model.geo.addVolume([loop])
    gmsh.model.geo.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", h)
    gmsh.option.setNumber("Mesh.MeshSizeMin", h / 4)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)  # HXT: fast and multithreaded
    gmsh.option.setNumber("Mesh.Optimize", 1)
    gmsh.model.mesh.generate(3)

    tags, coords, _ = gmsh.model.mesh.getNodes()
    types, _, nodes = gmsh.model.mesh.getElements(3)
    tets = nodes[list(types).index(4)].reshape(-1, 4)
    index = np.zeros(int(tags.max()) + 1, dtype=np.int64)
    index[tags.astype(np.int64)] = np.arange(len(tags))
    t = index[tets.astype(np.int64)]
    used, t = np.unique(t, return_inverse=True)
    p = np.ascontiguousarray(coords.reshape(-1, 3)[used].T)
    t = np.ascontiguousarray(t.reshape(-1, 4).T)
    if t.shape[1] == 0:
        raise RuntimeError("gmsh produced no tetrahedra")
    return p, t


def surface_areas(surface: trimesh.Trimesh, up: str = "z", threshold: float = 0.7) -> dict:
    """Floor, ceiling and wall areas [m²] of a closed surface with outward normals,
    split as in `from_surface`."""
    nz = surface.face_normals[:, AXES[up]]
    a = surface.area_faces
    return {"floor": float(a[nz < -threshold].sum()), "ceiling": float(a[nz > threshold].sum()),
            "walls": float(a[np.abs(nz) <= threshold].sum())}


def _facet_areas(mesh: MeshTet, facets: np.ndarray) -> np.ndarray:
    a, b, c = (mesh.p[:, mesh.facets[i, facets]] for i in range(3))
    return 0.5 * np.linalg.norm(np.cross(b - a, c - a, axis=0), axis=0)


def outward_normals(mesh: MeshTet, facets: np.ndarray) -> np.ndarray:
    """Unit outward normals (3 x n) of boundary facets."""
    a, b, c = (mesh.p[:, mesh.facets[i, facets]] for i in range(3))
    n = np.cross(b - a, c - a, axis=0)
    n /= np.linalg.norm(n, axis=0)
    inside = mesh.p[:, mesh.t[:, mesh.f2t[0, facets]]].mean(axis=1)
    flip = np.einsum("ij,ij->j", n, inside - (a + b + c) / 3) > 0
    n[:, flip] *= -1
    return n


def _split_by_orientation(mesh: MeshTet, up: int, threshold: float = 0.7) -> dict:
    """Floor: outward normal pointing down; ceiling: pointing up; walls: the rest."""
    bf = mesh.boundary_facets()
    nz = outward_normals(mesh, bf)[up]
    return {"floor": bf[nz < -threshold], "ceiling": bf[nz > threshold],
            "walls": bf[np.abs(nz) <= threshold]}
