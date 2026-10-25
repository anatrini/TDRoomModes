"""Export of modes for other tools: regular grids (TouchDesigner, GLSL), ParaView, CSV."""

import csv

import numpy as np

from .modes import Modes


def sample_grid(modes: Modes, spacing: float) -> dict:
    """Mode shapes on a regular grid covering the room.

    Returns:
        dict with axes "x", "y", "z", "shapes" (nx, ny, nz, n_modes; 0 outside the room),
        "inside" (nx, ny, nz bool), "frequencies" and "decay"
    """
    lo, hi = modes.room.bounds
    axes = [np.arange(a, b + spacing / 2, spacing) for a, b in zip(lo, hi)]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    values = modes.evaluate(np.column_stack([X.ravel(), Y.ravel(), Z.ravel()]))
    inside = ~np.isnan(values[:, 0])
    values[~inside] = 0.0
    shape = X.shape
    return {
        "x": axes[0], "y": axes[1], "z": axes[2],
        "shapes": values.reshape(*shape, len(modes)).astype(np.float32),
        "inside": inside.reshape(shape),
        "frequencies": modes.frequencies,
        "decay": modes.decay,
        "c": np.array(modes.c),
    }


def grid(modes: Modes, path, spacing: float):
    """Save `sample_grid` to a .npz file, loadable with numpy alone (`tdroommodes.synth.load`)."""
    np.savez_compressed(path, **sample_grid(modes, spacing))


def paraview(modes: Modes, path, max_modes: int | None = None):
    """Save the mesh and the mode shapes at its vertices to a .vtu file for ParaView."""
    import pyvista as pv

    mesh = modes.room.mesh
    grid_ = pv.UnstructuredGrid({pv.CellType.TETRA: mesh.t.T}, mesh.p.T)
    vertex_values = modes.shapes[modes.basis.nodal_dofs[0]]
    for i in range(len(modes) if max_modes is None else min(max_modes, len(modes))):
        grid_.point_data[f"mode_{i:03d}_{modes.frequencies[i]:.1f}Hz"] = vertex_values[:, i]
    grid_.save(path)


def table(modes: Modes, path, source=None, receiver=None):
    """Save one row per mode to a CSV file; with source and receiver, also their mode shape values."""
    columns = {
        "mode": np.arange(len(modes)),
        "frequency_hz": modes.frequencies,
        "t60_s": modes.t60,
        "decay_1_per_s": modes.decay,
        "damping_ratio": modes.damping_ratio,
        "bandwidth_hz": modes.bandwidth,
    }
    if source is not None:
        columns["shape_at_source"] = modes.evaluate([source])[0]
    if receiver is not None:
        columns["shape_at_receiver"] = modes.evaluate([receiver])[0]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in zip(*columns.values()):
            writer.writerow([f"{v:.6g}" if isinstance(v, float) else v for v in row])
