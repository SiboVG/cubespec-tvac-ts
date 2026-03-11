"""
Live matplotlib plot for strain-gauge streaming.

Reads plot configuration from ``setup.gse.labjack_t7.plot`` and
consumes shared buffers from ``tvac.strain_gauge``.
"""

import bisect

import matplotlib
# GUI Executor is Qt-based; prefer a Qt backend to avoid Tk/Qt event-loop conflicts.
if "qt" not in matplotlib.get_backend().lower():
    try:
        matplotlib.use("QtAgg")
    except Exception:
        pass
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from egse.setup import load_setup
from tvac.strain_gauge import (
    ch_buffers,
    get_sg_effective_settings,
    plot_lock,
    time_buffer,
)

# Default colours, extended automatically if more channels are needed.
_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
]


def open_live_plot(setup=None):
    """Open a non-blocking live plot window.

    Parameters are read from ``setup.gse.labjack_t7.plot`` and
    ``setup.gse.labjack_t7.channels``.
    """
    setup = setup or load_setup()
    effective = get_sg_effective_settings(setup=setup)

    window_seconds = float(effective["plot"]["window_seconds"])
    interval_ms = int(effective["plot"]["interval_ms"])
    show_stats = bool(effective["plot"]["show_stats"])

    selected_channels = [
        (sg_name, ch_cfg)
        for sg_name, ch_cfg in effective["channels"].items()
        if ch_cfg["enabled"]
    ]
    if not selected_channels:
        raise ValueError("No SG channels are enabled for plotting.")

    channel_names = [
        f"{sg_name} (AIN{int(ch_cfg['ain_channel'])})"
        for sg_name, ch_cfg in selected_channels
    ]
    num_channels = len(channel_names)

    colors = (_COLORS * ((num_channels // len(_COLORS)) + 1))[:num_channels]

    fig, axes = plt.subplots(num_channels, 1, figsize=(10, 2.5 * num_channels), sharex=True)
    if num_channels == 1:
        axes = [axes]
    fig.suptitle("LabJack T7 — Strain Gauge Live View", fontsize=13)

    lines = []
    stat_texts = []

    for ax, name, color in zip(axes, channel_names, colors):
        (line,) = ax.plot([], [], color=color, linewidth=0.8)
        lines.append(line)
        ax.set_ylabel(f"{name} (V)", fontsize=9)
        ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.6)
        ax.tick_params(labelsize=8)

        if show_stats:
            txt = ax.text(
                0.01, 0.97, "",
                transform=ax.transAxes,
                fontsize=7.5,
                verticalalignment="top",
                horizontalalignment="left",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          alpha=0.7, edgecolor="gray"),
                family="monospace",
            )
            stat_texts.append(txt)
        else:
            stat_texts.append(None)

    axes[-1].set_xlabel("Time since stream start (s)", fontsize=9)
    fig.tight_layout()

    keep_seconds = window_seconds * 1.2

    def _update(_frame):
        with plot_lock:
            if not time_buffer:
                return lines

            t_now = time_buffer[-1]
            t_start = max(0.0, t_now - window_seconds)

            lo_idx = bisect.bisect_left(time_buffer, t_start)
            t_win = time_buffer[lo_idx:]
            v_win = [ch_buffers[ch][lo_idx:] for ch in range(num_channels)]

            trim_idx = bisect.bisect_left(time_buffer, t_now - keep_seconds)
            if trim_idx > 0:
                del time_buffer[:trim_idx]
                for ch in range(num_channels):
                    del ch_buffers[ch][:trim_idx]

        if not t_win:
            return lines

        for ch, (line, ax, txt) in enumerate(zip(lines, axes, stat_texts)):
            line.set_data(t_win, v_win[ch])
            ax.set_xlim(t_start, t_now)
            ax.relim()
            ax.autoscale_view(scalex=False, scaley=True)

            if show_stats and txt is not None:
                lo = min(v_win[ch])
                hi = max(v_win[ch])
                mn = sum(v_win[ch]) / len(v_win[ch])
                txt.set_text(
                    f"min: {lo:+.5f} V\n"
                    f"max: {hi:+.5f} V\n"
                    f"mean:{mn:+.5f} V"
                )

        return lines

    _ani = animation.FuncAnimation(
        fig, _update,
        interval=interval_ms,
        blit=False,
        cache_frame_data=False,
    )

    # Keep a reference so the animation isn't garbage-collected
    fig._sg_animation = _ani

    plt.show(block=False)
