"""Smoke tests that open the real windows with demo agents (skipped if Tk can't start)."""
import time

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def root():
    tk = pytest.importorskip("tkinter")
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def pump(root, sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        root.update()
        time.sleep(0.02)


@pytest.fixture
def no_log(monkeypatch):
    errors = []
    import desk_window
    monkeypatch.setattr(desk_window, "log_error", lambda text, log=None: errors.append(text))
    return errors


def test_big_window_draws_every_scene_and_pins(root, no_log):
    import desk_window
    import scenes
    d = desk_window.DeskWindow(root, desk_window.DemoAgents(), next(iter(scenes.SCENES)), size=(300, 160),
                               pos=(50, 300))
    for key in scenes.SCENES:
        d.scene_key.set(key)
        d.set_scene()
        pump(root, 0.3)
        assert d.hits, f"{key}: nothing to click"
    d.pins.append(d.hits[0][4]["id"])
    d.mouse = ((d.hits[-1][0] + d.hits[-1][2]) / 2, (d.hits[-1][1] + d.hits[-1][3]) / 2)
    pump(root, 0.3)
    assert d.stack.win is not None and d.stack.win.state() != "withdrawn"
    assert no_log == []


def test_cards_survive_odd_names(root, no_log):
    import cards
    stack = cards.PinStack(root)
    agents = [{"id": str(i), "name": n, "state": s} for i, (n, s) in enumerate(
        [("   ", "working"), ("", "sleeping"), (None, "waiting"), ("x" * 500, "working"),
         ("[expr 1+1] $x {y} \\n", "weird-state")])]
    root.deiconify()
    stack.show(agents, "1", {}, lambda a: None)
    root.update()
    assert stack.win.state() != "withdrawn"
    stack.show([], None, {}, lambda a: None)
    assert stack.win.state() == "withdrawn"
