"""The look of the status cards, shared by the taskbar strip and the big window.

Cloud-white cards with a soft sky-blue edge: the character's round face
(ringed in the state colour), the chat name, and the state drawn as a small
symbol: drifting grey z's (napping), three softly glowing dots (working) or
a ❗ (needs you).
"""
import math
import os
import time
import tkinter.font as tkfont

import cast
import scenes
from frame_canvas import FrameCanvas

STATE_DOT = {"working": "#3fcf7f", "sleeping": "#7fb8e6", "waiting": "#ffa62b"}
CARD_BG, CARD_EDGE = "#ffffff", "#a9d6f5"
CARD_GHOST, CARD_GHOST_EDGE = "#eef7fe", "#6fb8ea"  # hover preview, not pinned yet
CARD_TEXT, CARD_MUTED = "#1f2d3a", "#7d93a6"
CARD_TRACK, CARD_TRACK_EDGE = "#e6f3fc", "#b7dbf3"
ZZZ_GREY = "#9a9a9a"  # the sleepy z's on the cards
STATE_W = 14  # logical px the state symbol takes up

_images = {}  # (kind, canvas, ...) -> PhotoImage (Tk drops images nobody holds on to)


def face_image(master, who, px):
    """Round face picture of character `who`, px pixels across, or None."""
    if not who or cast.Image is None:
        return None
    key = ("face", str(master), cast.DIR, who, px)
    if key not in _images:
        path = os.path.join(cast.DIR, who, "face.png")
        img = None
        if os.path.exists(path):
            src = cast.Image.open(path, formats=["PNG"]).convert("RGBA")
            img = cast.ImageTk.PhotoImage(src.resize((px, px), cast.Image.LANCZOS), master=master)
        _images[key] = img
    return _images[key]


