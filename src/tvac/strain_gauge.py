"""High-level strain-gauge session management and data fan-out.

This module sits one layer above :mod:`tvac.labjack_t7`.

Its responsibilities are:

1. read the strain-gauge configuration from the active CGSE setup,
2. apply in-memory runtime overrides from the GUI,
3. start and stop the :class:`tvac.labjack_t7.LabJackT7Logger`,
4. receive streamed batches through a callback,
5. write CSV output, and
6. maintain bounded in-memory plot buffers for the live plot window.

The module keeps the current session state in module-level globals because the
GUI tasks interact with it procedurally: ``start`` creates the singleton-like
streaming session, ``stop`` tears it down, and the plot window reads shared
buffers while the session is active.
"""

import bisect
import csv
import os
import threading
from pathlib import Path

from egse.observation import building_block, request_obsid
from egse.system import format_datetime
from egse.metricshub.client import MetricsHubSender

from egse.env import get_data_storage_location
from egse.setup import Setup, load_setup

from tvac.labjack_t7 import LabJackT7Logger

ORIGIN = "LJ_SG"

# ---------------------------------------------------------------------------
# Module-level state for the active logging session
# ---------------------------------------------------------------------------
# The strain-gauge GUI operates as a small state machine around a single
# streaming session. These globals represent that session and are protected
# by locks where they may be touched from multiple threads/callbacks.
_logger: LabJackT7Logger | None = (
    None  # LabJackT7Logger, imported lazily to avoid LJM init on import
)
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

# Metrics defaults (overridden by setup)
_metrics_enabled = True
_metrics_write_failed = False
_metrics_sender: MetricsHubSender | None = None

# Plot flag
_plot_enabled = False
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
        "enabled": False,
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
    """Emit opt-in debug logging for SG internals when enabled via env var."""
    if not os.environ.get("TVAC_SG_DEBUG", "").strip():
        return

    stamp = format_datetime()
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


def _resolve_csv_save_path(path: str) -> str:
    """Resolve SG CSV output paths relative to the CGSE daily data directory.

    Setup files currently use relative paths such as ``.``. For the strain
    gauge logger that means "store next to the CGSE daily data" rather than
    "store in the current process working directory".
    """
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return str(candidate)

    try:
        storage_root = Path(get_data_storage_location()).expanduser()
        daily_stamp = format_datetime(fmt="%Y%m%d")
        return str(storage_root / "daily" / daily_stamp / candidate)
    except Exception:
        return str(candidate)


def _snapshot_setup_cfg(setup: Setup) -> dict[str, dict[str, object]]:
    """Capture non-channel SG settings from the setup into plain Python data."""
    cfg = setup.gse.labjack_t7
    return {
        "stream": {
            "scan_rate": cfg.stream.scan_rate,
            "resync_interval_s": cfg.stream.resync_interval_s,
            "buffer_size": cfg.stream.buffer_size,
        },
        "csv": {
            "enabled": cfg.csv.enabled,
            "save_path": cfg.csv.save_path,
            "base_filename": cfg.csv.base_filename,
            "max_file_size_bytes": cfg.csv.max_file_size_bytes,
        },
        "metrics": {"enabled": cfg.metrics.enabled},
        "plot": {
            "enabled": cfg.plot.enabled,
            "window_seconds": cfg.plot.window_seconds,
            "interval_ms": cfg.plot.interval_ms,
            "show_stats": cfg.plot.show_stats,
        },
    }


def _snapshot_setup_channels(setup: Setup) -> dict[str, dict[str, object]]:
    """Capture SG channel definitions from the setup and refresh local caches."""
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
        _cached_channel_settings = {
            name: dict(values) for name, values in channels.items()
        }
    return channels


def _get_effective_settings(setup: Setup = None) -> dict[str, dict[str, object]]:
    """Return setup-derived stream/CSV/plot settings with runtime overrides."""
    setup = setup or load_setup()
    effective = _snapshot_setup_cfg(setup)
    for section_name, overrides in _runtime_overrides.items():
        effective[section_name].update(overrides)
    return effective


def _get_effective_channel_settings(
    setup: Setup = None,
) -> dict[str, dict[str, object]]:
    """Return setup-derived channel settings with per-channel overrides applied."""
    setup = setup or load_setup()
    effective = _snapshot_setup_channels(setup)
    for sg_name, overrides in _runtime_channel_overrides.items():
        if sg_name in effective:
            effective[sg_name].update(overrides)
    return effective


