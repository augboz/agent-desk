"""Minimal borderless, resizable, always-on-top window that hosts a scene.

- drag anywhere to move
- drag any edge or corner, scroll the mouse wheel, or right-click > Size to
  resize (height = zoom, width = how many agents fit)
- hover a character for its name; right-click for options; x (on hover) closes
"""
import ctypes
import math
import os
import random
import subprocess
import sys
import time
import tkinter as tk

import scenes

# Render at the screen's real resolution. Without this Windows stretches the
# window bitmap on high-DPI screens, which makes everything blurry.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
# The real PowerShell, never whatever "powershell" a folder on PATH might hold.
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32",
                          "WindowsPowerShell", "v1.0", "powershell.exe")
STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu",
                           "Programs", "Startup", "Agent Desk.lnk")
SIZES = [("Small", 200, 110), ("Medium", 260, 140), ("Large", 380, 200), ("Wide", 480, 150)]
EDGE = 7  # resize border width, logical px


_menus_open = 0


def menu_open():
    """True while a right-click menu is showing (the strip then stops pushing
    itself on top, which would cover the menu)."""
    return _menus_open > 0


def popup(menu, x, y):
    """Show a right-click menu at (x, y) above every other window.

    On Windows this waits until the menu closes, so the flag covers exactly
    the time it's open."""
    global _menus_open
    _menus_open += 1
    try:
        menu.tk_popup(x, y)
    finally:
        menu.grab_release()
        _menus_open -= 1


def add_menu_items(m, items):
    """Fill menu m from a list of entries:
    None (separator), ("cmd", label, fn), ("check", label, var, fn),
    ("radio", label, var, value, fn), ("cascade", label, entries or a function
    returning entries, built fresh each time the sub-menu opens)."""
    for item in items or []:
        if item is None:
            m.add_separator()
        elif item[0] == "check":
            m.add_checkbutton(label=item[1], variable=item[2], command=item[3])
        elif item[0] == "radio":
            m.add_radiobutton(label=item[1], variable=item[2], value=item[3], command=item[4])
        elif item[0] == "cascade":
            sub = tk.Menu(m, tearoff=0)
            if callable(item[2]):
                make = item[2]

                def refill(sub=sub, make=make):
                    sub.delete(0, "end")
                    add_menu_items(sub, make())
                sub.configure(postcommand=refill)
            else:
                add_menu_items(sub, item[2])
            m.add_cascade(label=item[1], menu=sub)
        else:
            m.add_command(label=item[1], command=item[2])


_last_errors = {}  # error text -> when it was last written


def log_error(text, log=None):
    """Append an error to agent_desk.log instead of dying silently.

    The same error is written at most once a minute (a bug in drawing would
    otherwise log 20 times a second), and the log is rotated at 200 KB.
    """
    import paths
    log = log or paths.LOG
    now = time.monotonic()
    text = text.rstrip()
    if now - _last_errors.get(text, -1e9) < 60:
        return
    if len(_last_errors) > 100:
        _last_errors.clear()
    _last_errors[text] = now
    try:
        os.makedirs(os.path.dirname(log), exist_ok=True)
        if os.path.exists(log) and os.path.getsize(log) > 200_000:
            os.replace(log, log + ".1")
        with open(log, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except OSError:
        pass


def startup_enabled():
    return os.path.exists(STARTUP_LNK)


def set_startup(on):
    """Add or remove a Startup-folder shortcut that runs agent_desk.py silently."""
    if not on:
        try:
            os.remove(STARTUP_LNK)
        except OSError:
            pass
        return True
    exe = sys.executable
    if os.path.basename(exe).lower() == "python.exe":
        exe = os.path.join(os.path.dirname(exe), "pythonw.exe")
    script = os.path.join(HERE, "agent_desk.py")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
          "$s.TargetPath=$env:EXE;$s.Arguments='\"'+$env:SCRIPT+'\"';"
          "$s.WorkingDirectory=$env:WD;$s.Description='Agent Desk';$s.Save()")
    env = dict(os.environ, LNK=STARTUP_LNK, EXE=exe, SCRIPT=script, WD=HERE)
    r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", ps],
                       env=env, capture_output=True, creationflags=0x08000000, timeout=30)
    return r.returncode == 0 and startup_enabled()

TICK_MS = 40
STATE_DOT = {"working": "#5be39a", "sleeping": "#7fb8e6", "waiting": "#ffb03b"}
STATE_WORD = {"working": "working", "sleeping": "napping", "waiting": "needs you"}


