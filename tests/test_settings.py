"""Settings and the error log: bad files never stop the app, nothing is lost."""
import json
from pathlib import Path

import pytest

import agent_desk
import desk_window

GOOD = {"version": 3, "x": 10, "y": 20, "w": 260, "h": 140, "names": False, "topmost": True,
        "strip": True, "scene": "cast", "strip_style": "cast", "chars": {"Chat": "hero"},
        "fish": {"Chat": "clown"}, "strip_spot": {"x": 398, "w": 473}, "strip_x": 150}


def test_good_config_round_trips(tmp_path):
    p = str(tmp_path / "config.json")
    agent_desk.save_config(GOOD, p)
    assert agent_desk.load_config(p) == GOOD
    assert not (tmp_path / "config.json.tmp").exists()


@pytest.mark.parametrize("text", [
    "", "{", "null", "[]", '"x"', "5", '{"version": 2, "x": 1}',
    '{"version": 3, "x": "5", "y": null, "w": "260", "h": [1], "chars": [1], '
    '"strip_spot": {"x": 1}, "names": "yes", "scene": 7}',
    '{"version": 3, "w": 1e308, "h": -5, "x": NaN, "fish": {"a": 1, "b": "ok"}}',
])
def test_bad_config_is_cleaned_not_fatal(tmp_path, text):
    p = tmp_path / "config.json"
    p.write_text(text)
    cfg = agent_desk.load_config(str(p))
    assert isinstance(cfg, dict)
    for key in ("x", "y", "w", "h"):
        assert key not in cfg or isinstance(cfg[key], int)
    assert 120 <= cfg.get("w", 260) <= 4000 and 70 <= cfg.get("h", 140) <= 3000
    assert all(isinstance(v, str) for v in cfg.get("fish", {}).values())
    json.dumps(cfg)  # and it can be saved again


def test_missing_config(tmp_path):
    assert agent_desk.load_config(str(tmp_path / "nope.json")) == {}


def test_log_is_deduplicated_and_rotated(tmp_path, monkeypatch):
    monkeypatch.setattr(desk_window, "_last_errors", {})
    log = str(tmp_path / "agent_desk.log")
    for _ in range(50):
        desk_window.log_error("same error", log)
    assert Path(log).read_text(encoding="utf-8").count("same error") == 1
    with open(log, "a", encoding="utf-8") as f:
        f.write("x" * 210_000)
    desk_window.log_error("another error", log)
    assert (tmp_path / "agent_desk.log.1").exists()
    assert "another error" in Path(log).read_text(encoding="utf-8")
