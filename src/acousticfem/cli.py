"""Command line: acousticfem ROOM.stl [options], or acousticfem --box L W H [options]."""

import argparse
import logging
import sys
import time
from pathlib import Path

from . import __version__
from .analysis import analyze
from .materials import list_materials


def _absorption(args):
    if not args.material:
        return args.absorption
    spec = {}
    for item in args.material:
        surface, _, value = item.partition("=")
        try:
            spec[surface] = float(value)
        except ValueError:
            spec[surface] = value
    return spec


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="acousticfem",
        description="Acoustic modes of a room with the finite element method.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  acousticfem room.stl
  acousticfem --box 8 6 3.5 --absorption 0.1
  acousticfem scan.obj --up y --material floor=wood_floor --material walls=plaster_gypsum \\
      --material ceiling=0.05 --grid 0.25
  acousticfem --list-materials""")
    p.add_argument("geometry", nargs="?", help="closed surface of the room (STL, OBJ, PLY, ...)")
    p.add_argument("--box", nargs=3, type=float, metavar=("L", "W", "H"), help="rectangular room [m]")
    p.add_argument("--version", action="version", version=f"acousticfem {__version__}")

    g = p.add_argument_group("geometry")
    g.add_argument("--scale", type=float, default=1.0, help="factor to metres (0.001 for mm)")
    g.add_argument("--up", choices="xyz", default="z", help="vertical axis (default z)")
    g.add_argument("--repair", action="store_true", help="fill holes and fix normals of the surface")
    g.add_argument("--mesher", choices=["auto", "gmsh", "tetwild"], default="auto",
                   help="volume mesher; auto tries gmsh, then fTetWild for scans")

    a = p.add_argument_group("analysis")
    a.add_argument("--fmax", type=float, help="highest frequency [Hz] (default: Schroeder frequency)")
    a.add_argument("--order", type=int, choices=[1, 2], default=2, help="element order (default 2)")
    a.add_argument("--h", type=float, help="element size [m] (default: from fmax)")
    a.add_argument("--absorption", type=float, default=0.1,
                   help="absorption coefficient of all surfaces (default 0.1)")
    a.add_argument("--material", action="append", metavar="SURFACE=MATERIAL",
                   help="material or coefficient of one surface: floor, ceiling, walls "
                        "(x0, x1, y0, y1, floor, ceiling for --box); repeat for each surface")
    a.add_argument("--source", nargs=3, type=float, metavar=("X", "Y", "Z"), help="source [m]")
    a.add_argument("--receiver", nargs=3, type=float, metavar=("X", "Y", "Z"), help="receiver [m]")
    a.add_argument("--temperature", type=float, default=20.0, help="[°C] (default 20)")
    a.add_argument("--humidity", type=float, default=50.0, help="relative humidity [%%] (default 50)")
    a.add_argument("--speed-of-sound", type=float, help="[m/s] (default: from temperature)")

    o = p.add_argument_group("output")
    o.add_argument("-o", "--output", help="output directory (default results/<name>)")
    o.add_argument("--grid", type=float, metavar="SPACING",
                   help="also save the modes on a regular grid with this spacing [m] (grid.npz)")
    o.add_argument("--paraview", action="store_true", help="also save modes.vtu for ParaView")
    o.add_argument("--no-plots", action="store_true", help="skip the HTML plots")
    o.add_argument("--no-wav", action="store_true", help="skip impulse_response.wav")
    o.add_argument("--slice-axis", choices="xyz", default="z", help="axis normal to the gallery plane")
    o.add_argument("--slice-position", type=float, help="gallery plane position [m] (default: middle)")
    o.add_argument("--gallery-modes", type=int, default=12, help="modes in the gallery (default 12)")
    p.add_argument("--list-materials", action="store_true", help="list the materials and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    if not args.list_materials and (args.geometry is None) == (args.box is None):
        p.error("give either a geometry file or --box L W H")
    return args


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    if args.list_materials:
        for key, label in list_materials().items():
            print(f"{key:28s} {label}")
        return 0

    start = time.perf_counter()
    try:
        result = analyze(args.box if args.box else args.geometry, absorption=_absorption(args),
                         f_max=args.fmax, order=args.order, h=args.h, temperature=args.temperature,
                         humidity=args.humidity, c=args.speed_of_sound, up=args.up, scale=args.scale,
                         repair=args.repair, mesher=args.mesher, source=args.source,
                         receiver=args.receiver)
        output = Path(args.output) if args.output else Path("results") / result.room.name.replace(" ", "_")
        result.write(output, plots_=not args.no_plots, grid_spacing=args.grid, paraview=args.paraview,
                     wav=not args.no_wav, slice_axis=args.slice_axis,
                     slice_position=args.slice_position, gallery_modes=args.gallery_modes)
    except (ValueError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    s, m = result.statistics, result.modes
    print(f"{result.room.name}: {s['volume_m3']:.1f} m³, {s['surface_area_m2']:.1f} m²")
    print(f"Schroeder frequency {s['schroeder_frequency_hz']:.1f} Hz")
    print(f"{len(m)} modes, {m.frequencies[0]:.1f}–{m.frequencies[-1]:.1f} Hz, "
          f"{m.info['dofs']} unknowns, element size {m.info['element_size_m']:.2f} m")
    for band in s["octave_bands"]:
        print(f"  {band['frequency_hz']:6.0f} Hz  T60 Sabine {band['t60_sabine_s']:5.2f} s  "
              f"Eyring {band['t60_eyring_s']:5.2f} s")
    print(f"results in {output}/ ({time.perf_counter() - start:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
