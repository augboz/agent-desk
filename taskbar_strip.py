"""The characters (or a tiny aquarium) on the Windows taskbar.

A borderless window kept on top of the taskbar's empty space, from the end
of the Widgets (weather) button to the Start button, at the taskbar's full
height (Windows 11 has no supported way to put custom content inside the
taskbar). A small background helper (taskbar_layout.ps1, UI Automation,
read-only) reports where those two buttons are, so the strip follows the
Start button as apps open and close. Hover a character for its name. Click a
character to pin its status card above the strip (a star appears next to it);
cards stack upwards in the order you pin them, and clicking the character
again unpins it. Click the little icon in the top-right corner to take the big
window out or put it away, right-click for options. It hides while a full-screen app is in front
or while the taskbar is auto-hidden.
"""
import ctypes
import ctypes.wintypes as wt
import math
import os
import subprocess
import threading
import time
import tkinter as tk

import cards
import cast
import scenes

user32 = ctypes.windll.user32
user32.GetParent.restype = wt.HWND
user32.GetForegroundWindow.restype = wt.HWND
user32.FindWindowW.restype = wt.HWND
user32.MonitorFromWindow.restype = wt.HANDLE

W_LOGICAL = 190  # fallback width (logical px) until the Start button has been found
GAP = 1.5  # logical px kept clear next to the Widgets and Start buttons
HERE = os.path.dirname(os.path.abspath(__file__))
HWND_TOPMOST = wt.HWND(-1)
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
STATE_WORD = {"working": "working", "sleeping": "napping", "waiting": "needs you"}


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD)]


def _rect(hwnd):
    r = wt.RECT()
    if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r.left, r.top, r.right, r.bottom
    return None


def _monitor(hwnd):
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)):
        m = mi.rcMonitor
        return m.left, m.top, m.right, m.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def taskbar():
    """(rect, monitor rect) of the main taskbar, or None if it can't be seen."""
    hwnd = user32.FindWindowW("Shell_TrayWnd", None)
    r = _rect(hwnd)
    if not r:
        return None
    mon = _monitor(hwnd)
    visible = min(r[3], mon[3]) - max(r[1], mon[1])
    if visible < (r[3] - r[1]) * 0.6 or r[2] - r[0] < r[3] - r[1]:  # auto-hidden, or vertical
        return None
    return r, mon


def fullscreen_app():
    """True when the window in front covers its whole monitor (game, video, slides)."""
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(fg, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "TkTopLevel"):
        return False
    r = _rect(fg)
    return bool(r) and r == _monitor(fg)


POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32",
                          "WindowsPowerShell", "v1.0", "powershell.exe")


class TaskbarLayout:
    """Where the Widgets button ends and the Start button starts (screen px).

    Runs taskbar_layout.ps1 once in the background; it prints a line only when
    something moves, and quits on its own when this app exits.
    """

    def __init__(self):
        self.edges = (None, None)  # (widgets_right, start_left), always replaced as a pair
        try:
            self.proc = subprocess.Popen(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", os.path.join(HERE, "taskbar_layout.ps1"), "-Owner", str(os.getpid())],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                text=True, creationflags=0x08000000)  # no console window
        except OSError:
            self.proc = None
            return
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.proc.stdout:
            try:
                wr, sl = (int(v) for v in line.split())
            except ValueError:
                continue
            self.edges = (wr if wr > 0 else None, sl if sl > 0 else None)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=2)
            except Exception:
                pass


