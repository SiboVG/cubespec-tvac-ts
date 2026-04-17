from typing import List

from egse.setup import load_setup

UI_TAB_DISPLAY_NAME = "Piezo Actuators"


def profiles() -> List[str]:
    """Name of the voltage profiles for the piezo actuators."""

    setup = load_setup()

    return list(setup.gse.wave_generators.piezo_tests.profiles.keys())


def piezos() -> List[str]:
    """Names of the piezo actuators.  Each of them has a dedicated channel in a dedicated wave generator."""

    piezo_list = []

    setup = load_setup()

    for _, awg in setup.gse.wave_generators.items():
        if "piezo_channels" in awg:  # Exclude the piezo_tests block
            for piezo_name in awg.piezo_channels:
                piezo_list.append(piezo_name)

    return piezo_list


def _sine_sweep_param(param: str) -> float:
    """Get a sine sweep parameter value from the Setup configuration."""
    setup = load_setup()
    return float(getattr(setup.gse.wave_generators.piezo_tests.sine_sweep, param))


def sine_sweep_amplitude() -> float:
    return _sine_sweep_param("amplitude")


def sine_sweep_dc_offset() -> float:
    return _sine_sweep_param("dc_offset")


def sine_sweep_start_frequency() -> float:
    return _sine_sweep_param("start_frequency")


def sine_sweep_stop_frequency() -> float:
    return _sine_sweep_param("stop_frequency")


def sine_sweep_time() -> float:
    return _sine_sweep_param("sweep_time")


def sine_sweep_fixed_voltage() -> float:
    return _sine_sweep_param("fixed_voltage")


def sine_sweep_sg_scan_rate() -> float:
    return 7500


def piezos_incl_all() -> List[str]:
    """Names of the piezo actuators.  Each of them has a dedicated channel in a dedicated wave generator."""

    piezo_list = ["All piezos"]

    setup = load_setup()

    for _, awg in setup.gse.wave_generators.items():
        if "piezo_channels" in awg:  # Exclude the calibration block
            for piezo_name in awg.piezo_channels:
                piezo_list.append(piezo_name)

    return piezo_list
