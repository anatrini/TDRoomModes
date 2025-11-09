"""
Reverberation Time (T60) Calculation Module

Implements physically accurate formulas for acoustic decay time:
- Sabine formula (low absorption)
- Eyring-Norris formula (higher absorption)
- Modal decay rates
"""

import numpy as np
from typing import Union, Optional, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def sabine_t60(
    volume: float,
    surface_area: float,
    alpha_avg: float,
    air_absorption: float = 0.0
) -> float:
    """
    Calculate T60 using Sabine formula.

    Valid for rooms with low absorption (α < 0.2).

    Formula:
        T60 = 0.161 * V / (α_avg * A + 4mV)

    where:
        V = volume [m³]
        A = total surface area [m²]
        α_avg = average absorption coefficient [0-1]
        m = air absorption coefficient [1/m]

    Args:
        volume: Room volume [m³]
        surface_area: Total surface area [m²]
        alpha_avg: Average absorption coefficient
        air_absorption: Air absorption coefficient [1/m]

    Returns:
        T60 in seconds

    References:
        Sabine, W. C. (1922). Collected Papers on Acoustics.
        ISO 3382-1:2009
    """
    if alpha_avg < 0 or alpha_avg > 1:
        raise ValueError(f"Absorption coefficient must be in [0,1], got {alpha_avg}")

    if volume <= 0:
        raise ValueError(f"Volume must be positive, got {volume}")

    if surface_area <= 0:
        raise ValueError(f"Surface area must be positive, got {surface_area}")

    # Total absorption
    total_absorption = alpha_avg * surface_area + 4 * air_absorption * volume

    if total_absorption < 1e-10:
        logger.warning("Total absorption near zero, T60 → ∞")
        return np.inf

    t60 = 0.161 * volume / total_absorption

    logger.info(f"Sabine T60 = {t60:.3f} s "
               f"(V={volume:.1f} m³, A={surface_area:.1f} m², α={alpha_avg:.3f})")

    return t60


def eyring_t60(
    volume: float,
    surface_area: float,
    alpha_avg: float,
    air_absorption: float = 0.0
) -> float:
    """
    Calculate T60 using Eyring-Norris formula.

    More accurate than Sabine for higher absorption (α > 0.2).

    Formula:
        T60 = 0.161 * V / [-A * ln(1 - α_avg) + 4mV]

    Args:
        volume: Room volume [m³]
        surface_area: Total surface area [m²]
        alpha_avg: Average absorption coefficient [0-1]
        air_absorption: Air absorption coefficient [1/m]

    Returns:
        T60 in seconds

    References:
        Eyring, C. F. (1930). Reverberation time in "dead" rooms.
        Norris, R. F., & Andree, C. A. (1930).
    """
    if alpha_avg < 0 or alpha_avg >= 1:
        raise ValueError(f"Absorption coefficient must be in [0,1), got {alpha_avg}")

    if volume <= 0:
        raise ValueError(f"Volume must be positive, got {volume}")

    if surface_area <= 0:
        raise ValueError(f"Surface area must be positive, got {surface_area}")

    # Handle α → 1 case
    if alpha_avg >= 0.999:
        logger.warning("Absorption coefficient very close to 1, T60 → 0")
        return 0.0

    # Total absorption
    total_absorption = -surface_area * np.log(1 - alpha_avg) + 4 * air_absorption * volume

    if total_absorption < 1e-10:
        logger.warning("Total absorption near zero, T60 → ∞")
        return np.inf

    t60 = 0.161 * volume / total_absorption

    logger.info(f"Eyring T60 = {t60:.3f} s "
               f"(V={volume:.1f} m³, A={surface_area:.1f} m², α={alpha_avg:.3f})")

    return t60


def calculate_alpha_avg(
    surface_areas: np.ndarray,
    absorption_coefficients: np.ndarray
) -> float:
    """
    Calculate average absorption coefficient from multiple surfaces.

    α_avg = Σ(α_i * A_i) / Σ(A_i)

    Args:
        surface_areas: Array of surface areas [m²]
        absorption_coefficients: Array of absorption coefficients [0-1]

    Returns:
        Average absorption coefficient
    """
    if len(surface_areas) != len(absorption_coefficients):
        raise ValueError("Surface areas and absorption coefficients must have same length")

    total_area = np.sum(surface_areas)
    if total_area <= 0:
        raise ValueError("Total surface area must be positive")

    alpha_avg = np.sum(absorption_coefficients * surface_areas) / total_area

    return alpha_avg


