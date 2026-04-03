import logging
import multiprocessing
import sys
from pathlib import Path

import click
import git
import invoke
import rich
from egse.log import egse_logger

multiprocessing.current_process().name = "update_tvac"

from egse.system import chdir

THIS_FILE_LOCATION = Path(__file__).parent
ROOT_PROJECT_FOLDER = THIS_FILE_LOCATION / "../.."

# Make sure the logging messages are also send to the log_cs

EGSE_LOGGER = egse_logger
MODULE_LOGGER = logging.getLogger("tvac.scripts")


class DirtyRepoError(Exception):
    pass


class GitCommandError(Exception):
    pass


def check_and_report_dirty_repo():
    repo = git.Repo(Path.cwd())

    if repo.is_dirty(untracked_files=False):
        rich.print("You have uncommitted changes, unable to install test scripts.")

        for item in repo.index.diff(None):
            rich.print(f"  [red]Modified: {item.a_path}")

        rich.print("Stash or submit your changes to GitHub.")

        raise DirtyRepoError()


def run_shell_command(cmd: str, hide: bool = True, warn: bool = True, msg: str = None):
    if msg is None:
        rich.print(f"Executing '{cmd}'...", end="", flush=True)
    else:
        rich.print(f"{msg}...", end="", flush=True)

    response = invoke.run(cmd, hide=hide, warn=warn)

    if response.return_code:
        rich.print("[red]FAILED[/red]")
        if response.stdout:
            rich.print(f"{response.stdout}")
        rich.print(f"[red]{response.stderr}[/]")
        raise GitCommandError()
    else:
        rich.print("[green]succeeded[/green]")

    return response


@click.group()
def cli():
    pass


@cli.command()
@click.option("--tag", help="The Release number to install.")
def ops(tag=None):
    """
    Update the test scripts on the operational machine. An operational installation is different
    from a developer installation. The installation shall be done for a particular release for the test house
    and that release will be checked out in a branch that will be your active installation..
    """
    with chdir(ROOT_PROJECT_FOLDER):
        rich.print("Updating cubespec-tvac-ts operational environment.")

        try:
            run_shell_command("git fetch updates")
            run_shell_command("git checkout main")

            check_and_report_dirty_repo()
        except (GitCommandError, DirtyRepoError):
            return

        if tag:
            try:
                run_shell_command(f"git checkout tags/{tag} -b {tag}-branch")
                run_shell_command(
                    f"{sys.executable} -m pip install -e .",
                    msg="Installing dependencies",
                )
            except GitCommandError:
                return
        else:
            # git rev-list --tags --timestamp --no-walk | sort -nr | head -n1 | cut -f 2 -d ' ' | xargs git describe --contains
            rich.print("Usage: update_tvac ops --tag=<tag name>")
            rc = invoke.run("git describe --tags --abbrev=0", hide="stdout")
            rich.print(f"The latest tag name is '{rc.stdout.strip()}'.")
            return


if __name__ == "__main__":
    sys.exit(cli())
