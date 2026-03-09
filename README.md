# cubespec-tvac-ts

Dependencies & scripts for the CubeSpec TVAC tests. Built on the [CGSE](https://github.com/IvS-KULeuven/cgse) framework.

## Prerequisites

- Python >= 3.11
- The [cubespec-tvac-conf](https://github.com/IvS-KULeuven/cubespec-tvac-conf) repository cloned alongside this one

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