def air_absorption_coefficient(
    temperature: float = 20.0,
    humidity: float = 50.0,
    frequency: float = 1000.0
) -> float:
    """
    Calculate air absorption coefficient.

    Uses ISO 9613-1:1993 model.

    Args:
        temperature: Temperature [°C]
        humidity: Relative humidity [%]
        frequency: Frequency [Hz]

    Returns:
        Absorption coefficient [1/m]

    References:
        ISO 9613-1:1993 Acoustics - Attenuation of sound during propagation outdoors
    """
    # Convert to absolute temperature
    T = temperature + 273.15  # Kelvin
    T0 = 293.15  # Reference temperature (20°C)

    # Convert frequency to kHz
    f_kHz = frequency / 1000.0

    # Saturation vapor pressure (simplified)
    psat = 10**(-6.8346 * (273.16/T)**1.261 + 4.6151)  # kPa
    h = humidity * (psat / 101.325) / 100  # Molar concentration of water vapor

    # Relaxation frequencies
    frO = (24 + 4.04e4 * h * (0.02 + h) / (0.391 + h)) / 1000  # Oxygen
    frN = (T / T0)**(-0.5) * (9 + 280 * h * np.exp(-4.17 * ((T/T0)**(-1/3) - 1))) / 1000  # Nitrogen

    # Atmospheric attenuation coefficient
    alpha = f_kHz**2 * (
        1.84e-11 * (T / T0)**0.5 +
        (T / T0)**(-2.5) * (
            0.01275 * np.exp(-2239.1 / T) * (frO + f_kHz**2 / frO)**(-1) +
            0.1068 * np.exp(-3352.0 / T) * (frN + f_kHz**2 / frN)**(-1)
        )
    )

    # Convert from dB/m to Neper/m (1 Neper = 8.686 dB)
    alpha_neper = alpha / 8.686

    return alpha_neper


def modal_damping_ratio(
    frequency: float,
    volume: float,
    surface_area: float,
    alpha_avg: float,
    air_absorption: float = 0.0
) -> float:
    """
    Calculate modal damping ratio ξ for a given mode.

    The damping ratio is related to T60 by:
        ξ = 2.2 / (ω * T60)

    where ω = 2πf is the angular frequency.

    Args:
        frequency: Modal frequency [Hz]
        volume: Room volume [m³]
        surface_area: Total surface area [m²]
        alpha_avg: Average absorption coefficient
        air_absorption: Air absorption coefficient [1/m]

    Returns:
        Damping ratio ξ (dimensionless)
    """
    # Calculate T60 (use Eyring for more accuracy)
    t60 = eyring_t60(volume, surface_area, alpha_avg, air_absorption)

    if t60 == 0:
        return 1.0  # Critical damping

    if not np.isfinite(t60):
        return 0.0  # No damping

    # Angular frequency
    omega = 2 * np.pi * frequency

    # Damping ratio
    xi = 2.2 / (omega * t60)

    return xi


def schroeder_frequency(volume: float, t60: float) -> float:
    """
    Calculate Schroeder frequency.

    The Schroeder frequency is the approximate frequency above which
    the modal density is high enough for statistical analysis to apply.

    f_s ≈ 2000 * √(T60 / V)

    Args:
        volume: Room volume [m³]
        t60: Reverberation time [s]

    Returns:
        Schroeder frequency [Hz]

    References:
        Schroeder, M. R. (1954). Statistical parameters of the frequency response curves.
    """
    if volume <= 0 or t60 <= 0:
        raise ValueError("Volume and T60 must be positive")

    f_s = 2000 * np.sqrt(t60 / volume)

    logger.info(f"Schroeder frequency = {f_s:.1f} Hz")
    logger.info(f"  Below f_s: modal behavior (discrete modes)")
    logger.info(f"  Above f_s: statistical behavior (diffuse field)")

    return f_s


def critical_distance(volume: float, surface_area: float, alpha_avg: float) -> float:
    """
    Calculate critical distance (reverberation radius).

    The critical distance is where direct sound equals reverberant sound.

    r_c = 0.141 * √(V * α_avg * A / T60)
        ≈ 0.057 * √(α_avg * A)  (using Sabine)

    Args:
        volume: Room volume [m³]
        surface_area: Total surface area [m²]
        alpha_avg: Average absorption coefficient

    Returns:
        Critical distance [m]
    """
    if alpha_avg <= 0:
        return 0.0

    r_c = 0.057 * np.sqrt(alpha_avg * surface_area)

    logger.info(f"Critical distance = {r_c:.2f} m")

    return r_c


