#!/usr/bin/env python3
"""
Acoustic FEM Analysis CLI Tool

Analyzes room acoustics from 3D mesh files using Finite Element Method.
Calculates modal frequencies, T60 reverberation times, and generates visualizations.

Author: AcousticFEM v2
License: MIT
"""

import sys
import argparse
from pathlib import Path
import time
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Import after path setup
try:
    from dolfinx import mesh as dmesh
    from mpi4py import MPI
    FENICSX_AVAILABLE = True
except ImportError:
    print("ERROR: FEniCSx not installed!")
    print("\nInstall with:")
    print("  conda env create -f environment.yml")
    print("  conda activate acoustics")
    sys.exit(1)

from mesh.importer import MeshImporter
from mesh.converter import trimesh_to_fenicsx, create_box_mesh
from analysis.modes import AcousticAnalyzer
from visualization.interactive import ModeVisualizer


def print_header():
    """Print application header."""
    print("=" * 80)
    print(" " * 20 + "ACOUSTIC FEM ANALYSIS v2.0")
    print(" " * 15 + "Room Acoustics Modal Analysis Tool")
    print("=" * 80)
    print()


def print_progress(step: int, total: int, description: str):
    """Print progress indicator."""
    bar_length = 40
    filled = int(bar_length * step / total)
    bar = '█' * filled + '░' * (bar_length - filled)
    percent = 100 * step / total
    print(f"\r[{bar}] {percent:>5.1f}% | {description}", end='', flush=True)
    if step == total:
        print()  # New line when complete


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Acoustic modal analysis of 3D room geometries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze STL file with default settings
  python acoustic_analysis.py room.stl

  # Analyze with custom parameters
  python acoustic_analysis.py room.obj --repair --modes 50 --freq-range 20 150

  # High quality analysis with detailed output
  python acoustic_analysis.py hall.ply --repair --resolution 25 --absorption 0.2 --output results/concert_hall

  # Quick preview analysis
  python acoustic_analysis.py space.stl --modes 15 --resolution 10 --no-visualizations

