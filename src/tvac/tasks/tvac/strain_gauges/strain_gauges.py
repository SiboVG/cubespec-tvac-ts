from pathlib import Path

from egse.setup import load_setup_from_disk
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback

from tvac.strain_gauge import (
    get_cached_sg_channel_names,
    get_sg_channel_names,
    get_sg_effective_settings,
    get_sg_settings,
    get_sg_status,
    reset_sg_runtime_settings,
    set_sg_channel_runtime_settings,
    set_sg_runtime_settings,
    start_sg_logging,
    stop_sg_logging,
)

UI_MODULE_DISPLAY_NAME = "1 - Strain Gauges"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"
_SG_NAME_OPTIONS: list[str] = []


def _sg_name_options() -> list[str]:
    global _SG_NAME_OPTIONS

    if _SG_NAME_OPTIONS:
        return _SG_NAME_OPTIONS

    # Keep this callback I/O-free; GUI builds argument panels on the UI thread.
    _SG_NAME_OPTIONS = get_cached_sg_channel_names() or ["SG_AIN0"]

    return _SG_NAME_OPTIONS


def _ain_channel_options() -> list[int]:
    return list(range(14))


def _ain_channel_default() -> int:
    return 0


def _voltage_range_options() -> list[float]:
    return [10.0, 1.0, 0.1, 0.01]


def _voltage_range_default() -> float:
    return 0.1


def _resolution_index_options() -> list[int]:
    return list(range(9))


def _resolution_index_default() -> int:
    return 0


@exec_ui(display_name="Query Settings", use_kernel=True)
def settings() -> None:
    """Print effective SG settings (Setup + runtime overrides)."""
    print(get_sg_settings())


@exec_ui(display_name="Configure SG channel", use_kernel=True)
def configure_sg_channel(
    sg_name: Callback(_sg_name_options, name="SG name") = None,
    enabled: bool = True,
    ain_channel: Callback(_ain_channel_options, default=_ain_channel_default, name="AIN channel") = None,
    voltage_range: Callback(_voltage_range_options, default=_voltage_range_default, name="Voltage range [V]") = None,
    resolution_index: Callback(_resolution_index_options, default=_resolution_index_default, name="Resolution index") = None,
) -> None:
    """Set runtime overrides for one SG channel (applied on next Start logging)."""
    try:
        name = sg_name.strip()
        if not name:
            available = get_sg_channel_names()
            if not available:
                raise ValueError("No SG channels were found in the setup.")
            name = available[0]
            print(f"sg_name was empty, using first setup SG channel: {name}")

        set_sg_channel_runtime_settings(
            sg_name=name,
            enabled=enabled,
            ain_channel=ain_channel,
            voltage_range=voltage_range,
            resolution_index=resolution_index,
        )
        print(f"Runtime channel settings updated for {name}.")
        print(get_sg_settings())
    except Exception as e:
        print(f"Failed to configure SG channel settings: {e}")


@exec_ui(display_name="Configure stream", use_kernel=True)
def configure_stream(
    scan_rate: float = 496.0,
    resync_interval_s: int = 60,
    buffer_size: int = 32768,
) -> None:
    """Set runtime stream settings (applied on next Start logging)."""
    try:
        set_sg_runtime_settings(
            scan_rate=scan_rate,
            resync_interval_s=resync_interval_s,
            buffer_size=buffer_size,
        )
        print("Stream runtime settings updated.")
        print(get_sg_settings())
    except Exception as e:
        print(f"Failed to configure stream settings: {e}")


@exec_ui(display_name="Configure CSV", use_kernel=True)
def configure_csv(
    enabled: bool = True,
    save_path: str = ".",
    base_filename: str = "labjack_sg_data",
    max_file_size_bytes: int = 5_120_000,
) -> None:
    """Set runtime CSV settings (applied on next Start logging)."""
    try:
        set_sg_runtime_settings(
            csv_enabled=enabled,
            csv_save_path=save_path,
            csv_base_filename=base_filename,
            csv_max_file_size_bytes=max_file_size_bytes,
        )
        print("CSV runtime settings updated.")
        print(get_sg_settings())
    except Exception as e:
        print(f"Failed to configure CSV settings: {e}")


@exec_ui(display_name="Configure plot", use_kernel=True)
def configure_plot(
    enabled: bool = True,
    window_seconds: float = 5.0,
    interval_ms: int = 500,
    show_stats: bool = True,
) -> None:
    """Set runtime plot settings (applied on next Start logging)."""
    try:
        set_sg_runtime_settings(
            plot_enabled=enabled,
            plot_window_seconds=window_seconds,
            plot_interval_ms=interval_ms,
            plot_show_stats=show_stats,
        )
        print("Plot runtime settings updated.")
        print(get_sg_settings())
    except Exception as e:
        print(f"Failed to configure plot settings: {e}")


@exec_ui(display_name="Reset runtime settings", use_kernel=True)
def reset_settings() -> None:
    """Clear SG runtime overrides and return to Setup values."""
    reset_sg_runtime_settings()
    print("Runtime settings reset.")
    print(get_sg_settings())


@exec_ui(display_name="Start logging", use_kernel=True)
def start_logging() -> None:
    """Start strain-gauge streaming and CSV logging.

    All parameters (channels, scan rate, voltage ranges, resolution indices,
    CSV path/enabled, plot enabled) are read from the active CGSE Setup
    (``setup.gse.labjack_t7``).
    """
    try:
        setup = load_setup_from_disk(None)
        start_sg_logging(setup=setup)

        if get_sg_effective_settings(setup=setup)["plot"]["enabled"]:
            from tvac.strain_gauge_plot import open_live_plot
            open_live_plot(setup=setup)

    except Exception as e:
        print(f"Failed to start strain-gauge logging: {e}")


@exec_ui(display_name="Stop logging", use_kernel=True)
def stop_logging() -> None:
    """Stop the active strain-gauge logging session."""
    try:
        stop_sg_logging()
    except Exception as e:
        print(f"Failed to stop strain-gauge logging: {e}")


@exec_ui(display_name="Status", use_kernel=True)
def status() -> None:
    """Print the current strain-gauge logging status."""
    print(get_sg_status())