class DemoAgents:
    NAMES = [("Fix login bug", "web-app"), ("Write unit tests", "api"),
             ("Dashboard charts", "dashboard"), ("Update the docs", "docs"),
             ("Agent desk scenes", "agent-desk"), ("Refactor parser", "parser"),
             ("Folder cleanup", "scratch")]

    def __init__(self, n=6):
        r = random.Random(7)
        now = time.monotonic()
        self.agents = []
        for i, (name, proj) in enumerate(self.NAMES[:n]):
            self.agents.append({"id": f"demo{i}", "seed": f"demo-{proj}", "name": name,
                                "project": proj, "sub": False,
                                "state": "working" if i % 2 == 0 else "sleeping",
                                "_next": now + r.uniform(5, 14)})
        self.r = r

    def get(self):
        now = time.monotonic()
        for a in self.agents:
            if now > a["_next"]:
                if a["state"] == "working":
                    a["state"] = "waiting" if self.r.random() < 0.12 else "sleeping"
                else:
                    a["state"] = "working"
                a["_next"] = now + self.r.uniform(6, 16)
        return self.agents


class LiveAgents:
    """The real sessions, looked up on a background thread so drawing never waits
    on the disk. Scanning pauses while nothing on screen is asking for them."""

    def __init__(self, poll=1.5):
        import threading

        import detect
        self.detect, self.poll, self.agents = detect, poll, []
        self.wanted = time.monotonic()
        self.wake = threading.Event()
        threading.Thread(target=self.run, daemon=True, name="agent-scan").start()

    def run(self):
        while True:
            if time.monotonic() - self.wanted < 5:
                try:
                    self.agents = self.detect.scan()  # swapped in whole: readers never see half a list
                except Exception:
                    import traceback
                    log_error(traceback.format_exc())
                self.wake.wait(self.poll)
            else:
                self.wake.wait()  # hidden: sleep until someone looks again
            self.wake.clear()

    def get(self):
        idle = time.monotonic() - self.wanted >= 5
        self.wanted = time.monotonic()
        if idle:
            self.wake.set()
        return self.agents


def _round_corners(win):
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), 4)
    except Exception:
        pass


