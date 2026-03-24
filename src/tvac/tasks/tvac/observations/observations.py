from gui_executor.exec import exec_ui
from egse.observation import start_observation as _start_observation
from egse.observation import end_observation as _end_observation
from egse.observation import request_obsid

UI_MODULE_DISPLAY_NAME = "1 — Managing observations"


@exec_ui(display_name="Start observation")
def start_observation(description: str = "replace this default description"):
    """Starts a new observation with the given description.

    Args:
        - description: Description of the new observation (which will appear in the obsid table).
    """

    obsid = _start_observation(description=description)
    print(f"Observation started with obsid={obsid}")


@exec_ui(display_name="End observation")
def end_observation():
    """Ends the current observation and reports on the OBSID that was ended."""

    _end_observation()


@exec_ui(display_name="Get obsid", use_kernel=True, immediate_run=True)
def get_obsid():
    """Returns the current OBSID or None when no observation is running."""

    obsid = request_obsid()
    if obsid:
        print(f"Current obsid={obsid}")
    else:
        print("There is currently no observation is running.")

    return obsid
