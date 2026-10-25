# TDRoomModes

The resonances of real rooms, computed with physical accuracy and played in TouchDesigner.

A room resonates at its modes: standing waves at particular frequencies, each with its own
pattern of loud and silent regions and its own decay time. Below the Schroeder frequency the
modes are few and far apart, and they shape what a room does to low sounds. TDRoomModes
computes them for rooms of any shape, from a 3D model or a scan, and brings them into
TouchDesigner, where the sound field of the room can be excited, animated and drawn in real
time: as slices, as point clouds, or as data for your own networks.

It works in two steps:

1. **Compute, once per room** (Python, `uv run tdroommodes room.stl --grid 0.25`): the finite
   element method finds every mode up to the Schroeder frequency on the real geometry, and the
   materials of floor, walls and ceiling give each mode its decay.
2. **Play, in real time** (TouchDesigner, `touchdesigner/`): a Script CHOP sets the weight of
   each mode for an impulse, a sine or a single mode at a source you can move; Script TOPs draw
   the resulting field. Each frame is one weighted sum of precomputed shapes.

The computation also gives reverberation times per octave band, the response between a source
and a receiver, and the modal impulse response as a WAV file.

## Installation

TDRoomModes needs [uv](https://docs.astral.sh/uv/) and runs on macOS, Windows and Linux.

```bash
git clone https://github.com/anatrini/TDRoomModes.git
cd TDRoomModes
uv sync
```

`uv sync` creates the environment in `.venv` with Python 3.11 or later and every dependency,
all from prebuilt packages: nothing to compile. Check it with `uv run pytest`.

## Quick start

```bash
# A scan or a 3D model: closed surface, in metres
uv run tdroommodes data/datini_25k.stl

# A rectangular room, 8 x 6 x 3.5 m, absorption 0.1 everywhere, modes up to 150 Hz
uv run tdroommodes --box 8 6 3.5 --absorption 0.1 --fmax 150

# Materials per surface, model in millimetres with y up, grid export for TouchDesigner
uv run tdroommodes hall.obj --scale 0.001 --up y \
    --material floor=wood_floor --material walls=plaster_gypsum --material ceiling=0.05 \
    --grid 0.25

uv run tdroommodes --list-materials
uv run tdroommodes --help
```

Results go to `results/<name>/`:

| File | Content |
|---|---|
| `summary.json` | volume, surfaces, reverberation times, Schroeder frequency, mesh, timings |
| `modes.csv` | one row per mode: frequency, T60, decay, damping ratio, bandwidth, value at source and receiver |
| `modes.npz` | frequencies, decay, mesh and mode shapes (numpy) |
| `spectrum.html` | the modes and the response at the receiver |
| `gallery.html` | mode shapes on a plane through the room |
| `impulse_response.wav` | modal part of the impulse response from source to receiver |
| `grid.npz` | with `--grid SPACING`: mode shapes on a regular grid |
| `modes.vtu` | with `--paraview`: mesh and mode shapes for ParaView |

Source and receiver default to two asymmetric points inside the room; set them with
`--source X Y Z` and `--receiver X Y Z`.

## Notebooks

```bash
uv run jupyter lab notebooks/
```

1. `01_rectangular_room.ipynb`: a rectangular room checked against the exact solution;
   materials, decay, response and listening.
2. `02_real_room_to_TouchDesigner.ipynb`: the scan of Palazzo Datini, from the surface to the
   animated field and the export for TouchDesigner.

## Python

```python
import tdroommodes as trm

result = trm.analyze(
    "data/datini_25k.stl",
    absorption={"floor": "wood_floor", "walls": "plaster_lime_rough", "ceiling": 0.1},
)
print(result.statistics["schroeder_frequency_hz"], len(result.modes))
print(result.modes.frequencies, result.modes.t60)
result.write("results/datini", grid_spacing=0.5)
```

For a rectangular room pass its dimensions, `trm.analyze((8, 6, 3.5), ...)`; its surfaces are
`x0, x1, y0, y1, floor, ceiling`. Absorption is a number for every surface, or a dict that gives
each surface a material name, a number, or six octave-band coefficients (125 Hz to 4 kHz).

The steps are also available one by one: `trm.load_surface`, `trm.from_surface` or `trm.box`,
`trm.compute`, `Modes.set_absorption`, `Modes.evaluate`, `trm.room_statistics`.

## TouchDesigner

[`touchdesigner/README.md`](touchdesigner/README.md) explains how to set up the three Script
operators, step by step:

| Operator | Output |
|---|---|
| Script CHOP, `modes_chop.py` | one sample per mode: `frequency`, `t60`, `weight`; excitation by impulse, sine or single mode, at a source you place |
| Script TOP, `slice_top.py` | the field on a plane through the room |
| Script TOP, `points_top.py` | the points inside the room, RGB = position, A = pressure, for instancing |

Below the Schroeder frequency the pressure in the room is a sum of modes,

$$p(\mathbf{x}, t) = \sum_n a_n\, \varphi_n(\mathbf{x})\, e^{-\delta_n t} \cos(\omega_n t + \theta_n).$$

The shapes φₙ are the expensive part and are computed once. Excitation, frequency, decay and
source position only change the weights aₙ, so each frame is one weighted sum: cheap enough
for real time. The work is done by `src/tdroommodes/runtime.py`, which imports only numpy, so
TouchDesigner's own Python runs it with nothing to install.

The data, for your own networks or shaders:

- `grid.npz`: `shapes` (x × y × z × modes, zero outside the room), `inside`, the axes `x`,
  `y`, `z`, `frequencies`, `decay`.
- `modes.npz`: `vertices`, `tetrahedra`, `vertex_shapes` (vertices × modes), on the mesh.
- `src/tdroommodes/synth.py` (numpy only): free decay, sine source, impulse response,
  transfer function.

## Method

**Modes.** The Helmholtz eigenvalue problem with rigid walls,
−∇²φ = k²φ in the room and ∂φ/∂n = 0 on the walls, f = ck/2π, is discretized with quadratic
Lagrange elements on tetrahedra ([scikit-fem](https://github.com/kinnala/scikit-fem)) and
solved with shift-invert Lanczos (SciPy, ARPACK). The solver asks for all modes above 0 Hz and
repeats with more if the highest one found is still below f_max, so no mode in the range is
skipped. Shapes are normalized to ∫φ² dV = 1.

**Mesh.** The element size is a quarter of the shortest wavelength (c / f_max / 4), which keeps
the frequency error below 1% (tests). The volume mesh comes from
[gmsh](https://gmsh.info) when the surface is clean, and from
[fTetWild](https://github.com/wildmeshing/fTetWild) when gmsh rejects it: scans often
intersect themselves, and fTetWild keeps the boundary within 0.2% of the room size from the
original. Separate parts below 0.1% of the room volume are scan debris and are dropped.

**Decay.** Wall absorption enters as a first-order perturbation of the rigid-wall modes
(Kuttruff, *Room Acoustics*, ch. 3): a wall of real normalized admittance β adds
(c/2) ∫ β φₙ² dS to the amplitude decay constant δₙ, and air adds c·m/2, with m the
energy attenuation of ISO 9613-1. β comes from the random-incidence absorption coefficient
by inverting the Paris formula (β ≈ α/8 for small α). For a diffuse field this reproduces the
Sabine formula exactly; for single modes it gives each mode its own decay. T60ₙ = 3 ln 10 / δₙ.
Absorption coefficients come from octave-band tables: below 125 Hz, where most modes are, the
125 Hz value is used.

**Limits.**

- Modes describe the room below the Schroeder frequency. Above it they overlap: the sum is
  still usable as material for sound and image, but no longer a faithful model of the room.
- The perturbation is accurate for absorption up to about 0.3–0.4 at the modal frequencies;
  above that, decay times are approximate (a warning says so).
- Walls are locally reacting with real impedance; the source is a point.
- The `up` axis decides which surfaces are floor and ceiling (outward normal within about 45°
  of vertical). Check the areas in `summary.json`: a model rotated by mistake shows almost
  only walls.
- Geometry details much smaller than the wavelength do not affect the modes; a scan can be
  coarse. Thin gaps in a scan, however, can create spurious cavities, which show up as
  Helmholtz resonances (very low modes concentrated in a small region).

## Validation

`uv run pytest` runs 39 tests, among them:

- frequencies of a rectangular room against the exact solution, error below 1% with linear
  and quadratic elements (0.45% for the 8 × 6 × 3.5 m room up to 150 Hz);
- mode shapes at given points against the exact cosine;
- decay of the oblique mode (1,1,1) against the Sabine formula;
- air attenuation against the table of ISO 9613-1 (20 °C, 50%, 125 Hz–4 kHz);
- volume and surfaces of an L-shaped room with both meshers;
- the command line end to end;
- the TouchDesigner side: fields against the formulas of `synth`, the field kept within
  [-1, 1], the runtime importing nothing but numpy, and the Script operator callbacks run
  against stand-ins for TouchDesigner's objects (not inside TouchDesigner itself).

## Structure

```
src/tdroommodes/
    geometry.py     surfaces, volume meshes (gmsh, fTetWild), floor/walls/ceiling
    modes.py        eigenmodes, decay from absorption, evaluation at points
    physics.py      Sabine, Eyring, ISO 9613-1, Schroeder, critical distance
    materials.py    absorption of the surfaces; materials.yaml, 25 materials
    statistics.py   reverberation time per octave band
    synth.py        sound fields from the modes, numpy only
    runtime.py      real-time fields for TouchDesigner, numpy only
    export.py       grid, ParaView, CSV
    plots.py        spectrum and mode gallery (Plotly)
    analysis.py     the whole pipeline
    cli.py          the tdroommodes command
touchdesigner/      Script CHOP and TOP callbacks, setup guide
notebooks/          examples
tests/              validation
examples/box/        modes of an 8 x 6 x 3.5 m room, ready for TouchDesigner
data/               scans of Palazzo Datini
```

## References

1. H. Kuttruff, *Room Acoustics*, 6th ed., CRC Press, 2016.
2. ISO 9613-1:1993, Acoustics — Attenuation of sound during propagation outdoors, part 1.
3. M. R. Schroeder, K. H. Kuttruff, "On frequency response curves in rooms", *JASA* 34, 1962.
4. T. Gustafsson, G. D. McBain, "scikit-fem: a Python package for finite element assembly",
   *Journal of Open Source Software* 5(52), 2020.
5. C. Geuzaine, J.-F. Remacle, "Gmsh: a 3-D finite element mesh generator", *IJNME* 79, 2009.
6. Y. Hu et al., "Fast tetrahedral meshing in the wild", *ACM Transactions on Graphics* 39(4), 2020.

## License

MIT, see [LICENSE](LICENSE).
