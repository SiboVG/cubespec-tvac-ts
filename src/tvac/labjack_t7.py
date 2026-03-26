"""LabJack T7 streaming support for the strain-gauge feature.

This module is intentionally narrow in scope:

1. connect to a single T7 over USB,
2. configure the requested analog input channels for differential reads,
3. start continuous streaming, and
4. translate each raw stream batch into timestamped scans before handing
   the data to a caller-supplied callback.

It does not know anything about CSV files, plotting, or GUI state. Those
concerns live in :mod:`tvac.strain_gauge`, which owns the higher-level
session lifecycle and output handling.
"""

import datetime
import threading

from egse.setup import Setup
from labjack import ljm
from labjack.ljm.ljm import LJMError


class LabJackT7Logger:
    """Stream differential analog inputs from a LabJack T7 over USB.

    Parameters
    ----------
    ain_channels : list[int]
        Positive AIN channel numbers (e.g. [0, 2, 4]).
        Negative channels are automatically assigned as ain+1.
    scan_rate : float
        Requested scan rate in Hz.
    voltage_range : float | list[float]
        Voltage range for positive channels. A single value applies to
        all channels; a list sets per-channel ranges. Default 0.1 V
        (minimum valid for streaming on the T7).
    neg_voltage_range : float | list[float]
        Voltage range for negative reference channels. Scalar or
        per-channel list. Default 10.0 V.
    resolution_index : int | list[int]
        Stream resolution index. Scalar or per-channel list. 0 = auto.
    resync_interval_s : int
        Seconds between host-clock re-anchor points to limit drift.
    buffer_size : int
        T7 stream buffer size in bytes (max 32768).

    Notes
    -----
    The logger exposes batches of scans through a callback instead of
    returning data directly. This mirrors how the LabJack LJM API delivers
    stream reads and keeps device I/O separate from downstream consumers
    such as the CSV writer and live plot.
    """

    @staticmethod
    def _expand(value, n, label):
        """Normalize scalar or per-channel input to a list of length ``n``."""
        if isinstance(value, (list, tuple)):
            if len(value) != n:
                raise ValueError(f"{label}: expected {n} values, got {len(value)}")
            return list(value)
        return [value] * n

    def __init__(
        self,
        ain_channels: list[int],
        scan_rate: float = 496,
        voltage_range: float | list[float] = 0.1,
        neg_voltage_range: float | list[float] = 10.0,
        resolution_index: int | list[int] = 0,
        resync_interval_s: int = 60,
        buffer_size: int = 32768,
    ):
        self.ain_channels = ain_channels
        self.scan_rate = scan_rate
        self.resync_interval_s = resync_interval_s
        self.buffer_size = buffer_size

        n = len(ain_channels)
        self.voltage_ranges = self._expand(voltage_range, n, "voltage_range")
        self.neg_voltage_ranges = self._expand(
            neg_voltage_range, n, "neg_voltage_range"
        )
        self.resolution_indices = self._expand(resolution_index, n, "resolution_index")

        # Derived
        self.neg_channels = [ch + 1 for ch in ain_channels]
        self.channel_names = [f"AIN{ch}" for ch in ain_channels]
        self.num_addresses = n
        self.scans_per_read = int(scan_rate / 2)

        # State
        self._handle = None
        self._actual_scan_rate = None
        self._callback = None
        self._lock = threading.Lock()
        self._streaming = False

        # Timestamp tracking
        self._t_anchor = None
        self._stream_start_time = None
        self._anchor_scan_count = 0
        self._scan_index = 0
        self._resync_interval_scans = int(scan_rate * resync_interval_s)

        self._connect()
        self._configure()

    @classmethod
    def from_setup(cls, setup: Setup = None):
        """Construct a LabJackT7Logger from a CGSE Setup object.

        Reads channel wiring and stream parameters from
        ``setup.gse.labjack_t7`` and expands them into the per-channel lists
        expected by :class:`LabJackT7Logger`.
        """
        from egse.setup import load_setup

        setup = setup or load_setup()
        cfg = setup.gse.labjack_t7

        # Build per-channel lists from the channels dict
        ain_channels = []
        voltage_ranges = []
        neg_voltage_ranges = []
        resolution_indices = []

        for ch_key in cfg.channels:
            ch_cfg = cfg.channels[ch_key]
            ain_channels.append(ch_cfg.ain_channel)
            voltage_ranges.append(ch_cfg.voltage_range)
            neg_voltage_ranges.append(ch_cfg.neg_voltage_range)
            resolution_indices.append(ch_cfg.resolution_index)

        stream = cfg.stream

        return cls(
            ain_channels=ain_channels,
            scan_rate=stream.scan_rate,
            voltage_range=voltage_ranges,
            neg_voltage_range=neg_voltage_ranges,
            resolution_index=resolution_indices,
            resync_interval_s=stream.resync_interval_s,
            buffer_size=stream.buffer_size,
        )

    @property
    def handle(self):
        """Return the active LJM device handle, or ``None`` if closed."""
        return self._handle

    @property
    def actual_scan_rate(self):
        """Return the actual scan rate negotiated with the device."""
        return self._actual_scan_rate

    @property
    def stream_start_time(self):
        """Return the host timestamp used as the stream time origin."""
        return self._stream_start_time

    def _connect(self):
        """Open the LabJack and verify that the detected device is a T7."""
        try:
            self._handle = ljm.openS("T7", "USB", "ANY")
        except LJMError as e:
            raise ValueError(f"Could not connect to T7: {e.errorString}") from None

        info = ljm.getHandleInfo(self._handle)
        if info[0] != ljm.constants.dtT7:
            ljm.close(self._handle)
            raise ValueError("Expected T7 device")

        print(
            f"Opened LabJack T7  Serial: {info[2]}  "
            f"IP: {ljm.numberToIP(info[3])}  Port: {info[4]}"
        )

    def _configure(self):
        """Write per-channel differential and stream-wide configuration."""
        names = []
        values = []

        # Each positive channel is read differentially against the next AIN
        # input. For example AIN0 uses AIN1 as the negative reference.
        for ch, neg_ch in zip(self.ain_channels, self.neg_channels):
            names.append(f"AIN{ch}_NEGATIVE_CH")
            values.append(neg_ch)

        for ch, vr in zip(self.ain_channels, self.voltage_ranges):
            names.append(f"AIN{ch}_RANGE")
            values.append(vr)

        for neg_ch, nvr in zip(self.neg_channels, self.neg_voltage_ranges):
            names.append(f"AIN{neg_ch}_RANGE")
            values.append(nvr)

        for ch, ri in zip(self.ain_channels, self.resolution_indices):
            names.append(f"AIN{ch}_RESOLUTION_INDEX")
            values.append(ri)

        names += [
            "STREAM_TRIGGER_INDEX",
            "STREAM_CLOCK_SOURCE",
            "STREAM_RESOLUTION_INDEX",
            "STREAM_SETTLING_US",
            "STREAM_NUM_SCANS",
            "STREAM_BUFFER_SIZE_BYTES",
        ]
        values += [
            0,  # free-running
            0,  # internal clock
            0,  # stream-level resolution (per-channel set above)
            0.0,  # auto settling (float < 1)
            0,  # continuous
            self.buffer_size,
        ]

        ljm.eWriteNames(self._handle, len(names), names, values)

        print("Configuration written:")
        for n, v in zip(names, values):
            print(f"    {n} : {v}")

    def _stream_callback(self, handle):
        """Handle one asynchronous LJM stream-read callback.

        The LabJack returns a flat list of interleaved channel samples. This
        callback groups the raw values back into per-scan rows, synthesizes a
        timestamp for each scan from the current host-time anchor, and then
        forwards the batch to the caller-supplied callback.
        """
        if handle != self._handle or not self._streaming:
            return

        try:
            ret = ljm.eStreamRead(handle)
        except LJMError as err:
            if err.errorCode == ljm.errorcodes.STREAM_NOT_RUNNING:
                return
            raise

        # LJM returns one flat vector of values ordered by scan:
        # [scan0_ch0, scan0_ch1, ..., scan1_ch0, scan1_ch1, ...]
        raw_data = ret[0]
        device_backlog = ret[1]
        ljm_backlog = ret[2]

        timestamps = []
        readings = []

        with self._lock:
            for i in range(0, len(raw_data), self.num_addresses):
                scans_since_anchor = self._scan_index - self._anchor_scan_count
                elapsed = datetime.timedelta(
                    seconds=scans_since_anchor / self._actual_scan_rate
                )
                scan_time = self._t_anchor + elapsed

                timestamps.append(scan_time)
                readings.append(raw_data[i : i + self.num_addresses])
                self._scan_index += 1

            # The T7 does not provide a per-scan host timestamp. We therefore
            # derive timestamps from the negotiated scan rate and periodically
            # re-anchor to the current host clock to limit long-run drift.
            if (
                self._scan_index - self._anchor_scan_count
            ) >= self._resync_interval_scans:
                self._t_anchor = datetime.datetime.now(tz=datetime.timezone.utc)
                self._anchor_scan_count = self._scan_index
                print(f"[Re-anchored host clock at scan {self._scan_index}]")

        if self._callback:
            self._callback(
                timestamps=timestamps,
                readings=readings,
                channel_names=self.channel_names,
                device_backlog=device_backlog,
                ljm_backlog=ljm_backlog,
            )

    def start_stream(self, callback):
        """Start streaming and register a data callback.

        Parameters
        ----------
        callback : callable
            Called for each batch of scans with keyword arguments:
                timestamps    : list[datetime.datetime]
                readings      : list[list[float]]
                channel_names : list[str]
                device_backlog : int
                ljm_backlog    : int

        Notes
        -----
        The actual scan rate may differ slightly from the requested value.
        ``self.actual_scan_rate`` is populated from :func:`ljm.eStreamStart`
        and is later used to derive scan timestamps.
        """
        self._callback = callback

        scan_list = ljm.namesToAddresses(self.num_addresses, self.channel_names)[0]
        self._actual_scan_rate = ljm.eStreamStart(
            self._handle,
            self.scans_per_read,
            self.num_addresses,
            scan_list,
            self.scan_rate,
        )

        self._t_anchor = datetime.datetime.now(tz=datetime.timezone.utc)
        self._stream_start_time = self._t_anchor
        self._anchor_scan_count = 0
        self._scan_index = 0
        self._streaming = True

        ljm.setStreamCallback(self._handle, self._stream_callback)

        print(
            f"Stream started at {self._actual_scan_rate:.1f} Hz  "
            f"({self.scans_per_read} scans/read, "
            f"re-anchor every {self._resync_interval_scans} scans)"
        )

    def stop_stream(self):
        """Stop the active LabJack stream if one is running."""
        self._streaming = False
        try:
            ljm.eStreamStop(self._handle)
        except Exception:
            pass
        print("Stream stopped.")

    def close(self):
        """Stop streaming and close the LabJack device handle."""
        self.stop_stream()
        if self._handle is not None:
            ljm.close(self._handle)
            self._handle = None
        print("Device closed.")
