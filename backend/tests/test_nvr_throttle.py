import sys
from pathlib import Path

AI = Path(__file__).resolve().parents[2] / "ai"
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))

from urbansense_ai.run_camera import due_for_post


def test_due_for_post_first_tick():
    assert due_for_post(None, 10.0, 2.5) is True


def test_due_for_post_inside_interval():
    assert due_for_post(10.0, 11.0, 2.5) is False


def test_due_for_post_after_interval():
    assert due_for_post(10.0, 12.5, 2.5) is True


def test_due_for_post_zero_interval():
    assert due_for_post(10.0, 10.1, 0) is True
