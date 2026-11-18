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


def test_still_mode_draws_rarely_and_wakes_for_the_mouse(root, no_log, monkeypatch):
    import cast
    import desk_window
    if not cast.available():
        pytest.skip("no character pictures")
    monkeypatch.setattr(cast, "ANIMATE", False)
    demo = desk_window.DemoAgents()
    for a in demo.agents:
        a["state"], a["_next"] = "sleeping", 1e12  # nobody changes state during the test
    d = desk_window.DeskWindow(root, demo, "cast", size=(300, 160), pos=(50, 300))
    pump(root, 0.5)
    assert d.frame_ms() == 500
    before = d.c.find_all()
    pump(root, 1.2)
    assert d.c.find_all() == before  # nothing moved, so nothing was made again
    d.mouse = (10, 10)
    assert d.frame_ms() == desk_window.TICK_MS
    assert no_log == []


def test_cards_follow_a_new_screen_scale(root, no_log):
    import cards
    stack = cards.PinStack(root)
    agent = {"id": "a", "name": "A chat", "state": "working"}
    stack.show([agent], None, {}, lambda a: None)
    stack.set_scale(1.0)
    stack.show([agent], None, {}, lambda a: None)
    small = stack.win.winfo_reqheight(), stack.font.cget("size")
    stack.set_scale(2.5)
    stack.show([agent], None, {}, lambda a: None)
    assert stack.font.cget("size") == -int(9 * 2.5) and small[1] == -9
    assert no_log == []
