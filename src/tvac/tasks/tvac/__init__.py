import os
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()

UI_TAB_ORDER = ["heaters", "strain_gauges"]


def _wait_for_ready(self, timeout: float = 60.0):
    return self._client.wait_for_ready(timeout=timeout)


def _resolve_cmd_log_dir() -> str:
    cmd_log = os.environ.get("CUBESPEC_LOG_FILE_LOCATION")
    if cmd_log is None or not os.access(cmd_log, os.W_OK):
        cmd_log = str(Path("~").expanduser())
    return cmd_log


def tvac_ui():
    import gui_executor.client as client

    from gui_executor.__main__ import main as gui_executor_main

    client.MyClient.wait_for_ready = _wait_for_ready  # type: ignore[assignment]

    sys.argv = [
        sys.argv[0],
        "--verbose",
        "--module-path",
        "tvac.tasks.tvac.heaters",
        "--module-path",
        "tvac.tasks.tvac.strain_gauges",
        "--logo",
        str(HERE / "icons/dashboard.svg"),
        "--cmd-log",
        _resolve_cmd_log_dir(),
        "--app-name",
        "TVAC GUI",
        *sys.argv[1:],
    ]
    return gui_executor_main()
