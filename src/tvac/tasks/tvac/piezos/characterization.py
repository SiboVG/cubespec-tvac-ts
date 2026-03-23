from egse.observation import start_observation, end_observation
from egse.setup import load_setup
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback
from reactivex.operators import finally_action

from tvac.tasks.tvac.piezos import piezos
from tvac.tasks.tvac.piezos import (
    sine_sweep_amplitude,
    sine_sweep_dc_offset,
    sine_sweep_start_frequency,
    sine_sweep_stop_frequency,
    sine_sweep_time,
    sine_sweep_fixed_voltage,
)
from tvac.wave_generation import characterize_piezo

UI_MODULE_DISPLAY_NAME = "1 - Characterisation"


@exec_ui(display_name="Start characterisation", use_kernel=True)
def start_piezo_characterization(
    piezo: Callback(piezos, name="Piezo actuator to sweep") = None,
    amplitude: Callback(sine_sweep_amplitude, name="Amplitude for frequency sweep [Vpp]") = None,
    dc_offset: Callback(sine_sweep_dc_offset, name="DC offset for frequency sweep [Vdc]") = None,
    start_frequency: Callback(sine_sweep_start_frequency, name="Sweep start frequency [Hz]") = None,
    stop_frequency: Callback(sine_sweep_stop_frequency, name="Sweep stop frequency [Hz]") = None,
    sweep_time: Callback(sine_sweep_time, name="Sweep time [s]") = None,
    fixed_voltage: Callback(sine_sweep_fixed_voltage, name="Constant voltage (other piezos) [Vdc]") = None,
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

    try:
        start_observation(f"Characterisation of piezo actuator {piezo}")

        characterize_piezo(
            piezo=piezo,
            amplitude=amplitude,
            dc_offset=dc_offset,
            start_frequency=start_frequency,
            stop_frequency=stop_frequency,
            sweep_time=sweep_time,
            fixed_voltage=fixed_voltage,
            setup=load_setup(),
        )
    finally:
        end_observation()
