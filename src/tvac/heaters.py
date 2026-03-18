from egse.command import InvalidArgumentsError
from egse.power_supply.kikusui.pmx_a.pmx_a import PmxAInterface
from egse.setup import Setup, load_setup


def print_heater_settings(heater_name: str, setup: Setup = None) -> None:
    """Prints the current settings for the given heater.

    Args:
        heater_name (str): Name of the heater.
        setup (Setup): Setup from which to extract the information from the heater and the corresponding Power Supply
                       Unit.
    """

    setup = setup or load_setup()

    power_supply_block = setup.gse.power_supply

    psu_setup = None
    for psu in power_supply_block:
        if power_supply_block[psu].heater.name == heater_name:
            psu_setup = power_supply_block[psu]
            break
    if not psu_setup:
        raise InvalidArgumentsError(f"No heater {heater_name} found in the setup")

    psu_device: PmxAInterface = psu_setup.device

    if not psu_device.get_output_status():
        print(f"Power supply to {heater_name} heater off -> No heat dissipation")

    else:
        resistance = psu_setup.heater.resistance  # R [Ohm]

        voltage = psu_device.get_voltage()  # [V]
        voltage_config = psu_device.get_voltage_config()  # [V]
        ovp = psu_device.get_ovp()  # [V]

        current = psu_device.get_current()  # [A]
        current_config = psu_device.get_current_config()  # [A]
        ocp = psu_device.get_ocp()  # [A]

        print(f"Power supply to {heater_name} heater ({resistance}Ω):")
        print(f"Voltage: {voltage}V - configured: {voltage_config}V - OVP: {ovp}V")
        print(f"Current: {current}A - configured: {current_config}A - OCP: {ocp}A")
        print(f"-> Dissipating {voltage * current}W")
