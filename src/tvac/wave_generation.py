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

from tvac.strain_gauge import disable_sg_logging, enable_sg_logging, disable_sg_channels

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
        # self._amplitude = float(np.max(signal))
        # self._dc_offset = float(np.max(signal) / 2.0)
        # noinspection PyUnresolvedReferences
        self._amplitude = float(np.max(signal) - np.min(signal))  # Amplitude [V]
        # noinspection PyUnresolvedReferences
        self._dc_offset = float(
            (np.max(signal) + np.min(signal)) / 2.0
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
        # min_signal, max_signal = 0, np.max(self.signal)
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

    The use of an external trigger means that - when the output is enabled - the wave generation already starts, but
    is frozen at the first value of the configured waveform.  It is only when the external trigger signal is received
    that the wave generation is resumed.  As a result, the channels are not synchronised and there can be a steep
    increase in voltage.  The latter would mean that a large current is drawn from the piezo actuators, which can
    potentially damage them.  This is why we've implemented a soft start.  More information can be found here:
    https://github.com/IvS-KULeuven/cubespec-tvac-ts/issues/52.

    Args:
        profile (str): Voltage profile.
        setup (Setup): Setup from which to extract the information from the wave generators.
    """

    setup = setup or load_setup()
    wave_generators_setup = setup.gse.wave_generators

    awg_list = []
    channel_list = []

    for _, awg_info in wave_generators_setup.items():
        if "piezo_channels" in awg_info:  # Exclude the non-device blocks
            awg: Tgf4000Interface = awg_info.device
            awg.reconnect()  # Mitigate possible connection issues (#54)

            for piezo_name, channel in awg_info.piezo_channels.items():
                awg_list.append(awg)
                channel_list.append(channel)

    # Extract the voltage profiles for the piezo actuators
    # -> These contain the amplitude, output load, DC offset, and signal (the frequency comes separately)

    v1_config, v2_config, v3_config, frequency = extract_awg_config_from_setup(
        profile, setup=setup
    )
    # We will configure all channels with the requested voltage profile (arbitrary waveform).  Have a look at #52 on
    # more information how this works.

    soft_start_dc_offset = []  # DC offset when the soft start begins
    final_dc_offset = []  # DC offset when the soft start ends (i.e. the actual DC offset of the waveform)

    for awg, channel, config in zip(
        awg_list, channel_list, (v1_config, v2_config, v3_config)
    ):
        soft_start_dc_offset.append(
            config.dc_offset - config.signal[0]
        )  # DC offset when the soft start begins
        final_dc_offset.append(
            config.dc_offset
        )  # DC offset when the soft start ends (i.e. the actual DC offset of the waveform)

        # Configure the current channel for the current wave generator, based on the current configuration information

        output_waveform_type = OutputWaveformType(f"ARB{channel}")

        awg.set_channel(channel)  # Select the channel (1/2)
        awg.set_waveform_shape(WaveformShape.ARB)  # Select "ARB" waveform
        awg.set_amplitude(config.amplitude)  # Amplitude [Vpp]
        awg.set_output_load(config.output_load)  # Output load
        awg.set_dc_offset(soft_start_dc_offset[-1])  # DC offset (soft start)
        awg.set_frequency(frequency)  # Frequency [Hz]
        awg.define_arb_waveform(output_waveform_type, config.name, Output.OFF)
        awg.load_arb1_ascii(
            config.get_signal_as_hex()
        ) if channel == 1 else awg.load_arb2_ascii(
            config.get_signal_as_hex()
        )  # Waveform shape
        time.sleep(2.5)
        awg.set_arb_waveform(output_waveform_type)

        # Set the output on, but wait for the external trigger signal to start generating waveforms

        awg.set_burst_trigger_source(TriggerSource.EXTERNAL)
        awg.set_burst(Burst.GATED)
        awg.set_output(Output.ON)

    # Soft start -> Linear increase in DC offset

    soft_start_setup = wave_generators_setup.piezo_tests.soft_start
    num_steps = soft_start_setup.num_steps
    delta_time = soft_start_setup.time / num_steps

    time.sleep(
        soft_start_setup.delay
    )  # Wait between enabling the channel output and the soft start

    soft_start_dc_offset_grid = [
        np.linspace(start, end, num_steps)
        for start, end in zip(soft_start_dc_offset, final_dc_offset)
    ]

    for dc_offset_list in zip(*soft_start_dc_offset_grid):
        for awg, channel, dc_offset in zip(awg_list, channel_list, dc_offset_list):
            awg.set_channel(channel)
            awg.set_dc_offset(dc_offset)

            time.sleep(delta_time / len(channel_list))

    # External trigger, coming from the Raspberry Pi -> Start waveform generation

    time.sleep(setup.gse.wave_generators.piezo_tests.trigger_delay)
    start_signal_trigger()


def extract_awg_config_from_setup(profile: str, setup: Setup = None):
    """Extracts the configuration of the wave generators from the setup.

    Args:
        profile (str): Voltage profile to be output on the awg.
        setup (Setup): Setup from which to extract the information from the wave generators.

    Returns:
        Three dictionaries with the waveform configuration for the three piezo actuators and the corresponding
        frequency [Hz].
    """

    setup = setup or load_setup()
    calibration = setup.gse.wave_generators.piezo_tests

    # noinspection PyUnresolvedReferences
    output_load = calibration.output_load
    # noinspection PyUnresolvedReferences
    profile = calibration.profiles[profile]
    frequency = profile["frequency"]

    v1_config = ArbConfig(
        name="V1_V",
        frequency=frequency,
        output_load=output_load,
        signal=profile["V1_V"],
    )
    v2_config = ArbConfig(
        name="V2_V",
        frequency=frequency,
        output_load=output_load,
        signal=profile["V2_V"],
    )
    v3_config = ArbConfig(
        name="V3_V",
        frequency=frequency,
        output_load=output_load,
        signal=profile["V3_V"],
    )

    return v1_config, v2_config, v3_config, frequency


@building_block
def sine_sweep(
    piezo: str,
    amplitude: float = 0.2,
    dc_offset: float = 0.15,
    start_frequency: float = 1.0,
    stop_frequency: float = 1500.0,
    sweep_time: float = 40.0,
    fixed_voltage: float = 0.15,
    strain_gauge: str = None,
    scan_rate: float = 7500.0,
    setup: Setup = None,
):
    """Performs a single sine sweep of the given piezo actuator, while keeping the others as a fixed voltage.

    Within the context of an observation, we perform the following steps:

        - Interrupt all logging from the LabJack, to ensure a clean logging of the requested strain gauge.
        - Configure + start logging of the requested strain gauge at the requested scan rate (all other configuration
          parameters are taken from the setup).
        - For the given piezo actuator, we configure (and switch on) a frequency sweep.  For the other piezo actuators,
          we configure a constant voltage.
        - Sleep for the requested duration of the sine sweep (we should only cover a single sine sweep).
        - Stop the wave generation.
        - Stop the logging of the requested strain gauge (disable + reset its parameters).

    Args:
        piezo: Name of the piezo actuator for which to configure a frequency sweep.
        amplitude (float): Amplitude for the frequency sweep [Vpp].
        dc_offset (float): DC offset for the frequency sweep [Vdc].
        start_frequency (float): Start frequency for the frequency sweep [Hz].
        stop_frequency (float): Stop frequency for the frequency sweep [Hz].
        sweep_time (float): Frequency sweep time [s].
        fixed_voltage (float): Fixed voltage for the other piezo actuators.
        strain_gauge (StrainGauge): Strain gauge to monitor.
        scan_rate (float): Scan rate for the monitored strain gauge [Hz].
        setup (Setup): Setup used for the setup phase of the wave generation.
    """

    setup = setup or load_setup()

    # Interrupt ongoing logging (this incl. resetting to defaults from the setup)
    # All channels should be disabled -> This may not be the default behaviour from the setup, so do this explicitly

    disable_sg_logging(setup=setup)
    disable_sg_channels(setup=setup)

    # Configure + enable the logging of the requested strain gauge

    enable_sg_logging(sg_name=strain_gauge, scan_rate=scan_rate, setup=setup)

    # Configure and initiate the sine sweep (keeps on going until the wave generation is stopped explicitly)

    start_sine_sweep(
        piezo=piezo,
        amplitude=amplitude,
        dc_offset=dc_offset,
        start_frequency=start_frequency,
        stop_frequency=stop_frequency,
        sweep_time=sweep_time,
        fixed_voltage=fixed_voltage,
        setup=setup,
    )

    # Let the sine sweep go on for the requested duration

    time.sleep(float(sweep_time))

    # Stop the wave generation + reset the wave generators

    stop_wave_generation_and_reset(setup=setup)

    # Disable the logging of the strain gauges
    # We don't explicitly disable the channels but settle for the default behaviour from the setup

    disable_sg_logging(setup=setup)


@building_block
def start_sine_sweep(
    piezo: str,
    amplitude: float,
    dc_offset: float,
    start_frequency: float,
    stop_frequency: float,
    sweep_time: float,
    fixed_voltage: float,
    setup: Setup = None,
) -> None:
    """Configures and starts sine sweeps of the given piezo actuator, while keeping the others as a fixed voltage.

    For the given piezo actuator, we configure (and switch on) a frequency sweep.  For the other piezo actuators, we
    configure a constant voltage.  The sine sweeps keep on going until the wave generation is stopped explicitly.

    Because we could not find a way to configure a triggered sweep with an external trigger signal (coming from a
    GPIO pin of a Raspberry Pi being set high), we first enable the channels with a constant voltage and then the
    sine sweep.

    Args:
        piezo (str): Name of the piezo actuator for which to configure a frequency sweep.
        amplitude (str): Amplitude for the frequency sweep [Vpp].
        dc_offset (str): DC offset for the frequency sweep [Vdc].
        start_frequency (float): Start frequency for the frequency sweep [Hz].
        stop_frequency (float): Stop frequency for the frequency sweep [Hz].
        sweep_time (float): Frequency sweep time [s].
        fixed_voltage (float): Fixed voltage for the other piezo actuators.
        setup (Setup): Setup.
    """

    setup = setup or load_setup()

    wave_generators_setup = setup.gse.wave_generators
    output_load = wave_generators_setup.piezo_tests.output_load

    sweep_awg = None
    sweep_channel = None

    # Loop over all wave generators

    for _, awg_info in wave_generators_setup.items():
        if "piezo_channels" in awg_info:  # Exclude the non-device blocks
            awg: Tgf4000Interface = awg_info.device
            awg.reconnect()  # Mitigate possible connection issues (#54)

            for piezo_name, channel in awg_info.piezo_channels.items():
                awg.set_channel(channel)

                if piezo_name == piezo:
                    sweep_awg: Tgf4000Interface = awg
                    sweep_channel = channel

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
                else:
                    # Configure the constant voltage

                    awg.set_waveform_shape(WaveformShape.ARB)
                    awg.set_arb_waveform(OutputWaveformType.DC)
                    awg.set_dc_offset(fixed_voltage)
                    awg.set_output_load(output_load)

                    awg.set_output(Output.ON)

                    # ARB DC cannot be selected when burst is enabled, and vice versa -> Error message -79

    sweep_awg.set_channel(sweep_channel)
    sweep_awg.set_output(Output.ON)


@building_block
def ramp(
    amplitude: float, period: float, piezo_list: list[str], setup: Setup = None
) -> None:
    """Ramps the voltage up and down for one piezo actuator after the other.

    Within the context of an observation, we perform the following steps:

        - Ramp the voltage up and down for one piezo after the other.  After that, the wave generation stops, but we
          still have to reset the settings of the wave generators.
        - Stop the wave generation and reset.

    Args:
        amplitude (float): Amplitude of the ramp [Vpp].
        period (float): Period of the ramp [s].
        piezo_list (list[str]): List of piezo actuator names.
    """

    setup = setup or load_setup()

    # Configure and initiate the voltage ramp (the wave generation stops automatically, but you will still have to
    # reset the wave generators)

    start_ramp(amplitude=amplitude, period=period, piezo_list=piezo_list, setup=setup)

    # Sleeping for the duration of each ramp has already been included in `start_ramp`
    # Stop the wave generation + reset the wave generators

    stop_wave_generation_and_reset(setup=setup)


@building_block
def start_ramp(
    amplitude: float, period: float, piezo_list: list[str], setup: Setup = None
) -> None:
    """Ramps the voltage up and down for one piezo actuator after the other.

    After that, the wave generation stops, but we still have to reset the settings of the wave generators.

    Args:
        amplitude (float): Amplitude of the ramp [Vpp].
        period (float): Period of the ramp [s].
        piezo_list (list[str]): List of piezo actuator names.
        setup (Setup): Setup.
    """

    setup = setup or load_setup()
    wave_generators_setup = setup.gse.wave_generators

    info = {}

    for _, awg_info in wave_generators_setup.items():
        if "piezo_channels" in awg_info:  # Exclude the non-device blocks
            awg: Tgf4000Interface = awg_info.device
            awg.reconnect()  # Mitigate possible connection issues (#54)

            for piezo_name, channel in awg_info.piezo_channels.items():
                info[piezo_name] = (awg, channel)

    for piezo in piezo_list:
        awg, channel = info[piezo]

        awg.set_channel(channel)
        awg.set_waveform_shape(WaveformShape.ARB)  # FIXME
        awg.set_amplitude(amplitude)
        awg.set_dc_offset(amplitude / 2.0)
        awg.set_output_load(
            wave_generators_setup.piezo_tests.output_load
        )  # Output load
        awg.set_period(period)  # Period [s]

        output_waveform_type = OutputWaveformType.TRIANGULAR
        awg.set_arb_waveform(output_waveform_type)

        awg.set_burst_trigger_source(TriggerSource.EXTERNAL)
        awg.set_burst(Burst.NCYC)
        awg.set_burst_count(1)
        awg.set_output(Output.ON)

        start_time = time.monotonic()

        start_signal_trigger()
        time.sleep(1)
        stop_signal_trigger()

        while (time.monotonic() - start_time) < period:
            time.sleep(0.5)

        awg.set_output(Output.OFF)


@building_block
def stop_wave_generation_and_reset(setup: Setup = None):
    """Switches off the wave generators.

    Args:
        setup (Setup): Setup from which to extract the information from the wave generators.
    """

    setup = setup or load_setup()
    wave_generators_setup = setup.gse.wave_generators

    # External trigger, coming from the Raspberry Pi -> Stop waveform generation

    stop_signal_trigger()
    time.sleep(setup.gse.wave_generators.piezo_tests.trigger_delay)

    awg1: Tgf4000Interface = wave_generators_setup.awg1.device
    awg1.reconnect()  # Mitigate possible connection issues (#54)
    awg2: Tgf4000Interface = wave_generators_setup.awg2.device
    awg2.reconnect()  # Mitigate possible connection issues (#54)

    for awg in (awg1, awg2):
        for channel in (1, 2):
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

        # Turn on LED indicator if configured

        led_gpio = TRIGGER_SETTINGS.get("LED_GPIO")
        if led_gpio is not None:
            pi.set_mode(led_gpio, pigpio.OUTPUT)
            pi.write(led_gpio, 1)
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

        # Turn off LED indicator if configured

        led_gpio = TRIGGER_SETTINGS.get("LED_GPIO")
        if led_gpio is not None:
            pi.set_mode(led_gpio, pigpio.OUTPUT)
            pi.write(led_gpio, 0)
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
        print("No settings found for the external trigger.  Please, check your local settings.")
        return

    if "HOSTNAME" not in TRIGGER_SETTINGS or "GPIO" not in TRIGGER_SETTINGS:
        print("Both the HOSTNAME and GPIO for the external trigger should be present in the settings file.")
        return

    hostname: str = TRIGGER_SETTINGS["HOSTNAME"]
    gpio: int = TRIGGER_SETTINGS["GPIO"]  # BCM numbering

    s = socket.socket()
    try:
        s.settimeout(3)
        s.connect((hostname, 8888))
        print("Port is reachable!")

        pi = pigpio.pi(hostname, 8888)
        if pi.connected:
            pi.set_mode(gpio, pigpio.OUTPUT)
            print(f"Output status of GPIO {gpio}: {pi.read(gpio)}")
            pi.stop()
    except Exception as e:
        print("Port not reachable:", e)
    finally:
        s.close()
