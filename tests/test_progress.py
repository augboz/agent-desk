"""The transcript reader: titles, your last message, task-list progress."""
import json
from collections import OrderedDict

import pytest

import progress


def line(**d):
    return json.dumps(d, separators=(",", ":")) + "\n"  # compact, like Claude Code writes


def user(text, ts="2026-01-01T10:00:00Z", **extra):
    return line(type="user", timestamp=ts, message={"role": "user", "content": text}, **extra)


def tool(name, inp, tid):
    return line(type="assistant", message={"content": [{"type": "tool_use", "id": tid, "name": name,
                                                        "input": inp}]})


@pytest.fixture
def transcript(tmp_path):
    path = tmp_path / "abc123.jsonl"
    path.write_text("")

    def write(*lines):
        with open(path, "a", encoding="utf-8") as f:
            f.write("".join(lines))
        return path
    return write


def track(path):
    tr = progress._Tracker(str(path))
    tr.update()
    return tr


def test_titles_prefer_your_own(transcript):
    p = transcript(line(type="ai-title", aiTitle="Claude's name", sessionId="abc123"))
    tr = track(p)
    assert tr.name() == "Claude's name"
    transcript(line(type="custom-title", customTitle="My name", sessionId="abc123"))
    tr.update()
    assert tr.name() == "My name"


def test_title_from_another_chat_is_ignored(transcript):
    tr = track(transcript(line(type="custom-title", customTitle="Other", sessionId="zzz")))
    assert tr.name() is None


def test_last_human_skips_scheduled_prompts(transcript):
    p = transcript(user("hello", ts="2026-01-01T10:00:00Z"),
                   user("<scheduled-task name='x'>run</scheduled-task>", ts="2026-01-01T11:00:00Z"))
    tr = track(p)
    assert tr.scheduled
    assert tr.last_human == pytest.approx(1767261600.0)  # 10:00, not the scheduled 11:00
    assert tr.turn_start == pytest.approx(1767265200.0)  # but the turn did start at 11:00


def test_tool_results_are_not_prompts(transcript):
    p = transcript(line(type="user", timestamp="2026-01-01T10:00:00Z",
                        message={"content": [{"type": "tool_result", "content": "x"},
                                             {"type": "text", "text": "x"}]}))
    assert track(p).last_human is None


def test_plan_progress(transcript):
    items = [{"content": c, "status": s} for c, s in (("a", "in_progress"), ("b", "pending"),
                                                       ("c", "pending"), ("d", "pending"))]
    p = transcript(user("go"), tool("mcp__ccd_turn__update_plan", {"items": items}, "t1"))
    tr = track(p)
    assert tr.progress() == pytest.approx(0.1)
    transcript(tool("mcp__ccd_turn__update_plan", {"advance": True}, "t2"))
    tr.update()
    assert tr.items == ["completed", "in_progress", "pending", "pending"]
    transcript(tool("mcp__ccd_turn__update_plan", {"done": [2, 3], "start": 4}, "t3"))
    tr.update()
    assert tr.items == ["completed", "completed", "completed", "in_progress"]
    transcript(tool("mcp__ccd_turn__wrap_up", {"recap": "x"}, "t4"))
    tr.update()
    assert tr.progress() == 1.0
    transcript(user("next"))  # a new prompt clears the list
    tr.update()
    assert tr.progress() is None


def test_todowrite(transcript):
    p = transcript(user("go"), tool("TodoWrite", {"todos": [{"status": "completed"},
                                                            {"status": "pending"}]}, "t1"))
    assert track(p).progress() == 0.5


def test_partial_line_is_finished_next_time(transcript):
    whole = line(type="custom-title", customTitle="Split", sessionId="abc123")
    p = transcript(whole[:20])
    tr = track(p)
    assert tr.name() is None
    transcript(whole[20:])
    tr.update()
    assert tr.name() == "Split"


def test_file_replaced_starts_over(transcript):
    p = transcript(line(type="custom-title", customTitle="Old title that is long", sessionId="abc123"))
    tr = track(p)
    p.write_text(line(type="custom-title", customTitle="New", sessionId="abc123")[:-1] + "\n")
    tr.update()
    assert tr.name() == "New"


@pytest.mark.parametrize("bad", [
    "[1, 2, 3]\n",
    '"just a string"\n',
    '{"type":"user","message":["not","a","dict"]}\n',
    '{"type":"user","timestamp":5,"message":{"content":"hi"}}\n',
    '{"type":"assistant","message":{"content":[{"type":"tool_use","name":7,"input":"x"}]}}\n',
    '{"type":"assistant","message":{"content":[{"type":"tool_use","id":[1], '
    '"name": "mcp__ccd_turn__update_plan", "input": {"items": ["x", 3]}}]}}\n',
    '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"q", '
    '"name": "mcp__ccd_turn__update_plan", "input": {"done": ["a", null], "start": "2"}}]}}\n',
    '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"r", '
    '"name": "TodoWrite", "input": {"todos": "nope"}}]}}\n',
    '{"type":"custom-title","customTitle":["x"],"sessionId":"abc123"}\n',
    "{not json at all\n",
    "\x00\xff garbage\n",
])
def test_malformed_lines_never_crash(transcript, bad):
    p = transcript(user("go"), bad, user("after", ts="2026-01-01T12:00:00Z"))
    tr = track(p)  # must not raise
    assert tr.last_human == pytest.approx(1767268800.0)
    assert tr.name() is None or isinstance(tr.name(), str)


def test_big_file_only_reads_the_tail(transcript, monkeypatch):
    monkeypatch.setattr(progress, "FIRST_READ", 200)
    filler = line(type="progress", data="x" * 100) * 50
    p = transcript(line(type="ai-title", aiTitle="Early", sessionId="abc123"), filler, user("late"))
    tr = track(p)
    assert tr.name() == "Early"  # found by the one-off title scan
    assert tr.last_human is not None


def test_tracker_cache_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(progress, "_trackers", OrderedDict())
    for i in range(progress.MAX_TRACKERS + 20):
        f = tmp_path / f"s{i}.jsonl"
        f.write_text(user("x"))
        progress.tracker(f"s{i}", str(f))
    assert len(progress._trackers) <= progress.MAX_TRACKERS
