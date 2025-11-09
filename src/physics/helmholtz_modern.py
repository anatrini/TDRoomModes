"""
Modern Helmholtz Eigenvalue Solver using FEniCSx (dolfinx)

Uses current FEniCSx API that works natively on Apple Silicon.
"""

import numpy as np
from typing import List, Tuple, Optional
import logging
import sys
from tqdm import tqdm

try:
    from dolfinx import mesh, fem, io
    from dolfinx.fem import functionspace, Function, form
    from dolfinx.fem.petsc import assemble_matrix
    from mpi4py import MPI
    from petsc4py import PETSc
    from slepc4py import SLEPc
    import ufl
    FENICSX_AVAILABLE = True
except ImportError:
    FENICSX_AVAILABLE = False
    logging.warning("FEniCSx not available. Install with: conda install -c conda-forge fenics-dolfinx mpich pyvista")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AcousticMode:
    """Container for a single acoustic mode."""

    def __init__(
        self,
        eigenvalue: float,
        eigenfunction: 'Function',
        mode_number: int,
        speed_of_sound: float = 343.0
    ):
        self.eigenvalue = eigenvalue
        self.eigenfunction = eigenfunction
        self.mode_number = mode_number
        self.speed_of_sound = speed_of_sound
        self.frequency = self._eigenvalue_to_frequency()
        self.amplitude = 1.0
        self.damping_ratio = 0.01

    def _eigenvalue_to_frequency(self) -> float:
        """Convert eigenvalue to frequency [Hz]."""
        if self.eigenvalue < 0:
            logger.warning(f"Negative eigenvalue: {self.eigenvalue}")
            return 0.0
        return self.speed_of_sound * np.sqrt(self.eigenvalue) / (2 * np.pi)

    def evaluate_at(self, point: np.ndarray) -> float:
        """Evaluate mode shape at a point."""
        try:
            # FEniCSx evaluation
            return self.eigenfunction.eval(point, 0)[0]
        except:
            logger.warning(f"Could not evaluate at point {point}")
            return 0.0

    def __repr__(self):
        return (f"Mode {self.mode_number}: f={self.frequency:.2f} Hz, "
                f"λ={self.eigenvalue:.4f}, ξ={self.damping_ratio:.4f}")