class DeskWindow:
    def __init__(self, master, provider, scene_key="slopes", label=None,
                 size=(300, 150), pos=None, on_close=None, on_change=None,
                 show_names=False, topmost=True, fish=None, on_hide=None, extra_menu=None):
        self.provider, self.label = provider, label
        self.on_close, self.on_change, self.on_hide = on_close, on_change, on_hide
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", topmost)
        self.k = max(1.0, round(self.win.winfo_fpixels("1i") / 96 * 2) / 2)
        w, h = int(size[0] * self.k), int(size[1] * self.k)
        x, y = pos if pos else (200, 200)
        self.win.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
        self.c = tk.Canvas(self.win, highlightthickness=0, bd=0, bg="#222")
        self.c.pack(fill="both", expand=True)
        self.scene_key = tk.StringVar(value=scene_key)
        self.fish_choice = dict(fish or {})
        self.scene = scenes.SCENES[scene_key]()
        self.scene.fish_choice = self.fish_choice
        self.show_names = tk.BooleanVar(value=show_names)
        self.topmost = tk.BooleanVar(value=topmost)
        self.mouse = None
        self.drag = None
        self.hits = []
        # Like the taskbar strip: click a character to pin its status card in a
        # stack above the window (a star floats over it); click again to unpin.
        # Hovering previews the card on top of the stack.
        import cards
        self.pins = []  # agent ids, oldest first
        self.stack = cards.PinStack(self.win)

        m = tk.Menu(self.win, tearoff=0)
        sm = tk.Menu(m, tearoff=0)
        for key, cls in scenes.SCENES.items():
            sm.add_radiobutton(label=cls.title, value=key, variable=self.scene_key,
                               command=self.set_scene)
        m.add_cascade(label="Scene", menu=sm)
        m.add_checkbutton(label="Show all cards", variable=self.show_names, command=self.changed)
        m.add_checkbutton(label="Always on top", variable=self.topmost, command=self.set_topmost)
        self.startup = tk.BooleanVar(value=startup_enabled())
        m.add_checkbutton(label="Start with Windows", variable=self.startup,
                          command=self.toggle_startup)
        m.add_separator()
        zm = tk.Menu(m, tearoff=0)
        for label, sw, sh in SIZES:
            zm.add_command(label=label, command=lambda a=sw, b=sh: self.set_size(a, b))
        zm.add_separator()
        zm.add_command(label="Bigger   (scroll up)", command=lambda: self.zoom(1.15))
        zm.add_command(label="Smaller  (scroll down)", command=lambda: self.zoom(1 / 1.15))
        m.add_cascade(label="Size", menu=zm)
        add_menu_items(m, extra_menu)
        m.add_separator()
        if on_hide:
            m.add_command(label="Hide tank", command=self.close)
            m.add_command(label="Quit Agent Desk", command=self.quit)
        else:
            m.add_command(label="Close", command=self.close)
        self.menu = m

        c = self.c
        c.bind("<ButtonPress-1>", self.press)
        c.bind("<B1-Motion>", self.motion_drag)
        c.bind("<ButtonRelease-1>", self.release)
        c.bind("<Motion>", self.hover_move)
        c.bind("<Leave>", lambda e: setattr(self, "mouse", None))
        wheel = lambda e: self.zoom(1.1 if e.delta > 0 else 1 / 1.1)
        c.bind("<MouseWheel>", wheel)
        self.win.bind("<MouseWheel>", wheel)
        c.bind("<Button-3>", self.right_click)
        self.win.after(50, lambda: _round_corners(self.win))
        self.tick()

    # ----- options -----
    def right_click(self, e):
        """Right-click on empty space opens the options; on a character it does nothing."""
        if self.agent_at(e.x, e.y):
            return
        popup(self.menu, e.x_root, e.y_root)

    def set_scene(self):
        self.scene = scenes.SCENES[self.scene_key.get()]()
        self.scene.fish_choice = self.fish_choice
        self.changed()

    def set_topmost(self):
        self.win.attributes("-topmost", self.topmost.get())
        self.changed()

    def changed(self):
        if self.on_change:
            self.on_change(self)

    def state(self):
        return {"scene": self.scene_key.get(), "names": self.show_names.get(),
                "fish": self.fish_choice,
                "topmost": self.topmost.get(), "x": self.win.winfo_x(), "y": self.win.winfo_y(),
                "w": round(self.win.winfo_width() / self.k), "h": round(self.win.winfo_height() / self.k)}

    def close(self):
        if self.on_hide:  # x hides the tank; the taskbar strip brings it back
            self.changed()
            self.on_hide(self)
            return
        self.quit()

    def quit(self):
        self.changed()
        self.win.destroy()
        if self.on_close:
            self.on_close(self)

    def toggle_startup(self):
        ok = set_startup(self.startup.get())
        self.startup.set(startup_enabled())
        if not ok:
            self.win.bell()

    # ----- geometry -----
    CURSORS = {"": "", "e": "size_we", "w": "size_we", "n": "size_ns", "s": "size_ns",
               "ne": "size_ne_sw", "sw": "size_ne_sw", "nw": "size_nw_se", "se": "size_nw_se"}

    def edge_at(self, x, y):
        """Which edge/corner (n, s, e, w, ne, ...) the point is on, or ''."""
        w, h = self.c.winfo_width(), self.c.winfo_height()
        e = EDGE * self.k
        c = 3 * e  # corners are easier to grab
        v = "n" if y < e else "s" if y > h - e else ""
        hz = "w" if x < e else "e" if x > w - e else ""
        if v and not hz:
            hz = "w" if x < c else "e" if x > w - c else ""
        if hz and not v:
            v = "n" if y < c else "s" if y > h - c else ""
        return v + hz

    def closebox(self, x, y):
        k = self.k
        w = self.c.winfo_width()
        return w - 24 * k < x < w - 6 * k and 6 * k < y < 24 * k

    def hover_move(self, e):
        self.mouse = (e.x, e.y)
        cur = self.CURSORS[self.edge_at(e.x, e.y)]
        if self.closebox(e.x, e.y) or (not self.edge_at(e.x, e.y) and self.agent_at(e.x, e.y)):
            cur = "hand2"
        if cur != self.c.cget("cursor"):
            self.c.configure(cursor=cur)

    def press(self, e):
        edge = self.edge_at(e.x, e.y)
        if not edge and self.closebox(e.x, e.y):
            self.close()
            return
        self.drag = (edge or "move", e.x_root, e.y_root, self.win.winfo_x(), self.win.winfo_y(),
                     self.win.winfo_width(), self.win.winfo_height())
        self.press_at = (e.x, e.y, e.x_root, e.y_root)

    def motion_drag(self, e):
        self.mouse = (e.x, e.y)
        if not self.drag:
            return
        mode, x0, y0, wx, wy, ww, wh = self.drag
        dx, dy = e.x_root - x0, e.y_root - y0
        if mode == "move":
            self.win.geometry(f"+{int(wx + dx)}+{int(wy + dy)}")
            return
        mw, mh = int(150 * self.k), int(80 * self.k)
        x, y, w, h = wx, wy, ww, wh
        if "e" in mode:
            w = max(mw, ww + dx)
        if "s" in mode:
            h = max(mh, wh + dy)
        if "w" in mode:
            w = max(mw, ww - dx)
            x = wx + ww - w
        if "n" in mode:
            h = max(mh, wh - dy)
            y = wy + wh - h
        self.win.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")

    def release(self, e):
        if not self.drag:
            return
        mode = self.drag[0]
        self.drag = None
        px, py, rx, ry = getattr(self, "press_at", (0, 0, 0, 0))
        if mode == "move" and e is not None and abs(e.x_root - rx) + abs(e.y_root - ry) < 5 * self.k:
            a = self.agent_at(px, py)  # a click, not a drag: pin or unpin its card
            if a:
                if a["id"] in self.pins:
                    self.pins.remove(a["id"])
                else:
                    self.pins.append(a["id"])
            return
        self.changed()

    def agent_at(self, x, y):
        for x0, y0, x1, y1, a in reversed(self.hits):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return a
        return None

    def set_size(self, w, h):
        self.win.geometry(f"{int(w * self.k)}x{int(h * self.k)}")
        self.win.after(50, self.changed)

    def zoom(self, f):
        w, h = self.win.winfo_width(), self.win.winfo_height()
        mw, mh = int(150 * self.k), int(80 * self.k)
        nw, nh = max(mw, int(w * f)), max(mh, int(h * f))
        self.win.geometry(f"{nw}x{nh}")
        self.win.after(50, self.changed)

    # ----- drawing -----
    def tick(self):
        try:
            if self.win.winfo_viewable():
                self.draw()
            else:
                self.stack.hide()
        except tk.TclError:
            return
        except Exception:
            import traceback
            log_error(traceback.format_exc())
        self.win.after(TICK_MS, self.tick)

    def draw(self):
        c = self.c
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10:
            return
        c.delete("all")
        s = h / scenes.H
        P = scenes.Pen(c, s)
        L = w / s
        agents = sorted(self.provider.get(), key=lambda a: a.get("id", ""))
        by_id = {a["id"]: a for a in agents}
        self.pins = [i for i in self.pins if i in by_id]  # session closed: drop its card
        self.scene.hide_labels = set(by_id)  # the card is the label
        t = time.monotonic()
        self.scene.draw(P, L, agents, t, False)
        self.hits = P.hits
        k = self.k
        if self.label:
            c.create_text(8 * k, 7 * k, text=self.label, anchor="nw",
                          fill="#ffffff", font=("Segoe UI Semibold", 9))
        if self.mouse:
            c.create_oval(w - 23 * k, 7 * k, w - 7 * k, 23 * k, fill="#123c5e", outline="")
            c.create_line(w - 18.5 * k, 11.5 * k, w - 11.5 * k, 18.5 * k, fill="#ffffff", width=1.6 * k)
            c.create_line(w - 11.5 * k, 11.5 * k, w - 18.5 * k, 18.5 * k, fill="#ffffff", width=1.6 * k)
            for i in range(3):
                o = (4 + i * 4) * k
                c.create_line(w - o, h - 3 * k, w - 3 * k, h - o, fill="#ffffff", width=max(1, k))
        self.draw_pins(by_id, t)

    def draw_pins(self, by_id, t):
        """Stars over pinned characters, and their cards stacked above the window."""
        import cards
        import cast
        k = self.k
        size = cast.STAR * k * 1.2
        bob = math.sin(t * 0.9) * 0.3 * k
        shown = [h[4]["id"] for h in self.hits]
        for x0, y0, x1, y1, a in self.hits:
            if a["id"] in self.pins:
                cards.draw_star(self.c, k, (x0 + x1) / 2, y0 - 3 * k - size / 2 + bob, size)
        hover = self.agent_at(*self.mouse) if self.mouse and not self.drag else None
        ids = list(self.pins)
        if self.show_names.get():  # "Show all cards": everyone on screen, in the stack
            ids += [i for i in shown if i not in ids]
        preview = hover["id"] if hover and hover["id"] not in ids else None
        if preview:
            ids.append(preview)
        bars = self.scene.update_bars(list(by_id.values()), t, 0) \
            if hasattr(self.scene, "update_bars") else {}

        def who(a):
            if self.scene_key.get() != "cast":
                return None
            return cast.shared().who.get(a["id"])
        self.stack.show([by_id[i] for i in ids], preview, bars, who, topmost=self.topmost.get())


