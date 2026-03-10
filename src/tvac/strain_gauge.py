"""
High-level strain-gauge logging functions.

Reads LabJack T7 and CSV configuration from the CGSE Setup, mirrors
the pattern of ``tvac.power_supply`` for heaters.
"""

import bisect
import csv
import datetime
import os
import threading

from egse.setup import Setup, load_setup_from_disk


# ---------------------------------------------------------------------------
# Module-level state for the active logging session
# ---------------------------------------------------------------------------
_logger = None  # LabJackT7Logger, imported lazily to avoid LJM init on import
_session_lock = threading.RLock()
_csv_lock = threading.Lock()
_csv_file = None
_csv_writer = None
_csv_filename = ""
_file_index = 0
_read_count = 0
_start_ts = ""

# CSV defaults (overridden by setup)
_csv_enabled = True
_save_path = "."
_base_filename = "labjack_sg_data"
_max_file_size = 5_000 * 1024

# Plot flag
_plot_enabled = True
_plot_keep_seconds = 60.0

# Runtime overrides applied on top of the Setup values. These overrides are
# intentionally in-memory only and affect newly started logging sessions.
_runtime_overrides: dict[str, dict[str, object]] = {
    "stream": {},
    "csv": {},
    "plot": {},
}
_runtime_channel_overrides: dict[str, dict[str, object]] = {}
_active_channel_labels: list[str] = []
_cached_channel_names: list[str] = ["SG_AIN0", "SG_AIN2", "SG_AIN4"]
_cached_channel_settings: dict[str, dict[str, object]] = {
    "SG_AIN0": {
        "enabled": True,
        "ain_channel": 0,
        "voltage_range": 0.1,
        "neg_voltage_range": 10.0,
        "resolution_index": 0,
    },
    "SG_AIN2": {
        "enabled": True,
        "ain_channel": 2,
        "voltage_range": 0.1,
        "neg_voltage_range": 10.0,
        "resolution_index": 0,
    },
    "SG_AIN4": {
        "enabled": True,
        "ain_channel": 4,
        "voltage_range": 0.1,
        "neg_voltage_range": 10.0,
        "resolution_index": 0,
    },
}

# Plot buffers (shared with any live-plot consumer)
plot_lock = threading.Lock()
time_buffer: list[float] = []
ch_buffers: list[list[float]] = []


def _sg_debug(message: str) -> None:
    if not os.environ.get("TVAC_SG_DEBUG", "").strip():
        return

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    thread_name = threading.current_thread().name
    print(f"[strain_gauge {stamp} {thread_name}] {message}")


def _coerce_bool(value, field_name: str) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled", "enable"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled", "disable"}:
            return False

    raise ValueError(f"Invalid boolean value for {field_name}: {value!r}")


def _coerce_positive_int(value, field_name: str) -> int:
    coerced = int(value)
    if coerced <= 0:
        raise ValueError(f"{field_name} must be > 0, got {coerced}")
    return coerced


def _coerce_non_negative_int(value, field_name: str) -> int:
    coerced = int(value)
    if coerced < 0:
        raise ValueError(f"{field_name} must be >= 0, got {coerced}")
    return coerced


def _coerce_positive_float(value, field_name: str) -> float:
    coerced = float(value)
    if coerced <= 0:
        raise ValueError(f"{field_name} must be > 0, got {coerced}")
    return coerced


def _snapshot_setup_cfg(setup: Setup) -> dict[str, dict[str, object]]:
    cfg = setup.gse.labjack_t7
    return {
        "stream": {
            "scan_rate": float(cfg.stream.scan_rate),
            "resync_interval_s": int(cfg.stream.resync_interval_s),
            "buffer_size": int(cfg.stream.buffer_size),
        },
        "csv": {
            "enabled": bool(cfg.csv.enabled),
            "save_path": str(cfg.csv.save_path),
            "base_filename": str(cfg.csv.base_filename),
            "max_file_size_bytes": int(cfg.csv.max_file_size_bytes),
        },
        "plot": {
            "enabled": bool(cfg.plot.enabled),
            "window_seconds": float(cfg.plot.window_seconds),
            "interval_ms": int(cfg.plot.interval_ms),
            "show_stats": bool(cfg.plot.show_stats),
        },
    }