class AcousticRoom:
    """
    Container for room acoustic properties.

    Calculates and stores various acoustic metrics.
    """

    def __init__(
        self,
        volume: float,
        surface_area: float,
        absorption_coefficients: Optional[Dict[str, float]] = None,
        surface_areas: Optional[Dict[str, float]] = None,
        temperature: float = 20.0,
        humidity: float = 50.0
    ):
        """
        Initialize acoustic room.

        Args:
            volume: Room volume [m³]
            surface_area: Total surface area [m²]
            absorption_coefficients: Dict of surface name → absorption coefficient
            surface_areas: Dict of surface name → area [m²]
            temperature: Air temperature [°C]
            humidity: Relative humidity [%]
        """
        self.volume = volume
        self.surface_area = surface_area
        self.temperature = temperature
        self.humidity = humidity

        # Calculate average absorption
        if absorption_coefficients and surface_areas:
            areas = np.array([surface_areas[k] for k in absorption_coefficients.keys()])
            alphas = np.array([absorption_coefficients[k] for k in absorption_coefficients.keys()])
            self.alpha_avg = calculate_alpha_avg(areas, alphas)
        else:
            self.alpha_avg = 0.1  # Default value

        logger.info(f"Acoustic room initialized: V={volume:.1f} m³, "
                   f"A={surface_area:.1f} m², α={self.alpha_avg:.3f}")

    def t60(self, frequency: float = 1000.0, method: str = 'eyring') -> float:
        """
        Calculate T60 at given frequency.

        Args:
            frequency: Frequency [Hz]
            method: 'sabine' or 'eyring'

        Returns:
            T60 [s]
        """
        air_abs = air_absorption_coefficient(
            self.temperature, self.humidity, frequency
        )

        if method == 'sabine':
            return sabine_t60(self.volume, self.surface_area, self.alpha_avg, air_abs)
        elif method == 'eyring':
            return eyring_t60(self.volume, self.surface_area, self.alpha_avg, air_abs)
        else:
            raise ValueError(f"Unknown method: {method}")

    def schroeder_freq(self) -> float:
        """Calculate Schroeder frequency."""
        t60 = self.t60()
        return schroeder_frequency(self.volume, t60)

    def critical_dist(self) -> float:
        """Calculate critical distance."""
        return critical_distance(self.volume, self.surface_area, self.alpha_avg)


if __name__ == "__main__":
    # Example usage
    print("=== Acoustic Decay Calculations ===\n")

    # Example room: 10m × 8m × 4m
    length, width, height = 10.0, 8.0, 4.0
    volume = length * width * height
    surface_area = 2 * (length * width + length * height + width * height)

    print(f"Room dimensions: {length}×{width}×{height} m")
    print(f"Volume: {volume} m³")
    print(f"Surface area: {surface_area} m²\n")

    # Different absorption scenarios
    alphas = [0.05, 0.1, 0.2, 0.4, 0.6, 0.8]

    print("Comparison of Sabine vs Eyring formulas:\n")
    print(f"{'α':>6} {'Sabine T60':>12} {'Eyring T60':>12} {'Difference':>12}")
    print("-" * 50)

    for alpha in alphas:
        t60_s = sabine_t60(volume, surface_area, alpha)
        t60_e = eyring_t60(volume, surface_area, alpha)
        diff = abs(t60_s - t60_e)
        print(f"{alpha:>6.2f} {t60_s:>12.3f} {t60_e:>12.3f} {diff:>12.3f}")

    print("\n" + "="*50 + "\n")

    # Detailed analysis for α = 0.15
    alpha = 0.15
    room = AcousticRoom(volume, surface_area)
    room.alpha_avg = alpha

    print(f"Detailed analysis for α = {alpha}:\n")
    print(f"T60 (Sabine): {room.t60(method='sabine'):.3f} s")
    print(f"T60 (Eyring): {room.t60(method='eyring'):.3f} s")
    print(f"Schroeder frequency: {room.schroeder_freq():.1f} Hz")
    print(f"Critical distance: {room.critical_dist():.2f} m")
