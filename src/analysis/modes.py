"""
Modal Analysis Module - Modern FEniCSx version

High-level interface for room acoustic analysis using FEniCSx.
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
import logging
from pathlib import Path
import time

try:
    from dolfinx import mesh
    from mpi4py import MPI
    import ufl
    FENICSX_AVAILABLE = True
except ImportError:
    FENICSX_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AcousticAnalyzer:
    """
    Complete acoustic analysis pipeline using modern FEniCSx.
    """

    def __init__(
        self,
        domain: 'mesh.Mesh',
        speed_of_sound: float = 343.0,
        temperature: float = 20.0,
        humidity: float = 50.0
    ):
        """
        Initialize analyzer.

        Args:
            domain: FEniCSx mesh
            speed_of_sound: Speed of sound [m/s]
            temperature: Air temperature [°C]
            humidity: Relative humidity [%]
        """
        if not FENICSX_AVAILABLE:
            raise ImportError("FEniCSx required. Install with: conda install -c conda-forge fenics-dolfinx mpich")

        self.domain = domain
        self.c = speed_of_sound
        self.temperature = temperature
        self.humidity = humidity

        # Calculate geometry
        self._calculate_geometry()

        # Storage
        self.modes = []
        self.solver = None
        self.room_properties = None

        logger.info("="*70)
        logger.info("ACOUSTIC ANALYZER INITIALIZED (FEniCSx)")
        logger.info("="*70)
        logger.info(f"Speed of sound: {self.c:.1f} m/s")
        logger.info(f"Estimated volume: {self.volume:.2f} m³")

    def _calculate_geometry(self):
        """Estimate room volume and surface area from mesh."""
        # Get bounding box
        coords = self.domain.geometry.x
        p_min = coords.min(axis=0)
        p_max = coords.max(axis=0)

        dims = p_max - p_min

        # Estimate volume (bounding box)
        self.volume = float(np.prod(dims))

        # Estimate surface area (bounding box)
        self.surface_area = 2.0 * (dims[0]*dims[1] + dims[0]*dims[2] + dims[1]*dims[2])

        logger.info(f"Dimensions: {dims[0]:.2f} × {dims[1]:.2f} × {dims[2]:.2f} m")
        logger.info(f"Volume: {self.volume:.2f} m³")
        logger.info(f"Surface area: {self.surface_area:.2f} m²")

    def compute_modes(
        self,
        num_modes: int = 30,
        freq_range: Optional[Tuple[float, float]] = None,
        element_degree: int = 1
    ) -> List:
        """
        Compute acoustic modes using FEniCSx.

        Args:
            num_modes: Number of modes to compute
            freq_range: (f_min, f_max) in Hz
            element_degree: FEM element degree (1 or 2)

        Returns:
            List of AcousticMode objects
        """
        from physics.helmholtz_modern import HelmholtzSolver

        logger.info("="*70)
        logger.info("COMPUTING ACOUSTIC MODES")
        logger.info("="*70)

        start_time = time.time()

        # Create solver
        self.solver = HelmholtzSolver(
            self.domain,
            speed_of_sound=self.c,
            element_degree=element_degree
        )

        # Solve
        self.modes = self.solver.solve_eigenproblem(
            num_modes=num_modes,
            freq_range=freq_range
        )

        elapsed = time.time() - start_time
        logger.info(f"Computation time: {elapsed:.2f} seconds")

        return self.modes

    def calculate_t60(
        self,
        alpha_avg: float = 0.15,
        method: str = 'eyring'
    ):
        """
        Calculate T60 and modal damping.

        Args:
            alpha_avg: Average absorption coefficient
            method: 'sabine' or 'eyring'
        """
        from physics.decay import (
            sabine_t60, eyring_t60, modal_damping_ratio,
            air_absorption_coefficient, AcousticRoom
        )

        logger.info("="*70)
        logger.info("CALCULATING REVERBERATION TIMES")
        logger.info("="*70)

        # Create room object
        self.room_properties = AcousticRoom(
            volume=self.volume,
            surface_area=self.surface_area,
            temperature=self.temperature,
            humidity=self.humidity
        )
        self.room_properties.alpha_avg = alpha_avg

        # Calculate T60
        octave_bands = [125, 250, 500, 1000, 2000, 4000]

        logger.info(f"\nT60 ({method.capitalize()} formula):")
        logger.info(f"{'Frequency [Hz]':>15} {'T60 [s]':>10}")
        logger.info("-"*30)

        for freq in octave_bands:
            t60 = self.room_properties.t60(frequency=freq, method=method)
            logger.info(f"{freq:>15} {t60:>10.3f}")

        # Calculate modal damping and T60 for each mode
        if self.modes:
            logger.info(f"\nModal T60 values (first 10 modes):")
            logger.info(f"{'Mode':>5} {'Freq [Hz]':>10} {'T60 [s]':>10} {'Damping ξ':>12}")
            logger.info("-"*40)

            for i, mode in enumerate(self.modes):
                air_abs = air_absorption_coefficient(
                    self.temperature, self.humidity, mode.frequency
                )
                mode.damping_ratio = modal_damping_ratio(
                    mode.frequency,
                    self.volume,
                    self.surface_area,
                    alpha_avg,
                    air_abs
                )

                # Calculate T60 for this mode from damping ratio
                # T60 = 2.2 / (ω * ξ) = 2.2 / (2πf * ξ)
                omega = 2 * np.pi * mode.frequency
                if mode.damping_ratio > 0:
                    mode.t60 = 2.2 / (omega * mode.damping_ratio)
                else:
                    mode.t60 = np.inf

                # Display first 10 modes
                if i < 10:
                    logger.info(f"{mode.mode_number:>5} {mode.frequency:>10.2f} "
                              f"{mode.t60:>10.3f} {mode.damping_ratio:>12.6f}")

        # Room acoustic metrics
        f_s = self.room_properties.schroeder_freq()
        r_c = self.room_properties.critical_dist()

        logger.info(f"\n{'='*70}")
        logger.info("ROOM ACOUSTIC METRICS")
        logger.info(f"{'='*70}")
        logger.info(f"Schroeder frequency: {f_s:.1f} Hz")
        logger.info(f"  → Below {f_s:.0f} Hz: Modal behavior (discrete modes)")
        logger.info(f"  → Above {f_s:.0f} Hz: Statistical behavior (diffuse field)")
        logger.info(f"\nCritical distance: {r_c:.2f} m")
        logger.info(f"  → Distance where direct sound = reverberant sound")

        # Modal density (average spacing)
        if len(self.modes) > 1:
            freqs = [m.frequency for m in self.modes]
            avg_spacing = np.mean(np.diff(sorted(freqs)))
            modal_density = 1.0 / avg_spacing if avg_spacing > 0 else 0
            logger.info(f"\nModal density: {modal_density:.3f} modes/Hz")
            logger.info(f"Average frequency spacing: {avg_spacing:.2f} Hz")

    def calculate_modal_amplitudes(
        self,
        source_position: Optional[np.ndarray] = None,
        excitation_type: str = 'point'
    ):
        """
        Calculate modal amplitudes based on excitation.

        Args:
            source_position: [x, y, z] position of sound source [m]
            excitation_type: 'point' or 'uniform'
        """
        logger.info("="*70)
        logger.info("CALCULATING MODAL AMPLITUDES")
        logger.info("="*70)

        if not self.modes:
            logger.error("No modes computed")
            return

        if excitation_type == 'point' and source_position is not None:
            # Point source: amplitude = mode shape at source location
            logger.info(f"Point source at: {source_position}")
            for mode in self.modes:
                try:
                    # Evaluate mode shape at source
                    amplitude = abs(mode.evaluate_at(source_position))
                    # Normalize (modes should already be normalized, but ensure non-zero)
                    mode.amplitude = amplitude if amplitude > 1e-10 else 1e-10
                except Exception as e:
                    logger.warning(f"Could not evaluate mode {mode.mode_number} at source: {e}")
                    mode.amplitude = 1.0

            # Normalize amplitudes to max = 1.0
            max_amp = max(m.amplitude for m in self.modes)
            if max_amp > 0:
                for mode in self.modes:
                    mode.amplitude /= max_amp

            logger.info(f"Modal amplitudes calculated (max normalized to 1.0)")
        else:
            # Uniform excitation (plane wave or diffuse field)
            for mode in self.modes:
                mode.amplitude = 1.0
            logger.info("Modal amplitudes set to 1.0 (uniform excitation)")

    def save_results(self, output_dir: str = "results", save_paraview: bool = False):
        """Save all results.

        Args:
            output_dir: Directory to save results
            save_paraview: If True, save modes in ParaView format (.xdmf/.h5)
        """
        import os
        import json

        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"Saving results to {output_dir}/")

        # Save mode data
        mode_data = {
            'geometry': {
                'volume': float(self.volume),
                'surface_area': float(self.surface_area)
            },
            'parameters': {
                'speed_of_sound': self.c,
                'temperature': self.temperature,
                'humidity': self.humidity
            },
            'modes': [
                {
                    'mode_number': m.mode_number,
                    'frequency': float(m.frequency),
                    'eigenvalue': float(m.eigenvalue),
                    'amplitude': float(m.amplitude),
                    'damping_ratio': float(m.damping_ratio),
                    't60': float(getattr(m, 't60', 0.0))  # T60 in seconds
                }
                for m in self.modes
            ]
        }

        # Add room metrics if available
        if self.room_properties:
            mode_data['room_metrics'] = {
                'schroeder_frequency': float(self.room_properties.schroeder_freq()),
                'critical_distance': float(self.room_properties.critical_dist()),
                't60_at_1khz': float(self.room_properties.t60(1000)),
                'alpha_avg': float(self.room_properties.alpha_avg)
            }

        with open(f"{output_dir}/mode_data.json", 'w') as f:
            json.dump(mode_data, f, indent=2)

        # Save CSV
        import pandas as pd
        df = pd.DataFrame([
            {
                'Mode': m.mode_number,
                'Frequency [Hz]': m.frequency,
                'T60 [s]': getattr(m, 't60', 0.0),
                'Damping Ratio': m.damping_ratio,
                'Amplitude': m.amplitude,
                'Eigenvalue': m.eigenvalue
            }
            for m in self.modes
        ])
        df.to_csv(f"{output_dir}/modes_summary.csv", index=False)

        # Save mode shapes (ParaView format - optional)
        if self.solver and save_paraview:
            logger.info("Saving modes in ParaView format (.xdmf/.h5)...")
            paraview_dir = f"{output_dir}/paraview"
            os.makedirs(paraview_dir, exist_ok=True)
            self.solver.save_modes(paraview_dir)
            logger.info(f"✓ ParaView files saved to {paraview_dir}/")

        logger.info("✓ Results saved!")

    def print_summary(self):
        """Print analysis summary."""
        logger.info("="*70)
        logger.info("ANALYSIS SUMMARY")
        logger.info("="*70)
        logger.info(f"\nGeometry:")
        logger.info(f"  Volume: {self.volume:.2f} m³")
        logger.info(f"  Surface area: {self.surface_area:.2f} m²")

        if self.modes:
            logger.info(f"\nModes computed: {len(self.modes)}")
            logger.info(f"  Frequency range: {self.modes[0].frequency:.1f} - "
                       f"{self.modes[-1].frequency:.1f} Hz")

        if self.room_properties:
            t60 = self.room_properties.t60(frequency=1000)
            logger.info(f"\nRoom acoustics:")
            logger.info(f"  T60 @ 1kHz: {t60:.3f} s")

        logger.info("="*70)