def _snapshot_setup_channels(setup: Setup) -> dict[str, dict[str, object]]:
    global _cached_channel_names, _cached_channel_settings
    cfg = setup.gse.labjack_t7
    channels: dict[str, dict[str, object]] = {}
    for sg_name in cfg.channels:
        ch_cfg = cfg.channels[sg_name]
        channels[sg_name] = {
            "enabled": True,
            "ain_channel": int(ch_cfg.ain_channel),
            "voltage_range": float(ch_cfg.voltage_range),
            "neg_voltage_range": float(ch_cfg.neg_voltage_range),
            "resolution_index": int(ch_cfg.resolution_index),
        }
    if channels:
        _cached_channel_names = list(channels.keys())
        _cached_channel_settings = {name: dict(values) for name, values in channels.items()}
    return channels


def _get_effective_settings(setup: Setup = None) -> dict[str, dict[str, object]]:
    setup = setup or load_setup_from_disk(None)
    effective = _snapshot_setup_cfg(setup)
    for section_name, overrides in _runtime_overrides.items():
        effective[section_name].update(overrides)
    return effective


def _get_effective_channel_settings(setup: Setup = None) -> dict[str, dict[str, object]]:
    setup = setup or load_setup_from_disk(None)
    effective = _snapshot_setup_channels(setup)
    for sg_name, overrides in _runtime_channel_overrides.items():
        if sg_name in effective:
            effective[sg_name].update(overrides)
    return effective


def get_sg_effective_settings(setup: Setup = None) -> dict[str, dict[str, object]]:
    """Return effective SG settings (Setup values + runtime overrides)."""
    setup = setup or load_setup_from_disk(None)
    return {
        **_get_effective_settings(setup),
        "channels": _get_effective_channel_settings(setup),
    }


def get_sg_channel_names(setup: Setup = None) -> list[str]:
    """Return the SG channel keys from the active setup."""
    return list(_snapshot_setup_channels(setup or load_setup_from_disk(None)).keys())


def get_cached_sg_channel_names() -> list[str]:
    """Return cached SG channel names without accessing setup storage."""
    return list(_cached_channel_names)


def get_cached_sg_channel_settings() -> dict[str, dict[str, object]]:
    """Return cached SG channel settings with runtime overrides applied."""
    settings = {name: dict(values) for name, values in _cached_channel_settings.items()}
    for sg_name, overrides in _runtime_channel_overrides.items():
        if sg_name in settings:
            settings[sg_name].update(overrides)
    return settings


def set_sg_runtime_settings(
    *,
    scan_rate=None,
    resync_interval_s=None,
    buffer_size=None,
    csv_enabled=None,
    csv_save_path=None,
    csv_base_filename=None,
    csv_max_file_size_bytes=None,
    plot_enabled=None,
    plot_window_seconds=None,
    plot_interval_ms=None,
    plot_show_stats=None,
) -> None:
    """Set in-memory SG runtime overrides for the next logging session."""
    if scan_rate is not None:
        _runtime_overrides["stream"]["scan_rate"] = _coerce_positive_float(
            scan_rate, "scan_rate"
        )
    if resync_interval_s is not None:
        _runtime_overrides["stream"]["resync_interval_s"] = _coerce_positive_int(
            resync_interval_s, "resync_interval_s"
        )
    if buffer_size is not None:
        _runtime_overrides["stream"]["buffer_size"] = _coerce_positive_int(
            buffer_size, "buffer_size"
        )

    if csv_enabled is not None:
        _runtime_overrides["csv"]["enabled"] = _coerce_bool(csv_enabled, "csv_enabled")
    if csv_save_path is not None:
        path = str(csv_save_path).strip()
        if not path:
            raise ValueError("csv_save_path cannot be empty")
        _runtime_overrides["csv"]["save_path"] = path
    if csv_base_filename is not None:
        filename = str(csv_base_filename).strip()
        if not filename:
            raise ValueError("csv_base_filename cannot be empty")
        _runtime_overrides["csv"]["base_filename"] = filename
    if csv_max_file_size_bytes is not None:
        _runtime_overrides["csv"]["max_file_size_bytes"] = _coerce_positive_int(
            csv_max_file_size_bytes, "csv_max_file_size_bytes"
        )

    if plot_enabled is not None:
        _runtime_overrides["plot"]["enabled"] = _coerce_bool(
            plot_enabled, "plot_enabled"
        )
    if plot_window_seconds is not None:
        _runtime_overrides["plot"]["window_seconds"] = _coerce_positive_float(
            plot_window_seconds, "plot_window_seconds"
        )
    if plot_interval_ms is not None:
        _runtime_overrides["plot"]["interval_ms"] = _coerce_positive_int(
            plot_interval_ms, "plot_interval_ms"
        )
    if plot_show_stats is not None:
        _runtime_overrides["plot"]["show_stats"] = _coerce_bool(
            plot_show_stats, "plot_show_stats"
        )


