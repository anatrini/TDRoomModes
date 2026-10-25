# TDRoomModes in TouchDesigner

Three Script operators turn the computed modes into a moving sound field:

| Operator | Callbacks | Output |
|---|---|---|
| Script CHOP | `modes_chop.py` | one sample per mode: `frequency`, `t60`, `weight` |
| Script TOP | `slice_top.py` | the field on a plane through the room |
| Script TOP | `points_top.py` | the points inside the room with their pressure, for instancing |

The CHOP decides how the room is excited; the TOPs draw the field as a weighted sum of the
mode shapes. All the work is done by `src/tdroommodes/runtime.py`, which needs only numpy:
TouchDesigner's own Python is enough, nothing to install inside TouchDesigner. It needs a
TouchDesigner build with Python 3.11 or later (2023 builds and newer).

These callbacks are tested outside TouchDesigner, against stand-ins for its objects. If a
step below does not behave as described in your build, please open an issue.

You need the TDRoomModes folder on the computer that runs TouchDesigner (clone it or download
the ZIP from GitHub). uv is needed only where you compute new rooms: to try things out,
`examples/box/grid.npz` already holds the modes of an 8 × 6 × 3.5 m room, and the operators
load it when their grid.npz parameter is empty.

## 1. Compute the modes

In a terminal, in the TDRoomModes folder:

```bash
uv run tdroommodes path/to/room.stl --grid 0.25
```

This writes `results/room/grid.npz`. The grid spacing sets the detail of the field in
TouchDesigner: 0.25 m is plenty below 100 Hz, where the shortest wavelength is over 3 m.
See the main README for materials, the vertical axis and the other options.

You can also start the computation from TouchDesigner without blocking it, e.g. from a Text DAT:

```python
import sys
sys.path.insert(0, "/path/to/TDRoomModes/src")
from tdroommodes import runtime
job = runtime.compute("/path/to/TDRoomModes", "/path/to/room.stl", "/path/to/results/room", 0.25)
# later: job.poll() is None while it runs, 0 when grid.npz is ready; the log is in compute.log
```

## 2. The modes CHOP

1. Add a **Script CHOP**. TouchDesigner creates a callbacks Text DAT next to it.
2. On that Text DAT, set **File** to `touchdesigner/modes_chop.py` in this folder and turn on
   **Sync to File**, so that the DAT follows the file. From that path the callbacks find the
   rest of TDRoomModes by themselves.
3. On the Script CHOP, Script page, pulse **Setup Parameters**. A **Room Modes** page appears.
4. **grid.npz**: leave it empty for the example room, or choose a computed file.
   **TDRoomModes folder** is needed only if the callbacks DAT is not synced to a file.

Parameters:

- **Excitation**: *Impulse at the source* (a click, then every mode rings and decays at its
  own rate; pulse **Trigger impulse** to click again, or set **Retrigger every**), *Sine at the
  source* (a steady sine at **Sine frequency**: the modes near it respond most), *Single mode*
  (mode **Mode index** on its own, without decay).
- **Source**: position in metres, in the coordinates of the model.
- **Speed**: time scale. Modes oscillate at tens of hertz, faster than the frame rate; 0.02
  slows them down fifty times, so you can watch each one breathe.

The weights keep the field within [-1, 1]. The callback reads `absTime.seconds`, so the CHOP
should cook every frame; if it stands still, force it from an Execute DAT:
`def onFrameStart(frame): op('script1').cook(force=True)`.

## 3. A slice of the field

1. Add a **Script TOP**; sync its callbacks DAT to `touchdesigner/slice_top.py` as above and
   pulse **Setup Parameters**.
2. Set **Modes CHOP** to the Script CHOP, and **grid.npz** to the same file as the CHOP (or
   leave both empty).
3. Common page: **Pixel Format** 32-bit float (RGBA), so negative values survive.
4. **Plane normal** and **Plane position** choose the plane; **Colors** gives red for positive
   and blue for negative pressure, or the raw value in RGB for your own processing. Alpha is 0
   outside the room.

One pixel per grid point; the image follows the grid. If it appears upside down in your
build, add a Flip TOP.

## 4. A point cloud

1. Add a **Script TOP** with `touchdesigner/points_top.py`, as above: Modes CHOP, the same
   grid.npz, Pixel Format 32-bit float (RGBA). Each pixel is one point inside the room:
   RGB = x, y, z in metres, A = pressure.
2. Add a **Geometry COMP** with a small Sphere or Box SOP inside, plus a Camera COMP, a Light COMP
   and a Render TOP.
3. On the Geometry COMP, Instance page: turn on **Instancing**, set **Instance OP** to the
   points TOP, **Translate X/Y/Z** to r, g, b, and drive scale or colour from a.
   For a size that follows the loudness regardless of sign, put a Math TOP (absolute value)
   on the alpha before the scale.

Spare pixels at the end of the image repeat the first point with zero pressure.

## 5. Sound

`results/room/impulse_response.wav` is the modal part of the room's impulse response from the
source to the receiver: play it with an Audio File In CHOP, or use it as a convolution reverb
for the low end. The channels of the modes CHOP (frequency, t60, weight) can drive oscillators
or be sent via OSC to Max or Pd, for a resonator bank tuned to the room.