class TaskbarStrip:
    def __init__(self, master, provider, desk, offset=None, on_click=None, on_change=None,
                 menu_items=None, is_open=None, style="cast", chars=None, spot=None):
        self.provider, self.desk = provider, desk
        self.on_click, self.on_change = on_click, on_change
        self.is_open = is_open or (lambda: False)
        self.offset = offset  # logical px from the taskbar's left edge (fixed)
        self.spot = dict(spot) if spot else None  # where the strip sits and how wide
        self.born = time.monotonic()
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.withdraw()
        self.k = max(1.0, round(self.win.winfo_fpixels("1i") / 96 * 2) / 2)
        self.c = tk.Canvas(self.win, highlightthickness=0, bd=0, bg="#174a78")
        self.c.pack(fill="both", expand=True)
        self.layout = TaskbarLayout()
        self.win.bind("<Destroy>", lambda e: e.widget is self.win and self.layout.stop())
        self.icon_box = (0, 0, 0, 0)  # the pop-out icon, canvas px
        self.pins = []  # agent ids with a pinned status card, oldest first
        self.stack = cards.PinStack(self.win)  # the pinned cards, above the strip
        self.bars, self.by_id = {}, {}
        self.star_img = {}
        self.face_img = {}
        self.hover_id = None
        self.pos = scenes.Aquarium()  # only for spreading the swimmers out
        self.hits, self.mouse = [], None
        self.cast = cast.shared(chars)
        self.style = tk.StringVar(value=style)
        self.shown = False
        self.last_place = 0

        from desk_window import add_menu_items
        m = tk.Menu(self.win, tearoff=0)
        add_menu_items(m, menu_items)
        self.menu = m

        c = self.c
        c.bind("<Motion>", self.motion)
        c.bind("<Leave>", lambda e: setattr(self, "mouse", None))
        c.bind("<Button-3>", self.right_click)
        c.bind("<ButtonRelease-1>", self.left_click)
        self.tick()

    def on_icon(self, x, y):
        x0, y0, x1, y1 = self.icon_box
        return x0 <= x <= x1 and y0 <= y <= y1

    def motion(self, e):
        self.mouse = (e.x, e.y)
        cur = "hand2" if self.on_icon(e.x, e.y) else ""
        if self.c.cget("cursor") != cur:
            self.c.configure(cursor=cur)

    def left_click(self, e):
        if self.on_icon(e.x, e.y):
            if self.on_click:
                self.on_click()
            return
        a = self.agent_at(e.x, e.y)
        if a:  # pin or unpin this character's status card
            if a["id"] in self.pins:
                self.pins.remove(a["id"])
            else:
                self.pins.append(a["id"])

    def agent_at(self, x, y):
        for x0, y0, x1, y1, ag in reversed(self.hits):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return ag
        return None

    def using_cast(self):
        return self.style.get() == "cast" and self.cast.ok()

    def right_click(self, e):
        """Right-click on empty space (or the icon) opens the options; on a character it does nothing."""
        from desk_window import popup
        if not self.on_icon(e.x, e.y) and self.agent_at(e.x, e.y):
            return
        popup(self.menu, e.x_root, e.y_root)

    def set_style(self):
        self.last_place = 0  # resize right away
        if self.on_change:
            self.on_change()

    # ----- placement -----
    def hwnd(self):
        return user32.GetParent(self.win.winfo_id())

    def place(self):
        """Fill the gap between the Widgets and Start buttons; hide when the taskbar can't be seen."""
        tb = None if fullscreen_app() else taskbar()
        if not tb:
            if self.shown:
                self.win.withdraw()
                self.shown = False
                self.stack.hide()
            return
        (l, t, r, b), mon = tb
        k = self.k
        gap = int(GAP * k)
        lay = self.layout
        spot = self.spot  # remembered {"x": left edge, "w": width}, screen px
        widgets_right, start_left = lay.edges
        if widgets_right is None or start_left is None:
            # Buttons not found yet (first second after start): use the remembered
            # spot so the strip never appears somewhere else and then jumps.
            if not spot:
                if time.monotonic() - self.born < 5:
                    return  # wait for the helper rather than show a wrong size
                spot = {"x": l + int(136 * k), "w": int(W_LOGICAL * k)}
            x0, w = spot["x"], spot["w"]
        else:
            x0 = widgets_right + gap
            room = start_left - gap - x0
            if not spot or spot.get("x") != x0:
                # first time, or the taskbar itself changed: measure the gap once
                spot = self.spot = {"x": x0, "w": room}
                if self.on_change:
                    self.on_change()
            # Fixed size from then on. It only gets narrower if the Start button
            # moves left far enough that the strip would cover it.
            w = min(spot["w"], room)
        w = max(int(60 * k), min(w, r - gap - x0))
        geo = f"{w}x{b - t}+{x0}+{t}"
        if not self.shown:
            self.win.deiconify()
            self.shown = True
        if self.win.geometry() != geo:
            self.win.geometry(geo)
        self.round_corners()  # cheap; also re-applies after the taskbar or display changes
        # The taskbar raises itself when clicked; put the strip back on top
        # (but not while a right-click menu is open: that would cover the menu).
        from desk_window import menu_open
        if not menu_open():
            user32.SetWindowPos(self.hwnd(), HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)

    def round_corners(self):
        try:
            pref = ctypes.c_int(3)  # small rounded corners
            ctypes.windll.dwmapi.DwmSetWindowAttribute(self.hwnd(), 33, ctypes.byref(pref), 4)
        except Exception:
            pass

    def draw_icon(self):
        """Small pop-out icon in the top-right corner: arrow out while the big
        window is away, arrow back in while it's out."""
        c, k = self.c, self.k
        w = c.winfo_width()
        size, m = 13 * k, 3 * k
        x0, y0 = w - size - m, m
        self.icon_box = (x0 - 2 * k, 0, w, y0 + size + 2 * k)
        hover = self.mouse is not None and self.on_icon(*self.mouse)
        scenes.round_rect(c, x0, y0, x0 + size, y0 + size, 3 * k,
                          fill="#1d5a8c" if hover else "#0b2e4d", outline="")
        out = self.is_open()
        col = "#ffffff" if hover else "#cfe8ff"
        lw = max(1.0, 1.1 * k)
        cx, cy, r = x0 + size / 2, y0 + size / 2, 3.2 * k
        c.create_line(cx + r * 0.1, cy - r, cx - r, cy - r, cx - r, cy + r, cx + r, cy + r,
                      cx + r, cy - r * 0.1, fill=col, width=lw, capstyle="round", joinstyle="round")
        inner, outer = (cx - r * 0.1, cy + r * 0.1), (cx + r * 1.15, cy - r * 1.15)
        tail, tip = (outer, inner) if out else (inner, outer)
        c.create_line(*tail, *tip, fill=col, width=lw, capstyle="round")
        hx, hy = tip
        sg, hl = (1 if out else -1), 2.4 * k
        c.create_line(hx + sg * hl, hy, hx, hy, hx, hy - sg * hl, fill=col, width=lw,
                      capstyle="round", joinstyle="round")

    # ----- drawing -----
    def tick(self):
        try:
            now = time.monotonic()
            if now - self.last_place > 0.4:
                self.last_place = now
                self.place()
            if self.shown:
                self.draw()
                if self.c.winfo_width() >= 10:
                    self.draw_stars()
                    self.draw_icon()
                self.hover()
                self.draw_pins()
        except tk.TclError:
            return
        except Exception:
            import traceback

            from desk_window import log_error
            log_error(traceback.format_exc())
        self.win.after(50, self.tick)

    def draw(self):
        c, k = self.c, self.k
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10:
            return
        c.delete("all")
        P = scenes.Pen(c, k)
        L, H = w / k, h / k
        t = time.monotonic()
        scene = self.desk.scene if isinstance(self.desk.scene, scenes.Aquarium) else self.pos
        agents = sorted(self.provider.get(), key=lambda a: a.get("id", ""))
        bars = scene.bars_now(agents, t)
        present = [a["id"] for a in agents]
        self.bars, self.by_id = bars, {a["id"]: a for a in agents}
        self.pins = [i for i in self.pins if i in self.by_id]  # session closed: drop its card
        if self.using_cast():
            self.hits = self.cast.draw(self, P, L, H, agents, bars, t)
            return

        P.vgrad(0, 0, L, H, "#4fb0dc", "#174a78", steps=14)
        P.poly([(-2, H), (-2, H - 3.5), (L * .3, H - 4.5), (L * .65, H - 3), (L + 2, H - 4.2), (L + 2, H)],
               "#e3c891", smooth=True)
        for sx, hh in ((5, 13), (L - 6, 10)):
            pts = [(sx + math.sin(t * 0.45 + j * 0.7 + sx) * j * 0.5, H - 3 - j * hh / 4) for j in range(5)]
            P.line(pts, "#3f9b6b", 1.6, smooth=True)
        for i in range(3):
            yy = H - 4 - ((t * 4 + i * 11) % (H - 4))
            P.oval(L * 0.22 + i * 2 + math.sin(t + i) * 1.2, yy, 0.8, 0.8, outline="#d9f3ff", w=0.4)

        main = [a for a in agents if not a.get("sub")]
        subs = [a for a in agents if a.get("sub") and a["state"] == "working"]
        work, sleep, wait = scenes.split(main)

        # resting fish along the sand, from the left
        fk = min(0.55, H / 60)
        n_fit = max(1, int((L - 8) // 18))
        for j, a in enumerate(sleep[:n_fit]):
            sp, col = scene.look(a, present)
            x, y = 11 + j * 18, H - 6.5 * fk / 0.55
            scene.fish(P, sp, x, y, 1, col, t, scenes.ident(a)["ph"], awake=False, k=fk)
            P.hit(x - 9, y - 6, x + 9, y + 6, a)
            if a["id"] in bars:  # just finished: full green bar for a moment
                P.bar(x, y - 9, 14, 1.8, bars[a["id"]][0], scenes.BAR_DONE)
        extra = len(sleep) - n_fit
        if extra > 0:
            P.text(L - 4, H - 6, f"+{extra}", "#eaf6ff", size=5, bold=True, anchor="e")

        # swimmers, spread out like in the big tank
        swimmers = work + subs
        self.pos.TOP, self.pos.BOT = 4, H - 14
        self.pos.SWIM_SPEED = scene.SWIM_SPEED * 1.6  # same pace across a shorter tank
        dt = 0 if self.pos.last_t is None else min(0.3, t - self.pos.last_t)
        self.pos.last_t = t
        slots = self.pos.place_swimmers(swimmers, t, dt)
        sk = min(0.72, H / 46)
        m = 12
        for a in swimmers:
            sp, col = scene.look(a, present)
            kk = sk * (0.7 if a.get("sub") else 1.0)
            off, lane = slots[a["id"]]
            p = (t * self.pos.SWIM_SPEED + off) % 1
            x = m + (0.5 - 0.5 * math.cos(2 * math.pi * p)) * (L - 2 * m)
            d = 1 if p < 0.5 else -1
            y = lane + 0.8 * math.sin(t * 0.35 + scenes.ident(a)["ph"] * 6)
            scene.fish(P, sp, x, y, d, col, t, scenes.ident(a)["ph"], awake=True, k=kk)
            P.hit(x - 12 * kk, y - 9 * kk, x + 12 * kk, y + 9 * kk, a)
            if a["id"] in bars:
                v, done = bars[a["id"]]
                P.bar(x, y + 8 * kk, 18 * kk, 2, v, scenes.progress_colour(v, done))

        for j, a in enumerate(wait):  # needs you: front and centre with a "!"
            sp, col = scene.look(a, present)
            x, y = L / 2 + (j - (len(wait) - 1) / 2) * 24, H / 2 + math.sin(t * 1.5)
            scene.fish(P, sp, x, y, 1, col, t, scenes.ident(a)["ph"], awake=True, k=sk)
            scenes.alert(P, x + 11 * sk, y - 9 * sk, t, k=0.55)
            P.hit(x - 12, y - 9, x + 12, y + 9, a)
        self.hits = P.hits

    def hover(self):
        """Hovering a character previews its card on top of the pinned stack."""
        a = None
        if self.mouse and not self.on_icon(*self.mouse):
            a = self.agent_at(*self.mouse)
        self.hover_id = a["id"] if a and a["id"] not in self.pins else None

    # ----- pinned status cards -----
    def who(self, a):
        """Which character this chat is on the strip."""
        return getattr(self.cast, "last_names", {}).get(a["id"]) or self.cast.who.get(a["id"])

    def star(self, px):
        """The star picture at px pixels tall (falls back to a drawn star)."""
        px_key = (cast.star_path(), px)
        if px_key in self.star_img:
            return self.star_img[px_key]
        img = None
        path = cast.star_path()
        if cast.Image is not None and os.path.exists(path):
            src = cast.Image.open(path, formats=["PNG"]).convert("RGBA")
            w = max(1, round(src.width * px / src.height))
            img = cast.ImageTk.PhotoImage(src.resize((w, px), cast.Image.LANCZOS), master=self.c)
        self.star_img[px_key] = img
        return img

    def draw_stars(self):
        """A small star floating above each character whose card is pinned.

        The character keeps cast.STAR_ROOM free above its head while pinned,
        so the star never touches it (bbox to bbox there's always a gap).
        """
        c, k = self.c, self.k
        size = int(cast.STAR * k)
        bob = math.sin(time.monotonic() * 0.9) * 0.3 * k
        img = self.star(size)
        for x0, y0, x1, y1, a in self.hits:
            if a["id"] not in self.pins:
                continue
            x = (x0 + x1) / 2
            y = y0 - cast.STAR_GAP * k - size / 2 + bob  # bottom of the star sits above the head
            ix0, iy0, ix1, iy1 = self.icon_box
            if x + size / 2 > ix0 and y - size / 2 < iy1:  # would sit under the pop-out icon
                x = ix0 - size / 2 - k
            if img is not None:
                c.create_image(x, y, image=img)
            else:
                pts = []
                for i in range(10):
                    r = size / 2 if i % 2 == 0 else size / 4.5
                    ang = -math.pi / 2 + i * math.pi / 5
                    pts += [x + r * math.cos(ang), y + r * math.sin(ang)]
                c.create_polygon(pts, fill="#f5c542", outline="#c99a1e")

    def draw_pins(self):
        """Pinned cards stacked above the strip, left-aligned with it (see cards.PinStack)."""
        agents = [self.by_id[i] for i in self.pins if i in self.by_id]
        preview = self.hover_id if self.hover_id in self.by_id else None
        if preview:
            agents.append(self.by_id[preview])  # ready to be added: shown on top
        self.stack.show(agents if self.shown else [], preview, self.bars, self.who)
