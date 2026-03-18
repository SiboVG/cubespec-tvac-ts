from pathlib import Path

from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback

from tvac.power_supply import clear_psu_alarms
from tvac.tasks.tvac.heaters import heaters

UI_MODULE_DISPLAY_NAME = "3 - Error recovery"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"


@exec_ui(display_name="Clear alarms", use_kernel=True)
def clear_alarms(heater: Callback(heaters, name="Heater") = None):
    """Clears the alarms for the Power Supply Unit for the given heater.

    Args:
        heater: Name of the heater.
    """

    try:
        clear_psu_alarms(heater_name=heater, setup=load_setup())
    except Exception as e:
        print(f"Failed to clear alarms for heater {heater}: {e}")


@exec_ui(display_name="Reset", use_kernel=True)
def reset(heater: Callback(heaters, name="Heater") = None):
    """Resets the Power Supply Unit for the given heater.

    Args:
        heater: Name of the heater.
    """

    try:
        clear_psu_alarms(heater_name=heater, setup=load_setup())
    except Exception as e:
        print(f"Failed to reset Power Supply Unit for heater {heater}: {e}")