def set_sg_channel_runtime_settings(
    *,
    sg_name: str,
    enabled=None,
    ain_channel=None,
    voltage_range=None,
    neg_voltage_range=None,
    resolution_index=None,
    setup: Setup = None,
) -> None:
    """Set in-memory runtime overrides for one SG channel definition."""
    setup = setup or load_setup_from_disk(None)
    channels = _snapshot_setup_channels(setup)
    valid_names = channels.keys()
    if sg_name not in valid_names:
        known = ", ".join(valid_names)
        raise ValueError(f"Unknown sg_name '{sg_name}'. Known SGs: {known}")

    _cached_channel_settings[sg_name] = dict(channels[sg_name])
    overrides = _runtime_channel_overrides.setdefault(sg_name, {})

    if enabled is not None:
        overrides["enabled"] = _coerce_bool(enabled, "enabled")
    if ain_channel is not None:
        overrides["ain_channel"] = _coerce_non_negative_int(ain_channel, "ain_channel")
    if voltage_range is not None:
        overrides["voltage_range"] = _coerce_positive_float(
            voltage_range, "voltage_range"
        )
    if neg_voltage_range is not None:
        overrides["neg_voltage_range"] = _coerce_positive_float(
            neg_voltage_range, "neg_voltage_range"
        )
    if resolution_index is not None:
        overrides["resolution_index"] = _coerce_non_negative_int(
            resolution_index, "resolution_index"
        )
    _cached_channel_settings[sg_name].update(overrides)


def reset_sg_runtime_settings() -> None:
    """Clear all in-memory SG runtime overrides."""
    for section in _runtime_overrides.values():
        section.clear()
    _runtime_channel_overrides.clear()
    try:
        _snapshot_setup_channels(load_setup_from_disk(None))
    except Exception:
        pass


def get_sg_settings(setup: Setup = None) -> str:
    """Return a human-readable snapshot of effective SG settings."""
    setup = setup or load_setup_from_disk(None)
    effective = _get_effective_settings(setup=setup)
    channels = _get_effective_channel_settings(setup=setup)

    lines = [
        "Strain-gauge effective settings:",
        (
            "stream: "
            f"scan_rate={effective['stream']['scan_rate']}, "
            f"resync_interval_s={effective['stream']['resync_interval_s']}, "
            f"buffer_size={effective['stream']['buffer_size']}"
        ),
        (
            "csv: "
            f"enabled={effective['csv']['enabled']}, "
            f"save_path={effective['csv']['save_path']}, "
            f"base_filename={effective['csv']['base_filename']}, "
            f"max_file_size_bytes={effective['csv']['max_file_size_bytes']}"
        ),
        (
            "plot: "
            f"enabled={effective['plot']['enabled']}, "
            f"window_seconds={effective['plot']['window_seconds']}, "
            f"interval_ms={effective['plot']['interval_ms']}, "
            f"show_stats={effective['plot']['show_stats']}"
        ),
        "channels:",
    ]
    for sg_name, ch_cfg in channels.items():
        lines.append(
            "  "
            f"{sg_name}: enabled={ch_cfg['enabled']}, "
            f"ain_channel={ch_cfg['ain_channel']}, "
            f"voltage_range={ch_cfg['voltage_range']}, "
            f"neg_voltage_range={ch_cfg['neg_voltage_range']}, "
            f"resolution_index={ch_cfg['resolution_index']}"
        )

    active_value_overrides = {
        section_name: values
        for section_name, values in _runtime_overrides.items()
        if values
    }
    if active_value_overrides or _runtime_channel_overrides:
        lines.append("runtime_overrides:")
        for section_name in ("stream", "csv", "plot"):
            overrides = active_value_overrides.get(section_name)
            if not overrides:
                continue
            override_txt = ", ".join(
                f"{key}={value}" for key, value in overrides.items()
            )
            lines.append(f"  {section_name}: {override_txt}")
        for sg_name in sorted(_runtime_channel_overrides):
            channel_overrides = _runtime_channel_overrides[sg_name]
            override_txt = ", ".join(
                f"{key}={value}" for key, value in channel_overrides.items()
            )
            lines.append(f"  channels.{sg_name}: {override_txt}")
    else:
        lines.append("runtime_overrides: none")

    lines.append(f"status: {get_sg_status()}")
    return "\n".join(lines)


