"""A same-path disk hash does not identify Python code already imported."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def test_loaded_module_can_differ_from_current_disk_at_same_path(tmp_path):
    module = tmp_path / "feature.py"
    module.write_text("VALUE = 'loaded-v1'\n", encoding="utf-8")
    child = (
        "import feature,hashlib,json,pathlib,sys\n"
        "print('ready',flush=True)\n"
        "sys.stdin.readline()\n"
        "path=pathlib.Path(feature.__file__)\n"
        "print(json.dumps({'loaded':feature.VALUE,'path':str(path),"
        "'disk_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}),flush=True)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", child], cwd=str(tmp_path),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        module.write_text("VALUE = 'disk-v2'\n", encoding="utf-8")
        disk_hash = hashlib.sha256(module.read_bytes()).hexdigest()
        process.stdin.write("\n")
        process.stdin.flush()
        observed = json.loads(process.stdout.readline())
        assert observed["path"] == str(module)
        assert observed["disk_sha256"] == disk_hash
        assert observed["loaded"] == "loaded-v1"
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
