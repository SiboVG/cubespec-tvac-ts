from pathlib import Path

from PyQt5.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit
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


def _set_line_text(field: QLineEdit, value) -> None:
    field.setText(str(value))


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

    def _current_config(self) -> dict[str, object]:
        return {
            "sg_name": self.sg_combo.currentText(),
            "enabled": self.enabled_cb.isChecked(),
            "ain_channel": int(self.ain_combo.currentText()),
            "voltage_range": float(self.voltage_combo.currentText()),
            "resolution_index": int(self.resolution_combo.currentText()),
        }

    def get_value(self):
        config = self._current_config()

        # The command itself runs in the kernel, but this widget lives in the GUI
        # process. Mirror the submitted values into the local cache so reopening the
        # form shows the latest channel state immediately.
        set_sg_channel_runtime_settings(
            sg_name=str(config["sg_name"]),
            enabled=bool(config["enabled"]),
            ain_channel=int(config["ain_channel"]),
            voltage_range=float(config["voltage_range"]),
            resolution_index=int(config["resolution_index"]),
        )
        self._channel_settings = get_cached_sg_channel_settings()
        self._apply_channel_defaults(str(config["sg_name"]))

        return config


class SGStreamConfig(TypeObject):
    def __init__(self, name: str = "Stream settings"):
        super().__init__(name=name)

    def get_widget(self):
        return SGStreamConfigWidget()


class SGStreamConfigWidget(UQWidget):
    def __init__(self):
        super().__init__()

        self.scan_rate = QLineEdit()
        self.resync_interval_s = QLineEdit()
        self.buffer_size = QLineEdit()

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scan_rate)
        layout.addWidget(self.resync_interval_s)
        layout.addWidget(self.buffer_size)
        self.setLayout(layout)

        self._refresh_from_effective_settings()

    def _refresh_from_effective_settings(self):
        stream = get_sg_effective_settings()["stream"]
        _set_line_text(self.scan_rate, stream["scan_rate"])
        _set_line_text(self.resync_interval_s, stream["resync_interval_s"])
        _set_line_text(self.buffer_size, stream["buffer_size"])

    def get_value(self):
        config = {
            "scan_rate": float(self.scan_rate.text()),
            "resync_interval_s": int(self.resync_interval_s.text()),
            "buffer_size": int(self.buffer_size.text()),
        }
        set_sg_runtime_settings(**config)
        self._refresh_from_effective_settings()
        return config


class SGCSVConfig(TypeObject):
    def __init__(self, name: str = "CSV settings"):
        super().__init__(name=name)

    def get_widget(self):
        return SGCSVConfigWidget()


class SGCSVConfigWidget(UQWidget):
    def __init__(self):
        super().__init__()

        self.enabled_cb = QCheckBox("enabled")
        self.save_path = QLineEdit()
        self.base_filename = QLineEdit()
        self.max_file_size_bytes = QLineEdit()

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.enabled_cb)
        layout.addWidget(self.save_path)
        layout.addWidget(self.base_filename)
        layout.addWidget(self.max_file_size_bytes)
        self.setLayout(layout)

        self._refresh_from_effective_settings()

    def _refresh_from_effective_settings(self):
        csv_cfg = get_sg_effective_settings()["csv"]
        self.enabled_cb.setChecked(bool(csv_cfg["enabled"]))
        _set_line_text(self.save_path, csv_cfg["save_path"])
        _set_line_text(self.base_filename, csv_cfg["base_filename"])
        _set_line_text(self.max_file_size_bytes, csv_cfg["max_file_size_bytes"])

    def get_value(self):
        config = {
            "csv_enabled": self.enabled_cb.isChecked(),
            "csv_save_path": self.save_path.text(),
            "csv_base_filename": self.base_filename.text(),
            "csv_max_file_size_bytes": int(self.max_file_size_bytes.text()),
        }
        set_sg_runtime_settings(**config)
        self._refresh_from_effective_settings()
        return {
            "enabled": bool(config["csv_enabled"]),
            "save_path": str(config["csv_save_path"]),
            "base_filename": str(config["csv_base_filename"]),
            "max_file_size_bytes": int(config["csv_max_file_size_bytes"]),
        }


