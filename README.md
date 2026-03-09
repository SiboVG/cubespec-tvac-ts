# cubespec-tvac-ts

Dependencies & scripts for the CubeSpec TVAC tests. Built on the [CGSE](https://github.com/IvS-KULeuven/cgse) framework.

## Prerequisites

- Python >= 3.11
- The [cubespec-tvac-conf](https://github.com/IvS-KULeuven/cubespec-tvac-conf) repository cloned alongside this one

## Hardware Setup

For the Strain Gauge readout, the DAQ is the [LabJack T7](https://labjack.com/products/labjack-t7) is used. To access more I/O, 
a [CB37 Terminal Board](https://labjack.com/products/cb37-terminal-board) (breakout board) is required.
Finally, the strain gauges require a stable supply voltage. This is supplied by 
the [LJTick-VRef, 2.5 V](https://labjack.com/products/ljtick-vref).

The image below shows how the hardware should be set up. The CB37 fits on the D-SUB connector on the T7.
The LJTick-VRef is screw into any of the screw terminals with `GND` and `VS` as pin 3 and 4, respectively.
You should connect `GND` of the LJTick-VRef to `GND` of the SG, and `VS` to `Vcc` of the SG.

![LJ_wiring.png](img/LJ_wiring.png)

The `IN+` and `IN-` terminals of the SG should be connected to an `AIN`-pair. The SG signal is a
small differential voltage signal that sits on a relatively large common-mode voltage. This
common-mode voltage must first be subtracted, and the remaining signal must then be amplified and
digitized. To accurately do this, we want to use the instrumentation amplifier of the T7.
However, the instrumentation amplifier is internally only routed to AIN pairs: `AIN0-AIN1`, `AIN2-AIN3`, etc.
So, for example, you must attach `IN+` of SG1 to `AIN0` and `IN-` to `AIN1`. For SG2, connect `IN+` to `AIN2`
and `IN-` to `AIN3`, and for SG3 `IN+` -> `AIN4` and `IN-` to `AIN5`.

|      | IN+ connected to T7 pin | IN- connected to T7 pin |
|------|-------------------------|-------------------------|
| SG 1 | AIN0                    | AIN1                    |
| SG 2 | AIN2                    | AIN3                    |
| SG 3 | AIN4                    | AIN5                    |

To use true differential measurements, we must configure the negative channel reference on the T7.
For `AIN0`, you set the negative channel to `AIN1`. For `AIN1`, the negative channel is `GND`. By 
setting this negative channel reference, the T7 routes `AIN0` and `AIN1` to the internal instrumentation
amplifier. The resulting measurement on `AIN0` will be `AIN0 - AIN1`. For example, if you input
2.501 V on `AIN0` and 2.499 V on `AIN1`, then `AIN0` will output 2.501 - 2.499 = 0.002 V. `AIN1` will
output 2.499 V, since it is reference to `GND`.

## Environment setup

Set up a virtual environment and install the dependencies:

```bash
$ uv venv --python 3.11
$ uv sync
```

The CGSE framework requires a set of environment variables. Add these to a local `.env` file and 
load them to your terminal (`export $(cat .env | xargs)`):

```bash
export PROJECT=CUBESPEC
export SITE_ID=KUL

export CUBESPEC_LOCAL_SETTINGS=../cubespec-tvac-conf/data/KUL/conf/SETUP_KUL_00001_260206_105400.yaml 
export CUBESPEC_DATA_STORAGE_LOCATION=~/data/CUBESPEC/KUL
export CUBESPEC_CONF_DATA_LOCATION=../cubespec-tvac-conf/data/KUL/conf
export CUBESPEC_LOG_FILE_LOCATION=~/data/CUBESPEC/KUL/log
```

`CUBESPEC_CONF_DATA_LOCATION` must point to the directory containing the `SETUP_KUL_*.yaml` files in the conf repo.

Create the data and log directories:

```bash
mkdir -p ~/data/CUBESPEC/KUL/log
```

## Installation

```bash
uv sync          # or: pip install -e .
```

## Usage

### GUI

```bash
tvac_ui
```

### Interactive session

```bash
PYTHONSTARTUP=startup.py python
```

```python
from egse.setup import load_setup
setup = load_setup()       # loads the latest SETUP_KUL_*.yaml

from tvac.strain_gauge import start_sg_logging, stop_sg_logging
start_sg_logging(setup=setup)
# ... Ctrl+C or:
stop_sg_logging()
```
