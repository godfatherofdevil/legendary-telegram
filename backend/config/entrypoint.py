import os
import shlex
import signal
import subprocess
import sys
from collections.abc import Sequence
from types import FrameType

child_process: subprocess.Popen[bytes] | None = None


def _forward_signal(signum: int, _frame: FrameType | None) -> None:
    if child_process is None or child_process.poll() is not None:
        raise SystemExit(128 + signum)

    child_process.send_signal(signum)


def _register_signal_handlers() -> None:
    for name in ("SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _forward_signal)


def _run_command(command: Sequence[str]) -> int:
    global child_process

    child_process = subprocess.Popen(command)
    try:
        return child_process.wait()
    finally:
        child_process = None


def _get_command(env_name: str, default: Sequence[str]) -> list[str]:
    override = os.environ.get(env_name)
    if not override:
        return list(default)

    return shlex.split(override)


def main() -> None:
    _register_signal_handlers()

    startup_exit_code = _run_command(
        _get_command("BACKEND_STARTUP_COMMAND", [sys.executable, "-m", "config.startup"])
    )
    if startup_exit_code != 0:
        raise SystemExit(startup_exit_code)

    server_exit_code = _run_command(
        _get_command(
            "BACKEND_SERVER_COMMAND",
            ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"],
        )
    )
    raise SystemExit(server_exit_code)


if __name__ == "__main__":
    main()
