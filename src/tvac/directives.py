from pathlib import Path

import numpy as np
import scipy.io
from navdict.navdict import get_resource_location


def load_piezo_voltage_profile(
    resource_name: str, parent_location: Path | None = None
) -> dict:
    """Loads the voltage profiles for the piezo actuators from the given file.

    Note that the frequency in the MatLab file refers to how fast we go from one point to the next one in the time
    series, rather than the rate at which to repeat the voltage profile as a whole.  The latter is the frequency that
    we use in the returned dictionary.

    Args:
        resource_name (str): Path to the resource, either relative or absolute.  If it starts with "piezo//", this
                             prefix will be stripped off.
        parent_location (Path): Parent location to be used to complete the relative path of the resource.

    Returns:
        Dictionary with the content of the MatLab file.
    """

    if resource_name.startswith("piezo//"):
        resource_name = resource_name[7:]

    if not resource_name:
        raise ValueError(
            f"Resource name should not be empty, but contain a valid filename."
        )

    parts = resource_name.rsplit("/", 1)
    [in_dir, fn] = parts if len(parts) > 1 else [None, parts[0]]

    mat_location = get_resource_location(parent_location, in_dir)

    piezo_setup = scipy.io.loadmat(mat_location / fn)

    signal_key = next(
        key for key in piezo_setup if not key.startswith("__")
    )  # Select only non-dunder keyword

    signal = piezo_setup[signal_key]

    intra_point_frequency = np.asarray(signal["f_Hz"][0, 0]).item()  # [Hz]
    num_points = len(np.ravel(signal["t_vec_s"][0, 0]))

    return {
        "frequency": intra_point_frequency / num_points,
        "time": np.ravel(signal["t_vec_s"][0, 0]),
        "V1_V": np.ravel(signal["V1_V"][0, 0]),
        "V2_V": np.ravel(signal["V2_V"][0, 0]),
        "V3_V": np.ravel(signal["V3_V"][0, 0]),
    }
