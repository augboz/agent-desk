"""Finding sessions: status words, labels, live sessions, recent closed chats."""
import json
import os
from collections import OrderedDict

import pytest

import detect
import progress


@pytest.mark.parametrize("raw,state", [
    ("busy", "working"), ("Running", "working"), ("idle", "sleeping"), (None, "sleeping"),
    ("waiting_for_permission", "waiting"), ("needs input", "waiting"), (5, "sleeping"),
])
def test_map_status(raw, state):
    assert detect.map_status(raw) == state


@pytest.mark.parametrize("cwd,label", [
    (r"C:\code\my-app", "my-app"),
    (r"C:\code\my-app\\", "my-app"),
    (r"C:\tmp\scratch-1a2b3c", "scratch"),
    (r"C:\code\shop\.claude-worktrees\feature-x", "shop (wt)"),
    ("", "?"), (None, "?"), (["not", "a", "path"], "?"),
])
def test_project_label(cwd, label):
    assert detect.project_label(cwd) == label


@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    sessions, projects = tmp_path / "sessions", tmp_path / "projects"
    sessions.mkdir()
    projects.mkdir()
    monkeypatch.setattr(detect, "SESSIONS_DIR", str(sessions))
    monkeypatch.setattr(detect, "PROJECTS_DIR", str(projects))
    monkeypatch.setattr(progress, "PROJECTS_DIR", str(projects))
    monkeypatch.setattr(progress, "_trackers", OrderedDict())
    monkeypatch.setattr(detect, "_recent", {"at": 0, "files": []})
    return sessions, projects


def chat(projects, sid, text, ts, title=None, proj="C--code-app"):
    d = projects / proj
    d.mkdir(exist_ok=True)
    lines = [{"type": "user", "timestamp": ts, "message": {"content": text}}]
    if title:
        lines.append({"type": "custom-title", "customTitle": title, "sessionId": sid})
    (d / f"{sid}.jsonl").write_text("".join(json.dumps(x, separators=(",", ":")) + "\n" for x in lines))


def test_live_session_found(claude_home):
    sessions, projects = claude_home
    me = os.getpid()
    (sessions / f"{me}.json").write_text(json.dumps(
        {"pid": me, "sessionId": "live1", "status": "busy", "cwd": r"C:\code\app", "startedAt": 1}))
    chat(projects, "live1", "hi", "2026-01-01T10:00:00Z", title="Live chat")
    agents = detect.scan()
    live = [a for a in agents if a["id"] == "live1"]
    assert live and live[0]["state"] == "working" and live[0]["last_msg"]


def test_dead_or_broken_session_files_are_skipped(claude_home):
    sessions, _ = claude_home
    (sessions / "1.json").write_text("{broken")
    (sessions / "2.json").write_text("[1, 2]")
    (sessions / "3.json").write_text(json.dumps({"pid": "abc", "sessionId": "x"}))
    (sessions / "4.json").write_text(json.dumps({"pid": 2 ** 31 - 2, "sessionId": "dead"}))
    assert [a for a in detect.scan() if not a.get("closed")] == []


def test_recent_closed_newest_first_and_skips_scheduled(claude_home):
    _, projects = claude_home
    chat(projects, "old", "hi", "2026-01-01T08:00:00Z", title="Old")
    chat(projects, "new", "hi", "2026-01-01T09:00:00Z", title="New")
    chat(projects, "sched", "<scheduled-task x>run</scheduled-task>", "2026-01-01T10:00:00Z")
    got = detect.recent_closed(set())
    assert [a["name"] for a in got] == ["New", "Old"]
    assert all(a["state"] == "sleeping" and a["closed"] for a in got)
    assert [a["id"] for a in detect.recent_closed({"new"})] == ["old"]


def test_pid_alive():
    assert detect.pid_alive(os.getpid())
    assert not detect.pid_alive(2 ** 31 - 2)


def test_a_chat_with_two_processes_shows_once(claude_home):
    sessions, projects = claude_home
    for pid, status in ((os.getpid(), "idle"), (os.getppid(), "busy")):
        (sessions / f"{pid}.json").write_text(json.dumps(
            {"pid": pid, "sessionId": "twice", "status": status, "cwd": r"C:\code\app", "startedAt": 1}))
    chat(projects, "twice", "hi", "2026-01-01T10:00:00Z", title="Two windows")
    found = [a for a in detect.scan() if a["id"] == "twice"]
    assert len(found) == 1
    assert found[0]["state"] == "working"  # the busier one wins
