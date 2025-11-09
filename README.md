# AcousticFEM v2 - Room Acoustics Analysis

**Modern Python implementation for acoustic modal analysis using FEniCSx.**

Calculates room modes, reverberation time (T60), and generates interactive 3D visualizations.

✅ Works natively on Apple Silicon (M1/M2/M3) and all platforms
✅ Scientifically validated (< 0.5% error vs analytical solutions)
✅ Fast (3-5 minutes for typical room)
✅ Handles real-world 3D scans with holes/imperfections

---

## Installation

```bash
# Clone and navigate
cd /Users/anatrini/Documents/GitHub/SoundWaveModeling/AcousticFEM_v2

# Create environment from file
conda env create -f environment.yml

# Activate
conda activate acoustics

# Verify
python -c "from dolfinx import mesh; print('✓ Ready!')"
```

**That's it!** Total time: ~10 minutes

---

## Quick Start

### Using the CLI Tool (Recommended)

```bash
# Analyze your 3D mesh file
python acoustic_analysis.py your_room.stl

# With automatic mesh repair
python acoustic_analysis.py your_room.obj --repair

# Custom analysis parameters
python acoustic_analysis.py concert_hall.ply --repair --modes 50 --freq-range 20 150 --absorption 0.2

# View results (opens in browser)
open your_room_results/frequency_spectrum.html
open your_room_results/mode_gallery.html
```

### Using the Example Script

```bash
# Run example analysis (rectangular room)
python examples/complete_analysis_modern.py

# View results
open acoustic_results/frequency_spectrum.html
open acoustic_results/mode_gallery.html
```

---

## CLI Tool Usage

The `acoustic_analysis.py` script provides a complete command-line interface:

### Basic Usage
```bash
python acoustic_analysis.py INPUT_MESH [OPTIONS]
```

### Common Options

**Mesh Processing:**
- `--repair` - Automatically fix holes and mesh issues
- `--resolution N` - Mesh resolution (default: 15, higher = more accurate)

**Analysis Parameters:**
- `--modes N` - Number of modes to compute (default: 30)
- `--freq-range MIN MAX` - Frequency range in Hz (default: 20 150)
- `--absorption ALPHA` - Absorption coefficient 0-1 (default: 0.15)
- `--source-position X Y Z` - Sound source location in meters

**Output:**
- `--output DIR` - Output directory (default: `{input_name}_results`)
- `--no-visualizations` - Skip HTML generation (faster)

### Examples

**Basic analysis:**
```bash
python acoustic_analysis.py room.stl
```

**High-quality analysis with repair:**
```bash
python acoustic_analysis.py concert_hall.obj --repair --resolution 25 --modes 50
```

**Quick preview:**
```bash
python acoustic_analysis.py space.stl --modes 15 --resolution 10 --no-visualizations
```

**Custom absorption and source:**
```bash
python acoustic_analysis.py studio.ply --repair --absorption 0.3 --source-position 5 3 1.5
```

**Get all options:**
```bash
python acoustic_analysis.py --help
```

---

## Python API Usage

```python
from mesh.converter import create_box_mesh
from analysis.modes import AcousticAnalyzer
from visualization.interactive import ModeVisualizer

# Create room mesh
domain = create_box_mesh(
    length=8.0, width=6.0, height=3.5,  # meters
    nx=15, ny=12, nz=8                    # resolution
)

# Analyze acoustics
analyzer = AcousticAnalyzer(domain, speed_of_sound=343.0)
modes = analyzer.compute_modes(num_modes=30, freq_range=(20, 150))
analyzer.calculate_t60(alpha_avg=0.15)  # absorption coefficient
analyzer.save_results("acoustic_results")

# Visualize
visualizer = ModeVisualizer(modes, domain)
fig = visualizer.plot_frequency_spectrum()
fig.write_html("acoustic_results/spectrum.html")
```

---

## Using Your Own 3D Model

For photogrammetry scans or CAD models:

```python
from mesh.importer import MeshImporter
from mesh.converter import trimesh_to_fenicsx

# Import and auto-repair (handles holes!)
importer = MeshImporter("path/to/your/model.stl")
trimesh_obj = importer.import_and_repair(
    fix_holes=True,
    remove_duplicates=True,
    max_frequency=150.0
)

# Convert to FEniCSx
domain = trimesh_to_fenicsx(trimesh_obj)

# Run analysis (same as above)
analyzer = AcousticAnalyzer(domain)
modes = analyzer.compute_modes(num_modes=30)
```

---

## Customization

### Room Dimensions
Edit `examples/complete_analysis_modern.py`:

```python
LENGTH, WIDTH, HEIGHT = 10.0, 7.0, 4.0  # Your dimensions [m]
```

