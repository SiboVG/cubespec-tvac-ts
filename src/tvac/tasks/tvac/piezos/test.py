from egse.observation import start_observation, end_observation
from egse.setup import load_setup
from gui_executor.exec import exec_ui
from gui_executor.utypes import Callback, DropdownList
from itertools import chain

from tvac import wave_generation
from tvac.tasks.tvac.piezos import (
    piezos,
    sine_sweep_sg_scan_rate,
    ramp_amplitude,
    ramp_period,
)
from tvac.tasks.tvac.piezos import (
    sine_sweep_amplitude,
    sine_sweep_dc_offset,
    sine_sweep_start_frequency,
    sine_sweep_stop_frequency,
    sine_sweep_time,
    sine_sweep_fixed_voltage,
)
from tvac.tasks.tvac.strain_gauges import strain_gauges

UI_MODULE_DISPLAY_NAME = "1 - Test"


# noinspection PyTypeHints
@exec_ui(display_name="Sine sweep", use_kernel=True)
def sine_sweep(
    piezo: Callback(piezos, name="Piezo actuator to sweep") = None,
    amplitude: Callback(
        sine_sweep_amplitude, name="Amplitude for frequency sweep [Vpp]"
    ) = None,
    dc_offset: Callback(
        sine_sweep_dc_offset, name="DC offset for frequency sweep [Vdc]"
    ) = None,
    start_frequency: Callback(
        sine_sweep_start_frequency, name="Sweep start frequency [Hz]"
    ) = None,
    stop_frequency: Callback(
        sine_sweep_stop_frequency, name="Sweep stop frequency [Hz]"
    ) = None,
    sweep_time: Callback(sine_sweep_time, name="Sweep time [s]") = None,
    fixed_voltage: Callback(
        sine_sweep_fixed_voltage, name="Constant voltage (other piezos) [Vdc]"
    ) = None,
    strain_gauge: Callback(strain_gauges, name="Strain gauge to monitor") = None,
    scan_rate: Callback(
        sine_sweep_sg_scan_rate, name="Scan rate for strain gauge [Hz]"
    ) = None,
):
    """Performs a single sine sweep of the given piezo actuator, while keeping the others at a fixed voltage.

    Within the context of an observation, we perform the following steps:

        - Interrupt all logging from the LabJack, to ensure a clean logging of the requested strain gauge.
        - Configure + start logging of the requested strain gauge at the requested scan rate (all other configuration
          parameters are taken from the setup).
        - For the given piezo actuator, we configure (and switch on) a frequency sweep.  For the other piezo actuators,
          we configure a constant voltage.
        - Sleep for the requested duration of the sine sweep (we should only cover a single sine sweep).
        - Stop the wave generation and reset.
        - Stop the logging of the requested strain gauge (disable + reset its parameters).

    Args:
        piezo: Name of the piezo actuator for which to configure a frequency sweep.
        amplitude (float): Amplitude for the frequency sweep [Vpp].
        dc_offset (float): DC offset for the frequency sweep [Vdc].
        start_frequency (float): Start frequency for the frequency sweep [Hz].
        stop_frequency (float): Stop frequency for the frequency sweep [Hz].
        sweep_time (float): Frequency sweep time [s].
        fixed_voltage (float): Fixed voltage for the other piezo actuators.
        strain_gauge (StrainGauge): Strain gauge to monitor.
        scan_rate (float): Scan rate for the monitored strain gauge [Hz].
    """

    start_observation(
        f"Sine sweep for piezo actuator {piezo}, while logging strain gauge {strain_gauge}"
    )

    try:
        wave_generation.sine_sweep(
            piezo=piezo,
            amplitude=float(amplitude),
            dc_offset=float(dc_offset),
            start_frequency=float(start_frequency),
            stop_frequency=float(stop_frequency),
            sweep_time=float(sweep_time),
            fixed_voltage=float(fixed_voltage),
            strain_gauge=strain_gauge,
            scan_rate=float(scan_rate),
            setup=load_setup(),
        )
    except Exception as e:
        print(f"Failed to execute sine sweep for piezo actuator {piezo}: {e}")

    end_observation()


