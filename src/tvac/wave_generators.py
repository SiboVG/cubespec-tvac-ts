import scipy.io
import time

import numpy as np
from egse.arbitrary_wave_generator.aim_tti import (
    WaveformShape,
    OutputWaveformType,
    Output,
)
from egse.arbitrary_wave_generator.aim_tti.tgf4000 import Tgf4000Interface
from egse.observation import building_block
from egse.setup import load_setup, Setup
from navdict.navdict import NavDict


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
def config_awg(profile: str, setup: Setup = None) -> None:
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

    for awg, channel, config, func in zip(
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
        awg.set_output(Output.ON)  # Switch on


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
def switch_off_awg(setup: Setup = None):
    """Switches off the wave generators.

    Args:
        setup (Setup): Setup from which to extract the information from the wave generators.
    """

    setup = setup or load_setup()

    awg1: Tgf4000Interface = setup.gse.wave_generators.awg1.device
    awg1.set_channel(1)
    awg1.set_output(Output.OFF)
    awg1.set_channel(2)
    awg1.set_output(Output.OFF)

    awg2: Tgf4000Interface = setup.gse.wave_generators.awg2.device
    awg2.set_channel(1)
    awg2.set_output(Output.OFF)


# def get_arb_waves(piezo_setup: dict, factor: float):
#                 # (filename: str = '/Users/sara/Downloads/SIGN_1_LG.mat', profile: str = None):
#     """Returns the frequency and time series for all piezo actuators.
#
#     In the given dictionary, the MatLab file with the voltage time series and corresponding frequency for the piezo
#     actuators has been loaded.  The format of this dictionary is a bit inconvenient, so we fix that in this method.
#
#     The voltages that are sent out by the wave generators will go through an amplifier before they are passed on to the
#     piezo actuators. This amplification has already been included in the voltage time series.  By multiplying with the
#     given factor, we undo this amplification (and hence we get the signal strength that we need for the wave
#     generators).
#
#     Args:
#          piezo_setup (dict): Dictionary in which the MatLab file with the voltage time series and corresponding
#                              frequency has been loaded.
#          factor (float):
#     """
#
#     # mat = scipy.io.loadmat(filename)
#     # profile = profile or str.split(filename, "/")[-1][:-4]
#
#     signal_key = next(key for key in piezo_setup if not key.startswith("__"))  # Select only non-dunder keyword
#
#     signal = piezo_setup[signal_key]
#
#     return {
#         "frequency": np.asarray(signal['f_Hz'][0, 0]).item(),
#         "time": np.ravel(signal['t_vec_s'][0, 0]),
#         "V1_V": np.ravel(signal['V1_V'][0, 0]) * factor,
#         "V2_V": np.ravel(signal['V2_V'][0, 0]) * factor,
#         "V3_V": np.ravel(signal['V3_V'][0, 0]) * factor,
#     }