def _rotate_csv(headers):
    global _file_index, _csv_file, _csv_writer, _csv_filename

    if _csv_file:
        _csv_file.close()
    fname = f"{_base_filename}_{_start_ts}_{_file_index:03d}.csv"
    _csv_filename = os.path.join(_save_path, fname)
    _csv_file = open(_csv_filename, "w", newline="")
    _csv_writer = csv.writer(_csv_file)
    _csv_writer.writerow(["Timestamp"] + headers)
    _file_index += 1
    print(f"Logging to: {_csv_filename}")


def _on_stream_data(*, timestamps, readings, channel_names, device_backlog, ljm_backlog):
    global _read_count, _csv_writer, _csv_file, _csv_filename

    if not timestamps or not readings:
        return

    with _session_lock:
        csv_enabled = _csv_enabled
        plot_enabled = _plot_enabled
        plot_keep_seconds = _plot_keep_seconds
        logger = _logger

    if csv_enabled:
        with _csv_lock:
            if _csv_writer is None:
                _rotate_csv(channel_names)

            rows = [
                [ts.isoformat()] + list(row)
                for ts, row in zip(timestamps, readings)
            ]
            _csv_writer.writerows(rows)
            _csv_file.flush()

            _read_count += 1
            if _read_count % 10 == 0:
                print(
                    f"Read #{_read_count}: {len(timestamps)} scans | "
                    f"Device backlog: {device_backlog} | LJM backlog: {ljm_backlog}"
                )

            if os.path.getsize(_csv_filename) >= _max_file_size:
                _rotate_csv(channel_names)

    if plot_enabled:
        if logger is None or logger.stream_start_time is None:
            return

        t0 = logger.stream_start_time
        new_times = [(ts - t0).total_seconds() for ts in timestamps]
        new_vals = list(zip(*readings))

        with plot_lock:
            time_buffer.extend(new_times)
            for ch_idx in range(len(channel_names)):
                ch_buffers[ch_idx].extend(new_vals[ch_idx])

            # Bound in-memory buffers even if no live-plot consumer is running.
            # This prevents runaway growth that can eventually stall the UI.
            cutoff = time_buffer[-1] - plot_keep_seconds
            trim_idx = bisect.bisect_left(time_buffer, cutoff)
            if trim_idx > 0:
                del time_buffer[:trim_idx]
                for ch_idx in range(len(channel_names)):
                    del ch_buffers[ch_idx][:trim_idx]