def emoji_image(master, ch, px):
    """A colour emoji as an image (Tk can only draw emoji in black and white)."""
    key = ("emoji", str(master), ch, px)
    if key not in _images:
        img = None
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            font = ImageFont.truetype("seguiemj.ttf", px * 2)
            im = Image.new("RGBA", (px * 4, px * 4), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((px, px), ch, font=font, embedded_color=True)
            im = im.crop(im.getbbox())
            s = px / max(im.width, im.height)
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
            img = ImageTk.PhotoImage(im, master=master)
        except Exception:
            pass
        _images[key] = img
    return _images[key]


def draw_face(c, k, who, state, fx, cy, fs):
    """Face of size fs with its left edge at fx, centred on cy, in a state-colour ring."""
    ring = STATE_DOT.get(state, "#ccc")
    c.create_oval(fx - 1.2 * k, cy - fs / 2 - 1.2 * k, fx + fs + 1.2 * k, cy + fs / 2 + 1.2 * k,
                  fill=ring, outline="")
    img = face_image(c, who, int(fs))
    if img is not None:
        c.create_image(fx + fs / 2, cy, image=img)
    else:  # no picture (e.g. the aquarium): a plain dot in the ring
        c.create_oval(fx + fs * 0.25, cy - fs * 0.25, fx + fs * 0.75, cy + fs * 0.25,
                      fill=CARD_BG, outline="")


def draw_state(c, k, state, right, cy):
    """The state symbol, right-aligned at x=right."""
    t = time.monotonic() if cast.ANIMATE else 0.0
    if state == "working":
        r = 1.5 * k
        for i in range(3):  # three still dots; a gentle, slow glow passes along them
            x = right - (2 - i) * 4.4 * k - r
            glow = max(0.0, math.sin(t * 1.1 - i * 0.9)) * 0.3
            c.create_oval(x - r, cy - r, x + r, cy + r, fill=scenes.mix(CARD_MUTED, CARD_TEXT, glow),
                          outline="")
        return
    if state == "sleeping":  # the same drifting grey z's as over the sleepers
        for i in range(3):
            q = (t * 0.12 + i / 3) % 1
            c.create_text(right - 11 * k + q * 6 * k, cy + 2 * k - q * 4 * k, text="z", fill=ZZZ_GREY,
                          font=("Segoe UI Semibold", -max(6, int((5 + q * 2) * k))))
        return
    img = emoji_image(c, "❗", int(11 * k))
    if img is not None:
        c.create_image(right, cy, image=img, anchor="e")
    else:
        c.create_text(right, cy, text="!", anchor="e", fill=CARD_MUTED,
                      font=("Segoe UI Semibold", -int(8 * k)))


def star_image(master, px):
    """The pinned star (characters/star.png) px pixels tall, or None."""
    key = ("star", str(master), cast.star_path(), px)
    if key not in _images:
        img = None
        path = cast.star_path()
        if cast.Image is not None and os.path.exists(path):
            src = cast.Image.open(path, formats=["PNG"]).convert("RGBA")
            w = max(1, round(src.width * px / src.height))
            img = cast.ImageTk.PhotoImage(src.resize((w, px), cast.Image.LANCZOS), master=master)
        _images[key] = img
    return _images[key]


def draw_star(c, k, x, y, size):
    """A star centred on (x, y), size px tall."""
    img = star_image(c, int(size))
    if img is not None:
        c.create_image(x, y, image=img)
        return
    pts = []
    for i in range(10):
        r = size / 2 if i % 2 == 0 else size / 4.5
        ang = -math.pi / 2 + i * math.pi / 5
        pts += [x + r * math.cos(ang), y + r * math.sin(ang)]
    c.create_polygon(pts, fill="#f5c542", outline="#c99a1e")


class PinStack:
    """The pinned status cards, stacked upwards just above a window, left-aligned
    with it (used by the taskbar strip and by the big window).

    The first one you pinned sits just above the window, the next one above
    that, and so on. Each shows the character's face, the chat name, and the
    state right next to its progress bar on the right. A hover preview (dashed)
    goes on top.
    """

    def __init__(self, owner):
        import tkinter as tk
        self.tk, self.owner = tk, owner
        self.win = None
        self.k = max(1.0, round(owner.winfo_fpixels("1i") / 96 * 2) / 2)

    def hide(self):
        if self.win is not None and self.win.state() != "withdrawn":
            self.win.withdraw()

    def show(self, agents, preview, bars, who, topmost=True):
        """agents: pinned, oldest first; preview: id of the hovered one (in agents) or None."""
        if not agents:
            self.hide()
            return
        tk, k = self.tk, self.k
        if self.win is None:
            self.win = tk.Toplevel(self.owner)
            self.win.overrideredirect(True)
            self.win.attributes("-transparentcolor", "#010203")
            self.c = FrameCanvas(self.win, highlightthickness=0, bd=0, bg="#010203")
            self.c.pack(fill="both", expand=True)
            self.font = tkfont.Font(root=self.win, family="Segoe UI Semibold", size=-int(9 * k))
        if bool(self.win.attributes("-topmost")) != bool(topmost):
            self.win.attributes("-topmost", topmost)
        c = self.c
        c.begin()
        f_name = ("Segoe UI Semibold", -int(9 * k))
        text_h = self.font.metrics("linespace")
        row_h0 = int(17 * k)
        face_px = row_h0 - int(3 * k)
        pad, dot, gap, bar_w = 2.5 * k, face_px + 4 * k, 5 * k, 34 * k
        rows = []
        for a in agents:
            name = " ".join(str(a.get("name") or "").split()) or "?"
            name = name if len(name) <= 34 else name[:33] + "\u2026"
            tw = pad + dot + self.font.measure(name) + 3 * gap + STATE_W * k + gap + bar_w + pad + 2 * k
            rows.append((a, name, tw, max(row_h0, text_h + 5 * k)))
        card_w = int(max(r[2] for r in rows))
        row_h = int(max(r[3] for r in rows))
        step = row_h + int(3 * k)
        total = step * len(rows)
        for i, (a, name, tw, _) in enumerate(rows):
            y0 = total - (i + 1) * step  # first pinned at the bottom
            y1, cy = y0 + row_h, y0 + row_h / 2
            if a["id"] == preview:  # hover preview: dashed and dimmer, not pinned yet
                scenes.round_rect(c, 1, y0 + 1, card_w - 1, y1 - 1, row_h / 2,
                                  fill=CARD_GHOST, outline=CARD_GHOST_EDGE, width=1, dash=(3, 2))
            else:
                scenes.round_rect(c, 1, y0 + 1, card_w - 1, y1 - 1, row_h / 2,
                                  fill=CARD_BG, outline=CARD_EDGE, width=1)
            draw_face(c, k, who(a), a["state"], pad + 1.5 * k, cy, face_px)
            bx1 = card_w - pad - 2 * k
            bx0, bh = bx1 - bar_w, 3.4 * k
            c.create_text(pad + dot, cy, text=name, anchor="w", fill=CARD_TEXT, font=f_name)
            draw_state(c, k, a["state"], bx0 - gap, cy)
            if a["id"] in bars:
                v, done = bars[a["id"]]
                col = scenes.progress_colour(v, done)
            else:
                v, col = 0.0, "#7fb8e6"
            scenes.round_rect(c, bx0, cy - bh / 2, bx1, cy + bh / 2, bh / 2,
                              fill=CARD_TRACK, outline=CARD_TRACK_EDGE, width=1)
            if v > 0.01:
                fw = max(bh, bar_w * min(1.0, v))
                scenes.round_rect(c, bx0 + 1, cy - bh / 2 + 1, bx0 + fw - 1, cy + bh / 2 - 1,
                                  bh / 2 - 1, fill=col, outline="")
        x = self.owner.winfo_rootx()
        y = self.owner.winfo_rooty() - total - int(3 * k)
        if y < 0:  # no room above (window at the top of the screen): just below it instead
            y = self.owner.winfo_rooty() + self.owner.winfo_height() + int(3 * k)
        geo = f"{card_w}x{total}+{x}+{y}"
        if self.win.state() == "withdrawn":
            self.win.deiconify()
        if self.win.geometry() != geo:
            self.win.geometry(geo)
        c.end()
