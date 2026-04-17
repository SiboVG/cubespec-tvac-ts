from pathlib import Path

from egse.observation import start_observation, end_observation
from egse.setup import load_setup
from gui_executor.exec import exec_ui

from tvac import wave_generation

UI_MODULE_DISPLAY_NAME = "3 - Stop wave generation + reset"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"


@exec_ui(display_name="Stop wave generation + reset", use_kernel=True)
def stop_wave_generation_and_reset() -> None:
    """Stops the wave generation and resets the wave generators."""

    start_observation("Stop wave generation + reset wave generators")

    try:
        wave_generation.stop_wave_generation_and_reset(setup=load_setup())
    except Exception as e:
        print(f"Failed to stop wave generation and reset wave generators: {e}")

    end_observation()
