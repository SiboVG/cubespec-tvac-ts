from pathlib import Path

from PyQt5.QtWidgets import QCheckBox, QComboBox, QHBoxLayout
from egse.setup import load_setup
from gui_executor.exec import exec_ui
from gui_executor.utypes import TypeObject, UQWidget

from tvac.strain_gauge import (
    get_cached_sg_channel_settings,
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

_AIN_OPTIONS = list(range(14))
_VOLTAGE_RANGE_OPTIONS = [10.0, 1.0, 0.1, 0.01]
_RESOLUTION_INDEX_OPTIONS = list(range(9))


def _set_combo_value(combo: QComboBox, value) -> None:
    idx = combo.findText(str(value))
    if idx >= 0:
        combo.setCurrentIndex(idx)


def _fallback_ain_channel(name: str) -> int:
    if "AIN" not in name:
        return 0
    try:
        return int(name.split("AIN", maxsplit=1)[1])
    except ValueError:
        return 0


class SGChannelConfig(TypeObject):
    def __init__(self, name: str = "SG channel"):
        super().__init__(name=name)

    def get_widget(self):
        return SGChannelConfigWidget()


class SGChannelConfigWidget(UQWidget):
    def __init__(self):
        super().__init__()

        self._channel_settings = get_cached_sg_channel_settings()
        if not self._channel_settings:
            self._channel_settings = {
                "SG_AIN0": {
                    "enabled": True,
                    "ain_channel": 0,
                    "voltage_range": 0.1,
                    "resolution_index": 0,
                }
            }

        self.sg_combo = QComboBox()
        self.sg_combo.addItems(self._channel_settings.keys())

        self.enabled_cb = QCheckBox("enabled")
        self.ain_combo = QComboBox()
        self.ain_combo.addItems(str(v) for v in _AIN_OPTIONS)
        self.voltage_combo = QComboBox()
        self.voltage_combo.addItems(str(v) for v in _VOLTAGE_RANGE_OPTIONS)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(str(v) for v in _RESOLUTION_INDEX_OPTIONS)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.sg_combo)
        layout.addWidget(self.enabled_cb)
        layout.addWidget(self.ain_combo)
        layout.addWidget(self.voltage_combo)
        layout.addWidget(self.resolution_combo)
        self.setLayout(layout)

        self.sg_combo.currentTextChanged.connect(self._apply_channel_defaults)
        self._apply_channel_defaults(self.sg_combo.currentText())

    def _apply_channel_defaults(self, sg_name: str):
        defaults = self._channel_settings.get(sg_name, {})
        ain_channel = int(defaults.get("ain_channel", _fallback_ain_channel(sg_name)))
        voltage_range = float(defaults.get("voltage_range", 0.1))
        resolution_index = int(defaults.get("resolution_index", 0))
        enabled = bool(defaults.get("enabled", True))

        self.enabled_cb.setChecked(enabled)
        _set_combo_value(self.ain_combo, ain_channel)
        _set_combo_value(self.voltage_combo, voltage_range)
        _set_combo_value(self.resolution_combo, resolution_index)

    def get_value(self):
        return {
            "sg_name": self.sg_combo.currentText(),
            "enabled": self.enabled_cb.isChecked(),
            "ain_channel": int(self.ain_combo.currentText()),
            "voltage_range": float(self.voltage_combo.currentText()),
            "resolution_index": int(self.resolution_combo.currentText()),
        }


@exec_ui(display_name="Query Settings", use_kernel=True)
def settings() -> None:
    """Print effective SG settings (Setup + runtime overrides)."""
    print(get_sg_settings())


@exec_ui(display_name="Configure SG channel", use_kernel=True)
def configure_sg_channel(
    config: SGChannelConfig(name="SG / AIN / Range / Resolution") = None,
) -> None:
    """Set runtime overrides for one SG channel (applied on next Start logging)."""
    try:
        cfg = config or {}
        name = str(cfg.get("sg_name", "")).strip()
        if not name:
            available = get_sg_channel_names()
            if not available:
                raise ValueError("No SG channels were found in the setup.")
            name = available[0]
            print(f"sg_name was empty, using first setup SG channel: {name}")

        set_sg_channel_runtime_settings(
            sg_name=name,
            enabled=bool(cfg.get("enabled", True)),
            ain_channel=int(cfg.get("ain_channel", 0)),
            voltage_range=float(cfg.get("voltage_range", 0.1)),
            resolution_index=int(cfg.get("resolution_index", 0)),
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
        setup = load_setup()
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
