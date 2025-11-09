"""
Interactive 3D Visualization Module

Create interactive visualizations of acoustic modes using Plotly.
"""

import numpy as np
from typing import List, Optional, Tuple
import logging
from tqdm import tqdm

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logging.warning("Plotly not available. Install with: pip install plotly")

try:
    from dolfinx import mesh, fem
    from dolfinx.fem import Function
    FENICSX_AVAILABLE = True
except ImportError:
    FENICSX_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModeVisualizer:
    """
    Interactive visualization of acoustic modes using Plotly.
    """

    def __init__(self, modes: List, mesh: Optional['Mesh'] = None):
        """
        Initialize visualizer.

        Args:
            modes: List of AcousticMode objects
            mesh: FEniCS mesh (optional, will extract from modes if not provided)
        """
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly required. Install with: pip install plotly")

        self.modes = modes
        self.mesh = mesh

        if not self.modes:
            raise ValueError("No modes provided")

        # Extract mesh from first mode if not provided
        if self.mesh is None and hasattr(self.modes[0].eigenfunction, 'function_space'):
            self.mesh = self.modes[0].eigenfunction.function_space.mesh

    def plot_mode_interactive(
        self,
        mode_index: int = 0,
        slice_axis: str = 'z',
        num_slices: int = 5,
        colorscale: str = 'RdBu',
        show_mesh: bool = False
    ):
        """
        Create interactive 3D visualization of a single mode.

        Args:
            mode_index: Index of mode to visualize
            slice_axis: Axis for slicing ('x', 'y', or 'z')
            num_slices: Number of cross-sections
            colorscale: Plotly colorscale name
            show_mesh: Show mesh wireframe

        Returns:
            Plotly Figure object
        """
        if mode_index >= len(self.modes):
            raise ValueError(f"Mode index {mode_index} out of range (max: {len(self.modes)-1})")

        mode = self.modes[mode_index]

        logger.info(f"Creating visualization for Mode {mode.mode_number}: {mode.frequency:.2f} Hz")

        # Sample mode shape on a grid
        grid_data = self._sample_mode_on_grid(mode, resolution=50)

        # Create figure
        fig = self._create_volume_plot(
            grid_data, mode, slice_axis, num_slices, colorscale
        )

        return fig

    def plot_all_modes_gallery(
        self,
        max_modes: int = 12,
        slice_plane: str = 'z',
        slice_position: float = 0.5,
        colorscale: str = 'RdBu'
    ):
        """
        Create gallery view of multiple modes.

        Args:
            max_modes: Maximum number of modes to show
            slice_plane: Plane for 2D slice ('x', 'y', or 'z')
            slice_position: Position along axis (0-1)
            colorscale: Colorscale name

        Returns:
            Plotly Figure with subplots
        """
        n_modes = min(max_modes, len(self.modes))

        logger.info(f"Creating gallery of {n_modes} modes")

        # Calculate grid layout
        n_cols = min(4, n_modes)
        n_rows = int(np.ceil(n_modes / n_cols))

        # Create subplots
        fig = make_subplots(
            rows=n_rows, cols=n_cols,
            subplot_titles=[f"Mode {m.mode_number}: {m.frequency:.1f} Hz"
                          for m in self.modes[:n_modes]],
            specs=[[{'type': 'heatmap'} for _ in range(n_cols)] for _ in range(n_rows)],
            horizontal_spacing=0.1,
            vertical_spacing=0.15
        )

        # Determine axis labels based on slice plane
        if slice_plane == 'z':
            xlabel, ylabel = 'X [m]', 'Y [m]'
            slice_info = f'Horizontal slice at Z = {slice_position:.1f}'
        elif slice_plane == 'y':
            xlabel, ylabel = 'X [m]', 'Z [m]'
            slice_info = f'Vertical slice at Y = {slice_position:.1f}'
        else:  # x
            xlabel, ylabel = 'Y [m]', 'Z [m]'
            slice_info = f'Vertical slice at X = {slice_position:.1f}'

        # Add each mode as a heatmap
        for i, mode in enumerate(tqdm(self.modes[:n_modes], desc="Sampling modes", unit="mode")):
            row = i // n_cols + 1
            col = i % n_cols + 1

            # Sample mode on 2D slice
            slice_data = self._sample_mode_on_slice(mode, slice_plane, slice_position)

            fig.add_trace(
                go.Heatmap(
                    z=slice_data['values'],
                    x=slice_data['x'],
                    y=slice_data['y'],
                    colorscale=colorscale,
                    showscale=(i == 0),  # Only show colorbar for first plot
                    hovertemplate=f'<b>Mode {mode.mode_number}</b><br>' +
                                 f'Frequency: {mode.frequency:.1f} Hz<br>' +
                                 f'{xlabel}: %{{x:.2f}}<br>' +
                                 f'{ylabel}: %{{y:.2f}}<br>' +
                                 f'Pressure: %{{z:.3f}}<extra></extra>',
                    colorbar=dict(
                        title=dict(
                            text="Pressure<br>Amplitude",
                            side="right"
                        )
                    ) if i == 0 else None
                ),
                row=row, col=col
            )

        # Update axes labels for all subplots
        for i in range(1, n_modes + 1):
            row = (i - 1) // n_cols + 1
            col = (i - 1) % n_cols + 1
            fig.update_xaxes(title_text=xlabel, row=row, col=col)
            fig.update_yaxes(title_text=ylabel, row=row, col=col)

        # Update layout
        fig.update_layout(
            title=f"<b>Acoustic Modes Gallery</b><br>" +
                  f"<sub>{slice_info} - Showing sound pressure distribution (Red = high, Blue = low)</sub>",
            height=300 * n_rows,
            width=300 * n_cols,
            showlegend=False
        )

        return fig

    def plot_frequency_spectrum(
        self,
        show_amplitudes: bool = True,
        show_damping: bool = False
    ):
        """
        Plot frequency spectrum with modal amplitudes.

        Args:
            show_amplitudes: Show modal amplitudes as bar heights
            show_damping: Color bars by damping ratio

        Returns:
            Plotly Figure
        """
        frequencies = [m.frequency for m in self.modes]
        amplitudes = [m.amplitude for m in self.modes]
        damping = [m.damping_ratio for m in self.modes]

        if show_amplitudes:
            y_values = amplitudes
            y_label = "Modal Amplitude"
        else:
            y_values = [1.0] * len(self.modes)
            y_label = "Presence"

        # Create stem plot (works better for clustered frequencies)
        fig = go.Figure()

        # Determine colors
        if show_damping:
            colors = damping
            colorscale = 'Viridis'
            show_colorbar = True
            colorbar_title = "Damping Ratio ξ"
        else:
            colors = 'steelblue'
            colorscale = None
            show_colorbar = False
            colorbar_title = None

        # Add stems (vertical lines)
        for i, mode in enumerate(self.modes):
            fig.add_trace(go.Scatter(
                x=[mode.frequency, mode.frequency],
                y=[0, y_values[i]],
                mode='lines',
                line=dict(color='lightgray', width=1),
                showlegend=False,
                hoverinfo='skip'
            ))

        # Add markers at the top
        if show_damping:
            fig.add_trace(go.Scatter(
                x=frequencies,
                y=y_values,
                mode='markers',
                marker=dict(
                    size=10,
                    color=damping,
                    colorscale='Viridis',
                    colorbar=dict(title="Damping Ratio ξ"),
                    showscale=True,
                    line=dict(width=1, color='white')
                ),
                hovertemplate='<b>Mode %{customdata[0]}</b><br>' +
                             'Frequency: %{x:.2f} Hz<br>' +
                             'Amplitude: %{customdata[1]:.3f}<br>' +
                             'Damping: %{customdata[2]:.4f}<extra></extra>',
                customdata=[[m.mode_number, m.amplitude, m.damping_ratio] for m in self.modes],
                showlegend=False
            ))
        else:
            fig.add_trace(go.Scatter(
                x=frequencies,
                y=y_values,
                mode='markers',
                marker=dict(
                    size=10,
                    color='steelblue',
                    line=dict(width=1, color='white')
                ),
                hovertemplate='<b>Mode %{customdata[0]}</b><br>' +
                             'Frequency: %{x:.2f} Hz<br>' +
                             'Amplitude: %{customdata[1]:.3f}<extra></extra>',
                customdata=[[m.mode_number, m.amplitude] for m in self.modes],
                showlegend=False
            ))

        # Determine appropriate x-axis range
        freq_min = min(frequencies)
        freq_max = max(frequencies)
        freq_range = freq_max - freq_min

        # Add some padding around the data
        if freq_range < 1:  # Very narrow range
            x_min = freq_min - 5
            x_max = freq_max + 5
        else:
            x_min = freq_min - 0.1 * freq_range
            x_max = freq_max + 0.1 * freq_range

        fig.update_layout(
            title="<b>Modal Frequency Spectrum</b><br>" +
                  f"<sub>{len(self.modes)} acoustic modes | Frequency range: {freq_min:.1f}-{freq_max:.1f} Hz</sub>",
            xaxis_title="Frequency [Hz]",
            yaxis_title=y_label,
            xaxis=dict(range=[x_min, x_max]),
            yaxis=dict(rangemode='tozero'),
            hovermode='closest',
            height=600,
            font=dict(size=12)
        )

        return fig

    def create_interactive_explorer(self, resolution: int = 30):
        """
        Create fully interactive mode explorer with sliders.

        Args:
            resolution: Grid resolution for sampling

        Returns:
            Plotly Figure with slider controls
        """
        logger.info("Creating interactive mode explorer (this may take a moment)...")

        # Sample all modes on a grid
        all_grids = []
        for mode in tqdm(self.modes, desc="Sampling modes on 3D grid", unit="mode"):
            grid_data = self._sample_mode_on_grid(mode, resolution=resolution)
            all_grids.append(grid_data)

        # Create figure with frames (one per mode)
        frames = []
        for i, (mode, grid) in enumerate(zip(self.modes, all_grids)):
            # Create isosurface for this mode
            frame = go.Frame(
                data=[go.Isosurface(
                    x=grid['x'].flatten(),
                    y=grid['y'].flatten(),
                    z=grid['z'].flatten(),
                    value=grid['values'].flatten(),
                    isomin=-np.max(np.abs(grid['values'])),
                    isomax=np.max(np.abs(grid['values'])),
                    surface_count=5,
                    colorscale='RdBu',
                    caps=dict(x_show=False, y_show=False, z_show=False),
                    colorbar=dict(title="Amplitude"),
                    hovertemplate='x: %{x:.2f}<br>y: %{y:.2f}<br>z: %{z:.2f}<br>φ: %{value:.3f}<extra></extra>'
                )],
                name=str(i),
                layout=dict(
                    title=f"Mode {mode.mode_number}: {mode.frequency:.2f} Hz, "
                          f"ξ={mode.damping_ratio:.4f}"
                )
            )
            frames.append(frame)

        # Initial figure (first mode)
        grid0 = all_grids[0]
        mode0 = self.modes[0]

        fig = go.Figure(
            data=[go.Isosurface(
                x=grid0['x'].flatten(),
                y=grid0['y'].flatten(),
                z=grid0['z'].flatten(),
                value=grid0['values'].flatten(),
                isomin=-np.max(np.abs(grid0['values'])),
                isomax=np.max(np.abs(grid0['values'])),
                surface_count=5,
                colorscale='RdBu',
                caps=dict(x_show=False, y_show=False, z_show=False),
                colorbar=dict(title="Amplitude")
            )],
            frames=frames
        )

        # Add slider
        sliders = [dict(
            active=0,
            yanchor="top",
            y=-0.1,
            xanchor="left",
            currentvalue=dict(
                prefix="Mode: ",
                visible=True,
                xanchor="right"
            ),
            steps=[dict(
                args=[
                    [str(i)],
                    dict(frame=dict(duration=0, redraw=True), mode="immediate")
                ],
                label=f"{m.mode_number} ({m.frequency:.1f} Hz)",
                method="animate"
            ) for i, m in enumerate(self.modes)]
        )]

        fig.update_layout(
            title=f"Mode {mode0.mode_number}: {mode0.frequency:.2f} Hz",
            sliders=sliders,
            scene=dict(
                xaxis_title="X [m]",
                yaxis_title="Y [m]",
                zaxis_title="Z [m]",
                aspectmode='data'
            ),
            height=700
        )

        return fig

    def _sample_mode_on_grid(
        self,
        mode,
        resolution: int = 50
    ) -> dict:
        """
        Sample mode shape on a regular 3D grid.

        Args:
            mode: AcousticMode object
            resolution: Number of points per dimension

        Returns:
            Dict with 'x', 'y', 'z', 'values'
        """
        # Get mesh bounds
        coords = self.mesh.geometry.x
        x_min, y_min, z_min = coords.min(axis=0)
        x_max, y_max, z_max = coords.max(axis=0)

        # Create grid
        x = np.linspace(x_min, x_max, resolution)
        y = np.linspace(y_min, y_max, resolution)
        z = np.linspace(z_min, z_max, resolution)

        X, Y, Z = np.meshgrid(x, y, z, indexing='ij')

        # Sample eigenfunction
        values = np.zeros_like(X)

        logger.info(f"Sampling mode on {resolution}³ grid...")

        for i in range(resolution):
            for j in range(resolution):
                for k in range(resolution):
                    point = np.array([X[i,j,k], Y[i,j,k], Z[i,j,k]])
                    try:
                        values[i,j,k] = mode.evaluate_at(point)
                    except:
                        values[i,j,k] = 0.0

        return {'x': X, 'y': Y, 'z': Z, 'values': values}

    def _sample_mode_on_slice(
        self,
        mode,
        axis: str = 'z',
        position: float = 0.5,
        resolution: int = 100
    ) -> dict:
        """
        Sample mode on a 2D slice.

        Args:
            mode: AcousticMode object
            axis: Slice axis ('x', 'y', or 'z')
            position: Position along axis (0-1)
            resolution: Grid resolution

        Returns:
            Dict with slice data
        """
        coords = self.mesh.geometry.x
        x_min, y_min, z_min = coords.min(axis=0)
        x_max, y_max, z_max = coords.max(axis=0)

        if axis == 'z':
            z_val = z_min + position * (z_max - z_min)
            x = np.linspace(x_min, x_max, resolution)
            y = np.linspace(y_min, y_max, resolution)
            X, Y = np.meshgrid(x, y)
            values = np.zeros_like(X)

            for i in range(resolution):
                for j in range(resolution):
                    try:
                        values[i,j] = mode.evaluate_at([X[i,j], Y[i,j], z_val])
                    except:
                        values[i,j] = 0.0

            return {'x': x, 'y': y, 'values': values}

        elif axis == 'y':
            y_val = y_min + position * (y_max - y_min)
            x = np.linspace(x_min, x_max, resolution)
            z = np.linspace(z_min, z_max, resolution)
            X, Z = np.meshgrid(x, z)
            values = np.zeros_like(X)

            for i in range(resolution):
                for j in range(resolution):
                    try:
                        values[i,j] = mode.evaluate_at([X[i,j], y_val, Z[i,j]])
                    except:
                        values[i,j] = 0.0

            return {'x': x, 'y': z, 'values': values}

        else:  # axis == 'x'
            x_val = x_min + position * (x_max - x_min)
            y = np.linspace(y_min, y_max, resolution)
            z = np.linspace(z_min, z_max, resolution)
            Y, Z = np.meshgrid(y, z)
            values = np.zeros_like(Y)

            for i in range(resolution):
                for j in range(resolution):
                    try:
                        values[i,j] = mode.evaluate_at([x_val, Y[i,j], Z[i,j]])
                    except:
                        values[i,j] = 0.0

            return {'x': y, 'y': z, 'values': values}

    def _create_volume_plot(
        self,
        grid_data: dict,
        mode,
        slice_axis: str,
        num_slices: int,
        colorscale: str
    ):
        """Create 3D volume plot with slices."""
        fig = go.Figure()

        # Add isosurface
        fig.add_trace(go.Isosurface(
            x=grid_data['x'].flatten(),
            y=grid_data['y'].flatten(),
            z=grid_data['z'].flatten(),
            value=grid_data['values'].flatten(),
            isomin=-np.max(np.abs(grid_data['values'])),
            isomax=np.max(np.abs(grid_data['values'])),
            surface_count=num_slices,
            colorscale=colorscale,
            caps=dict(x_show=False, y_show=False, z_show=False),
            colorbar=dict(title="Amplitude"),
            hovertemplate='x: %{x:.2f} m<br>y: %{y:.2f} m<br>z: %{z:.2f} m<br>φ: %{value:.3f}<extra></extra>'
        ))

        fig.update_layout(
            title=f"Mode {mode.mode_number}: {mode.frequency:.2f} Hz (ξ={mode.damping_ratio:.4f})",
            scene=dict(
                xaxis_title="X [m]",
                yaxis_title="Y [m]",
                zaxis_title="Z [m]",
                aspectmode='data'
            ),
            height=700
        )

        return fig


if __name__ == "__main__":
    print("=== Mode Visualization Example ===\n")
    print("This module requires FEniCS and computed modes.")
    print("See examples/02_complete_analysis.py for full workflow.")
