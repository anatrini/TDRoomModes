"""Acoustic modes of a room with the finite element method.

The modes solve the Helmholtz eigenvalue problem with rigid walls,

    -∇²φ = k² φ in the room,   ∂φ/∂n = 0 on the walls,   f = c k / (2π),

with Lagrange elements on tetrahedra (scikit-fem) and a shift-invert Lanczos solver (SciPy).
Mode shapes are normalized so that ∫ φ² dV = 1.

Wall absorption enters as a first-order perturbation (Kuttruff, Room Acoustics, ch. 3):
a wall with real normalized admittance β adds to the amplitude decay constant of mode n

    δ_n = (c / 2) ∫_walls β φ_n² dS + c m / 2,

where m is the energy attenuation of air. For a diffuse field this reduces to the Sabine
formula; for modes it gives each mode its own decay, e.g. axial modes between two
absorbing walls decay faster than modes grazing them. The perturbation is accurate while
β ≪ 1, i.e. for absorption coefficients up to about 0.3-0.4.
"""

import logging
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import LinearOperator, eigsh, splu
from scipy.spatial import cKDTree
from skfem import Basis, BilinearForm, ElementTetP1, ElementTetP2, FacetBasis, MeshTet, asm
from skfem.helpers import dot, grad

from . import materials, physics
from .geometry import Room

logger = logging.getLogger(__name__)

ELEMENTS = {1: ElementTetP1, 2: ElementTetP2}


@BilinearForm
def _stiffness(u, v, _):
    return dot(grad(u), grad(v))


@BilinearForm
def _mass(u, v, _):
    return u * v


@dataclass
class Modes:
    """Modes of a room.

    Attributes:
        room: the room
        basis: scikit-fem basis of the mode shapes
        c: speed of sound [m/s]
        frequencies: modal frequencies [Hz], ascending
        shapes: mode shapes, one column per mode, values at the basis degrees of freedom
        decay: amplitude decay constants δ [1/s], set by `set_absorption`
    """
    room: Room
    basis: Basis
    c: float
    frequencies: np.ndarray
    shapes: np.ndarray
    decay: np.ndarray = None
    info: dict = field(default_factory=dict)

    def __len__(self):
        return len(self.frequencies)

    @property
    def omega(self) -> np.ndarray:
        return 2.0 * np.pi * self.frequencies

    @property
    def t60(self) -> np.ndarray:
        """Reverberation time of each mode [s]."""
        return physics.t60_from_decay(self._decay())

    @property
    def damping_ratio(self) -> np.ndarray:
        """ξ = δ / ω."""
        return self._decay() / self.omega

    @property
    def bandwidth(self) -> np.ndarray:
        """Half-power bandwidth of each resonance [Hz]: δ / π."""
        return self._decay() / np.pi

    def _decay(self):
        if self.decay is None:
            raise RuntimeError("no absorption yet: call set_absorption()")
        return self.decay

    def set_absorption(self, absorption, temperature: float = 20.0, humidity: float = 50.0):
        """Decay constant of every mode from the wall absorption and the air.

        Args:
            absorption: see `tdroommodes.materials`
            temperature: [°C], for air absorption
            humidity: relative humidity [%], for air absorption
        """
        bands = materials.resolve(absorption, self.room.surfaces)
        decay = self.c * physics.air_attenuation(self.frequencies, temperature, humidity) / 2.0
        alpha_max = 0.0
        for name, facets in self.room.surfaces.items():
            if len(facets) == 0:
                continue
            fb = FacetBasis(self.room.mesh, self.basis.elem, facets=facets)
            B = asm(_mass, fb)
            wall_energy = np.einsum("in,in->n", self.shapes, B @ self.shapes)
            alpha = materials.at_frequency(bands[name], self.frequencies)
            alpha_max = max(alpha_max, float(alpha.max()))
            decay += self.c / 2.0 * physics.admittance_from_alpha(alpha) * wall_energy
        if alpha_max > 0.4:
            logger.warning("absorption %.2f at the modal frequencies: above 0.4 the modal decay "
                           "times are approximate (perturbation theory)", alpha_max)
        self.decay = decay
        self.info.update(absorption={k: v.tolist() for k, v in bands.items()},
                         temperature=temperature, humidity=humidity)
        return self

    def evaluate(self, points) -> np.ndarray:
        """Mode shapes at points.

        Args:
            points: array (n_points, 3) [m]

        Returns:
            array (n_points, n_modes); NaN for points outside the room
        """
        points = np.atleast_2d(np.asarray(points, dtype=float))
        values = np.full((len(points), len(self)), np.nan)
        P, inside = probe_matrix(self.basis, points)
        values[inside] = P @ self.shapes
        return values

    def to_dict(self, vertex_shapes: bool = True) -> dict:
        """Arrays that describe the modes, for `save` and for `tdroommodes.synth`."""
        data = {
            "frequencies": self.frequencies,
            "decay": self._decay(),
            "c": np.array(self.c),
            "order": np.array(self.basis.elem.maxdeg),
            "vertices": self.room.mesh.p.T,
            "tetrahedra": self.room.mesh.t.T,
            "shapes": self.shapes.astype(np.float32),
        }
        if vertex_shapes:
            data["vertex_shapes"] = self.shapes[self.basis.nodal_dofs[0]].astype(np.float32)
        for name, facets in self.room.surfaces.items():
            data[f"surface_{name}"] = facets
        return data

    def save(self, path):
        """Save to a .npz file, readable with numpy alone (see `tdroommodes.synth.load`)."""
        np.savez_compressed(path, **self.to_dict())

    @classmethod
    def load(cls, path) -> "Modes":
        data = np.load(path)
        mesh = MeshTet(np.ascontiguousarray(data["vertices"].T), np.ascontiguousarray(data["tetrahedra"].T))
        surfaces = {k[len("surface_"):]: data[k] for k in data.files if k.startswith("surface_")}
        basis = Basis(mesh, ELEMENTS[int(data["order"])]())
        return cls(Room(mesh, surfaces), basis, float(data["c"]), data["frequencies"],
                   data["shapes"].astype(float), data["decay"])