class HelmholtzSolver:
    """
    Modern Helmholtz eigenvalue solver using FEniCSx.

    Solves: -∇²p = λp with ∂p/∂n = 0 (rigid boundaries)
    """

    def __init__(
        self,
        domain: 'mesh.Mesh',
        speed_of_sound: float = 343.0,
        element_degree: int = 1
    ):
        """
        Initialize solver.

        Args:
            domain: FEniCSx mesh
            speed_of_sound: Speed of sound [m/s]
            element_degree: Polynomial degree (1 or 2)
        """
        if not FENICSX_AVAILABLE:
            raise ImportError("FEniCSx required. Install with: conda install -c conda-forge fenics-dolfinx mpich pyvista")

        self.domain = domain
        self.c = speed_of_sound
        self.degree = element_degree

        # Create function space
        logger.info(f"Creating function space (P{element_degree})...")
        self.V = functionspace(domain, ("Lagrange", element_degree))
        logger.info(f"  DOFs: {self.V.dofmap.index_map.size_global}")

        # Assemble matrices
        self._assemble_matrices()

        # Storage
        self.modes: List[AcousticMode] = []

    def _assemble_matrices(self):
        """Assemble stiffness and mass matrices."""
        logger.info("Assembling FEM matrices...")

        # Trial and test functions
        u = ufl.TrialFunction(self.V)
        v = ufl.TestFunction(self.V)

        # Weak form
        a = ufl.inner(ufl.grad(u), ufl.grad(v)) * ufl.dx  # Stiffness
        m = ufl.inner(u, v) * ufl.dx                       # Mass

        # Assemble into PETSc matrices
        self.K = assemble_matrix(form(a))
        self.K.assemble()

        self.M = assemble_matrix(form(m))
        self.M.assemble()

        logger.info(f"  Matrix size: {self.K.getSize()[0]} × {self.K.getSize()[1]}")

    def solve_eigenproblem(
        self,
        num_modes: int = 20,
        freq_range: Optional[Tuple[float, float]] = None,
        tolerance: float = 1e-8,
        max_iterations: int = 1000
    ) -> List[AcousticMode]:
        """
        Solve eigenvalue problem.

        Args:
            num_modes: Number of modes to compute
            freq_range: (f_min, f_max) frequency range [Hz]
            tolerance: Convergence tolerance
            max_iterations: Maximum iterations

        Returns:
            List of AcousticMode objects
        """
        logger.info("="*70)
        logger.info("SOLVING EIGENVALUE PROBLEM (FEniCSx)")
        logger.info("="*70)
        logger.info(f"Requesting {num_modes} modes")

        if freq_range:
            logger.info(f"Frequency range: {freq_range[0]:.1f} - {freq_range[1]:.1f} Hz")

        # Setup SLEPc eigensolver
        eigensolver = SLEPc.EPS().create(MPI.COMM_WORLD)
        eigensolver.setOperators(self.K, self.M)
        eigensolver.setProblemType(SLEPc.EPS.ProblemType.GHEP)

        # Use shift-and-invert
        st = eigensolver.getST()
        st.setType(SLEPc.ST.Type.SINVERT)

        # Target eigenvalue
        if freq_range:
            f_mid = (freq_range[0] + freq_range[1]) / 2
            target = (2 * np.pi * f_mid / self.c)**2
        else:
            target = 0.1

        eigensolver.setTarget(target)
        eigensolver.setWhichEigenpairs(SLEPc.EPS.Which.TARGET_MAGNITUDE)

        # Solver settings
        eigensolver.setType(SLEPc.EPS.Type.KRYLOVSCHUR)
        eigensolver.setDimensions(nev=num_modes, ncv=min(num_modes*3, self.V.dofmap.index_map.size_global))
        eigensolver.setTolerances(tol=tolerance, max_it=max_iterations)

        # Set up monitoring for progress feedback
        # Progress tracking
        progress_bar = None
        last_iteration = [0]

        def monitor(eps, its, nconv, eig, err):
            """Monitor function called by SLEPc during iterations."""
            nonlocal progress_bar, last_iteration

            if progress_bar is None:
                # Initialize progress bar on first call
                max_its = eps.getTolerances()[1]  # max_iterations
                progress_bar = tqdm(total=max_its, desc="Solving eigenvalue problem",
                                   unit="iter", file=sys.stdout,
                                   bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} iterations [{elapsed}<{remaining}]')

            # Update progress
            delta = its - last_iteration[0]
            if delta > 0:
                progress_bar.update(delta)
                last_iteration[0] = its

        # Set the monitor
        eigensolver.setMonitor(monitor)

        # Solve
        logger.info("Running eigenvalue solver...")
        eigensolver.solve()

        # Close progress bar if it was created
        if progress_bar is not None:
            progress_bar.close()

        # Get converged eigenvalues
        nconv = eigensolver.getConverged()
        logger.info(f"Converged eigenvalues: {nconv}")

        if nconv < num_modes:
            logger.warning(f"Only {nconv}/{num_modes} modes converged")

        # Extract modes
        self.modes = []
        vr, vi = self.K.createVecs()

        logger.info("Extracting eigenvalues and eigenfunctions...")
        for i in tqdm(range(min(nconv, num_modes)),
                     desc="Extracting mode data",
                     unit="mode",
                     bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} modes [{elapsed}<{remaining}]'):
            # Get eigenvalue
            eigval = eigensolver.getEigenvalue(i).real

            # Get eigenvector
            eigensolver.getEigenvector(i, vr, vi)

            # Create function
            eigenfunction = Function(self.V)
            eigenfunction.x.array[:] = vr.array

            # Create mode object
            mode = AcousticMode(
                eigenvalue=eigval,
                eigenfunction=eigenfunction,
                mode_number=i,
                speed_of_sound=self.c
            )

            # Filter by frequency range
            if freq_range:
                if freq_range[0] <= mode.frequency <= freq_range[1]:
                    self.modes.append(mode)
            else:
                self.modes.append(mode)

        logger.info(f"Extracted {len(self.modes)} modes")

        # Sort by frequency
        self.modes.sort(key=lambda m: m.frequency)
        for i, mode in enumerate(self.modes):
            mode.mode_number = i

        # Display
        self._display_mode_summary()

        return self.modes

    def _display_mode_summary(self):
        """Display mode summary."""
        logger.info("="*70)
        logger.info("MODE SUMMARY")
        logger.info("="*70)
        logger.info(f"{'Mode':>5} {'Frequency [Hz]':>15} {'Eigenvalue':>15}")
        logger.info("-"*70)

        for mode in self.modes[:20]:
            logger.info(f"{mode.mode_number:>5} {mode.frequency:>15.2f} {mode.eigenvalue:>15.6f}")

        if len(self.modes) > 20:
            logger.info(f"... ({len(self.modes) - 20} more modes)")

        logger.info("="*70)

    def save_modes(self, output_dir: str = "results"):
        """Save mode shapes to files."""
        import os
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"Saving modes to {output_dir}/")

        for mode in tqdm(self.modes, desc="Saving modes"):
            filename = f"{output_dir}/mode_{mode.mode_number:03d}_f{mode.frequency:.1f}Hz.xdmf"

            with io.XDMFFile(self.domain.comm, filename, "w") as xdmf:
                xdmf.write_mesh(self.domain)
                xdmf.write_function(mode.eigenfunction)

        logger.info("Done!")


def create_box_mesh(
    length: float,
    width: float,
    height: float,
    nx: int = 20,
    ny: int = 20,
    nz: int = 20
) -> 'mesh.Mesh':
    """
    Create rectangular box mesh using modern FEniCSx API.

    Args:
        length: Length in x [m]
        width: Width in y [m]
        height: Height in z [m]
        nx, ny, nz: Number of elements per dimension

    Returns:
        FEniCSx mesh
    """
    logger.info(f"Creating box mesh: {length}×{width}×{height} m")
    logger.info(f"Resolution: {nx}×{ny}×{nz}")

    domain = mesh.create_box(
        MPI.COMM_WORLD,
        [[0.0, 0.0, 0.0], [length, width, height]],
        [nx, ny, nz],
        cell_type=mesh.CellType.tetrahedron
    )

    logger.info(f"Created mesh: {domain.topology.index_map(0).size_global} vertices, "
               f"{domain.topology.index_map(3).size_global} cells")

    return domain


if __name__ == "__main__":
    print("=== Modern Helmholtz Solver Test (FEniCSx) ===\n")

    if FENICSX_AVAILABLE:
        # Create mesh
        print("Creating mesh...")
        domain = create_box_mesh(5.0, 4.0, 3.0, nx=10, ny=8, nz=6)

        # Create solver
        print("\nInitializing solver...")
        solver = HelmholtzSolver(domain, speed_of_sound=343.0)

        # Solve
        print("\nSolving eigenvalue problem...")
        modes = solver.solve_eigenproblem(
            num_modes=20,
            freq_range=(20, 150)
        )

        print(f"\nFound {len(modes)} modes")
        print("\nFirst 10 modes:")
        for mode in modes[:10]:
            print(mode)

    else:
        print("FEniCSx not available.")
        print("Install with: conda install -c conda-forge fenics-dolfinx mpich pyvista")
