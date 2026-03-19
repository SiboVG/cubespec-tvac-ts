import socket

import numpy as np
import pigpio
import time
from egse.arbitrary_wave_generator.aim_tti import (
    WaveformShape,
    OutputWaveformType,
    Output,
    SweepType,
    SweepMode,
    Sweep,
    TriggerSource,
    Burst,
)
from egse.arbitrary_wave_generator.aim_tti.tgf4000 import Tgf4000Interface
from egse.observation import building_block
from egse.settings import Settings
from egse.setup import load_setup, Setup

TRIGGER_SETTINGS = Settings.load("Aim-TTi TGF4000").get("TRIGGER")


class ArbConfig:
    def __init__(
        self, name: str, frequency: float, output_load: float | str, signal: np.ndarray
    ):
        """Initialisation of a configuration for an arbitrary waveform for an Aim-TTi TGF4000 device.

        Args:
            name (str): User=specified waveform name.
            frequency (float): Waveform frequency [Hz].
            output_load (float| str): Output load, ranging from 1 to 100000 Ohm, or "OPEN".
            signal (np.ndarray): Voltage profile to use for the waveform [V].  The amplitude and DC offset are derived
                                 from this array.
        """

        self._name = name

        self._frequency = frequency  # Frequency [Hz]
        # noinspection PyUnresolvedReferences
        self._amplitude = float(np.max(signal) - np.min(signal))  # Amplitude [V]
        # noinspection PyUnresolvedReferences
        self._dc_offset = float(
            (np.max(signal) - np.min(signal)) / 2.0
        )  # DC offset [V]
        self._output_load = output_load  # Output load [Ω]

        self._signal = signal

    @property
    def name(self) -> str:
        """Returns the name of the waveform.

        Returns:
            Name of the waveform.
        """

        return self._name

    @property
    def frequency(self) -> float:
        """Returns the frequency of the waveform.

        Returns:
            Frequency of the waveform [Hz].
        """

        return self._frequency

    @property
    def amplitude(self) -> float:
        """Returns the amplitude of the waveform.

        Returns:
            Amplitude of the waveform [Vpp].
        """

        return self._amplitude

    @property
    def dc_offset(self) -> float:
        """Returns the DC offset of the waveform.

        Returns:
            DC offset of the waveform [V].
        """

        return self._dc_offset

    @property
    def output_load(self) -> float | str:
        """Returns the output load of the waveform.

        Returns:
            Output load of the waveform, ranging from 1 to 100000 Ohm, or "OPEN".
        """

        return self._output_load

    @property
    def signal(self) -> np.ndarray:
        """Returns the original voltage profile that will be fed to an Aim-TTi TGF4000 device.

        Returns:
            Original voltage profile that will be fed to an Aim-TTi TGF4000 device.
        """

        return self._signal

    def get_signal_as_hex(self) -> str:
        """Returns the string that must be passed to the ARB1/2/3/4 command to load an arbitrary waveform.

        Returns:
            Data consisting of two bytes per point with no characters between bytes or points. The point data is sent
            high byte first. The data block has a header which consists of the # character followed by several ascii
            coded numeric characters. The first of these defines the number of ascii characters to follow and these
            following characters define the length of the binary data in bytes. The instrument will wait for data
            indefinitely If less data is sent. If more data is sent the extra is processed by the command parser which
            results in a command error.
        """

        def int16_to_hex(value):
            return int(value).to_bytes(2, byteorder="big", signed=True).hex().upper()

        # Map to signed 16-bit integer (in the range [-32767, 32767])

        min_signal, max_signal = np.min(self.signal), np.max(self.signal)
        signal16 = (self.signal - min_signal) / (max_signal - min_signal) * (
            65535 - 1
        ) - (65535 // 2)
        signal16 = signal16.astype(np.int16)

        array = []
        for number in signal16:
            hex_number = int16_to_hex(number)

            u = np.uint16(int(hex_number, 16))
            s = u.view(np.int16)
            array.append(int(s))

        byte_string = bytes()

        for number in array:
            byte_string += number.to_bytes(length=2, byteorder="big", signed=True)

        byte_array = byte_string.decode(encoding="latin1", errors="ignore")
        str_num_bytes = str(len(byte_array))  # Number of points in the waveform
        len_num_bytes = len(
            str_num_bytes
        )  # Number of digits needed to express the number of points in the waveform
        arb = rf"#{len_num_bytes:1d}{str_num_bytes}{byte_array}"

        return arb


@building_block
def load_voltage_profile(profile: str, setup: Setup = None) -> None:
    """Configures the wave generators to send voltage profiles to the piezo actuators.

    Args:
        profile (str): Voltage profile.
        setup (Setup): Setup from which to extract the information from the wave generators.
    """

    setup = setup or load_setup()

    v1_config, v2_config, v3_config, frequency = extract_awg_config_from_setup(
        profile, setup=setup
    )

    awg1: Tgf4000Interface = setup.gse.wave_generators.awg1.device
    awg2: Tgf4000Interface = setup.gse.wave_generators.awg2.device

    for awg, channel, config in zip(
        (awg1, awg1, awg2), (1, 2, 1), (v1_config, v2_config, v3_config)
    ):
        # Configure the current channel for the current wave generator, based on the current configuration information

        output_waveform_type = OutputWaveformType(f"ARB{channel}")

        awg.set_channel(channel)  # Select the channel (1/2)
        awg.set_waveform_shape(WaveformShape.ARB)  # Select "ARB" waveform
        awg.set_amplitude(config.amplitude)  # Amplitude [Vpp]
        awg.set_output_load(config.output_load)  # Output load
        awg.set_dc_offset(config.dc_offset)  # DC offset
        awg.set_frequency(frequency)  # Frequency [Hz]
        awg.define_arb_waveform(output_waveform_type, config.name, Output.OFF)
        awg.load_arb1_ascii(
            config.get_signal_as_hex()
        ) if channel == 1 else awg.load_arb2_ascii(
            config.get_signal_as_hex()
        )  # Waveform shape
        time.sleep(2)
        awg.set_arb_waveform(output_waveform_type)

        # Set the output on, but wait for the external trigger signal to start generating waveforms

        awg.set_burst_trigger_source(TriggerSource.EXTERNAL)
        awg.set_burst(Burst.GATED)
        awg.set_output(Output.ON)

    # External trigger, coming from the Raspberry Pi -> Start waveform generation

    start_signal_trigger()


def extract_awg_config_from_setup(profile: str, setup: Setup = None):
    """Extracts the configuration of the wave generators from the setup.

    Args:
        profile (str): Voltage profile.
        setup (Setup): Setup from which to extract the information from the wave generators.

    Returns:
        Three dictionaries with the waveform configuration for the three piezo actuators and the corresponding
        frequency [Hz].
    """

    setup = setup or load_setup()
    calibration = setup.gse.wave_generators.calibration

    # noinspection PyUnresolvedReferences
    factor = calibration.factor
    # noinspection PyUnresolvedReferences
    output_load = calibration.output_load
    # noinspection PyUnresolvedReferences
    profile = calibration.profiles[profile]
    frequency = profile["frequency"]

    v1_config = ArbConfig(
        name="V1_V",
        frequency=frequency,
        output_load=output_load,
        signal=profile["V1_V"] * factor,
    )
    v2_config = ArbConfig(
        name="V2_V",
        frequency=frequency,
        output_load=output_load,
        signal=profile["V2_V"] * factor,
    )
    v3_config = ArbConfig(
        name="V3_V",
        frequency=frequency,
        output_load=output_load,
        signal=profile["V3_V"] * factor,
    )

    return v1_config, v2_config, v3_config, frequency


@building_block
def characterize_piezo(
    piezo: str,
    amplitude: float,
    dc_offset: float,
    start_frequency: float,
    stop_frequency: float,
    sweep_time: float,
    fixed_voltage: float,
    setup: Setup = None,
) -> None:
    """Charactersisation of the given piezo actuator.

    For the given piezo actuator, we configure (and switch on) a frequency sweep.  For the other piezo actuators, we
    configure a constant voltage.

    Args:
        piezo (str): Name of the piezo actuator for which to configure a frequency sweep.
        amplitude (str): Amplitude for the frequency sweep [Vpp].
        dc_offset (str): DC offset for the frequency sweep [Vdc].
        start_frequency (float): Start frequency for the frequency sweep [Hz].
        stop_frequency (float): Stop frequency for the frequency sweep [Hz].
        sweep_time (float): Frequency sweep time [s].
        fixed_voltage (float): Fixed voltage for the other piezo actuators.
        setup (Setup): Setup from which to extract the information from the piezo actuators and corresponding Wave
                       Generators.
    """

    setup = setup or load_setup()

    wave_generators_setup = setup.gse.wave_generators
    output_load = wave_generators_setup.calibration.output_load

    # Loop over all wave generators

    for _, awg in wave_generators_setup.items():
        if "piezo_channels" in awg:  # Exclude the calibration block
            for piezo_name, channel in awg.piezo_channels.items():
                awg.set_channel(channel)

                if piezo_name == piezo:
                    awg.set_waveform_shape(WaveformShape.SINE)
                    awg.set_amplitude(amplitude)
                    awg.set_dc_offset(dc_offset)
                    awg.set_output_load(output_load)

                    # Configure the frequency sweep

                    awg.set_sweep_type(SweepType.LINUP)
                    awg.set_sweep_mode(SweepMode.CONTINUOUS)
                    awg.set_sweep_start_frequency(start_frequency)
                    awg.set_sweep_stop_frequency(stop_frequency)
                    awg.set_sweep_time(sweep_time)

                    awg.set_sweep(Sweep.ON)

                    # Set the output on, but wait for the external trigger signal to start generating waveforms

                    awg.set_burst_trigger_source(TriggerSource.EXTERNAL)
                    awg.set_burst(Burst.GATED)
                else:
                    # Configure the constant voltage

                    awg.set_waveform_shape(WaveformShape.ARB)
                    awg.set_arb_waveform(OutputWaveformType.DC)
                    awg.set_dc_offset(fixed_voltage)

                    # ARB DC cannot be selected when burst is enabled, and vice versa -> Error message -79

                awg.set_output(Output.ON)

    # External trigger, coming from the Raspberry Pi -> Start waveform generation

    start_signal_trigger()


@building_block
def switch_off_awg(setup: Setup = None):
    """Switches off the wave generators.

    Args:
        setup (Setup): Setup from which to extract the information from the wave generators.
    """

    setup = setup or load_setup()

    awg1: Tgf4000Interface = setup.gse.wave_generators.awg1.device
    awg2: Tgf4000Interface = setup.gse.wave_generators.awg2.device

    # External trigger, coming from the Raspberry Pi -> Stop waveform generation

    stop_signal_trigger()

    for awg, channel in zip((awg1, awg1, awg2), (1, 2, 1)):
        awg.set_channel(channel)
        awg.set_output(Output.OFF)

        # Make sure that you return to the default operation settings
        # (e.g. no frequency sweep, no external trigger, etc.)

        awg.reset()


def start_signal_trigger() -> None:
    """Sets the triggering GPIO pin high on the Raspberry Pi.

    The given GPIO pin on the Raspberry Pi is connected to the TRIG/COUNT (DC) IN port (BNC centre) on the rear panel
    of the wave generators.  That way it can act as external trigger source, to make sure all waveforms are in sync.
    The wave generators must therefore be configured in gated burst with an external trigger source.  This means that
    waveforms will be generated as long as the GPIO is high.

    Raises:
        AttributeError: If no settings for external trigger are found.
    """

    if not TRIGGER_SETTINGS:
        raise AttributeError("No settings for for external trigger")

    hostname = TRIGGER_SETTINGS["HOSTNAME"]
    gpio = TRIGGER_SETTINGS["GPIO"]  # BCM numbering

    # Connect to the Raspberry Pi on port 8888

    pi = pigpio.pi(hostname, 8888)
    if not pi.connected:
        raise RuntimeError("Could not connect to pigpio daemon at {}".format(hostname))

    try:
        # Set GPIO pin high

        pi.set_mode(gpio, pigpio.OUTPUT)
        pi.write(gpio, 1)
    finally:
        # Disconnect from the Raspberry Pi

        pi.stop()


def stop_signal_trigger():
    """Sets the triggering GPIO pin low on the Raspberry Pi.

    The given GPIO pin on the Raspberry Pi is connected to the TRIG/COUNT (DC) IN port (BNC centre) on the rear panel
    of the wave generators.  That way it can act as external trigger source, to make sure all waveforms are in sync.
    The wave generators must therefore be configured in gated burst with an external trigger source.  This means that
    waveforms will be generated as long as the GPIO is high.

    Raises:
        AttributeError: If no settings for external trigger are found.
    """

    if not TRIGGER_SETTINGS:
        raise AttributeError("No settings for for external trigger")

    hostname = TRIGGER_SETTINGS["HOSTNAME"]
    gpio = TRIGGER_SETTINGS["GPIO"]  # BCM numbering

    # Connect to the Raspberry Pi on port 8888

    pi = pigpio.pi(hostname, 8888)
    if not pi.connected:
        raise RuntimeError("Could not connect to pigpio daemon at {}".format(hostname))

    try:
        # Set GPIO pin low

        pi.set_mode(gpio, pigpio.OUTPUT)
        pi.write(gpio, 0)
    finally:
        # Disconnect from the Raspberry Pi

        pi.stop()


def check_trigger() -> None:
    """Checks whether a connection can be established with the Raspberry Pi that is used as external trigger source.

    The required GPIO pin on the Raspberry Pi is connected to the TRIG/COUNT (DC) IN port (BNC centre) on the rear panel
    of the wave generators.  That way it can act as external trigger source, to make sure all waveforms are in sync.
    The wave generators must therefore be configured in gated burst with an external trigger source.  This means that
    waveforms will be generated as long as the GPIO is high.

    Raises:
        AttributeError: If no settings for external trigger are found.
    """

    if not TRIGGER_SETTINGS:
        raise AttributeError("No settings for for external trigger")

    hostname = TRIGGER_SETTINGS["HOSTNAME"]

    s = socket.socket()
    try:
        s.settimeout(3)
        s.connect((hostname, 8888))
        print("Port is reachable!")
    except Exception as e:
        print("Port not reachable:", e)
    finally:
        s.close()
