import math

from egse.command import InvalidArgumentsError
from egse.observation import building_block
from egse.power_supply.kikusui.pmx import IntSwitch
from egse.power_supply.kikusui.pmx_a.pmx_a import PmxAInterface
from egse.setup import Setup, load_setup


@building_block
def config_psu(heater_name: str, dissipation: str, setup: Setup = None):
    """Configures the Power Supply Unit for the given heater and switches the output on.

    Args:
        heater_name (str): Name of the heater.
        dissipation (str): If this is set to "hot", we use the HOT case (science observation dissipation).  If this is
                           set to "cold", we use the cold case (safe mode dissipation).
        setup (Setup): Setup from which to extract the information from the heater (resistance, dissipation,
                       maximum dissipation) and the corresponding Power Supply Unit.
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

    resistance = psu_setup.heater.resistance  # R [Ohm]
    power = 0  # P [W]
    try:
        if "HOT" in dissipation:
            power = psu_setup.heater.power.hot
        elif "COLD" in dissipation:
            power = psu_setup.heater.power.cold
    except AttributeError:
        raise AttributeError(
            f"Requested heat dissipation mode for heater {heater_name} not found in the setup"
        )
    max_power = psu_setup.heater.max_power  # P_max [W]

    # Combine:
    #   - Ohm's law: V = I * R
    #   - Power equation: P = V * I = I^2 * R = v^2 / R
    # -> Extract V & I
    #
    # For the OVP & OCP: use same equation but with P_max instead of P

    voltage = math.sqrt(power * resistance)  # [V]
    psu_device.set_voltage(voltage)

    ovp = math.sqrt(max_power * resistance)  # [V]
    psu_device.set_ovp(ovp)

    current = math.sqrt(power / resistance)  # [Ohm]
    psu_device.set_current(current)

    ocp = math.sqrt(max_power / resistance)  # [Ohm]
    psu_device.set_ocp(ocp)

    print(f"Power supply to {heater_name} heater ({resistance}Ω):")
    print(f"Heat dissipation mode: {dissipation}")
    print(f"Voltage: {voltage}V - OVP: {ovp}V")
    print(f"Current: {current}A - OCP: {ocp}A")
    print(f"-> Dissipating {voltage * current}W")

    psu_device.set_output_status(IntSwitch.ON)


@building_block
def switch_off_psu(heater_name: str, setup: Setup = None) -> None:
    """Switches off the output the Power Supply Unit for the given heater.

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

    psu_device.set_output_status(IntSwitch.OFF)


@building_block
def clear_psu_alarms(heater_name: str, setup: Setup = None) -> None:
    """Clears the alarms for the Power Supply Unit for the given heater.

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

    psu_device.clear_alarms()


@building_block
def reset_psu(heater_name: str, setup: Setup = None) -> None:
    """Resets the Power Supply Unit for the given heater.

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

    psu_device.reset()
