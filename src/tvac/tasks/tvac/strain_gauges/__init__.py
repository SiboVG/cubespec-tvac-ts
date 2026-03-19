from typing import List

from egse.setup import load_setup

UI_TAB_DISPLAY_NAME = "Strain Gauges"


def strain_gauges() -> List[str]:
    """Name of the strain gauges."""

    setup = load_setup()

    return list(setup.gse.labjack_t7.channels.keys())
