from pathlib import Path

from gui_executor.exec import exec_ui

from tvac.wave_generation import check_trigger

UI_MODULE_DISPLAY_NAME = "5 - External trigger"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"


@exec_ui(display_name="Check trigger status", use_kernel=True)
def check_trigger_state() -> None:
    """Checks whether a connection can be established with the Raspberry Pi that is used as external trigger source.

    The required GPIO pin on the Raspberry Pi is connected to the TRIG/COUNT (DC) IN port (BNC centre) on the rear panel
    of the wave generators.  That way it can act as external trigger source, to make sure all waveforms are in sync.
    The wave generators must therefore be configured in gated burst with an external trigger source.  This means that
    waveforms will be generated as long as the GPIO is high.

    Raises:
        AttributeError: If no settings for external trigger are found.
    """

    check_trigger()