def compute(room: Room, f_max: float, c: float = 343.2, order: int = 2) -> Modes:
    """All modes of `room` from 0 Hz up to `f_max` [Hz].

    The constant mode (0 Hz) is left out. The mesh must be fine enough for f_max:
    see `tdroommodes.geometry.element_size`.
    """
    start = time.perf_counter()
    basis = Basis(room.mesh, ELEMENTS[order]())
    K = asm(_stiffness, basis).tocsc()
    M = asm(_mass, basis).tocsc()
    n_dofs = K.shape[0]
    assembled = time.perf_counter()

    # Shift slightly below zero: K is singular (the constant mode), K - σM is not.
    sigma = -(2.0 * np.pi * 1.0 / c) ** 2
    # K - σM is symmetric positive definite: a symmetric ordering without pivoting halves
    # the fill-in and the time compared with SuperLU's default
    lu = splu((K - sigma * M).tocsc(), permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0,
              options={"SymmetricMode": True})
    OPinv = LinearOperator(K.shape, matvec=lu.solve, dtype=float)

    expected = physics.mode_count(f_max, room.volume, room.surface_area(), c)
    k = min(int(1.2 * expected) + 20, n_dofs - 2)
    while True:
        eigenvalues, vectors = eigsh(K, k=k, M=M, sigma=sigma, which="LM", OPinv=OPinv)
        frequencies = c * np.sqrt(np.clip(eigenvalues, 0, None)) / (2.0 * np.pi)
        if frequencies.max() > f_max or k >= n_dofs - 2:
            break
        k = min(int(k * 1.5) + 10, n_dofs - 2)
    solved = time.perf_counter()

    order_ = np.argsort(frequencies)
    frequencies, vectors = frequencies[order_], vectors[:, order_]
    keep = (frequencies > 0.5) & (frequencies <= f_max)
    frequencies, vectors = frequencies[keep], vectors[:, keep]
    vectors /= np.sqrt(np.einsum("in,in->n", vectors, M @ vectors))

    info = {"f_max": f_max, "order": order, "dofs": int(n_dofs), "modes": int(len(frequencies)),
            "seconds_assembly": assembled - start, "seconds_eigensolver": solved - assembled}
    logger.info("%d modes up to %.1f Hz, %d degrees of freedom, %.1f s",
                len(frequencies), f_max, n_dofs, solved - start)
    return Modes(room, basis, c, frequencies, vectors, info=info)


def locate(mesh: MeshTet, points: np.ndarray, candidates: int = 12):
    """Tetrahedron containing each point (-1 outside) and the point's reference coordinates."""
    if not hasattr(mesh, "_tdroommodes_tree"):
        mesh._tdroommodes_tree = cKDTree(mesh.p[:, mesh.t].mean(axis=1).T)
    mapping = mesh._mapping()
    cells = np.full(len(points), -1)
    ref = np.zeros((3, len(points)))
    todo = np.arange(len(points))
    for k in (candidates, 8 * candidates):
        if len(todo) == 0:
            break
        _, near = mesh._tdroommodes_tree.query(points[todo], k=min(k, mesh.t.shape[1]))
        near = np.atleast_2d(near.T).T
        for j in range(near.shape[1]):
            X = mapping.invF(points[todo].T[:, :, None], tind=near[:, j])[:, :, 0]
            hit = np.all(X >= -1e-9, axis=0) & (X.sum(axis=0) <= 1 + 1e-9) & (cells[todo] < 0)
            cells[todo[hit]] = near[hit, j]
            ref[:, todo[hit]] = X[:, hit]
        todo = todo[cells[todo] < 0]
    return cells, ref


def probe_matrix(basis: Basis, points: np.ndarray):
    """Sparse matrix mapping basis coefficients to values at the points inside the mesh.

    Returns:
        (matrix with one row per inside point, boolean mask of the inside points)
    """
    cells, ref = locate(basis.mesh, points)
    inside = cells >= 0
    cells, ref = cells[inside], ref[:, inside]
    n = len(cells)
    phis = np.array([basis.elem.gbasis(basis.mapping, ref[:, :, None], k, tind=cells)[0][:, 0]
                     for k in range(basis.Nbfun)])
    rows = np.tile(np.arange(n), basis.Nbfun)
    cols = basis.element_dofs[:, cells].flatten()
    return coo_matrix((phis.flatten(), (rows, cols)), shape=(n, basis.N)).tocsr(), inside
