from typing import List

from egse.setup import load_setup

UI_TAB_DISPLAY_NAME = "Piezo actuators"


def profiles() -> List[str]:
    """Name of the voltage profiles for the piezo actuators."""

    setup = load_setup()

    return list(setup.gse.wave_generators.calibration.profiles.keys())


def piezos() -> List[str]:
    """Names of the piezo actuators.  Each of them has a dedicated channel in a dedicated wave generator."""

    piezo_list = []

    setup = load_setup()

    for _, awg in setup.gse.wave_generators.items():
        if "piezo_channels" in awg:  # Exclude the calibration block
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
