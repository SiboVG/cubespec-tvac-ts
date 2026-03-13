from egse.observation import start_observation, end_observation
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback

from tvac.tasks.tvac.piezos import piezos
from tvac.wave_generation import characterize_piezo

UI_MODULE_DISPLAY_NAME = "1 - Characterisation"


@exec_ui(display_name="Start characterisation", use_kernel=True)
def start_piezo_characterization(
    piezo: Callback(piezos, name="Piezo actuator with frequency sweep") = None,
    amplitude: Callback(float, name="Amplitude for frequency sweep [Vpp]") = 5.0,
    dc_offset: Callback(float, name="DC offset for frequency sweep [Vdc]") = 0,
    start_frequency: Callback(float, name="Sweep start frequency [Hz]") = 1000,
    stop_frequency: Callback(float, name="Sweep stop frequency [Hz]") = 10000,
    sweep_time: Callback(float, name="Sweep time [s]") = 60,
    fixed_voltage: Callback(float, name="Constant voltage (other piezos) [Vdc]") = 0.0,
):
    """Charactersisation of the given piezo actuator.

    For the given piezo actuator, we configure (and switch on) a frequency sweep.  For the other piezo actuators, we
    configure a constant voltage.

    Args:
        piezo: Name of the piezo actuator for which to configure a frequency sweep.
        amplitude (str): Amplitude for the frequency sweep [Vpp].
        dc_offset (str): DC offset for the frequency sweep [Vdc].
        start_frequency (float): Start frequency for the frequency sweep [Hz].
        stop_frequency (float): Stop frequency for the frequency sweep [Hz].
        sweep_time (float): Frequency sweep time [s].
        fixed_voltage (float): Fixed voltage for the other piezo actuators.
    """

    start_observation(f"Characterisation of piezo actuator {piezo}")

    characterize_piezo(
        piezo,
        amplitude,
        dc_offset,
        start_frequency,
        stop_frequency,
        sweep_time,
        fixed_voltage,
    )

    end_observation()
