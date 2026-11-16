"""Open all four scene prototypes side by side.

    python prototypes.py          demo agents that change state every few seconds
    python prototypes.py --live   your real Claude Code sessions
"""
import ctypes
import ctypes.wintypes
import sys
import tkinter as tk

from desk_window import DemoAgents, DeskWindow, LiveAgents

OPTIONS = [("slopes", "A"), ("desks", "B"), ("build", "C"), ("aquarium", "D")]


def work_area():
    r = ctypes.wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right, r.bottom


def main():
    root = tk.Tk()
    root.withdraw()
    provider = LiveAgents() if "--live" in sys.argv else DemoAgents()
    k = max(1.0, round(root.winfo_fpixels("1i") / 96 * 2) / 2)
    w, h = 300, 150
    l, t, r, b = work_area()
    open_wins = []

    def closed(win):
        open_wins.remove(win)
        if not open_wins:
            root.destroy()

    import scenes
    for i, (key, letter) in enumerate(OPTIONS):
        col, row = i % 2, i // 2
        x = int(r - (2 - col) * (w + 12) * k - 12 * k)
        y = int(b - (2 - row) * (h + 12) * k - 12 * k)
        win = DeskWindow(root, provider, key, label=f"{letter} · {scenes.SCENES[key].title}",
                         size=(w, h), pos=(x, y), on_close=closed)
        open_wins.append(win)
    root.mainloop()


if __name__ == "__main__":
    main()
