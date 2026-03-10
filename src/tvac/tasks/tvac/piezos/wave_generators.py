from pathlib import Path

from egse.observation import start_observation, end_observation
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback

from tvac.tasks.tvac.piezos import profiles
from tvac.wave_generators import config_awg

UI_MODULE_DISPLAY_NAME = "1 - Wave generators"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"

@exec_ui(display_name="Test", use_kernel=True)
def print_test():
    print("Test")

# @exec_ui(display_name="Configuration & switch-on", use_kernel=True)
# def switch_on_piezos(profile: Callback(profiles, name="Voltage profile") = None
# ) -> None:
#     """Configures and switches on the Wave Generators for the given voltage profile.
#
#     Args:
#         profile: Voltage profile.
#     """
#
#     start_observation("Configure + switch on wave generators, using profile {profile}")
#
#     try:
#         config_awg(profile=profile)
#     except Exception as e:
#         print(f"Failed to configure + switch on wave generators, using profile {profile}: {e}")
#
#     end_observation()
#
#
# @exec_ui(display_name="Switch-off", use_kernel=True)
# def switch_off_piezos(
# ) -> None:
#     """Switches off the Wave Generators."""
#
#     pass