For more information: https://github.com/yourusername/AcousticFEM_v2
        """
    )

    # Required arguments
    parser.add_argument(
        'input_mesh',
        type=str,
        help='Input mesh file (STL, OBJ, or PLY format)'
    )

    # Mesh processing
    mesh_group = parser.add_argument_group('Mesh Processing')
    mesh_group.add_argument(
        '--repair',
        action='store_true',
        help='Automatically repair mesh (fix holes, non-manifold edges)'
    )
    mesh_group.add_argument(
        '--resolution',
        type=int,
        default=15,
        metavar='N',
        help='Mesh resolution (elements per dimension). Higher = more accurate but slower. Default: 15 (good quality)'
    )

    # Analysis parameters
    analysis_group = parser.add_argument_group('Analysis Parameters')
    analysis_group.add_argument(
        '--modes',
        type=int,
        default=30,
        metavar='N',
        help='Number of acoustic modes to compute (default: 30)'
    )
    analysis_group.add_argument(
        '--freq-range',
        type=float,
        nargs=2,
        default=[20, 150],
        metavar=('MIN', 'MAX'),
        help='Frequency range in Hz (default: 20 150)'
    )
    analysis_group.add_argument(
        '--absorption',
        type=float,
        default=0.15,
        metavar='ALPHA',
        help='Average absorption coefficient 0-1 (default: 0.15). Examples: 0.05=hard, 0.15=medium, 0.40=soft'
    )
    analysis_group.add_argument(
        '--source-position',
        type=float,
        nargs=3,
        default=None,
        metavar=('X', 'Y', 'Z'),
        help='Sound source position [x, y, z] in meters. Default: center of room'
    )

    # Environmental conditions
    env_group = parser.add_argument_group('Environmental Conditions')
    env_group.add_argument(
        '--temperature',
        type=float,
        default=20.0,
        metavar='T',
        help='Air temperature in °C (default: 20.0)'
    )
    env_group.add_argument(
        '--humidity',
        type=float,
        default=50.0,
        metavar='H',
        help='Relative humidity in %% (default: 50.0)'
    )
    env_group.add_argument(
        '--speed-of-sound',
        type=float,
        default=343.0,
        metavar='C',
        help='Speed of sound in m/s (default: 343.0)'
    )

    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--output',
        '-o',
        type=str,
        default=None,
        metavar='DIR',
        help='Output directory (default: <input_name>_results)'
    )
    output_group.add_argument(
        '--no-visualizations',
        action='store_true',
        help='Skip generating HTML visualizations (faster)'
    )
    output_group.add_argument(
        '--max-gallery-modes',
        type=int,
        default=12,
        metavar='N',
        help='Maximum modes to show in gallery (default: 12)'
    )
    output_group.add_argument(
        '--save-paraview',
        action='store_true',
        help='Save modes in ParaView format (.xdmf/.h5) for advanced 3D visualization'
    )

    # Advanced options
    advanced_group = parser.add_argument_group('Advanced Options')
    advanced_group.add_argument(
        '--element-degree',
        type=int,
        default=1,
        choices=[1, 2],
        help='FEM element polynomial degree (default: 1). Use 2 for higher accuracy'
    )
    advanced_group.add_argument(
        '--slice-plane',
        type=str,
        default='z',
        choices=['x', 'y', 'z'],
        help='Plane for 2D mode visualizations (default: z = horizontal)'
    )
    advanced_group.add_argument(
        '--slice-position',
        type=float,
        default=0.5,
        metavar='POS',
        help='Slice position 0-1 along axis (default: 0.5 = middle)'
    )
    advanced_group.add_argument(
        '--t60-method',
        type=str,
        default='eyring',
        choices=['sabine', 'eyring'],
        help='T60 calculation method (default: eyring, more accurate for high absorption)'
    )

    # Info
    parser.add_argument(
        '--version',
        action='version',
        version='AcousticFEM v2.0.0'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )

    return parser.parse_args()


def load_mesh(input_path: str, repair: bool, max_frequency: float) -> 'dmesh.Mesh':
    """
    Load and process mesh file.

    Args:
        input_path: Path to mesh file
        repair: Whether to repair mesh
        max_frequency: Maximum frequency for adaptive meshing

    Returns:
        FEniCSx mesh object
    """
    input_file = Path(input_path)

    if not input_file.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    print(f"Loading mesh: {input_file.name}")
    print(f"  Format: {input_file.suffix.upper()}")

    # Import mesh
    importer = MeshImporter(input_path)
    trimesh_obj = importer.import_mesh()

    # Check if repair needed
    quality = importer.check_mesh_quality()
    print(f"  Vertices: {quality['vertices']:,}")
    print(f"  Faces: {quality['faces']:,}")
    print(f"  Watertight: {'✓ Yes' if quality['is_watertight'] else '✗ No'}")

    if repair or quality['needs_repair']:
        if not repair:
            print("\n⚠️  Mesh needs repair. Use --repair flag to fix automatically.")
            response = input("Attempt automatic repair? [y/N]: ")
            if response.lower() != 'y':
                print("Exiting. Please repair mesh manually or use --repair flag.")
                sys.exit(1)

        print("\nRepairing mesh...")
        print_progress(1, 4, "Fixing holes")
        trimesh_obj = importer.repair_mesh(
            fix_holes=True,
            remove_duplicates=True,
            max_frequency=max_frequency
        )
        print_progress(4, 4, "Repair complete")
        print()

        # Verify repair
        quality = importer.check_mesh_quality()
        print(f"✓ Mesh repaired: {quality['vertices']:,} vertices, watertight: {quality['is_watertight']}")

    # Convert to FEniCSx
    print("\nConverting to FEM mesh...")
    domain = trimesh_to_fenicsx(trimesh_obj)
    print(f"✓ FEM mesh created: {domain.topology.index_map(0).size_global:,} DOFs")

    return domain


def run_analysis(args):
    """Run complete acoustic analysis pipeline."""

    print_header()

    # Determine output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        input_name = Path(args.input_mesh).stem
        output_dir = Path("acoustic_results") / input_name

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")
    print()

    # Step 1: Load mesh
    print("STEP 1/6: Loading mesh")
    print("-" * 80)
    start_time = time.time()

    domain = load_mesh(
        args.input_mesh,
        args.repair,
        max_frequency=args.freq_range[1]
    )

    print(f"✓ Completed in {time.time() - start_time:.1f}s\n")

    # Step 2: Initialize analyzer
    print("STEP 2/6: Initializing analyzer")
    print("-" * 80)
    start_time = time.time()

    analyzer = AcousticAnalyzer(
        domain,
        speed_of_sound=args.speed_of_sound,
        temperature=args.temperature,
        humidity=args.humidity
    )

    print(f"✓ Completed in {time.time() - start_time:.1f}s\n")

    # Step 3: Compute modes
    print("STEP 3/6: Computing acoustic modes")
    print("-" * 80)
    print(f"Target: {args.modes} modes in {args.freq_range[0]}-{args.freq_range[1]} Hz")
    start_time = time.time()

    modes = analyzer.compute_modes(
        num_modes=args.modes,
        freq_range=tuple(args.freq_range),
        element_degree=args.element_degree
    )

    print(f"\n✓ Computed {len(modes)} modes in {time.time() - start_time:.1f}s\n")

    # Step 4: Calculate T60
    print("STEP 4/6: Calculating reverberation times")
    print("-" * 80)
    start_time = time.time()

    analyzer.calculate_t60(
        alpha_avg=args.absorption,
        method=args.t60_method
    )

    print(f"\n✓ Completed in {time.time() - start_time:.1f}s\n")

    # Step 5: Calculate modal amplitudes
    print("STEP 5/6: Calculating modal amplitudes")
    print("-" * 80)
    start_time = time.time()

    if args.source_position:
        source_pos = np.array(args.source_position)
        print(f"Point source at: {source_pos}")
        analyzer.calculate_modal_amplitudes(
            source_position=source_pos,
            excitation_type='point'
        )
    else:
        # Use center of room
        coords = domain.geometry.x
        center = (coords.min(axis=0) + coords.max(axis=0)) / 2
        center[2] = 1.2  # Ear height
        print(f"Point source at room center: [{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}] m")
        analyzer.calculate_modal_amplitudes(
            source_position=center,
            excitation_type='point'
        )

    print(f"\n✓ Completed in {time.time() - start_time:.1f}s\n")

    # Step 6: Save results and create visualizations
    print("STEP 6/6: Saving results")
    print("-" * 80)
    start_time = time.time()

    # Save data
    analyzer.save_results(str(output_dir), save_paraview=args.save_paraview)
    print(f"✓ Data saved to {output_dir}/")

    # Create visualizations
    if not args.no_visualizations:
        print("\nGenerating visualizations...")
        visualizer = ModeVisualizer(modes, domain)

        # Frequency spectrum
        print_progress(1, 3, "Frequency spectrum")
        fig_spectrum = visualizer.plot_frequency_spectrum(
            show_amplitudes=True,
            show_damping=True
        )
        spectrum_file = output_dir / "frequency_spectrum.html"
        fig_spectrum.write_html(str(spectrum_file))

        # Mode gallery
        print_progress(2, 3, "Mode gallery")
        fig_gallery = visualizer.plot_all_modes_gallery(
            max_modes=args.max_gallery_modes,
            slice_plane=args.slice_plane,
            slice_position=args.slice_position
        )
        gallery_file = output_dir / "mode_gallery.html"
        fig_gallery.write_html(str(gallery_file))

        print_progress(3, 3, "Visualizations complete")
        print()

        print(f"✓ Visualizations saved:")
        print(f"  - {spectrum_file}")
        print(f"  - {gallery_file}")

    print(f"\n✓ Completed in {time.time() - start_time:.1f}s\n")

    # Final summary
    print("=" * 80)
    print("ANALYSIS COMPLETE!")
    print("=" * 80)
    print()
    print("Output files:")
    print(f"  {output_dir}/mode_data.json         - Complete mode data (JSON)")
    print(f"  {output_dir}/modes_summary.csv      - Mode summary (CSV - open in Excel)")
    if not args.no_visualizations:
        print(f"  {output_dir}/frequency_spectrum.html - Interactive spectrum (open in browser)")
        print(f"  {output_dir}/mode_gallery.html      - Mode visualizations (open in browser)")
    print()

    # Quick stats
    if modes:
        print("Quick Statistics:")
        print(f"  Frequency range: {modes[0].frequency:.1f} - {modes[-1].frequency:.1f} Hz")
        print(f"  Number of modes: {len(modes)}")
        if hasattr(modes[0], 't60'):
            avg_t60 = np.mean([m.t60 for m in modes if hasattr(m, 't60') and np.isfinite(m.t60)])
            print(f"  Average T60: {avg_t60:.3f} s")
        if analyzer.room_properties:
            print(f"  Schroeder frequency: {analyzer.room_properties.schroeder_freq():.1f} Hz")
            print(f"  Critical distance: {analyzer.room_properties.critical_dist():.2f} m")
    print()

    if not args.no_visualizations:
        print("To view results:")
        print(f"  open {output_dir}/frequency_spectrum.html")
    print()


def main():
    """Main entry point."""
    args = parse_arguments()

    try:
        run_analysis(args)
    except KeyboardInterrupt:
        print("\n\nAnalysis interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
