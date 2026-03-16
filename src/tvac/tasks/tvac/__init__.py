import os
from pathlib import Path

import sys
from executor import ExternalCommand

HERE = Path(__file__).parent.resolve()

UI_TAB_ORDER = ["heaters", "piezos"]


def tvac_ui():
    logo_path = HERE / "icons/dashboard.svg"

    cmd_log = os.environ.get("CUBESPEC_LOG_FILE_LOCATION")
    if cmd_log is None or not os.access(cmd_log, os.W_OK):
        cmd_log = str(Path("~").expanduser())

    cmd = ExternalCommand(
        f"gui-executor --verbose --module-path tvac.tasks.tvac.heaters "
        f"--module-path tvac.tasks.tvac.piezos "
        f"--kernel-name cubespec-tvac-ts --single "
        f"--logo {logo_path} --cmd-log {cmd_log} --app-name 'TVAC GUI' "
        f"{' '.join(sys.argv[1:])}",
        asynchronous=True,
    )
    cmd.start()