class SGPlotConfig(TypeObject):
    def __init__(self, name: str = "Plot settings"):
        super().__init__(name=name)

    def get_widget(self):
        return SGPlotConfigWidget()


class SGPlotConfigWidget(UQWidget):
    def __init__(self):
        super().__init__()

        self.enabled_cb = QCheckBox("enabled")
        self.window_seconds = QLineEdit()
        self.interval_ms = QLineEdit()
        self.show_stats_cb = QCheckBox("show_stats")

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.enabled_cb)
        layout.addWidget(self.window_seconds)
        layout.addWidget(self.interval_ms)
        layout.addWidget(self.show_stats_cb)
        self.setLayout(layout)

        self._refresh_from_effective_settings()

    def _refresh_from_effective_settings(self):
        plot = get_sg_effective_settings()["plot"]
        self.enabled_cb.setChecked(bool(plot["enabled"]))
        _set_line_text(self.window_seconds, plot["window_seconds"])
        _set_line_text(self.interval_ms, plot["interval_ms"])
        self.show_stats_cb.setChecked(bool(plot["show_stats"]))

    def get_value(self):
        config = {
            "plot_enabled": self.enabled_cb.isChecked(),
            "plot_window_seconds": float(self.window_seconds.text()),
            "plot_interval_ms": int(self.interval_ms.text()),
            "plot_show_stats": self.show_stats_cb.isChecked(),
        }
        set_sg_runtime_settings(**config)
        self._refresh_from_effective_settings()
        return {
            "enabled": bool(config["plot_enabled"]),
            "window_seconds": float(config["plot_window_seconds"]),
            "interval_ms": int(config["plot_interval_ms"]),
            "show_stats": bool(config["plot_show_stats"]),
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
    config: SGStreamConfig(name="scan_rate / resync_interval_s / buffer_size") = None,
) -> None:
    """Set runtime stream settings (applied on next Start logging)."""
    try:
        cfg = config or {}
        set_sg_runtime_settings(
            scan_rate=float(cfg.get("scan_rate", 496.0)),
            resync_interval_s=int(cfg.get("resync_interval_s", 60)),
            buffer_size=int(cfg.get("buffer_size", 32768)),
        )
        print("Stream runtime settings updated.")
        print(get_sg_settings())
    except Exception as e:
        print(f"Failed to configure stream settings: {e}")


@exec_ui(display_name="Configure CSV", use_kernel=True)
def configure_csv(
    config: SGCSVConfig(
        name="enabled / save_path / base_filename / max_file_size_bytes"
    ) = None,
) -> None:
    """Set runtime CSV settings (applied on next Start logging)."""
    try:
        cfg = config or {}
        set_sg_runtime_settings(
            csv_enabled=bool(cfg.get("enabled", True)),
            csv_save_path=str(cfg.get("save_path", ".")),
            csv_base_filename=str(cfg.get("base_filename", "labjack_sg_data")),
            csv_max_file_size_bytes=int(cfg.get("max_file_size_bytes", 5_120_000)),
        )
        print("CSV runtime settings updated.")
        print(get_sg_settings())
    except Exception as e:
        print(f"Failed to configure CSV settings: {e}")


@exec_ui(display_name="Configure metrics", use_kernel=True)
def config_metrics(enabled: bool = True) -> None:
    """Enabled/disabled metrics collection.

    Args:
        enabled (bool): Whether to enable metrics collection.
    """

    try:
        set_sg_runtime_settings(metrics_enabled=enabled)
    except Exception as e:
        print(f"Failed to configure metrics settings: {e}")


@exec_ui(display_name="Configure plot", use_kernel=True)
def configure_plot(
    config: SGPlotConfig(
        name="enabled / window_seconds / interval_ms / show_stats"
    ) = None,
) -> None:
    """Set runtime plot settings (applied on next Start logging)."""
    try:
        cfg = config or {}
        set_sg_runtime_settings(
            plot_enabled=bool(cfg.get("enabled", True)),
            plot_window_seconds=float(cfg.get("window_seconds", 5.0)),
            plot_interval_ms=int(cfg.get("interval_ms", 500)),
            plot_show_stats=bool(cfg.get("show_stats", True)),
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
