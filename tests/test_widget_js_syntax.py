"""The embeddable widget is a single IIFE. A missing function declaration
makes the whole file a SyntaxError, so the launcher never mounts and no
customer conversation can start — which looks like an empty dashboard.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
WIDGET = ROOT / "web" / "widget" / "widget.js"


def test_widget_js_parses_as_script() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to syntax-check web/widget/widget.js")
    result = subprocess.run(
        [node, "--check", str(WIDGET)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
