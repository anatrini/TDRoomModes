# TDRoomModes in TouchDesigner

`TDRoomModes.tox` turns the computed modes of a room into a moving sound field. It needs a
TouchDesigner build with Python 3.11 or later (2023 builds and newer) and nothing to install
inside TouchDesigner: the work is done by `src/tdroommodes/runtime.py`, which needs only numpy.

## What you need

- The TDRoomModes folder on the computer that runs TouchDesigner: clone it, or download the
  ZIP from GitHub and unpack it. The component reads its Python modules from there.
- The modes of a room, `grid.npz`. `examples/box/grid.npz` holds an 8 × 6 × 3.5 m room, used
  when no file is given. For your own rooms see "Compute a room" below, the only step that
  needs uv.

## Use the component

1. Drag `touchdesigner/TDRoomModes.tox` into your network.
2. Page **Room**, **TDRoomModes folder**: choose the TDRoomModes folder. Until it is set the
   operators inside show an error, because they cannot find the Python modules.
3. **grid.npz**: leave it empty for the example room, or choose a computed file.

The component has two outputs: a TOP with the field on a plane through the room, and a CHOP
with one sample per mode and the channels `frequency` [Hz], `t60` [s] and `weight` (the current
amplitude of each mode).

### Page Room

| Parameter | Meaning |
|---|---|
| TDRoomModes folder | the folder of the repository |
| grid.npz | the modes of the room; empty: the example room |

### Page Excitation

| Parameter | Meaning |
|---|---|
| Excitation | *Single mode*: one mode on its own, without decay. *Impulse at the source*: a click at the source, then every mode rings and decays at its own rate. *Sine at the source*: a steady sine at the source; the modes near its frequency respond most |
| Mode index | the mode for *Single mode*; 0 is the lowest. Frequencies are in the `frequency` channel and in `modes.csv` |
| Source | position of the source [m], in the coordinates of the model; it must be inside the room |
| Sine frequency | frequency of the sine [Hz]; at the frequency of a mode, that mode dominates |
| Trigger impulse | starts a new impulse |
| Retrigger every | repeats the impulse every so many seconds; 0 = never |
| Speed | time scale: modes oscillate at tens of hertz, faster than the frame rate; 0.05 slows them down twenty times |

### Page View

| Parameter | Meaning |
|---|---|
| Plane normal | the axis perpendicular to the plane: z gives a horizontal plane |
| Plane position | where the plane cuts the room, from 0 to 1 along that axis |
| Colors | *Red + / blue -*: positive pressure red, negative blue, zero black. *Raw value in RGB*: the pressure in R, G and B, for your own processing. Alpha is 0 outside the room |
| Brightness | *Auto*: every frame at full scale, so the shape is always visible. *Physical*: the real level, which shows the decay after an impulse. Below −40 dB the image is black in both |
| Gain | multiplies the pressure |

The image has one pixel per point of the grid, 32-bit float RGBA.

### Things to know

- **Paths.** For files inside the project folder TouchDesigner stores relative paths. If you
  move the .toe file, choose the folder and grid.npz again.
- **Example room.** Its first modes and what they look like on the horizontal plane at mid
  height: 21.45 Hz two halves, left and right; 28.60 Hz two halves, top and bottom; 35.75 Hz
  four quadrants; 42.90 Hz three bands; 49.04 Hz black (a vertical mode, zero at mid height).
  With *Sine at the source* at one of these frequencies the field looks about 85% like that mode.

## Compute a room

In a terminal, in the TDRoomModes folder:

```bash
uv run tdroommodes path/to/room.stl --grid 0.5 -o results/myroom
```

This writes `results/myroom/grid.npz`, to choose as grid.npz. `results/myroom/summary.json`
gives `source_m`, a point inside the room to use as Source, and the floor, ceiling and wall
areas: a floor near zero means the wrong vertical axis (`--up y` or `--up x`). See the main
README for units, materials and the other options.

The computation can also be started from TouchDesigner without blocking it, e.g. from a Text DAT:

```python
import sys
sys.path.insert(0, "/path/to/TDRoomModes/src")
from tdroommodes import runtime
job = runtime.compute("/path/to/TDRoomModes", "/path/to/room.stl", "/path/to/results/room", 0.5)
# job.poll() is None while it runs, 0 when grid.npz is ready; the log is in compute.log
```

## Inside the component

| Operator | Role |
|---|---|
| `script1` (Script CHOP), callbacks from `modes_chop.py` | the weight of each mode at each frame |
| `script2` (Script TOP), callbacks from `slice_top.py` | the field on the plane |
| `execute1` (Execute DAT) | cooks `script1` and `script2` at every frame start; without it they update only when a parameter changes |
| Parameter Execute DAT | passes **Trigger impulse** of the component on to `script1` |
| Out TOP, Out CHOP | the outputs |

The parameters of `script1` and `script2` follow those of the component through expressions
such as `parent().par.Folder`.

The callbacks are stored inside the .tox. After changing `modes_chop.py` or `slice_top.py`,
paste the new text into the callbacks DATs and save the component again. Changes to
`src/tdroommodes` need nothing: the callbacks reload those modules when their files change.

## A point cloud

`points_top.py` is not in the component yet. It is a Script TOP that writes one pixel per point
inside the room, as 32-bit floats: RGB = x, y, z [m], A = pressure. To use it:

1. Inside the component, add a **Script TOP**; set **File** of its callbacks DAT to
   `touchdesigner/points_top.py`, turn on **Sync to File**, and pulse **Setup Parameters**.
2. Set its folder and grid.npz like those of `script2`; it finds `script1` by itself.
3. Add `op('script3').cook(force=True)` to `onFrameStart` in `execute1`, using its real name.
4. Add a **Geometry COMP** with a small Box SOP inside, plus a Camera, a Light and a Render TOP.
   On the Instance page turn on **Instancing**, set **Instance OP** to the Script TOP,
   **Translate X/Y/Z** to r, g, b, and drive scale or colour from a.

## Sound

`impulse_response.wav`, written next to `grid.npz` by `tdroommodes`, is the modal part of the
room's impulse response from source to receiver: play it with an Audio File In CHOP, or use it
as a convolution reverb for the low end. The CHOP output (frequency, t60, weight) can drive
oscillators or be sent via OSC to Max or Pd, for a resonator bank tuned to the room.
