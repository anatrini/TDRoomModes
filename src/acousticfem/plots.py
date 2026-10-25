"""Interactive plots (Plotly)."""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import synth
from .geometry import AXES
from .modes import Modes


def spectrum(modes: Modes, source=None, receiver=None, schroeder: float | None = None):
    """Modal frequencies with their reverberation times and, given a source and a receiver,
    the frequency response between them."""
    rows = 2 if source is not None and receiver is not None else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=(["Response at the receiver"] if rows == 2 else []) + ["Modes"])
    f = modes.frequencies

    if rows == 2:
        phi = modes.evaluate([source, receiver])
        freqs = np.linspace(max(f.min() * 0.8, 1.0), f.max() * 1.05, 2000)
        H = synth.transfer_function(freqs, f, modes.decay, phi[0], phi[1], modes.c)
        fig.add_trace(go.Scatter(x=freqs, y=20 * np.log10(np.abs(H) / np.abs(H).max()),
                                 mode="lines", line=dict(width=1.5), name="response",
                                 hovertemplate="%{x:.1f} Hz<br>%{y:.1f} dB<extra></extra>"), 1, 1)
        fig.update_yaxes(title_text="Level [dB]", row=1, col=1)

    row = rows
    x = np.repeat(f, 3)
    y = np.column_stack([np.zeros_like(f), modes.t60, np.full_like(f, np.nan)]).ravel()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="lightgray", width=1),
                             hoverinfo="skip", showlegend=False), row, 1)
    fig.add_trace(go.Scatter(
        x=f, y=modes.t60, mode="markers", showlegend=False,
        marker=dict(size=8, color=modes.bandwidth, colorscale="Viridis",
                    colorbar=dict(title="Bandwidth [Hz]", len=0.45, y=0.22 if rows == 2 else 0.5)),
        customdata=np.column_stack([np.arange(len(f)), modes.bandwidth]),
        hovertemplate="mode %{customdata[0]}<br>%{x:.2f} Hz<br>T60 %{y:.2f} s"
                      "<br>bandwidth %{customdata[1]:.2f} Hz<extra></extra>"), row, 1)
    fig.update_yaxes(title_text="T60 of the mode [s]", rangemode="tozero", row=row, col=1)
    fig.update_xaxes(title_text="Frequency [Hz]", row=row, col=1)

    if schroeder:
        for r in range(1, rows + 1):
            fig.add_vline(x=schroeder, line_dash="dash", line_color="gray", row=r, col=1)
        fig.add_annotation(x=schroeder, y=1, yref="paper", text="Schroeder", showarrow=False,
                           xanchor="left", font=dict(color="gray"))
    fig.update_layout(height=350 * rows + 100, title=f"{len(f)} modes, {f.min():.1f}–{f.max():.1f} Hz")
    return fig


def slice_values(modes: Modes, axis: str = "z", position: float | None = None,
                 resolution: float = 0.1, mode_indices=None):
    """Mode shapes on a plane perpendicular to `axis` at `position` [m] (default: middle).

    Returns:
        (u axis, v axis, values of shape (n_modes, len(v), len(u)), NaN outside the room)
    """
    k = AXES[axis]
    lo, hi = modes.room.bounds
    position = (lo[k] + hi[k]) / 2 if position is None else position
    u_axis, v_axis = [i for i in range(3) if i != k]
    u = np.arange(lo[u_axis], hi[u_axis] + resolution / 2, resolution)
    v = np.arange(lo[v_axis], hi[v_axis] + resolution / 2, resolution)
    U, V = np.meshgrid(u, v)
    points = np.zeros((U.size, 3))
    points[:, u_axis], points[:, v_axis], points[:, k] = U.ravel(), V.ravel(), position
    values = modes.evaluate(points)
    if mode_indices is not None:
        values = values[:, mode_indices]
    return u, v, values.T.reshape(-1, *U.shape)


def gallery(modes: Modes, axis: str = "z", position: float | None = None, max_modes: int = 12,
            resolution: float | None = None, columns: int = 4):
    """Pressure of the first modes on a plane through the room.

    Red and blue have opposite sign; white lines are the nodal lines, where the mode is silent.
    """
    n = min(max_modes, len(modes))
    lo, hi = modes.room.bounds
    resolution = resolution or float(np.max(hi - lo)) / 120
    u, v, values = slice_values(modes, axis, position, resolution, np.arange(n))
    names = [c for c in "xyz" if c != axis]
    columns = min(columns, n)
    rows = int(np.ceil(n / columns))
    fig = make_subplots(rows=rows, cols=columns, horizontal_spacing=0.04, vertical_spacing=0.08,
                        subplot_titles=[f"{i}: {modes.frequencies[i]:.1f} Hz" for i in range(n)])
    for i in range(n):
        z = values[i] / np.nanmax(np.abs(values[i]))
        fig.add_trace(go.Heatmap(x=u, y=v, z=z, zmin=-1, zmax=1, colorscale="RdBu_r",
                                 showscale=i == 0, colorbar=dict(title="Pressure"),
                                 hovertemplate=f"{names[0]} %{{x:.2f}} m<br>{names[1]} %{{y:.2f}} m"
                                               "<br>%{z:.2f}<extra></extra>"),
                      i // columns + 1, i % columns + 1)
    fig.update_yaxes(scaleanchor="x", constrain="domain")
    for i in range(1, n + 1):
        fig.update_yaxes(scaleanchor=f"x{i}" if i > 1 else "x", row=(i - 1) // columns + 1, col=(i - 1) % columns + 1)
    width = 1200
    height = int(rows * width / columns * (v[-1] - v[0]) / (u[-1] - u[0])) + 120
    k = AXES[axis]
    at = (lo[k] + hi[k]) / 2 if position is None else position
    fig.update_layout(width=width, height=height, title=f"Mode shapes, plane {axis} = {at:.2f} m")
    return fig
