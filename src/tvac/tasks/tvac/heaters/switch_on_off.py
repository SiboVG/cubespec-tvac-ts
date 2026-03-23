from pathlib import Path
from typing import final

from egse.observation import start_observation, end_observation
from egse.setup import load_setup
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback

from tvac.power_supply import switch_off_psu, config_psu
from tvac.tasks.tvac.heaters import heaters_incl_all, heaters, dissipation_modes

UI_MODULE_DISPLAY_NAME = "1 - Switch-on && Switch-off"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"


@exec_ui(display_name="Switch-on", use_kernel=True)
def switch_on_heater(
    heater: Callback(heaters_incl_all, name="Heater") = None,
    dissipation: Callback(dissipation_modes, name="Heat dissipation") = None,
) -> None:
    """Configures and switches on the Power Supply Unit for the given heater in the given heat dissipation mode.

    Args:
        heater: Name of the heater.
        dissipation: Heat dissipation mode.  The corresponding resistance, power, and maximum power are read from the
                     setup.
    """

    try:
        setup = load_setup()

        if heater.startswith("H"):
            start_observation(f"Configure + switch on heater {heater}")

            try:
                config_psu(heater_name=heater, dissipation=dissipation, setup=setup)
            except Exception as e:
                print(f"Failed to configure + switch on heater {heater}: {e}")

        else:
            start_observation(f"Configure + switch on all heaters")

            for heater_name in heaters():
                try:
                    config_psu(
                        heater_name=heater_name, dissipation=dissipation, setup=setup
                    )
                except Exception as e:
                    print(f"Failed to configure + switch on heater {heater_name}: {e}")
    finally:
        end_observation()


@exec_ui(display_name="Switch-off", use_kernel=True)
def switch_off_heater(heater: Callback(heaters_incl_all, name="Heater") = None) -> None:
    """Switches off the Power Supply Unit for the given heater.

    Args:
        heater: Name of the heater.
    """

    try:
        setup = load_setup()

        if heater.startswith("H"):
            start_observation(f"Switch off heater {heater}")

            try:
                switch_off_psu(heater_name=heater, setup=setup)
            except Exception as e:
                print(f"Failed to switch off heater {heater}: {e}")

        else:
            start_observation(f"Switch off all heaters")

            for heater_name in heaters():
                try:
                    switch_off_psu(heater_name=heater_name, setup=setup)
                except Exception as e:
                    print(f"Failed to switch off heater {heater_name}: {e}")
    finally:
        end_observation()
