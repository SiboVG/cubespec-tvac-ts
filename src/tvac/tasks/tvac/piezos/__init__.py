from typing import List

from egse.setup import load_setup, Setup
from tvac.runtime_config import is_amplifier_excluded

UI_TAB_DISPLAY_NAME = "Piezo Actuators"


def profiles() -> List[str]:
    """Name of the voltage profiles for the piezo actuators."""

    setup = load_setup()

    return [
        profile
        for profile in setup.gse.wave_generators.piezo_tests.profiles.keys()
        if profile != "labjack_logging"
    ]


def piezos() -> List[str]:
    """Names of the piezo actuators.  Each of them has a dedicated channel in a dedicated wave generator."""

    piezo_list = []

    setup = load_setup()

    for _, awg in setup.gse.wave_generators.items():
        if "piezo_channels" in awg:  # Exclude the piezo_tests block
            for piezo_name in awg.piezo_channels:
                piezo_list.append(piezo_name)

    return piezo_list


def piezos_incl_all() -> List[str]:
    """Names of the piezo actuators.  Each of them has a dedicated channel in a dedicated wave generator."""

    piezo_list = ["All piezos"]

    setup = load_setup()

    for _, awg in setup.gse.wave_generators.items():
        if "piezo_channels" in awg:  # Exclude the calibration block
            for piezo_name in awg.piezo_channels:
                piezo_list.append(piezo_name)

    return piezo_list


def _sine_sweep_param(param: str, setup: Setup | None = None) -> float:
    """Get a sine sweep parameter value from the setup.

    Args:
        param (str): Parameter name.
        setup (Setup | None): Setup.

    Returns:
        Parameter value.
    """

    setup = setup or load_setup()
    return float(getattr(setup.gse.wave_generators.piezo_tests.sine_sweep, param))


def sine_sweep_amplitude() -> float:
    setup = load_setup()

    if is_amplifier_excluded():
        amplification = setup.gse.wave_generators.piezo_tests.amplification
        return amplification * _sine_sweep_param("amplitude", setup=setup)
    else:
        return _sine_sweep_param("amplitude", setup=setup)


def sine_sweep_dc_offset() -> float:
    setup = load_setup()

    if is_amplifier_excluded():
        amplification = setup.gse.wave_generators.piezo_tests.amplification
        return amplification * _sine_sweep_param("dc_offset", setup)
    else:
        return _sine_sweep_param("dc_offset", setup=setup)


def sine_sweep_start_frequency() -> float:
    return _sine_sweep_param("start_frequency")


def sine_sweep_stop_frequency() -> float:
    return _sine_sweep_param("stop_frequency")


def sine_sweep_time() -> float:
    return _sine_sweep_param("sweep_time")


def sine_sweep_fixed_voltage() -> float:
    setup = load_setup()

    if is_amplifier_excluded():
        amplification = setup.gse.wave_generators.piezo_tests.amplification
        return amplification * _sine_sweep_param("fixed_voltage", setup=setup)
    else:
        return _sine_sweep_param("fixed_voltage", setup=setup)


def _sine_sweep_labjack_logging_param(param: str) -> float:
    """Get a sine sweep parameter LabJack logging value from the setup."""
    setup = load_setup()
    return float(
        getattr(setup.gse.wave_generators.piezo_tests.sine_sweep.labjack_logging, param)
    )


def sine_sweep_sg_pos_voltage_range() -> float:
    _sine_sweep_labjack_logging_param("voltage_range")


def sine_sweep_sg_neg_voltage_range() -> float:
    return _sine_sweep_param("neg_voltage_range")


def sine_sweep_sg_resolution_index() -> float:
    return int(_sine_sweep_labjack_logging_param("resolution_index"))


def sine_sweep_sg_scan_rate() -> float:
    return _sine_sweep_labjack_logging_param("scan_rate")


def _ramp_param(param: str) -> float:
    """Get a ramp parameter value from the setup.

    Args:
        param (str): Parameter name.

    Returns:
        Parameter value.
    """

    setup = load_setup()
    return float(getattr(setup.gse.wave_generators.piezo_tests.ramp, param))


def ramp_amplitude() -> float:
    if is_amplifier_excluded():
        # We normally wanted 10 V here, but the AWG cannot output this unless the
        # output load is set to OPEN instead of 50 Ohm.
        return 5.0
    return _ramp_param("amplitude")


def ramp_period() -> float:
    return _ramp_param("period")


def _plateau_param(param: str, setup: Setup | None = None) -> float:
    """Get a plateau parameter value from the setup.

    Args:
        param (str): Parameter name.
        setup (Setup | None): Setup.

    Returns:
        Parameter value.
    """

    setup = setup or load_setup()
    return float(getattr(setup.gse.wave_generators.piezo_tests.plateau, param))


def plateau_voltage() -> float:
    setup = load_setup()

    if is_amplifier_excluded():
        amplification = setup.gse.wave_generators.piezo_tests.amplification
        return amplification * _plateau_param("voltage", setup=setup)
    else:
        return _plateau_param("voltage", setup=setup)


def plateau_duration() -> float:
    return _plateau_param("duration")


def plateau_edge_duration() -> float:
    return _plateau_param("edges")
