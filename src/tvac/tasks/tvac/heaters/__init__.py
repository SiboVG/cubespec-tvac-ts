from typing import List

from egse.setup import load_setup

UI_TAB_DISPLAY_NAME = "Heaters"


def heaters() -> List[str]:
    """Names of the heaters.  Each of them has a dedicated Power Supply Unit."""

    heater_list = []

    setup = load_setup()

    for _, psu in setup.gse.power_supply.items():
        heater_list.append(psu.heater.name)

    return heater_list


def heaters_incl_all() -> List[str]:
    """Names of the heaters.  Each of them has a dedicated Power Supply Unit."""

    heater_list = ["All heaters"]

    setup = load_setup()

    for _, psu in setup.gse.power_supply.items():
        heater_list.append(psu.heater.name)

    return heater_list


def dissipation_modes() -> List[str]:
    """Heat dissipation modes of the heaters."""

    return ["HOT case (science observations)", "COLD case (safe dissipation)"]
