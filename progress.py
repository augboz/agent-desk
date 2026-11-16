"""Estimate how far along a session's current turn is, from its transcript.

Claude Code records each session's task list as tool calls in its transcript
(~/.claude/projects/*/<sessionId>.jsonl):
  - desktop app:  mcp__ccd_turn__update_plan  (items / advance / done / start)
                  mcp__ccd_turn__wrap_up      (turn finished)
  - terminal CLI: TodoWrite                   (full todo list with statuses)
A new user prompt starts a new turn and clears the list.

The transcript is read incrementally (only new bytes each poll).
progress() returns (fraction or None, turn_start_epoch or None).
"""
import glob
import json
import os
from collections import OrderedDict
from datetime import datetime

PROJECTS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "projects")
FIRST_READ = 3_000_000  # bytes read from the end the first time a session is seen
_INTERESTING = (b'"type":"user"', b"update_plan", b"wrap_up", b"TodoWrite", b'-title"')
MAX_TRACKERS = 64  # transcripts kept open in memory; the least recently used is dropped


def _str(v):
    """v if it's a non-empty string, else None (transcripts are untrusted input)."""
    return v if isinstance(v, str) and v else None


def _ts(s):
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class _Tracker:
    def __init__(self, path):
        self.path = path
        self.offset = None
        self.partial = b""
        self.items = None      # list of "pending" / "in_progress" / "completed"
        self.turn_start = None  # start of the current turn (any prompt, scheduled ones too)
        self.last_human = None  # when you last typed a message in this chat yourself
        self.scheduled = False  # a scheduled task has sent this chat a prompt
        self.seen = set()
        self.sid = os.path.basename(path)[:-6]
        self.title = None  # the chat's name: your title, else Claude's
        self.ai_title = None
        self.title_scanned = False
        self.cwd = None  # the folder the chat ran in

    def update(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return
        if self.offset is None:
            self.offset = max(0, size - FIRST_READ)
            skip_first = self.offset > 0
        else:
            skip_first = False
        if size < self.offset:  # file replaced
            self.offset, self.partial = 0, b""
        if size == self.offset:
            return
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read(size - self.offset)
        self.offset = size
        data = self.partial + data
        lines = data.split(b"\n")
        self.partial = lines.pop()  # incomplete last line, finish next time
        if skip_first and lines:
            lines.pop(0)
        if skip_first and not self.title_scanned:
            self._find_title()  # the title may be further back than the part we read
        for line in lines:
            if not any(k in line for k in _INTERESTING):
                continue
            if b'"tool_result"' in line and b'"type":"user"' in line:
                continue  # tool output (often huge), never a prompt: don't parse it
            self._feed(line, self._line)

    @staticmethod
    def _feed(line, handler):
        """Parse one JSONL line and hand it on; bad or odd lines are skipped."""
        try:
            d = json.loads(line)
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        try:
            handler(d)
        except (AttributeError, TypeError, KeyError, ValueError):
            pass  # a field of an unexpected type: ignore the line

    def _find_title(self):
        """One pass over the whole file for title lines (only the first time)."""
        self.title_scanned = True
        try:
            with open(self.path, "rb") as f:
                for line in f:
                    if b'-title"' in line:
                        self._feed(line, self._title)
        except OSError:
            pass

    def _title(self, d):
        if d.get("sessionId") not in (None, self.sid):
            return  # a title line copied from another chat
        if d.get("type") == "custom-title" and _str(d.get("customTitle")):
            self.title = d["customTitle"][:200]
        elif d.get("type") == "ai-title" and _str(d.get("aiTitle")):
            self.ai_title = d["aiTitle"][:200]

    def name(self):
        return self.title or self.ai_title

    def _line(self, d):
        if d.get("type") in ("custom-title", "ai-title"):
            self._title(d)
            return
        if d.get("isSidechain"):
            return
        msg = d.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if d.get("type") == "user":
            self.cwd = _str(d.get("cwd")) or self.cwd
        if d.get("type") == "user" and not d.get("isMeta"):
            if isinstance(content, str) or (
                    isinstance(content, list)
                    and any(isinstance(x, dict) and x.get("type") == "text" for x in content)
                    and not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in content)):
                self.items = None
                self.seen.clear()  # tool ids only matter within one turn
                when = _ts(d.get("timestamp", ""))
                self.turn_start = when or self.turn_start
                text = content if isinstance(content, str) else next(
                    (x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text"), "")
                if text.lstrip().startswith("<scheduled-task"):
                    self.scheduled = True  # an automated run, not you
                elif when:
                    self.last_human = when
            return
        if d.get("type") != "assistant" or not isinstance(content, list):
            return
        for x in content:
            if not isinstance(x, dict) or x.get("type") != "tool_use":
                continue
            tid = x.get("id")
            if not isinstance(tid, str) or tid in self.seen:
                continue
            self.seen.add(tid)
            name, inp = x.get("name"), x.get("input")
            if not isinstance(name, str) or not isinstance(inp, dict):
                continue
            if name.endswith("update_plan"):
                self._plan(inp)
            elif name.endswith("wrap_up") and self.items:
                self.items = ["completed"] * len(self.items)
            elif name == "TodoWrite":
                todos = inp.get("todos")
                if isinstance(todos, list):
                    self.items = [_status(t) for t in todos] or None

    def _plan(self, inp):
        if isinstance(inp.get("items"), list) and inp["items"]:
            self.items = [_status(i) for i in inp["items"]]
            return
        if not self.items:
            return
        it = self.items
        if inp.get("advance"):
            for i, st in enumerate(it):
                if st == "in_progress":
                    it[i] = "completed"
                    break
            for i, st in enumerate(it):
                if st == "pending":
                    it[i] = "in_progress"
                    break
        done = inp.get("done")
        for n in done if isinstance(done, list) else []:
            if isinstance(n, int) and 1 <= n <= len(it):
                it[n - 1] = "completed"
        n = inp.get("start")
        if isinstance(n, int) and 1 <= n <= len(it):
            it[n - 1] = "in_progress"

    def progress(self):
        if not self.items:
            return None
        done = sum(1 for s in self.items if s == "completed")
        busy = sum(1 for s in self.items if s == "in_progress")
        return min(1.0, (done + 0.4 * busy) / len(self.items))


def _status(item):
    st = item.get("status") if isinstance(item, dict) else None
    return st if st in ("pending", "in_progress", "completed") else "pending"


_trackers = OrderedDict()  # session id -> _Tracker, least recently used first


def tracker(session_id, path=None):
    """The (cached) reader for one chat's transcript, brought up to date."""
    tr = _trackers.get(session_id)
    if tr is not None:
        _trackers.move_to_end(session_id)
    else:
        if path is None:
            hits = glob.glob(os.path.join(PROJECTS_DIR, "*", glob.escape(session_id) + ".jsonl"))
            if not hits:
                return None
            path = hits[0]
        tr = _trackers[session_id] = _Tracker(path)
        while len(_trackers) > MAX_TRACKERS:
            _trackers.popitem(last=False)
    try:
        tr.update()
    except OSError:
        pass
    return tr


def progress(session_id):
    tr = tracker(session_id)
    if tr is None:
        return None, None
    return tr.progress(), tr.turn_start


if __name__ == "__main__":
    import sys
    import time
    for sid in sys.argv[1:]:
        t0 = time.time()
        p, start = progress(sid)
        print(sid[:8], "progress", p, "turn started", start and round(time.time() - start), "s ago",
              f"({time.time() - t0:.2f}s)")