# noinspection PyTypeHints
@exec_ui(display_name="Ramp", use_kernel=True)
def ramp(
    amplitude: Callback(ramp_amplitude, name="Ramp amplitude [Vpp]") = None,
    period: Callback(ramp_period, name="Ramp period [s]") = None,
    piezo_list: DropdownList(
        piezos(), name="Pick a piezo actuator", defaults=piezos()
    ) = None,
) -> None:
    """Ramps the voltage up and down for one piezo actuator after the other.

    Within the context of an observation, we perform the following steps:

        - Ramp the voltage up and down for one piezo after the other.  After that, the wave generation stops, but we
          still have to reset the settings of the wave generators.
        - Stop the wave generation and reset.

    Args:
        amplitude (float): Amplitude of the ramp [Vpp].
        period (float): Period of the ramp [s].
        piezo_list (list[str]): List of piezo actuator names.
    """

    start_observation(
        f"Subsequent voltage ramps (up and down) for piezo actuators {piezo_list}"
    )

    try:
        wave_generation.ramp(
            amplitude=amplitude,
            period=period,
            piezo_list=list(chain.from_iterable(piezo_list)),
            setup=load_setup(),
        )
    except Exception as e:
        print(
            f"Failed to ramp voltages up and down for piezo actuators {piezo_list}: {e}"
        )

    end_observation()


# class PiezoList(ListList):
#     def __init__(
#         self,
#         literals: List[str | Callable],
#         defaults: List = None,
#         name: str = None,
#     ):
#         super().__init__(literals, defaults, name)
#
#     def get_widget(self):
#         return PiezoListWidget(self)
#
#
# class PiezoListWidget(QWidget):
#     # class ListListWidget(UQWidget):
#     def __init__(self, type_object: ListList):
#         super().__init__()
#
#         self._type_object = type_object
#         self._rows: List[List] = []
#         self._rows_layout = QVBoxLayout()
#
#         row, fields = self._row("+", expand_default=True)
#
#         self._rows_layout.addWidget(row)
#         self._rows_layout.setContentsMargins(0, 0, 0, 0)
#
#         self._rows.append(fields)
#
#         self.setLayout(self._rows_layout)
#
#     def get_value(self) -> List[List]:
#         return [
#             [self._cast_arg(f, t) for f, (t, d) in zip(field, self._type_object)]
#             for field in self._rows
#         ]
#
#     def _row(self, row_button: str, expand_default: bool = False):
#         widget = QWidget()
#
#         hbox = QHBoxLayout()
#
#         fields = []
#         for x, y in self._type_object:
#             drop_down_menu = combo_box_from_list(piezos())
#             drop_down_menu.setCurrentIndex(0)
#             field = drop_down_menu
#
#             fields.append(field)
#             type_hint = QLabel(x if isinstance(x, str) else x.__name__)
#             type_hint.setStyleSheet("color: gray")
#             hbox.addWidget(field)
#             hbox.addWidget(type_hint)
#
#         if row_button == "+":
#             button = IconLabel(icon_path=HERE / "icons/add.svg")
#             button.mousePressEvent = partial(self._add_row, "x")
#         elif row_button == "x":
#             button = IconLabel(icon_path=HERE / "icons/delete.svg")
#             button.mousePressEvent = partial(self._delete_row, widget, fields)
#         else:
#             raise ValueError(f"Unknown row_button '{row_button}', use '+' or 'x'")
#
#         hbox.addWidget(button)
#         hbox.setContentsMargins(0, 0, 0, 0)
#         widget.setLayout(hbox)
#
#         return widget, fields
#
#     def _add_row(self, button_type: str, *args):
#         row, fields = self._row(button_type)
#         self._rows_layout.addWidget(row)
#         self._rows.append(fields)
#
#     def _delete_row(self, widget: QWidget, fields: List, *args):
#         self._rows_layout.removeWidget(widget)
#         self._rows.remove(fields)
