from pathlib import Path

from egse.setup import load_setup
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback

from tvac.heaters import print_heater_settings
from tvac.tasks.tvac.heaters import heaters

UI_MODULE_DISPLAY_NAME = "2 - Settings"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"


@exec_ui(display_name="Heater settings", use_kernel=True)
def get_heater_settings(heater: Callback(heaters, name="Heater") = None) -> None:
    """Prints the settings for the given heater.

    Args:
        heater (Callback | None): Name of the heater.
    """

    print_heater_settings(heater_name=heater, setup=load_setup())