def get_sg_effective_settings(setup: Setup = None) -> dict[str, dict[str, object]]:
    """Return effective SG settings (Setup values + runtime overrides)."""
    setup = setup or load_setup()
    return {
        **_get_effective_settings(setup),
        "channels": _get_effective_channel_settings(setup),
    }


def get_sg_channel_names(setup: Setup = None) -> list[str]:
    """Return the SG channel keys from the active setup."""
    return list(_snapshot_setup_channels(setup or load_setup()).keys())


def get_cached_sg_channel_names() -> list[str]:
    """Return cached SG channel names without accessing setup storage."""
    return list(_cached_channel_names)


def get_cached_sg_channel_settings() -> dict[str, dict[str, object]]:
    """Return GUI-safe cached channel settings with runtime overrides applied.

    The GUI process may need to populate widgets without reloading the setup
    file every time. This cache tracks the latest setup snapshot plus any
    in-memory overrides applied during the current process lifetime.
    """
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
    metrics_enabled=None,
    plot_enabled=None,
    plot_window_seconds=None,
    plot_interval_ms=None,
    plot_show_stats=None,
) -> None:
    """Set in-memory SG runtime overrides for the next logging session.

    These overrides do not edit the setup file. They only affect the effective
    settings used by a future ``start_sg_logging()`` call.
    """
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

    if metrics_enabled is not None:
        _runtime_overrides["metrics"]["enabled"] = _coerce_bool(
            metrics_enabled, "metrics_enabled"
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
    """Set in-memory runtime overrides for one SG channel definition.

    The override model mirrors the GUI behavior: users can temporarily change
    channel enable flags or acquisition parameters, inspect the effective
    result, and then start a session without persisting those changes back to
    the setup repository.
    """
    setup = setup or load_setup()
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
    """Clear all in-memory SG runtime overrides.

    After reset, newly started sessions will use the setup values again.
    """
    for section in _runtime_overrides.values():
        section.clear()
    _runtime_channel_overrides.clear()
    try:
        _snapshot_setup_channels(load_setup())
    except Exception:
        pass


def get_sg_settings(setup: Setup = None) -> str:
    """Return a human-readable snapshot of effective SG settings."""
    setup = setup or load_setup()
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
    """Open the next CSV file segment and write the header row."""
    global _file_index, _csv_file, _csv_writer, _csv_filename

    if _csv_file:
        _csv_file.close()
    fname = f"{_base_filename}_{_start_ts}_{_file_index:03d}.csv"
    _csv_filename = os.path.join(_save_path, fname)
    _csv_file = open(_csv_filename, "w", newline="")
    _csv_writer = csv.writer(_csv_file)
    _csv_writer.writerow(["timestamp"] + headers)
    _file_index += 1
    print(f"Logging to: {_csv_filename}")


def _on_stream_data(
    *,
    timestamps,
    readings,
    channel_names,
    device_backlog,
    ljm_backlog,
):
    """Process one streamed batch from :class:`LabJackT7Logger`.

    This callback is the central fan-out point of the SG data flow:

    1. receive timestamped scan rows from the LabJack logger,
    2. append them to the current CSV file and rotate files when needed,
    3. update the shared live-plot buffers.

    The callback does not talk to the GUI directly. The live plot reads the
    shared ``time_buffer`` and ``ch_buffers`` data structures independently.
    """
    global _read_count, _csv_writer, _csv_file, _csv_filename, _metrics_write_failed

    if not timestamps or not readings:
        return

    with _session_lock:
        # Copy session state under lock so the rest of the callback can operate
        # without holding the session lock around file I/O or buffer work.
        csv_enabled = _csv_enabled
        metrics_enabled = _metrics_enabled
        plot_enabled = _plot_enabled
        plot_keep_seconds = _plot_keep_seconds
        logger: LabJackT7Logger = _logger
        sender = _metrics_sender

    if csv_enabled:
        with _csv_lock:
            if _csv_writer is None:
                _rotate_csv(channel_names)

            # The logger already grouped raw stream values into per-scan rows.
            # CSV output therefore becomes a simple row-wise append.
            rows = [
                [ts.isoformat()] + list(row) for ts, row in zip(timestamps, readings)
            ]
            _csv_writer.writerows(rows)
            _csv_file.flush()

            _read_count += 1
            if _read_count % 10 == 0:
                _sg_debug(
                    f"Read #{_read_count}: {len(timestamps)} scans | "
                    f"Device backlog: {device_backlog} | LJM backlog: {ljm_backlog}"
                )

            if os.path.getsize(_csv_filename) >= _max_file_size:
                _rotate_csv(channel_names)

    if metrics_enabled and sender is not None:
        try:
            for ts, row in zip(timestamps, readings):
                sender.send(
                    {
                        "measurement": ORIGIN.lower(),
                        "time": ts.isoformat(),
                        "fields": dict(zip(channel_names, row)),
                    }
                )
        except Exception as exc:
            if not _metrics_write_failed:
                print(f"Warning: metrics write to MetricsHub failed: {exc}")
                _metrics_write_failed = True
            _sg_debug(f"metrics write failed: {exc}")

    if plot_enabled:
        if logger is None or logger.stream_start_time is None:
            return

        # The live plot uses seconds-from-start on the x-axis instead of raw
        # datetimes, so convert timestamps into offsets from the stream start.
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

    The startup sequence is:

    1. load setup values,
    2. merge any in-memory runtime overrides,
    3. validate the enabled channel set,
    4. initialise CSV / plot session state,
    5. create the LabJack logger,
    6. start the stream so data begins arriving through ``_on_stream_data``.
    """
    global _logger, _csv_enabled, _save_path, _base_filename, _max_file_size
    global _metrics_enabled, _metrics_write_failed, _metrics_sender
    global _plot_enabled, _plot_keep_seconds, _start_ts
    global _file_index, _read_count, _csv_file, _csv_writer, _csv_filename
    global _active_channel_labels

    setup = setup or load_setup()
    effective = _get_effective_settings(setup=setup)
    effective_channels = _get_effective_channel_settings(setup=setup)
    selected_channels = [
        (sg_name, ch_cfg)
        for sg_name, ch_cfg in effective_channels.items()
        if ch_cfg["enabled"]
    ]
    if not selected_channels:
        raise ValueError(
            "No SG channels are enabled. Enable at least one channel first."
        )

    # Flatten the enabled channel mapping into the parallel lists expected by
    # LabJackT7Logger and the plot buffers.
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

        # Session settings are copied into module-level state so the callback
        # can operate without repeatedly consulting setup objects.
        _csv_enabled = bool(effective["csv"]["enabled"])
        _save_path = _resolve_csv_save_path(str(effective["csv"]["save_path"]))
        _base_filename = str(effective["csv"]["base_filename"])
        _max_file_size = int(effective["csv"]["max_file_size_bytes"])

        if _csv_enabled:
            os.makedirs(_save_path, exist_ok=True)

        _start_ts = format_datetime()
        _file_index = 0
        _read_count = 0
        _csv_file = None
        _csv_writer = None
        _csv_filename = ""

        _metrics_enabled = bool(effective["metrics"]["enabled"])
        _metrics_write_failed = False
        if _metrics_enabled:
            _metrics_sender = MetricsHubSender()
            _metrics_sender.connect()
        else:
            _metrics_sender = None

        _plot_enabled = bool(effective["plot"]["enabled"])
        _plot_keep_seconds = max(1.0, float(effective["plot"]["window_seconds"]) * 1.2)
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
        # One buffer per enabled channel, aligned with the order used by the
        # LabJack stream and CSV output.
        time_buffer.clear()
        ch_buffers.clear()
        ch_buffers.extend([] for _ in range(n_ch))

    _sg_debug(
        "starting stream "
        f"channels={_active_channel_labels} "
        f"scan_rate={effective['stream']['scan_rate']} "
        f"plot_enabled={effective['plot']['enabled']} "
        f"csv_enabled={effective['csv']['enabled']}"
        f"metrics_enabled={effective['metrics']['enabled']}",
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
    """Stop the active strain-gauge logging session and release resources."""
    global \
        _logger, \
        _csv_file, \
        _csv_filename, \
        _csv_writer, \
        _active_channel_labels, \
        _metrics_sender

    with _session_lock:
        logger = _logger
        if logger is None:
            print(
                "No strain-gauge logging session is active. Starting new session to close the device."
            )
            _logger = LabJackT7Logger(ain_channels=[])
            logger = _logger

    _sg_debug("stop requested")

    try:
        logger.close()
    finally:
        # Tear down each output path even if the device close raised, so the
        # next start begins from a clean session state.
        with _session_lock:
            if _logger is logger:
                _logger = None
            _active_channel_labels = []
            sender = _metrics_sender
            _metrics_sender = None

        if sender is not None:
            sender.close()

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
    """Return a short human-readable status string for the current session."""
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
    """Remove plot-buffer samples older than ``keep_seconds`` from the latest.

    This helper is used by the plotting layer when it wants tighter control
    over memory than the default bounded-buffer logic inside ``_on_stream_data``.
    """
    with plot_lock:
        if not time_buffer:
            return
        cutoff = time_buffer[-1] - keep_seconds
        idx = bisect.bisect_left(time_buffer, cutoff)
        if idx > 0:
            del time_buffer[:idx]
            for buf in ch_buffers:
                del buf[:idx]


@building_block
def enable_sg_logging(sg_name: str, scan_rate: float, setup: Setup) -> None:
    """Enables the logging for the given strain gauge.

    The following steps are performed:

        - For the given strain gauge, set the voltage ranges and resolution index (from the setup), and enable its
          channel,
        - Set the scan rate for the logging of the requested strain gauge,
        - Enable HK and metrics,
        - Make sure that the HK ends up in the folder, dedicated to the current observation, and that the filenames
          also refer to the current observation (since this function is a building block, it can only be run in the
          context of an observation, so the obsid is guaranteed to be not None),
        - Start the logging of the LabJack.
    """

    setup = setup or load_setup()

    sg_setup = setup.gse.labjack_t7.channels[sg_name]
    stream_setup = setup.gse.labjack_t7.stream

    # Set the voltage ranges + resolution index (for the requested strain gauge), and enable the channel

    set_sg_channel_runtime_settings(
        sg_name=sg_name,
        enabled=True,
        ain_channel=sg_setup.ain_channel,
        voltage_range=sg_setup.voltage_range,
        neg_voltage_range=sg_setup.neg_voltage_range,
        resolution_index=sg_setup.resolution_index,
        setup=setup,
    )

    # Configure the runtime settings:
    #   - Scan rate [Hz]
    #   - Enable HK + metrics

    obsid = request_obsid()  # Since we're in a building block, this will not be None
    csv_base_filename = f"{obsid}_{ORIGIN}"
    csv_save_path = f"{os.environ.get('CUBESPEC_DATA_STORAGE_LOCATION')}/obs/{obsid}"

    set_sg_runtime_settings(
        scan_rate=scan_rate,
        resync_interval_s=stream_setup.resync_interval_s,
        buffer_size=stream_setup.buffer_size,
        csv_enabled=True,
        csv_save_path=csv_save_path,
        csv_base_filename=csv_base_filename,
        metrics_enabled=True,
    )

    start_sg_logging(setup=setup)


@building_block
def disable_sg_logging(setup: Setup = None) -> None:
    """Disables the logging of all strain gauges.

    The following steps are performed:

        - Stop the logging of the strain gauges,
        - Revert the configuration of the LabJack to the values in the setup,
        - Disable all LabJack channels.
    """

    setup = setup or load_setup()
    sg_setup = setup.gse.labjack_t7.channels

    # Stop logging (for all strain gauges)

    stop_sg_logging()

    # Reset the runtime settings (for all strain gauges)

    reset_sg_runtime_settings()
    reset_sg()

    # Disable all LabJack channels

    for sg_name, sg_info in sg_setup.items():
        set_sg_channel_runtime_settings(
            sg_name=sg_name,
            enabled=False,
            ain_channel=sg_info.ain_channel,
            setup=setup,
        )


@building_block
def reset_sg(setup: Setup = None) -> None:
    """Reverts the configuration of the LabJack to the values in the setup.

    This includes reverting the information from the channels (runtime settings), stream, CSV, metrics, and plot
    sections.

    Args:
        setup (Setup): Setup with the values to revert to.
    """

    setup = setup or load_setup()
    lj_setup = setup.gse.labjack_t7
    stream_setup = lj_setup.stream
    csv_setup = lj_setup.csv
    metrics_setup = lj_setup.metrics
    plot_setup = lj_setup.plot

    # Reset the channels (voltage ranges  + resolution index)

    reset_sg_runtime_settings()

    # Reset stream + CSV + metrics + plot

    set_sg_runtime_settings(
        scan_rate=stream_setup.scan_rate,
        resync_interval_s=stream_setup.resync_interval_s,
        buffer_size=stream_setup.buffer_size,
        csv_enabled=csv_setup.enabled,
        csv_save_path=csv_setup.save_path,
        csv_base_filename=csv_setup.base_filename,
        csv_max_file_size_bytes=csv_setup.max_file_size_bytes,
        metrics_enabled=metrics_setup.enabled,
        plot_enabled=plot_setup.enabled,
        plot_window_seconds=plot_setup.window_seconds,
        plot_interval_ms=plot_setup.interval_ms,
        plot_show_stats=plot_setup.show_stats,
    )
