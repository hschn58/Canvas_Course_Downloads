import subprocess
import sys


def test_help_flag():
    result = subprocess.run(
        [sys.executable, "-m", "canvas_course_downloads", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "canvas-download" in result.stdout
    assert "--url" in result.stdout
    assert "--output" in result.stdout


def test_missing_url_exits_with_error():
    result = subprocess.run(
        [sys.executable, "-m", "canvas_course_downloads"],
        capture_output=True,
        text=True,
        env={"PATH": "", "HOME": "/tmp"},
    )
    assert result.returncode != 0
    assert "Canvas URL is required" in result.stderr
