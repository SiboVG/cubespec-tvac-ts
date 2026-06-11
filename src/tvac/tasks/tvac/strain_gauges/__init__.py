from typing import List

from egse.setup import load_setup

from tvac.strain_gauge import get_sg_effective_settings

UI_TAB_DISPLAY_NAME = "Strain Gauges"


def strain_gauges() -> List[str]:
    """Name of the strain gauges."""

    setup = load_setup()

    return list(setup.gse.labjack_t7.channels.keys())


def ain_channels() -> List[str]:
    """List of AIN channels."""

    setup = load_setup()

    return list(setup.gse.labjack_t7.channels.keys())


def voltage_ranges() -> List[float]:
    """List of voltage ranges for the strain gauges.

    These are both the positive and negative voltage ranges/
    """

    return [0.01, 0.1, 1.0, 10.0]


def resolution_indices() -> List[int]:
    """List of resolution indices for the strain gauges."""

    return [0, 1, 2, 3, 4, 5, 6, 7, 8]


# Stream callbacks


def sg_scan_rate() -> float:
    return float(get_sg_effective_settings()["stream"]["scan_rate"])


def sg_resync_interval_s() -> int:
    return int(get_sg_effective_settings()["stream"]["resync_interval_s"])


def sg_buffer_size() -> int:
    return int(get_sg_effective_settings()["stream"]["buffer_size"])


# CSV callbacks


def sg_csv_enabled() -> bool:
    return bool(get_sg_effective_settings()["csv"]["enabled"])


def sg_csv_save_path() -> str:
    return str(get_sg_effective_settings()["csv"]["save_path"])


def sg_csv_base_filename() -> str:
    return str(get_sg_effective_settings()["csv"]["base_filename"])


def sg_csv_max_file_size_bytes() -> int:
    return int(get_sg_effective_settings()["csv"]["max_file_size_bytes"])


# Plot callbacks


def sg_plot_enabled() -> bool:
    return bool(get_sg_effective_settings()["plot"]["enabled"])


def sg_plot_window_seconds() -> float:
    return float(get_sg_effective_settings()["plot"]["window_seconds"])


def sg_plot_interval_ms() -> int:
    return int(get_sg_effective_settings()["plot"]["interval_ms"])


def sg_plot_show_stats() -> bool:
    return bool(get_sg_effective_settings()["plot"]["show_stats"])
