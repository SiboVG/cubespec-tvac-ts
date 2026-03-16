from pathlib import Path

import numpy as np
import scipy.io
from navdict.navdict import get_resource_location


def load_mat(resource_name: str, parent_location: Path | None = None) -> dict:
    """Loads a MatLab file into dictionary.

    Args:
        resource_name (str): Path to the resource, either relative or absolute.  If it starts with "mat//", this
                             prefix will be stripped off.
        parent_location (Path): Parent location to be used to complete the relative path of the resource.

    Returns:
        Dictionary with the content of the MatLab file.
    """

    if resource_name.startswith("mat//"):
        resource_name = resource_name[5:]

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

    return {
        "frequency": np.asarray(signal["f_Hz"][0, 0]).item(),
        "time": np.ravel(signal["t_vec_s"][0, 0]),
        "V1_V": np.ravel(signal["V1_V"][0, 0]),
        "V2_V": np.ravel(signal["V2_V"][0, 0]),
        "V3_V": np.ravel(signal["V3_V"][0, 0]),
    }
