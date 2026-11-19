"""Read-only detection of running Claude Code sessions and their subagents.

Sources (nothing is written, no hooks needed):
  ~/.claude/sessions/<pid>.json         one per live Claude Code process; has
                                        "status" (busy/idle), "name", "cwd".
  ~/.claude/projects/*/<sessionId>/subagents/agent-*.jsonl
                                        subagent transcripts; the last line
                                        says whether the subagent finished.

A session file can outlive its process (crash, kill), so each pid is checked
against the process creation time recorded in "procStart".
"""
import ctypes
import glob
import json
import os
import time
from ctypes import wintypes

import progress as _progress

CLAUDE_DIR = os.path.join(os.path.expanduser("~"), ".claude")
SESSIONS_DIR = os.path.join(CLAUDE_DIR, "sessions")
PROJECTS_DIR = os.path.join(CLAUDE_DIR, "projects")

SUB_ACTIVE_SECS = 90     # subagent transcript untouched this long -> stalled
SUB_DONE_LINGER = 45     # show a finished subagent napping this long, then hide

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_QUERY_LIMITED = 0x1000
_STILL_ACTIVE = 259


def pid_alive(pid, proc_start=None):
    """True if pid runs and (when known) was created at proc_start (FILETIME)."""
    h = _k32.OpenProcess(_QUERY_LIMITED, False, int(pid))
    if not h:
        return ctypes.get_last_error() == 5  # access denied: exists, not ours
    try:
        code = wintypes.DWORD()
        if _k32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value != _STILL_ACTIVE:
            return False
        if proc_start:
            c, e, k, u = (wintypes.FILETIME() for _ in range(4))
            if _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
                created = (c.dwHighDateTime << 32) | c.dwLowDateTime
                # pid reused by another process -> creation times differ
                if abs(created - int(proc_start)) > 10_000_000:  # 1 s
                    return False
        return True
    finally:
        _k32.CloseHandle(h)


MAX_SESSION_FILE = 1_000_000  # a session file is a few hundred bytes; ignore anything huge


def _read_json(path):
    """A JSON object from a small file, or None (missing, too big, broken, not an object)."""
    try:
        if os.path.getsize(path) > MAX_SESSION_FILE:
            return None
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _s(v, default=""):
    return v if isinstance(v, str) else default


def _last_json_line(path, chunk=65536):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - chunk))
            data = f.read()
    except OSError:
        return None, b""
    for line in reversed(data.splitlines()):
        line = line.strip()
        if line.startswith(b"{"):
            try:
                return json.loads(line), data
            except ValueError:
                continue
    return None, data


def map_status(raw):
    s = _s(raw).lower()
    if s in ("busy", "running", "working", "thinking"):
        return "working"
    if any(w in s for w in ("wait", "permission", "input", "blocked", "ask")):
        return "waiting"
    return "sleeping"


def project_label(cwd):
    cwd = _s(cwd)
    base = os.path.basename((cwd or "").rstrip("\\/")) or "?"
    # desktop app scratch workspaces have long random names
    if base.startswith("scratch-"):
        return "scratch"
    if ".claude-worktrees" in (cwd or "") or "\\worktrees\\" in (cwd or ""):
        parts = cwd.replace("/", "\\").split("\\")
        for i, p in enumerate(parts):
            if p in (".claude-worktrees", "worktrees") and i > 0:
                return parts[i - 1] + " (wt)"
    return base


_subdir_cache = {}  # session id -> (subagents folder or None, when looked)
SUBDIR_RECHECK = 30  # seconds before looking again for a session that had no subagents


def _subagent_dir(session_id):
    hit = _subdir_cache.get(session_id)
    now = time.monotonic()
    if hit:
        d, at = hit
        if d and os.path.isdir(d):
            return d
        if d is None and now - at < SUBDIR_RECHECK:
            return None
    hits = glob.glob(os.path.join(PROJECTS_DIR, "*", glob.escape(session_id), "subagents"))
    d = hits[0] if hits else None
    if len(_subdir_cache) > 500:
        _subdir_cache.clear()
    _subdir_cache[session_id] = (d, now)
    return d


def _subagents(session_id, started_ms, now):
    out = []
    d = _subagent_dir(session_id)
    if not d:
        return out
    for path in glob.glob(os.path.join(d, "agent-*.jsonl")):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime * 1000 < started_ms or now - mtime > max(SUB_ACTIVE_SECS, SUB_DONE_LINGER) + 30:
            continue
        meta = _read_json(path[:-6] + ".meta.json") or {}
        last, tail = _last_json_line(path)
        msg = (last or {}).get("message") or {}
        finished = bool(
            meta.get("finished")
            or (last or {}).get("toolEndsTurn")
            or ((last or {}).get("type") == "assistant" and msg.get("stop_reason") == "end_turn"))
        age = now - mtime
        if finished:
            if age > SUB_DONE_LINGER:
                continue
            state = "sleeping"
        elif age <= SUB_ACTIVE_SECS:
            state = "working"
        else:
            continue
        kind = meta.get("description") or meta.get("agentType") or (last or {}).get("attributionAgent")
        if not kind:
            i = tail.rfind(b'"attributionAgent":"')
            if i >= 0:
                j = tail.find(b'"', i + 20)
                kind = tail[i + 20:j].decode("utf-8", "replace")
        agent_id = os.path.basename(path)[6:-6]
        out.append({
            "id": session_id + ":" + agent_id,
            "name": kind or "subagent",
            "project": "subagent",
            "state": state,
            "sub": True,
            "seed": agent_id,
        })
    out.sort(key=lambda a: a["id"])
    return out


