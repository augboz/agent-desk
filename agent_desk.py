"""Agent Desk: your Claude Code sessions as characters, on the taskbar and in a window.

- Up to 5 characters sit on the taskbar: asleep while a session is idle,
  bouncing with a progress bar while it works. Hover one for its name.
- The big window opens only when you click the little icon in the strip's
  top-right corner, and closes the same way (or with its x).

Run:  double-click "Agent Desk.cmd"   (or: pythonw agent_desk.py)
      python agent_desk.py --demo     fake agents, to try it out
"""
import ctypes
import ctypes.wintypes
import json
import math
import os
import sys
import tkinter as tk
import traceback

import paths
from desk_window import DemoAgents, DeskWindow, LiveAgents, log_error
from taskbar_strip import TaskbarStrip

CONFIG_VERSION = 3

OWN_PICTURES_HELP = """The built-in wizards, skiers and animals are only basic placeholders. Your own pictures look far better, and it's quick:

1. Drop pictures into the folder that opens next:
   {folder}

   Just one picture per character, e.g.  fox.png
   (asleep, it's shown a bit greyed out), or two:  fox awake.png  and  fox asleep.png
   Up to 5 characters show at once.

   A transparent or plain white background works best.

2. Right-click the strip → Characters → My own pictures.

That's it. Add, change or remove pictures any time and the strip updates by itself. Your pictures stay on your computer."""


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clean_config(raw):
    """Only the settings we know, of the right types and sane sizes.

    A hand-edited or half-written config.json must never stop the app from
    starting: anything odd is dropped and its default used instead.
    """
    if not isinstance(raw, dict) or raw.get("version") != CONFIG_VERSION:
        return {}
    out = {"version": CONFIG_VERSION}
    for key in ("x", "y", "strip_x"):
        if _num(raw.get(key)) and abs(raw[key]) < 100_000:
            out[key] = int(raw[key])
    for key, lo, hi in (("w", 120, 4000), ("h", 70, 3000)):
        if _num(raw.get(key)):
            out[key] = int(min(max(raw[key], lo), hi))
    for key in ("names", "topmost", "strip", "animate"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    for key in ("scene", "strip_style", "theme"):
        if isinstance(raw.get(key), str) and len(raw[key]) < 40:
            out[key] = raw[key]
    for key in ("chars", "fish"):
        v = raw.get(key)
        if isinstance(v, dict):
            out[key] = {k: c for k, c in list(v.items())[:200] if isinstance(k, str) and isinstance(c, str)}
    sp = raw.get("strip_spot")
    if isinstance(sp, dict) and _num(sp.get("x")) and _num(sp.get("w")) and 0 < sp["w"] < 20_000:
        out["strip_spot"] = {"x": int(sp["x"]), "w": int(sp["w"])}
    return out


def load_config(path=None):
    path = path or paths.CONFIG
    try:
        if os.path.getsize(path) > 1_000_000:
            return {}
        with open(path, encoding="utf-8") as f:
            return clean_config(json.load(f))
    except (OSError, ValueError):
        return {}


def save_config(cfg, path=None):
    """Write to a temp file, then swap it in: a crash mid-save can't wipe your settings."""
    path = path or paths.CONFIG
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def work_area():
    r = ctypes.wintypes.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
        return r.left, r.top, r.right, r.bottom
    return 0, 0, 1920, 1040


def single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\AgentDeskSingleton")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


class App:
    def __init__(self, root, demo):
        self.root, self.demo = root, demo
        cfg = {} if demo else load_config()
        self.cfg = cfg
        self.provider = DemoAgents() if demo else LiveAgents()
        self.use_strip = tk.BooleanVar(value=cfg.get("strip", True))
        self.use_cast = tk.BooleanVar(value=cfg.get("strip_style", "cast") == "cast")
        self.animate = tk.BooleanVar(value=cfg.get("animate", False))  # off: lightest on the PC
        self.look = tk.StringVar()  # a theme name, or "fish"
        self.own_sig, self.own_busy, self.own_done = None, False, False  # your own pictures
        self.chars = dict(cfg.get("chars", {}))
        k = max(1.0, round(root.winfo_fpixels("1i") / 96 * 2) / 2)
        w, h = cfg.get("w", 260), cfg.get("h", 140)
        x, y = cfg.get("x"), cfg.get("y")
        l, t, r, b = work_area()
        if x is None or y is None or not (l <= x < r - 60 and t <= y < b - 60):
            x, y = int(l + 120 * k), int(b - h * k - 12 * k)

        options = [None, ("cascade", "Characters", self.look_items),
                   ("cmd", "Use your own pictures…", self.own_pictures_help),
                   ("check", "Animations", self.animate, self.set_animate),
                   ("check", "Show on the taskbar", self.use_strip, self.toggle_strip)]
        import cast
        import scenes
        cast.ANIMATE = self.animate.get()
        cast.shared(self.chars)  # tank and strip share one cast and your picks
        theme = cast.set_theme(cfg.get("theme"))
        self.look.set(theme if self.use_cast.get() else "fish")
        scene = cfg.get("scene", "cast")
        if scene not in scenes.SCENES:
            scene = "aquarium"
        self.desk = DeskWindow(root, self.provider, scene, size=(w, h),
                               pos=(x, y), show_names=cfg.get("names", False),
                               topmost=cfg.get("topmost", True), fish=cfg.get("fish", {}),
                               on_change=lambda win: self.save(),
                               on_hide=lambda win: self.hide_tank(),
                               on_close=lambda win: self.quit(), extra_menu=options)
        self.strip = None
        if self.use_strip.get():
            self.make_strip()

        # The big window stays hidden until you click the strip's icon
        # (unless the strip is switched off, then the window is all there is).
        if self.strip:
            self.desk.win.withdraw()
        if not demo:
            self.root.after(3000, self.watch_own_pictures)

    def make_strip(self):
        options = [("cmd", "Show / hide the big window", self.toggle_tank), None,
                   ("check", "Start with Windows", self.desk.startup, self.desk.toggle_startup),
                   None,
                   ("cascade", "Characters", self.look_items),
                   ("cmd", "Use your own pictures…", self.own_pictures_help),
                   ("check", "Animations", self.animate, self.set_animate),
                   ("check", "Show on the taskbar", self.use_strip, self.toggle_strip),
                   ("cmd", "Quit Agent Desk", self.quit)]
        self.strip = TaskbarStrip(self.root, self.provider, self.desk,
                                  offset=self.cfg.get("strip_x"), on_click=self.toggle_tank,
                                  on_change=self.save, menu_items=options,
                                  is_open=self.tank_open, chars=self.chars,
                                  style="cast" if self.use_cast.get() else "fish",
                                  spot=self.cfg.get("strip_spot"))

    # ----- tank -----
    def tank_open(self):
        return self.desk.win.state() != "withdrawn"

    def show_tank(self):
        if self.tank_open():
            return
        win = self.desk.win
        win.deiconify()
        self.keep_on_screen()
        if self.desk.topmost.get():
            win.attributes("-topmost", True)
        win.lift()

    def hide_tank(self):
        if not self.strip:  # nothing to bring it back with: quit instead
            self.quit()
            return
        self.desk.win.withdraw()

    def toggle_tank(self):
        if self.tank_open():
            self.hide_tank()
        else:
            self.show_tank()

    def keep_on_screen(self):
        """After a monitor or resolution change the saved spot may be off-screen."""
        win = self.desk.win
        l, t, r, b = work_area()
        x, y, w, h = win.winfo_x(), win.winfo_y(), win.winfo_width(), win.winfo_height()
        nx, ny = min(max(x, l), r - w), min(max(y, t), b - h)
        if (nx, ny) != (x, y):
            win.geometry(f"+{int(nx)}+{int(ny)}")

    def set_animate(self):
        """Hopping, drifting z's and clouds. Off, the characters still wake up and
        fall asleep, but nothing else moves and the app barely uses the CPU."""
        import cast
        cast.ANIMATE = self.animate.get()
        for w in (self.strip, self.desk):
            if w:
                w.soon()
        self.save()

    def look_items(self):
        """The Characters sub-menu: your own pictures, the basic themes, then the fish."""
        import cast
        items = [("radio", "My own pictures", self.look, "mine", self.set_look)]
        items += [("radio", cast.THEME_LABELS[k] + "  (basic)", self.look, k, self.set_look)
                  for k in cast.themes() if k != "mine"]
        return [*items, None, ("radio", "Fish (drawn)", self.look, "fish", self.set_look)]

    def set_look(self):
        import cast
        look = self.look.get()
        if look == "mine" and not self.own_pictures_ready():
            return  # nothing to show yet: the guide is up, and the old look stays
        self.use_cast.set(look != "fish")
        if look != "fish":
            cast.set_theme(look)
        if self.strip:
            self.strip.style.set("cast" if self.use_cast.get() else "fish")
            self.strip.set_style()
        self.save()

    # ----- your own pictures -----
    def own_pictures_ready(self):
        """Make sure your pictures are turned into characters. False (and the guide
        is shown) when there aren't any yet."""
        import cast
        try:
            import make_characters as mc
        except ImportError:  # no Pillow
            return "mine" in cast.themes()
        if mc.find_pictures(mc.SOURCES) and mc.signature() != self.own_sig:
            self.own_sig = mc.signature()
            mc.build(log=lambda line: None)  # a few pictures: well under a second
        if "mine" in cast.themes():
            return True
        self.look.set(cast.THEME if self.use_cast.get() else "fish")
        self.own_pictures_help()
        return False

    def watch_own_pictures(self):
        """While you use your own pictures, pick up new or changed ones by themselves."""
        import threading

        import cast
        try:
            import make_characters as mc
            if cast.THEME == "mine" and not self.own_busy and mc.signature() != self.own_sig:
                self.own_sig, self.own_busy = mc.signature(), True

                def work():
                    try:
                        mc.build(log=lambda line: None)
                    except Exception:
                        log_error(traceback.format_exc())
                    self.own_done = True
                threading.Thread(target=work, daemon=True).start()
            if self.own_done:  # finished building: show the new cast (on the Tk thread)
                self.own_done = self.own_busy = False
                cast.set_theme("mine")
        except ImportError:
            pass
        except Exception:
            log_error(traceback.format_exc())
        self.root.after(3000, self.watch_own_pictures)

    def own_pictures_help(self):
        """Explain how to use your own pictures, and open the folder they go in."""
        from tkinter import messagebox

        import make_characters as mc
        try:
            os.makedirs(mc.SOURCES, exist_ok=True)
        except OSError:
            pass
        messagebox.showinfo("Use your own pictures", OWN_PICTURES_HELP.format(folder=mc.SOURCES))
        try:
            os.startfile(mc.SOURCES)
        except OSError:
            pass

    def toggle_strip(self):
        if self.use_strip.get() and not self.strip:
            self.make_strip()
        elif not self.use_strip.get() and self.strip:
            self.strip.win.destroy()
            self.strip = None
            self.show_tank()
        self.save()

    # ----- settings -----
    def save(self):
        if self.demo:
            return
        try:
            st = self.desk.state()
        except tk.TclError:
            return
        import cast
        st.update(version=CONFIG_VERSION, strip=self.use_strip.get(), chars=self.chars,
                  strip_style="cast" if self.use_cast.get() else "fish", theme=cast.THEME,
                  animate=self.animate.get())
        if self.strip and self.strip.spot:
            st["strip_spot"] = self.strip.spot
        elif "strip_spot" in self.cfg:
            st["strip_spot"] = self.cfg["strip_spot"]
        if self.strip and self.strip.offset is not None:
            st["strip_x"] = self.strip.offset
        elif "strip_x" in self.cfg:
            st["strip_x"] = self.cfg["strip_x"]
        self.cfg = st
        save_config(st)

    def quit(self):
        self.save()
        self.root.destroy()


def main():
    demo = "--demo" in sys.argv
    paths.ensure_data_dir()
    if not demo and not single_instance():
        return
    root = tk.Tk()
    root.withdraw()
    root.report_callback_exception = lambda *exc: log_error("".join(traceback.format_exception(*exc)))
    try:
        App(root, demo)
    except Exception:  # pythonw has no console: leave a note in the log, not just nothing
        log_error(traceback.format_exc())
        raise
    try:
        root.mainloop()
    except Exception:
        log_error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