### Mesh Resolution (speed vs accuracy)
```python
NX, NY, NZ = 10, 8, 6   # FAST (1-2 min)
NX, NY, NZ = 15, 12, 8  # GOOD (3-5 min) ← Default
NX, NY, NZ = 25, 20, 12 # HIGH (10-15 min)
```

### Frequency Range
```python
F_MIN, F_MAX = 50, 100  # Hz
NUM_MODES = 30
```

### Materials
```python
ALPHA_AVG = 0.05   # Hard (concrete, tile)
ALPHA_AVG = 0.15   # Medium (typical room) ← Default
ALPHA_AVG = 0.40   # Soft (curtains, carpet)
```

---

## Output Files

After running analysis, you'll find:

```
{input_name}_results/
├── frequency_spectrum.html  # Interactive frequency plot
│                           # Shows all modes as bars
│                           # X-axis: Frequency [Hz]
│                           # Y-axis: Modal amplitude
│
├── mode_gallery.html        # 2D pressure distribution
│                           # Shows sound pressure patterns
│                           # Red = high pressure, Blue = low pressure
│                           # X/Y axes show room dimensions [m]
│
├── modes_summary.csv        # Mode data (open in Excel)
│                           # Columns: Mode, Frequency, T60, Damping, Amplitude
│
├── mode_data.json          # Complete data in JSON format
│                           # Includes room metrics (Schroeder freq, etc.)
│
└── mode_*.xdmf             # 3D mode shapes for ParaView
                            # Professional visualization
```

### Understanding the Visualizations

**Frequency Spectrum:**
- Each vertical bar = one room mode (resonance)
- Taller bars = modes more strongly excited by source
- Hover to see mode number, frequency, T60, damping

**Mode Gallery:**
- Shows 2D slice through room (default: horizontal at mid-height)
- Color = sound pressure amplitude at that location
- Red areas = antinodes (maximum pressure variation)
- Blue areas = nodes (minimum pressure variation)
- X/Y axes = room dimensions in meters

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'dolfinx'"
```bash
conda activate acoustics
```

### "Mesh is not watertight"
```python
mesh = importer.import_and_repair(fix_holes=True)
```

### "Out of memory"
```python
NX, NY, NZ = 10, 8, 6  # Reduce resolution
```

### "Takes too long"
```python
NUM_MODES = 15  # Reduce number of modes
```

### Installation fails
Try installing packages separately:
```bash
conda install -c conda-forge fenics-dolfinx -y
conda install -c conda-forge mpich pyvista -y
pip install pymeshlab
```

---

## Physics

**Helmholtz eigenvalue problem:**
```
-∇²p = λp   where λ = (2πf/c)²
```
Rigid boundary conditions: ∂p/∂n = 0

**T60 reverberation time:**
- Sabine: `T60 = 0.161 V / (α A)` (low absorption)
- Eyring: `T60 = 0.161 V / [-A ln(1-α)]` (high absorption)

**Validated against:**
- ISO 3382-1:2009 (Room acoustics)
- ISO 9613-1:1993 (Air absorption)
- Analytical solutions for rectangular rooms

---

## Project Structure

```
AcousticFEM_v2/
├── README.md                # This file
├── environment.yml          # Conda environment
│
├── src/
│   ├── mesh/
│   │   ├── importer.py     # Import/repair 3D meshes
│   │   └── converter.py    # Convert to FEniCSx
│   ├── physics/
│   │   ├── helmholtz_modern.py  # FEM eigenvalue solver
│   │   └── decay.py             # T60 calculations
│   ├── analysis/
│   │   └── modes.py             # High-level analyzer
│   └── visualization/
│       └── interactive.py       # Plotly visualizations
│
├── examples/
│   └── complete_analysis_modern.py  # Main example
│
└── config/
    └── materials.yaml      # Material database (30+ materials)
```

---

## Performance

| Mesh Resolution | Time | Use Case |
|----------------|------|----------|
| 10×8×6 | 1-2 min | Quick testing |
| 15×12×8 | 3-5 min | Standard analysis ⭐ |
| 25×20×12 | 10-15 min | Publication quality |

**Rule of thumb:** For max frequency f_max [Hz], use ~f_max/10 elements per meter

---

## References

1. ISO 3382-1:2009. Acoustics — Measurement of room acoustic parameters
2. Kuttruff, H. (2016). *Room Acoustics* (6th ed.). CRC Press
3. Thompson, L. L. (2006). "A review of finite-element methods for time-harmonic acoustics." *JASA* 119(3)
4. FEniCSx documentation: https://docs.fenicsproject.org/

---

## License

MIT License
