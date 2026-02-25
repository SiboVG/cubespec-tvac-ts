from pathlib import Path

from egse.observation import start_observation, end_observation
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback

from tvac.power_supply import config_psu, switch_off_psu, clear_psu_alarms
from tvac.tasks.tvac.heaters import heaters, dissipation_modes, heaters_incl_all

UI_MODULE_DISPLAY_NAME = "1 - Power supplies"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"


@exec_ui(display_name="Configuration & switch-on", use_kernel=True)
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

    if heater.startswith("H"):
        start_observation(f"Configure + switch on heater {heater}")

        try:
            config_psu(heater_name=heater, dissipation=dissipation)
        except Exception as e:
            print(f"Failed to configure + switch on heater {heater}: {e}")

    else:
        start_observation(f"Configure + switch on all heaters")

        for heater_name in heaters():
            try:
                config_psu(heater_name=heater_name, dissipation=dissipation)
            except Exception as e:
                print(f"Failed to configure + switch on heater {heater_name}: {e}")

    end_observation()


@exec_ui(display_name="Switch-off", use_kernel=True)
def switch_off_heater(heater: Callback(heaters_incl_all, name="Heater") = None) -> None:
    """Switches off the Power Supply Unit for the given heater.

    Args:
        heater: Name of the heater.
    """

    if heater.startswith("H"):
        start_observation(f"Switch off heater {heater}")

        try:
            switch_off_psu(heater_name=heater)
        except Exception as e:
            print(f"Failed to switch off heater {heater}: {e}")

    else:
        start_observation(f"Switch off all heaters")

        for heater_name in heaters():
            try:
                switch_off_psu(heater_name=heater_name)
            except Exception as e:
                print(f"Failed to switch off heater {heater_name}: {e}")

    end_observation()


@exec_ui(display_name="Clear alarms", use_kernel=True)
def clear_alarms(heater: Callback(heaters, name="Heater") = None):
    """Clears the alarms for the Power Supply Unit for the given heater.

    Args:
        heater: Name of the heater.
    """

    try:
        clear_psu_alarms(heater_name=heater)
    except Exception as e:
        print(f"Failed to clear alarms for heater {heater}: {e}")


@exec_ui(display_name="Reset", use_kernel=True)
def reset(heater: Callback(heaters, name="Heater") = None):
    """Resets the Power Supply Unit for the given heater.

    Args:
        heater: Name of the heater.
    """

    try:
        clear_psu_alarms(heater_name=heater)
    except Exception as e:
        print(f"Failed to reset Power Supply Unit for heater {heater}: {e}")
