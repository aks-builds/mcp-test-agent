import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_run_demo_passes_end_to_end():
    result = subprocess.run(
        [sys.executable, "run_demo.py", "--headless", "--fast", "--no-wait", "--no-dashboard"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STEP 8/8" in result.stdout
    assert '[FAIL] Click on #add-task-btn failed' in result.stdout
    assert "[HEAL]" in result.stdout
    assert "NASH-101 PASSED: 5/5 checks, 1 self-heal" in result.stdout
