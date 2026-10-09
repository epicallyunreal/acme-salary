"""The boot runs `seed_data --if-empty` under `set -eu` (entrypoint.sh), so a command that fails to
import stops the container. In-process tests import the apps in their own order and can hide an
import cycle, so each command is loaded here in a fresh process, as the boot loads it."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("command", ["seed_data", "reset_demo", "make_import_file"])
def test_the_command_loads_in_a_fresh_process(command):
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "acme_salary.settings.test"}
    done = subprocess.run(
        [sys.executable, "manage.py", "help", command],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert done.returncode == 0, done.stderr[-2000:]
