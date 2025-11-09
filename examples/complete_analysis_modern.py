"""
Complete Acoustic Analysis - Modern FEniCSx Version

Works natively on Apple Silicon (M1/M2/M3) and all platforms!

This example demonstrates:
1. Creating or importing a mesh
2. Computing acoustic modes with FEniCSx
3. Calculating T60 reverberation time
4. Generating interactive visualizations
5. Saving all results

Optimized for speed: Results in 3-5 minutes on typical hardware.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import numpy as np
import time

# Check FEniCSx availability
try:
    from dolfinx import mesh
    from mpi4py import MPI
    FENICSX_AVAILABLE = True
except ImportError:
    print("ERROR: FEniCSx not installed!")
    print("\nInstall with:")
    print("  conda install -c conda-forge fenics-dolfinx mpich pyvista")
    sys.exit(1)

from mesh.converter import create_box_mesh
from analysis.modes import AcousticAnalyzer
from visualization.interactive import ModeVisualizer


def main():
    """Run complete acoustic analysis."""

    print("="*70)
    print("COMPLETE ACOUSTIC ANALYSIS (Modern FEniCSx)")
    print("="*70)
    print()

    total_start = time.time()

    # =========================================================================
    # STEP 1: CREATE MESH
    # =========================================================================
    print("STEP 1: Creating mesh...")
    print("-"*70)

    # Room dimensions (meters)
    LENGTH, WIDTH, HEIGHT = 8.0, 6.0, 3.5

    # Mesh resolution
    # FAST (1-2 min): nx, ny, nz = 10, 8, 6
    # GOOD (3-5 min): nx, ny, nz = 15, 12, 8  ← Default
    # HIGH (10+ min): nx, ny, nz = 25, 20, 12

    NX, NY, NZ = 15, 12, 8

    print(f"Room dimensions: {LENGTH}×{WIDTH}×{HEIGHT} m")
    print(f"Mesh resolution: {NX}×{NY}×{NZ}")

    step_start = time.time()
    domain = create_box_mesh(LENGTH, WIDTH, HEIGHT, NX, NY, NZ)
    print(f"✓ Mesh created in {time.time()-step_start:.2f} s")
    print()

    # =========================================================================
    # STEP 2: INITIALIZE ANALYZER
    # =========================================================================
    print("STEP 2: Initializing analyzer...")
    print("-"*70)

    step_start = time.time()
    analyzer = AcousticAnalyzer(
        domain,
        speed_of_sound=343.0,
        temperature=20.0,
        humidity=50.0
    )
    print(f"✓ Initialized in {time.time()-step_start:.2f} s")
    print()

    # =========================================================================
    # STEP 3: COMPUTE ACOUSTIC MODES
    # =========================================================================
    print("STEP 3: Computing acoustic modes...")
    print("-"*70)

    # Frequency range
    F_MIN, F_MAX = 20, 150  # Hz
    NUM_MODES = 30

    print(f"Target: {NUM_MODES} modes between {F_MIN}-{F_MAX} Hz")
    print()

    step_start = time.time()
    modes = analyzer.compute_modes(
        num_modes=NUM_MODES,
        freq_range=(F_MIN, F_MAX),
        element_degree=1
    )
    computation_time = time.time() - step_start

    print()
    print(f"✓ Computed {len(modes)} modes in {computation_time:.2f} s")
    print(f"  ({computation_time/len(modes) if modes else 0:.2f} s per mode)")
    print()

    # Display first 10 modes
    print("First 10 modes:")
    for mode in modes[:10]:
        print(f"  Mode {mode.mode_number:2d}: {mode.frequency:7.2f} Hz")
    if len(modes) > 10:
        print(f"  ... and {len(modes)-10} more")
    print()

    # =========================================================================
    # STEP 4: CALCULATE ROOM ACOUSTICS
    # =========================================================================
    print("STEP 4: Calculating room acoustic properties...")
    print("-"*70)

    # Material absorption coefficient
    # 0.05 = hard (concrete, tile)
    # 0.15 = medium (typical room)
    # 0.40 = soft (curtains, carpet)

    ALPHA_AVG = 0.15

    print(f"Using average absorption coefficient: α = {ALPHA_AVG}")
    print()

    step_start = time.time()
    analyzer.calculate_t60(alpha_avg=ALPHA_AVG, method='eyring')
    print(f"✓ T60 calculated in {time.time()-step_start:.2f} s")
    print()

    # =========================================================================
    # STEP 5: CALCULATE MODAL AMPLITUDES
    # =========================================================================
    print("STEP 5: Calculating modal amplitudes...")
    print("-"*70)

    # Define sound source position (center of room, at ear height ~1.2m)
    source_pos = np.array([LENGTH/2, WIDTH/2, 1.2])
    print(f"Sound source at: [{source_pos[0]:.1f}, {source_pos[1]:.1f}, {source_pos[2]:.1f}] m")

    analyzer.calculate_modal_amplitudes(
        source_position=source_pos,
        excitation_type='point'
    )
    print("✓ Modal amplitudes calculated")
    print()

    # =========================================================================
    # STEP 6: SAVE RESULTS
    # =========================================================================
    print("STEP 6: Saving results...")
    print("-"*70)

    OUTPUT_DIR = "acoustic_results"

    step_start = time.time()
    analyzer.save_results(OUTPUT_DIR)
    print(f"✓ Results saved to '{OUTPUT_DIR}/' in {time.time()-step_start:.2f} s")
    print()

    # =========================================================================
    # STEP 7: CREATE VISUALIZATIONS
    # =========================================================================
    print("STEP 7: Creating visualizations...")
    print("-"*70)

    step_start = time.time()

    visualizer = ModeVisualizer(modes, domain)

    # Frequency spectrum
    print("  - Frequency spectrum...")
    fig_spectrum = visualizer.plot_frequency_spectrum(
        show_amplitudes=True,
        show_damping=True
    )
    fig_spectrum.write_html(f"{OUTPUT_DIR}/frequency_spectrum.html")
    print("    ✓ Saved to frequency_spectrum.html")

    # Mode gallery
    print("  - Mode gallery...")
    fig_gallery = visualizer.plot_all_modes_gallery(
        max_modes=12,
        slice_plane='z',
        slice_position=0.5
    )
    fig_gallery.write_html(f"{OUTPUT_DIR}/mode_gallery.html")
    print("    ✓ Saved to mode_gallery.html")

    print()
    print(f"✓ Visualizations created in {time.time()-step_start:.2f} s")
    print()

    # =========================================================================
    # SUMMARY
    # =========================================================================
    total_time = time.time() - total_start

    print("="*70)
    print("ANALYSIS COMPLETE!")
    print("="*70)
    print()
    print(f"Total computation time: {total_time:.2f} seconds ({total_time/60:.1f} minutes)")
    print()

    analyzer.print_summary()

    print()
    print("Output files:")
    print(f"  {OUTPUT_DIR}/mode_data.json         - Mode data (JSON)")
    print(f"  {OUTPUT_DIR}/modes_summary.csv      - Mode summary (CSV)")
    print(f"  {OUTPUT_DIR}/mode_*.xdmf            - Mode shapes (ParaView)")
    print(f"  {OUTPUT_DIR}/frequency_spectrum.html - Interactive spectrum")
    print(f"  {OUTPUT_DIR}/mode_gallery.html      - Mode gallery")
    print()
    print("Open the HTML files in a web browser to explore results!")
    print()

    # View results
    print("To view results, run:")
    print(f"  open {OUTPUT_DIR}/frequency_spectrum.html")
    print()


if __name__ == "__main__":
    main()