def _SAFE_ID(sid):
    """Session ids are used in file paths: letters, digits, '-' and '_' only."""
    return 0 < len(sid) <= 100 and all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in sid)


RECENT_EVERY = 10  # seconds between looks at the transcript folder
_recent = {"at": 0, "files": []}


def _recent_files():
    """Chat transcripts, newest first (re-listed every RECENT_EVERY seconds)."""
    now = time.time()
    if now - _recent["at"] > RECENT_EVERY:
        files = []
        try:  # os.scandir: Windows hands out file times with the listing, no extra calls
            projects = [e.path for e in os.scandir(_progress.PROJECTS_DIR) if e.is_dir()]
        except OSError:
            projects = []
        for proj in projects:
            try:
                with os.scandir(proj) as it:
                    for e in it:
                        if e.name.endswith(".jsonl") and e.is_file():
                            files.append((e.stat().st_mtime, e.path))
            except OSError:
                pass
        files.sort(reverse=True)
        _recent["at"], _recent["files"] = now, files[:40]
    return _recent["files"]


def recent_closed(live_ids, want=5):
    """The chats you texted most recently that have no Claude process running.

    The desktop app shuts down chats you aren't using, so on their own the
    running sessions can be just one or two. These fill the strip up to 5,
    always shown asleep.
    """
    out = []
    for mtime, path in _recent_files():
        sid = os.path.basename(path)[:-6]
        if sid in live_ids:
            continue
        tr = _progress.tracker(sid, path)
        if tr is None or not tr.last_human:
            continue  # you never typed in it (e.g. a scheduled task's chat)
        label = project_label(tr.cwd) if tr.cwd else "chat"
        out.append({
            "id": sid,
            "name": tr.name() or label,
            "project": label,
            "cwd": "",
            "state": "sleeping",
            "raw_status": "closed",
            "sub": False,
            "seed": sid,
            "started": 0,
            "closed": True,
            "progress": None,
            "turn_start": tr.turn_start,
            "last_msg": tr.last_human,
            "scheduled": False,
        })
    out.sort(key=lambda a: -a["last_msg"])
    return out[:want]


def scan():
    """Return list of agent dicts: id, name, project, state, sub, seed, cwd."""
    now = time.time()
    agents = []
    for path in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        d = _read_json(path)
        sid = _s(d.get("sessionId")) if d else ""
        if not sid or not _SAFE_ID(sid):
            continue
        try:
            pid, start = int(d.get("pid")), d.get("procStart")
            start = int(start) if start is not None else None
            if not (0 < pid < 2 ** 32) or not pid_alive(pid, start):
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        started = d.get("startedAt", 0)
        agents.append({
            "id": sid,
            "name": _s(d.get("name"))[:200] or project_label(d.get("cwd")),
            "project": project_label(d.get("cwd")),
            "cwd": _s(d.get("cwd")),
            "state": map_status(d.get("status")),
            "raw_status": _s(d.get("status")),
            "sub": False,
            "seed": sid,
            "started": started if isinstance(started, (int, float)) else 0,
        })
    # One chat can have two Claude processes (e.g. opened in two places). Show it
    # once, as the busier of the two, or it takes two spots and two characters.
    busy = {"waiting": 2, "working": 1}
    one = {}
    for a in agents:
        b = one.get(a["id"])
        if b is None or busy.get(a["state"], 0) > busy.get(b["state"], 0):
            one[a["id"]] = a
    agents = sorted(one.values(), key=lambda a: a["started"])
    result = []
    for a in agents:
        try:
            a["progress"], a["turn_start"] = _progress.progress(a["id"])
            tr = _progress.tracker(a["id"])
            a["last_msg"] = tr.last_human if tr else None
            a["scheduled"] = bool(tr and tr.scheduled and not tr.last_human)
        except Exception:
            a["progress"], a["turn_start"] = None, None
            a["last_msg"], a["scheduled"] = None, False
        result.append(a)
        result.extend(_subagents(a["id"], a["started"], now))
    try:
        result.extend(recent_closed({a["id"] for a in agents}))
    except Exception:
        pass
    return result


if __name__ == "__main__":
    for a in scan():
        tag = " (not running)" if a.get("closed") else ""
        print(("   ↳ " if a["sub"] else "") + f"{a['state']:9} {a['project']:22} {a['name']}{tag}")