def start_sg_logging(setup: Setup = None):
    """Start strain-gauge streaming and CSV logging from the CGSE Setup.

    Reads all LabJack T7 channel, stream, and CSV parameters from
    ``setup.gse.labjack_t7``.
    """
    global _logger, _csv_enabled, _save_path, _base_filename, _max_file_size
    global _plot_enabled, _plot_keep_seconds, _start_ts
    global _file_index, _read_count, _csv_file, _csv_writer, _csv_filename
    global _active_channel_labels

    setup = setup or load_setup_from_disk(None)
    effective = _get_effective_settings(setup=setup)
    effective_channels = _get_effective_channel_settings(setup=setup)
    selected_channels = [
        (sg_name, ch_cfg)
        for sg_name, ch_cfg in effective_channels.items()
        if ch_cfg["enabled"]
    ]
    if not selected_channels:
        raise ValueError("No SG channels are enabled. Enable at least one channel first.")

    n_ch = len(selected_channels)

    ain_channels = []
    voltage_ranges = []
    neg_voltage_ranges = []
    resolution_indices = []
    active_channel_labels = []
    for sg_name, ch_cfg in selected_channels:
        ain_channels.append(int(ch_cfg["ain_channel"]))
        voltage_ranges.append(float(ch_cfg["voltage_range"]))
        neg_voltage_ranges.append(float(ch_cfg["neg_voltage_range"]))
        resolution_indices.append(int(ch_cfg["resolution_index"]))
        active_channel_labels.append(f"{sg_name}(AIN{int(ch_cfg['ain_channel'])})")

    if len(set(ain_channels)) != len(ain_channels):
        raise ValueError("Enabled SG channels must use unique AIN channels.")

    from tvac.labjack_t7 import LabJackT7Logger

    with _session_lock:
        if _logger is not None:
            print("Strain-gauge logging is already running.")
            return

        _csv_enabled = bool(effective["csv"]["enabled"])
        _save_path = str(effective["csv"]["save_path"])
        _base_filename = str(effective["csv"]["base_filename"])
        _max_file_size = int(effective["csv"]["max_file_size_bytes"])

        if _csv_enabled:
            os.makedirs(_save_path, exist_ok=True)

        _start_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        _file_index = 0
        _read_count = 0
        _csv_file = None
        _csv_writer = None
        _csv_filename = ""

        _plot_enabled = bool(effective["plot"]["enabled"])
        _plot_keep_seconds = max(
            1.0, float(effective["plot"]["window_seconds"]) * 1.2
        )
        _active_channel_labels = active_channel_labels

        _logger = LabJackT7Logger(
            ain_channels=ain_channels,
            scan_rate=float(effective["stream"]["scan_rate"]),
            voltage_range=voltage_ranges,
            neg_voltage_range=neg_voltage_ranges,
            resolution_index=resolution_indices,
            resync_interval_s=int(effective["stream"]["resync_interval_s"]),
            buffer_size=int(effective["stream"]["buffer_size"]),
        )
        logger = _logger

    with plot_lock:
        time_buffer.clear()
        ch_buffers.clear()
        ch_buffers.extend([] for _ in range(n_ch))

    _sg_debug(
        "starting stream "
        f"channels={_active_channel_labels} "
        f"scan_rate={effective['stream']['scan_rate']} "
        f"plot_enabled={effective['plot']['enabled']} "
        f"csv_enabled={effective['csv']['enabled']}"
    )

    try:
        logger.start_stream(callback=_on_stream_data)
    except Exception:
        try:
            logger.close()
        except Exception:
            pass
        with _session_lock:
            if _logger is logger:
                _logger = None
        raise


def stop_sg_logging():
    """Stop the active strain-gauge logging session."""
    global _logger, _csv_file, _csv_filename, _csv_writer, _active_channel_labels

    with _session_lock:
        logger = _logger
        if logger is None:
            print("No strain-gauge logging session is active.")
            return

    _sg_debug("stop requested")

    try:
        logger.close()
    finally:
        with _session_lock:
            if _logger is logger:
                _logger = None
            _active_channel_labels = []

        with _csv_lock:
            if _csv_file:
                _csv_file.close()
            _csv_file = None
            _csv_writer = None
            _csv_filename = ""

        with plot_lock:
            time_buffer.clear()
            ch_buffers.clear()

    print("Strain-gauge logging stopped.")


def get_sg_status() -> str:
    """Return a short status string for the current logging session."""
    with _session_lock:
        logger = _logger
        channels = (
            ", ".join(_active_channel_labels) if _active_channel_labels else "n/a"
        )
    if logger is None:
        return "Not running"
    rate = logger.actual_scan_rate
    return (
        f"Running at {rate:.1f} Hz, "
        f"{logger.num_addresses} channels, "
        f"[{channels}], "
        f"{_read_count} reads, "
        f"file: {_csv_filename}"
    )


def trim_plot_buffers(keep_seconds: float):
    """Remove plot-buffer samples older than *keep_seconds* from the latest."""
    with plot_lock:
        if not time_buffer:
            return
        cutoff = time_buffer[-1] - keep_seconds
        idx = bisect.bisect_left(time_buffer, cutoff)
        if idx > 0:
            del time_buffer[:idx]
            for buf in ch_buffers:
                del buf[:idx]
