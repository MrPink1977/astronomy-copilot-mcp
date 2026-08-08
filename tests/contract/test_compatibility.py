from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract
REPOSITORY_ROOT = Path(__file__).parents[2]
MANIFEST_PATH = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "compatibility" / "raw_server_manifest.json"
)


def normalized_sha256(path: Path) -> str:
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def decorated_tool_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                names.append(node.name)
    return names


def test_raw_compatibility_sources_match_published_baseline():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    actual = {
        filename: normalized_sha256(REPOSITORY_ROOT / filename) for filename in manifest["files"]
    }

    assert actual == manifest["files"]


def test_raw_mcp_retains_179_unique_tool_definitions():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["raw_mcp"]
    names = decorated_tool_names(REPOSITORY_ROOT / "nina_advanced_mcp.py")
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)

    assert len(names) == manifest["decorated_definitions"]
    assert len(set(names)) == manifest["unique_tool_names"]
    assert duplicates == manifest["duplicate_names"]


def test_curated_import_has_no_network_file_or_environment_side_effects(tmp_path):
    script = """
import os
import socket
import sys
from pathlib import Path

before_environment = dict(os.environ)
before_files = set(Path.cwd().iterdir())

def blocked_connection(*args, **kwargs):
    raise AssertionError("network access attempted during import")

class GuardedSocket(socket.socket):
    def connect(self, *args, **kwargs):
        return blocked_connection(*args, **kwargs)

socket.socket = GuardedSocket
socket.create_connection = blocked_connection

import astronomy_copilot.server

assert "nina_advanced_mcp" not in sys.modules
assert dict(os.environ) == before_environment
assert set(Path.cwd().iterdir()) == before_files
"""
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(REPOSITORY_ROOT), existing_pythonpath) if part
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
