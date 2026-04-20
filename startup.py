"""
This is the startup file for the CubeSpec TVAC Tests using the CGSE .

The purpose is to start an interactive Python session with all required imports automatically loaded.

Make sure the PYTHONSTARTUP environment variable is defined in your terminal environment or the
variable is defined and loaded in the Console preferences in PyCharm.
"""

import logging
import sys

from rich import pretty, print

pretty.install()

print()
print("[blue]CubeSpec TVAC Scripts and CGSE Software.[/blue]")
print("Loading default and required modules..")

import numpy as np
from egse.setup import list_setups, load_setup, submit_setup

from egse.observation import start_observation, end_observation, execute
from tvac import heaters, power_supply, wave_generation

print("Loading Setup...", flush=True)
setup = load_setup()
if setup is not None:
    print(f" Setup ID {setup.get_id()} loaded.", flush=True)
else:
    print("[red] No setup loaded, check error messages.[/red]", flush=True)
