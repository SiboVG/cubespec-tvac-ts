from pathlib import Path

from egse.observation import start_observation, end_observation
from egse.setup import load_setup
from gui_executor.exec import exec_ui

from tvac.wave_generation import switch_off_awg

UI_MODULE_DISPLAY_NAME = "3 - Switch-off"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"


@exec_ui(display_name="Switch-off", use_kernel=True)
def switch_off_piezos() -> None:
    """Switches off the Wave Generators."""

    try:
        start_observation("Switch off wave generation for piezo actuators")

        try:
            switch_off_awg(setup=load_setup())
        except Exception as e:
            print(f"Failed to switch off wave generation for piezo actuators: {e}")
    finally:
        end_observation()
