from pathlib import Path

from egse.observation import start_observation, end_observation
from egse.setup import load_setup
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback

from tvac.tasks.tvac.piezos import profiles
from tvac.wave_generation import load_voltage_profile

UI_MODULE_DISPLAY_NAME = "2 - Profiles"
HERE = Path(__file__).parent.parent.resolve()
ICON_PATH = HERE / "icons/"


@exec_ui(display_name="Load profile", use_kernel=True)
def load_profile(
    profile: Callback(profiles, name="Voltage profile") = None,
) -> None:
    """Configures and switches on the Wave Generators for the given voltage profile.

    Args:
        profile: Voltage profile.
    """

    start_observation("Configure + switch on wave generators, using profile {profile}")

    try:
        load_voltage_profile(profile=profile, setup=load_setup())
    except Exception as e:
        print(
            f"Failed to configure + switch on wave generators, using profile {profile}: {e}"
        )

    end_observation()


@exec_ui(display_name="Plot profile", use_kernel=True)
def plot_profile(profile: Callback(profiles, name="Voltage profile") = None,) -> None:
    """Plots the given voltage profile.

    Args:
        profile: Voltage profile.
    """

    import matplotlib.pyplot as plt

    setup = load_setup()
    voltage_profiles = setup.gse.wave_generators.piezo_tests.profiles[profile]

    plt.plot(voltage_profiles["time"], voltage_profiles["V1_V"], label="V1_V")
    plt.plot(voltage_profiles["time"], voltage_profiles["V2_V"], label="V2_V")
    plt.plot(voltage_profiles["time"], voltage_profiles["V3_V"], label="V3_V")

    plt.suptitle(f"Voltage profile {profile}")
    plt.title("(before amplification)")

    plt.xlabel("Time [s]")
    plt.ylabel("Voltage [V]")

    plt.legend()

    plt.show()
