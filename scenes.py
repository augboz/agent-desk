"""Animated scenes for Agent Desk, drawn with smooth Tk canvas shapes.

Every scene works in a logical space H=180 units tall and L units wide
(L grows with the window width). Pen converts to canvas pixels.
States: "working", "sleeping", "waiting".
"""
import math
import random
import time

H = 180

COATS = ["#e4572e", "#2e86ab", "#f2a541", "#6a4c93", "#3bb273",
         "#e86a92", "#1b998b", "#f25f5c", "#4f6d7a", "#c97b2a"]
SKINS = ["#f3cfb1", "#e8b48f", "#c98e66", "#9a6644"]
HAIRS = ["#2b2118", "#5a3a22", "#9c5a2e", "#d4ae6a", "#1c1c1c", "#6e4630"]
CODE = ["#7cf2a0", "#8ec9f5", "#f7d96b", "#f5a3c0", "#c3b5ff"]
PANTS = "#323a48"


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    A, B = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(A, B))


def ident(a):
    r = random.Random(a.get("seed") or a.get("id"))
    return {"coat": r.choice(COATS), "skin": r.choice(SKINS), "hair": r.choice(HAIRS),
            "ph": r.random(), "sp": 0.85 + r.random() * 0.3}


def tri(p):
    return 1 - abs(2 * p - 1)


BAR_RED, BAR_ORANGE, BAR_GREEN, BAR_DONE = "#ff4b4b", "#ffa02e", "#7be36a", "#3ddc84"


def progress_colour(v, done=False):
    if done:
        return BAR_DONE
    if v < 0.2:
        return mix(BAR_RED, BAR_ORANGE, v / 0.2)
    if v < 0.7:
        return BAR_ORANGE
    return mix(BAR_ORANGE, BAR_GREEN, min(1.0, (v - 0.7) / 0.3))


def round_rect(c, x0, y0, x1, y1, r, **kw):
    """Rounded rectangle on a Tk canvas (smoothed polygon)."""
    r = max(1, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, splinesteps=8, **kw)


class Pen:
    def __init__(self, c, s):
        self.c, self.s, self.hits = c, s, []

    def _xy(self, pts):
        out = []
        for x, y in pts:
            out += [x * self.s, y * self.s]
        return out

    def rect(self, x0, y0, x1, y1, fill):
        s = self.s
        self.c.create_rectangle(x0 * s, y0 * s, x1 * s, y1 * s, fill=fill, outline="")

    def oval(self, cx, cy, rx, ry, fill="", outline="", w=1):
        s = self.s
        self.c.create_oval((cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s,
                           fill=fill, outline=outline, width=max(1, w * s) if outline else 0)

    def chord(self, cx, cy, r, fill, start=0, extent=180):
        s = self.s
        self.c.create_arc((cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s,
                          start=start, extent=extent, style="chord", fill=fill, outline="")

    def poly(self, pts, fill, smooth=False):
        self.c.create_polygon(*self._xy(pts), fill=fill, outline="", smooth=smooth,
                              splinesteps=12)

    def line(self, pts, fill, w=1, smooth=False):
        self.c.create_line(*self._xy(pts), fill=fill, width=max(1, w * self.s),
                           capstyle="round", joinstyle="round", smooth=smooth, splinesteps=12)

    def text(self, x, y, t, fill, size=6, bold=False, anchor="center"):
        font = ("Segoe UI Semibold" if bold else "Segoe UI", -max(7, int(size * self.s)))
        self.c.create_text(x * self.s, y * self.s, text=t, fill=fill, font=font, anchor=anchor)

    def vgrad(self, x0, y0, x1, y1, c0, c1, steps=28):
        hgt = (y1 - y0) / steps
        for i in range(steps):
            self.rect(x0, y0 + i * hgt, x1, y0 + (i + 1) * hgt + 0.6, mix(c0, c1, i / (steps - 1)))

    def tag(self, x, y, t, size=5.6, max_chars=18, L=None, dot=None):
        """Small rounded name pill centred on (x, y), with a dot in the fish's colour."""
        t = " ".join(str(t or "").split()) or "?"
        if len(t) > max_chars:
            t = t[:max_chars - 1] + "\u2026"
        s, c = self.s, self.c
        font = ("Segoe UI Semibold", -max(9, int(size * s)))
        tid = c.create_text(x * s, y * s, text=t, fill="#eaf6ff", font=font)
        x0, y0, x1, y1 = c.bbox(tid)
        hgt = y1 - y0
        dot_w = hgt * 0.75 if dot else 0
        c.move(tid, dot_w / 2, 0)
        x0, x1 = x0 + dot_w / 2 - dot_w, x1 + dot_w / 2
        if L is not None:  # keep the pill inside the window
            shift = max(0, 5 * s - x0) - max(0, x1 - (L - 5) * s)
            if shift:
                c.move(tid, shift, 0)
                x0, x1 = x0 + shift, x1 + shift
        pad = hgt * 0.45
        round_rect(c, x0 - pad, y0 - 1, x1 + pad, y1 + 1, hgt / 2,
                   fill="#0b2e4d", outline="#2f6a96", width=1)
        if dot:
            r = hgt * 0.2
            cx, cy = x0 + dot_w * 0.35, (y0 + y1) / 2
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=dot, outline="")
        c.tag_raise(tid)

    def bar(self, cx, y, w, h, frac, fill):
        """Rounded progress bar centred on cx."""
        s, c = self.s, self.c
        x0 = cx - w / 2
        round_rect(c, x0 * s, y * s, (x0 + w) * s, (y + h) * s, h * s / 2,
                   fill="#061a2c", outline="#7fb2d9", width=1)
        if frac > 0.01:
            fw = max(h, w * min(1.0, frac))
            round_rect(c, (x0 + 0.5) * s, (y + 0.5) * s, (x0 + fw - 0.5) * s, (y + h - 0.5) * s,
                       (h - 1) * s / 2, fill=fill, outline="")

    def hit(self, x0, y0, x1, y1, agent):
        s = self.s
        self.hits.append((x0 * s, y0 * s, x1 * s, y1 * s, agent))


# ---------- shared bits ----------

def zzz(P, x, y, t, color, k=1.0):
    for i in range(3):
        p = (t * 0.45 + i / 3) % 1
        P.text(x + p * 7 * k, y - p * 14 * k, "z", color, size=(4 + p * 4) * k, bold=True)


def alert(P, x, y, t, k=1.0):
    bob = math.sin(t * 1.2) * 0.5
    P.oval(x, y + bob, 5.5 * k, 5.5 * k, "#ffffff")
    P.poly([(x - 2 * k, y + 4 * k + bob), (x - 4 * k, y + 8.5 * k + bob), (x + 1 * k, y + 5 * k + bob)],
           "#ffffff")
    P.text(x, y + bob - 0.3, "!", "#ff8c1a", size=8 * k, bold=True)


def name_tag(P, x, y, text, color, show):
    if show:
        P.text(x, y, text if len(text) <= 14 else text[:13] + "…", color, size=5.6)


def head(P, x, y, r, idn, hat=None, hat_color=None, asleep=False, face=1, tilt=0):
    P.oval(x, y, r, r, idn["skin"])
    if hat == "beanie":
        P.chord(x, y - 0.4, r + 0.5, hat_color, start=0 + tilt, extent=180)
        P.oval(x + math.sin(math.radians(tilt)) * -r, y - r - 1, 1.3, 1.3, "#ffffff")
    elif hat == "hard":
        P.chord(x, y - 0.3, r + 0.6, "#f2c230", start=5 + tilt, extent=170)
        P.line([(x - (r + 1.8) * face * -1, y - 0.6), (x + (r + 2.4) * face, y - 0.6)], "#d9a91f", 1.1)
    else:
        P.chord(x, y - 0.2, r + 0.3, idn["hair"], start=10 + tilt, extent=170)
    if asleep:
        P.line([(x + face * (r * 0.25), y + 0.6), (x + face * (r * 0.75), y + 0.9)], "#3a2a22", 0.6)
    else:
        P.oval(x + face * r * 0.5, y + 0.4, 0.65, 0.75, "#2a1d16")


def overflow(P, L, n):
    if n > 0:
        P.tag(20, 11, f"+{n} resting", size=5.4, L=L)


def split(agents):
    w = [a for a in agents if a["state"] == "working"]
    s = [a for a in agents if a["state"] == "sleeping"]
    q = [a for a in agents if a["state"] == "waiting"]
    return w, s, q


# ---------- A: ski slope ----------

def pine(P, x, base, h, col):
    P.line([(x, base), (x, base - h * 0.25)], "#5b4636", max(0.8, h * 0.08))
    for i in range(3):
        wd = h * (0.42 - 0.1 * i)
        y0 = base - h * (0.18 + 0.24 * i)
        P.poly([(x - wd, y0), (x + wd, y0), (x, y0 - h * 0.42)], col)
    P.poly([(x - h * 0.08, base - h * 0.88), (x + h * 0.08, base - h * 0.88), (x, base - h)], "#f4f8fc")


class Slopes:
    title = "Slopes (ski down / lift up)"

    def draw(self, P, L, agents, t, names):
        P.vgrad(0, 0, L, H, "#8cc0ea", "#eaf3fb")
        P.oval(L - 30, 26, 10, 10, "#fff6dc")
        pk = [(0, 110), (L * .16, 56), (L * .31, 90), (L * .49, 44), (L * .67, 86), (L * .85, 52), (L, 94)]
        P.poly(pk + [(L, H), (0, H)], "#b4c6dc")
        for i in (1, 3, 5):
            px, py = pk[i]
            P.poly([(px, py), (px + 10, py + 12), (px + 5, py + 10), (px, py + 14),
                    (px - 5, py + 10), (px - 10, py + 12)], "#f2f6fb")
        P.poly([(0, 100), (L * .3, 84), (L * .6, 102), (L * .85, 90), (L, 104), (L, H), (0, H)],
               "#9fb4cc", smooth=True)

        ys = lambda x: 62 + 94 * x / L
        for fx, sz in ((0.1, 10), (0.19, 8), (0.4, 11), (0.7, 9), (0.9, 12)):
            x = fx * L
            pine(P, x, ys(x) + 1, sz, "#4a7565")
        P.poly([(0, ys(0)), (L, ys(L)), (L, H), (0, H)], "#f7fafd")
        P.poly([(0, ys(0) + 46), (L, ys(L) + 16), (L, H), (0, H)], "#eaf0f7")

        # chairlift
        xb, yb, xt, yt = L * 0.96, 104, L * 0.05, 18
        cab = lambda p: (xb + (xt - xb) * p, yb + (yt - yb) * p)
        for fx in (0.28, 0.55, 0.8):
            x = fx * L
            cy = yb + (yt - yb) * (x - xb) / (xt - xb)
            P.line([(x, cy - 2), (x, ys(x) + 7)], "#6b7280", 1.5)
            P.line([(x - 4, cy - 2), (x + 4, cy - 2)], "#6b7280", 1.3)
        P.line([cab(0), cab(1)], "#4b5563", 0.7)
        for hx in (xt, xb):
            hy = ys(hx) + 6
            P.rect(hx - 7, hy - 9, hx + 7, hy, "#8a5a3b")
            P.poly([(hx - 9, hy - 9), (hx + 9, hy - 9), (hx, hy - 15)], "#c0392b")

        work, sleep, wait = split(agents)
        n_ch = max(7, len(sleep) + 3)
        riders = {round(j * n_ch / max(1, len(sleep))) % n_ch: a for j, a in enumerate(sleep)}
        for k in range(n_ch):
            p = (k / n_ch + t * 0.03) % 1
            x, y = cab(p)
            self.chair(P, x, y, riders.get(k), t, names)

        for i, a in enumerate(work):
            idn = ident(a)
            pos = lambda p: (L * 0.06 + p * L * 0.86,
                             ys(L * 0.06 + p * L * 0.86) + 10 + 5 * math.sin(p * 2 * math.pi * 3 + i * 1.7))
            p = (i / max(1, len(work)) + t * 0.085) % 1
            trail = [pos(max(0, p - d * 0.015)) for d in range(9)]
            if len(trail) > 1:
                P.line(trail, "#d6e1ee", 0.9, smooth=True)
            x, y = pos(p)
            self.skier(P, x, y, idn, t, L)
            P.hit(x - 7, y - 28, x + 9, y + 2, a)
            name_tag(P, x, y + 6, a["project"], "#5c6f86", names)

        for j, a in enumerate(wait):
            idn = ident(a)
            x = L * 0.86 - j * 12
            y = ys(x) + 16
            self.stander(P, x, y, idn, t)
            alert(P, x + 6, y - 32, t)
            P.hit(x - 5, y - 30, x + 5, y, a)
            name_tag(P, x, y + 6, a["project"], "#5c6f86", names)

    def skier(self, P, x, y, idn, t, L):
        ang = math.atan2(94, L)
        ux, uy = math.cos(ang), math.sin(ang)
        P.line([(x - 9 * ux, y - 9 * uy), (x + 10 * ux, y + 10 * uy)], "#2b2f36", 1.2)
        P.line([(x + 10 * ux, y + 10 * uy), (x + 11.5 * ux + 0.4, y + 9 * uy - 0.8)], "#2b2f36", 1.2)
        knee, hip, sh = (x + 3, y - 5.5), (x - 2, y - 10), (x + 1.5, y - 18)
        P.line([(x - 1, y - 0.5), knee, hip], PANTS, 3.2)
        P.line([hip, sh], idn["coat"], 5.6)
        wob = math.sin(t * 9 + idn["ph"] * 6) * 1.2
        P.line([(x + 0.5, y - 19.5), (x - 3.5, y - 19 + wob), (x - 7, y - 18.5 - wob)],
               mix(idn["coat"], "#ffffff", 0.45), 1.4, smooth=True)
        P.line([(x + 6, y - 13), (x - 5, y - 1)], "#6b7280", 0.6)
        P.line([sh, (x + 6, y - 13)], idn["coat"], 2.2)
        head(P, x + 3.5, y - 22.5, 3.4, idn, hat="beanie", hat_color=mix(idn["coat"], "#1b1b1b", 0.25))
        P.line([(x + 4.5, y - 22.6), (x + 7, y - 22.6)], "#273142", 1.2)

    def chair(self, P, x, y, a, t, names):
        P.line([(x, y), (x + 4, y + 5), (x + 4, y + 14)], "#4b5563", 0.9)
        P.line([(x - 6, y + 14), (x + 4, y + 14)], "#4b5563", 1.2)
        if not a:
            return
        idn = ident(a)
        P.line([(x + 1.5, y + 13), (x - 4, y + 13), (x - 4.5, y + 18.5)], PANTS, 2.8)
        P.line([(x - 8, y + 19.5), (x + 0.5, y + 19)], "#2b2f36", 1)
        P.line([(x + 2, y + 12.5), (x + 2, y + 5.5)], idn["coat"], 4.8)
        head(P, x + 1, y + 2, 2.9, idn, hat="beanie", hat_color=mix(idn["coat"], "#1b1b1b", 0.25),
             asleep=True, face=-1)
        zzz(P, x + 4, y - 2, t + idn["ph"] * 3, "#ffffff", 0.8)
        P.hit(x - 8, y - 2, x + 6, y + 20, a)
        name_tag(P, x - 1, y + 24, a["project"], "#5c6f86", names)

    def stander(self, P, x, y, idn, t):
        P.line([(x - 1.5, y), (x - 1, y - 10)], PANTS, 2.8)
        P.line([(x + 1.5, y), (x + 1, y - 10)], PANTS, 2.8)
        P.line([(x, y - 10), (x, y - 19)], idn["coat"], 5.6)
        wave = math.sin(t * 8) * 2
        P.line([(x + 1, y - 18), (x + 5 + wave * 0.3, y - 26 + abs(wave) * 0.3)], idn["coat"], 2.2)
        head(P, x, y - 23, 3.4, idn, hat="beanie", hat_color=mix(idn["coat"], "#1b1b1b", 0.25))


# ---------- B: office desks ----------

class Desks:
    title = "Office (own desks)"
    SLOT = 74

    def draw(self, P, L, agents, t, names):
        P.vgrad(0, 0, L, 140, "#f2e8d6", "#e6d6bc")
        n_fit = max(1, int((L - 8) // self.SLOT))
        shown = agents[:n_fit]
        x0 = (L - len(shown) * self.SLOT) / 2
        for i in range(len(shown)):
            cx = x0 + self.SLOT * (i + 0.5)
            self.window(P, cx, t)
        P.rect(0, 136, L, 141, "#cbb391")
        P.vgrad(0, 141, L, H, "#b98b5d", "#a4774b", steps=10)
        for gx in range(-20, int(L) + 40, 34):
            P.line([(gx, 141), (gx - 12, H)], "#a87c50", 0.5)
        if not shown:
            P.text(L / 2, 100, "nobody in today", "#9b8566", size=8)
        for i, a in enumerate(shown):
            self.desk(P, x0 + self.SLOT * (i + 0.5), a, t, names)
        overflow(P, L, len(agents) - len(shown))

    def window(self, P, cx, t):
        P.rect(cx - 17, 30, cx + 17, 72, "#d9c7a8")
        P.vgrad(cx - 15, 32, cx + 15, 70, "#9fd0f2", "#dff0fb", steps=8)
        P.oval(cx - 4 + 3 * math.sin(t * 0.05 + cx), 44, 6, 2.4, "#ffffff")
        P.line([(cx, 32), (cx, 70)], "#d9c7a8", 1.4)
        P.line([(cx - 15, 51), (cx + 15, 51)], "#d9c7a8", 1.4)

    def desk(self, P, cx, a, t, names):
        idn = ident(a)
        st = a["state"]
        on = st == "working"
        # chair
        P.line([(cx - 28, 100), (cx - 26, 122)], "#3a3f47", 2.6)
        P.line([(cx - 27, 122), (cx - 12, 122)], "#3a3f47", 2.6)
        P.line([(cx - 20, 122), (cx - 20, 134)], "#3a3f47", 1.5)
        P.line([(cx - 27, 136), (cx - 13, 136)], "#3a3f47", 1.4)
        # desk
        P.line([(cx - 20, 114), (cx - 20, 140)], "#6e472c", 2)
        P.line([(cx + 27, 114), (cx + 27, 140)], "#6e472c", 2)
        # monitor
        P.line([(cx + 12, 110), (cx + 12, 103)], "#2d3138", 1.8)
        P.line([(cx + 7, 110), (cx + 17, 110)], "#2d3138", 1.4)
        P.rect(cx - 1, 80, cx + 25, 103, "#2d3138")
        P.rect(cx + 1, 82, cx + 23, 101, "#1d3550" if on else "#15181c")
        if on:
            r = random.Random(f"{a.get('seed')}{int(t * 3)}")
            for j in range(5):
                yy = 84.5 + j * 3.3
                P.line([(cx + 3, yy), (cx + 3 + r.uniform(3, 17), yy)], r.choice(CODE), 1.0)
        # mug
        P.rect(cx - 7, 104, cx - 2, 110, "#f4f1ea")
        if on:
            for j in range(2):
                ph = t * 2 + j * 2
                P.line([(cx - 5.5 + j * 2, 102), (cx - 5 + j * 2 + math.sin(ph), 99),
                        (cx - 5.5 + j * 2, 96)], "#ffffff", 0.6, smooth=True)
        if st == "waiting":
            self.person_wave(P, cx, idn, t)
            alert(P, cx - 9, 76, t)
            P.hit(cx - 28, 82, cx - 14, 136, a)
        elif on:
            self.person_type(P, cx, idn, t)
            P.hit(cx - 24, 86, cx - 4, 136, a)
        else:
            self.person_sleep(P, cx, idn, t)
            P.hit(cx - 24, 96, cx + 2, 136, a)
        P.rect(cx - 26, 110, cx + 31, 114, "#8b5e3c")
        name_tag(P, cx + 2, 152, a["project"], "#f6e7cf", names)

    def person_type(self, P, cx, idn, t):
        bob = math.sin(t * 3 + idn["ph"] * 6) * 0.4
        P.line([(cx - 20, 120), (cx - 8, 120), (cx - 8, 136)], PANTS, 4)
        P.oval(cx - 6.5, 137, 2.8, 1.3, "#222")
        P.line([(cx - 20, 119), (cx - 18, 101 + bob)], idn["coat"], 8.5)
        tap = math.sin(t * 16 + idn["ph"] * 9) * 0.7
        P.line([(cx - 17, 103 + bob), (cx - 11, 111), (cx - 3, 109 + tap)], idn["coat"], 2.6)
        P.oval(cx - 2.2, 109 + tap, 1.4, 1.1, idn["skin"])
        head(P, cx - 16.5, 93 + bob, 5.2, idn)

    def person_sleep(self, P, cx, idn, t):
        br = math.sin(t * 1.5 + idn["ph"] * 6) * 0.5
        P.line([(cx - 20, 120), (cx - 8, 120), (cx - 8, 136)], PANTS, 4)
        P.oval(cx - 6.5, 137, 2.8, 1.3, "#222")
        P.line([(cx - 20, 119), (cx - 11, 106 + br)], idn["coat"], 8.5)
        P.oval(cx - 6, 108 + br * 0.3, 7, 2.8, idn["coat"])
        head(P, cx - 6, 103.5 + br * 0.5, 5, idn, asleep=True)
        zzz(P, cx - 1, 96, t + idn["ph"] * 3, "#8a7a63")

    def person_wave(self, P, cx, idn, t):
        P.line([(cx - 24, 136), (cx - 24, 118)], PANTS, 2.8)
        P.line([(cx - 20, 136), (cx - 20, 118)], PANTS, 2.8)
        P.line([(cx - 22, 118), (cx - 22, 100)], idn["coat"], 8.5)
        wv = math.sin(t * 8) * 2.5
        P.line([(cx - 19, 101), (cx - 13 + wv * 0.4, 89)], idn["coat"], 2.6)
        P.oval(cx - 13 + wv * 0.4, 88, 1.5, 1.5, idn["skin"])
        head(P, cx - 22, 92, 5.2, idn)


# ---------- C: construction site ----------

class Build:
    title = "Building site"

    def __init__(self):
        self.progress, self.last = 0.0, None

    def draw(self, P, L, agents, t, names):
        work, sleep, wait = split(agents)
        dt = 0 if self.last is None else min(0.2, t - self.last)
        self.last = t
        self.progress = (self.progress + dt * 0.18 * len(work)) % 11

        P.vgrad(0, 0, L, 150, "#f8c58c", "#fff2de")
        P.oval(L * 0.78, 42, 15, 15, "#fff8ea")
        P.poly([(-10, 150), (-10, 126), (L * .2, 110), (L * .45, 124), (L * .72, 106), (L + 10, 120),
                (L + 10, 150)], "#b7cf9e", smooth=True)
        P.rect(0, 148, L, H, "#cfa978")
        P.rect(0, 146, L, 150, "#93b56f")
        for gx in range(6, int(L), 23):
            P.oval(gx, 163 + (gx * 7) % 9, 1.6, 0.8, "#b8925f")

        bx0, bx1 = 14, 92
        xc = 70
        # crane (behind)
        P.line([(xc - 3, 148), (xc - 3, 24)], "#e09a2d", 1.4)
        P.line([(xc + 3, 148), (xc + 3, 24)], "#e09a2d", 1.4)
        for yy in range(30, 148, 10):
            P.line([(xc - 3, yy), (xc + 3, yy + 10)], "#e09a2d", 0.7)
        P.line([(xc - 52, 24), (xc + 34, 24)], "#e09a2d", 2.2)
        P.line([(xc, 24), (xc, 14), (xc - 52, 24)], "#e09a2d", 0.8)
        P.line([(xc, 14), (xc + 34, 24)], "#e09a2d", 0.8)
        P.rect(xc + 22, 24, xc + 32, 31, "#6b7280")
        tx = xc - 34 + 8 * math.sin(t * 0.35)
        sw = math.sin(t * 1.3) * 2
        P.line([(tx, 24), (tx + sw, 62)], "#4b5563", 0.6)
        P.rect(tx + sw - 6, 62, tx + sw + 6, 65, "#8b5e3c")
        for i in range(3):
            P.rect(tx + sw - 5 + i * 3.6, 58.5, tx + sw - 2 + i * 3.6, 62, "#c0623f")

        # brick wall
        rows = 3 + int(self.progress)
        P.rect(bx0, 148 - rows * 6, bx1, 148, "#e7d4b8")
        for r in range(rows):
            y = 148 - (r + 1) * 6
            off = 6 if r % 2 else 0
            for bx in range(bx0 - off, bx1, 12):
                xa, xb = max(bx, bx0) + 0.5, min(bx + 12, bx1) - 0.5
                if xb > xa:
                    shade = ("#c0623f", "#b5583a", "#c96b45")[(bx // 12 + r) % 3]
                    P.rect(xa, y + 0.5, xb, y + 5.5, shade)
        for px in (bx0 - 4, bx1 + 4):
            P.line([(px, 148), (px, 148 - rows * 6 - 10)], "#8d99a6", 1)
        for yy in range(148 - 18, 148 - rows * 6 - 12, -18):
            P.line([(bx0 - 6, yy), (bx1 + 6, yy)], "#a27a52", 1.4)

        # brick pile
        px = L - 30
        for r in range(3):
            for c in range(4 - r):
                P.rect(px - 13 + c * 7 + r * 3.5, 142 - r * 4.5, px - 7 + c * 7 + r * 3.5, 146 - r * 4.5,
                       "#c0623f")

        xa, xb = bx1 + 12, L - 46
        for i, a in enumerate(work):
            idn = ident(a)
            p = (t * 0.07 * idn["sp"] + idn["ph"]) % 1
            x = xb - tri(p) * max(10, xb - xa)
            d = -1 if p < 0.5 else 1
            y = 151 + (i % 3) * 2.5
            self.walker(P, x, y, d, idn, t, carry=p < 0.5)
            P.hit(x - 5, y - 28, x + 5, y, a)
            name_tag(P, x, y + 6, a["project"], "#7a5a35", names)

        n_fit = max(1, int((L - 20) // 24))
        seat = sleep[:n_fit]
        for j, a in enumerate(seat):
            idn = ident(a)
            x = L - 18 - j * 24
            self.sitter(P, x, 174, idn, t)
            P.hit(x - 10, 150, x + 10, 176, a)

        for j, a in enumerate(wait):
            idn = ident(a)
            x = L - 50 - j * 12
            self.walker(P, x, 150, -1, idn, t, carry=False, still=True)
            alert(P, x + 5, 118, t)
            P.hit(x - 5, 122, x + 5, 150, a)
        overflow(P, L, len(sleep) - len(seat))

    def walker(self, P, x, y, d, idn, t, carry, still=False):
        s = 0 if still else math.sin(t * 9 * idn["sp"] + idn["ph"] * 6) * 3.2
        hip = (x, y - 10)
        P.line([(x + s, y), hip], "#3b4a5c", 2.8)
        P.line([(x - s, y), hip], "#3b4a5c", 2.8)
        sh = (x + 0.6 * d, y - 18.5)
        P.line([hip, sh], idn["coat"], 5.8)
        P.line([(x - 2.2, y - 13), (x + 2.2, y - 17)], "#f7d13d", 0.9)
        if carry:
            P.line([sh, (x + d * 5, y - 15)], idn["coat"], 2.2)
            P.rect(x + d * 4.5 - 3.5, y - 18.5, x + d * 4.5 + 3.5, y - 14.5, "#c0623f")
        elif still:
            P.line([sh, (x + 4, y - 27 + math.sin(t * 8))], idn["coat"], 2.2)
        else:
            P.line([sh, (x - s * 0.6, y - 11)], idn["coat"], 2.2)
        head(P, x + 0.8 * d, y - 22.5, 3.4, idn, hat="hard", face=d)

    def sitter(self, P, x, y, idn, t):
        br = math.sin(t * 1.4 + idn["ph"] * 6) * 0.4
        P.oval(x, y + 0.5, 9, 1.6, "#b8925f")
        P.line([(x, y - 2), (x + 6, y - 6), (x + 9, y)], "#3b4a5c", 2.8)
        P.line([(x, y - 2), (x - 3, y - 12 + br)], idn["coat"], 5.8)
        head(P, x - 3.5, y - 16.5 + br, 3.3, idn, hat="hard", asleep=True, face=1, tilt=-12)
        zzz(P, x + 1, y - 21, t + idn["ph"] * 3, "#8a6a45", 0.8)


# ---------- D: aquarium ----------

FISH = {
    "classic": ["#f2a541", "#e4572e", "#3bb273", "#2e86ab"],
    "puffer": ["#f7d96b", "#d9b98a", "#9fd0a8"],
    "angel": ["#f4f1ea", "#ffd27a", "#b9a7f2"],
    "tetra": ["#2e6fd8", "#7b5cc4", "#1b998b"],
    "clown": ["#ff7f2a", "#ff5d5d", "#ffb000"],
    "betta": ["#e0245e", "#7b3fe4", "#1f9fd6", "#ff6f91"],
}
SPECIES = list(FISH)
SPECIES_NAMES = {"classic": "Goldfish", "puffer": "Pufferfish", "angel": "Angelfish",
                 "tetra": "Neon tetra", "clown": "Clownfish", "betta": "Betta"}
COMBOS = [(sp, FISH[sp][j]) for j in range(4) for sp in SPECIES if j < len(FISH[sp])]


def _h(s):
    v = 0
    for ch in s or "":
        v = (v * 131 + ord(ch)) & 0xFFFFFFFF
    return v


class Aquarium:
    title = "Aquarium"
    FK = 1.35  # fish size

    def __init__(self):
        self.hide_labels = set()  # ids whose info card is open (no pill needed)
        self.looks = {}
        self.fish_choice = {}  # session name -> species, set from the window/config
        self.chosen_ids = set()
        self.bars = {}  # id -> progress bar state
        self.swim = {}  # id -> swimming slot (phase offset, lane), see place_swimmers
        self.last_t = None
        self._bars_t = None

    SWIM_SPEED = 0.018  # swim cycles per second: one crossing ~28 s, same for every fish
    TOP, BOT = 20, 116  # swimming band

    def place_swimmers(self, swimmers, t, dt):
        """Spread swimming fish evenly and keep them apart.

        All fish swim at the same pace, so their spacing never drifts. With n
        fish, fish i starts at i/(n-1) of the way across (two fish: opposite
        ends), neighbours heading opposite ways, each in its own depth lane.
        When the count changes, offsets and lanes glide to the new layout.
        Returns {id: (phase_offset, lane_y)}.
        """
        ids = [a["id"] for a in swimmers]
        for gone in [i for i in self.swim if i not in ids]:
            del self.swim[gone]
        order = sorted(ids, key=lambda i: self.swim[i]["since"] if i in self.swim else t + 1)
        n = len(order)
        base = t * self.SWIM_SPEED
        out = {}
        for i, aid in enumerate(order):
            u = 0.5 if n == 1 else i / (n - 1)  # 0 = left wall, 1 = right wall
            a = math.acos(max(-1.0, min(1.0, 1 - 2 * u))) / (2 * math.pi)  # phase in [0, .5]
            p_target = a if i % 2 == 0 else 1 - a  # even: heading right, odd: heading left
            off_target = (p_target - base) % 1
            lane_target = self.TOP + (i + 0.5) * (self.BOT - self.TOP) / n
            st = self.swim.get(aid)
            if st is None:
                st = self.swim[aid] = {"since": t, "off": off_target, "lane": lane_target}
            else:  # glide along the shortest way round the cycle
                diff = ((off_target - st["off"] + 0.5) % 1) - 0.5
                st["off"] = (st["off"] + diff * min(1, dt * 0.6)) % 1
                st["lane"] += (lane_target - st["lane"]) * min(1, dt * 0.8)
            out[aid] = (st["off"], st["lane"])
        return out

    DONE_SHOW = 4.0  # seconds a full bar stays under a fish that just finished

    def bars_now(self, agents, t):
        """Advance the bars to time t; safe to call from the tank and the taskbar strip."""
        dt = 0 if self._bars_t is None else max(0.0, min(0.3, t - self._bars_t))
        self._bars_t = t
        return self.update_bars(agents, t, dt)

    def update_bars(self, agents, t, dt):
        """Work out each main session's bar value; returns {id: (value, done)}."""
        now = time.time()
        out = {}
        for a in agents:
            if a.get("sub"):
                continue
            b = self.bars.get(a["id"])
            st = a["state"]
            if st in ("working", "waiting"):
                if b is None or b["done"] is not None or b["turn"] != a.get("turn_start"):
                    if b is None or b["state"] != st or b["turn"] != a.get("turn_start"):
                        b = {"v": 0.0, "seen": now, "done": None, "state": st,
                             "turn": a.get("turn_start")}
                        self.bars[a["id"]] = b
                b["state"], b["done"] = st, None
                p = a.get("progress")
                if p is None:  # no task list: creep forward with time
                    started = a.get("turn_start") or b["seen"]
                    p = 0.9 * (1 - math.exp(-max(0, now - started) / 240))
                target = max(p, 0.04)
                if st == "working":
                    b["v"] += (target - b["v"]) * min(1, dt * 3)
                out[a["id"]] = (b["v"], False)
            elif b is not None:
                if b["state"] in ("working", "waiting") and b["done"] is None:
                    b["done"], b["state"] = t, st
                if b["done"] is not None and t - b["done"] < self.DONE_SHOW:
                    b["v"] += (1 - b["v"]) * min(1, dt * 6)
                    out[a["id"]] = (b["v"], True)
                else:
                    self.bars.pop(a["id"], None)
        return out

    # agent id -> (species, colour); sticky so a fish never changes

    def look(self, a, present):
        key = a.get("id")
        chosen = self.fish_choice.get(a.get("name") or "")
        if chosen not in FISH:
            chosen = None
        if key in self.looks and (chosen is None or self.looks[key][0] == chosen):
            return self.looks[key]
        self.looks.pop(key, None)
        in_use = [self.looks[i] for i in present if i in self.looks]
        if chosen:  # user picked the species: its classic colour wins over automatic fish
            pal = FISH[chosen]
            taken = {self.looks[i] for i in present if i in self.looks and i in self.chosen_ids}
            col = min(pal, key=lambda c: ((chosen, c) in taken, pal.index(c)))
            for i in present:
                if i in self.looks and i not in self.chosen_ids and self.looks[i] == (chosen, col):
                    del self.looks[i]  # that automatic fish picks a new look next frame
            self.looks[key] = (chosen, col)
            self.chosen_ids.add(key)
            return self.looks[key]
        self.chosen_ids.discard(key)
        sp_count = dict.fromkeys(SPECIES, 0)
        for sp, _ in in_use:
            sp_count[sp] += 1
        h = _h(a.get("seed") or key)
        n = len(COMBOS)
        best = min(range(n), key=lambda i: (COMBOS[i] in in_use, sp_count[COMBOS[i][0]], (i - h) % n))
        self.looks[key] = COMBOS[best]
        return COMBOS[best]

    def colour_of(self, agent_id):
        look = self.looks.get(agent_id)
        return look[1] if look else None

    def draw(self, P, L, agents, t, names):
        P.vgrad(0, 0, L, H, "#74c8ea", "#1c5a8c")
        P.poly([(-5, 160), (-5, 154), (L * .25, 150), (L * .5, 158), (L * .75, 151), (L + 5, 156),
                (L + 5, 160)], "#e3c891", smooth=True)
        P.rect(0, 157, L, H, "#e3c891")
        for gx in range(5, int(L), 13):
            P.oval(gx, 164 + (gx * 7) % 12, 0.9, 0.6, "#c7aa71")
        P.oval(L * 0.32, 156, 13, 8, "#6f7d8c")
        P.oval(L * 0.36, 158, 8, 5, "#8a97a5")
        P.oval(L * 0.84, 157, 10, 6, "#7b8896")
        for k, fx in enumerate((0.06, 0.18, 0.47, 0.62, 0.93)):
            bx = fx * L
            hgt = 38 + (k * 13) % 26
            for strand, col, wd in ((0, "#3f9b6b", 3.2), (1, "#5bbf86", 2)):
                pts = []
                for sgm in range(6):
                    yy = 158 - sgm * hgt / 5
                    pts.append((bx + strand * 4 + math.sin(t * 0.45 + sgm * 0.6 + k + strand) * sgm * 1.1, yy))
                P.line(pts, col, wd, smooth=True)
        bx = L * 0.12
        for i in range(6):
            yy = 156 - ((t * 7 + i * 27) % 156)
            r = 1.4 + (i % 3) * 0.5
            P.oval(bx + math.sin(t * 0.8 + i) * 2, yy, r, r, outline="#d9f3ff", w=0.5)

        dt = 0 if self.last_t is None else min(0.3, t - self.last_t)
        self.last_t = t
        bars = self.bars_now(agents, t)
        present = [a["id"] for a in agents]
        main = [a for a in agents if not a.get("sub")]
        subs = [a for a in agents if a.get("sub") and a["state"] == "working"]
        work, sleep, wait = split(main)
        labels = []

        swimmers = work + subs
        slots = self.place_swimmers(swimmers, t, dt)
        m = 24
        for a in swimmers:
            idn = ident(a)
            sp, col = self.look(a, present)
            k = 0.85 if a.get("sub") else self.FK
            off, lane = slots[a["id"]]
            p = (t * self.SWIM_SPEED + off) % 1
            x = m + (0.5 - 0.5 * math.cos(2 * math.pi * p)) * (L - 2 * m)
            d = 1 if p < 0.5 else -1
            y = lane + 2 * math.sin(t * 0.35 + idn["ph"] * 6)
            self.fish(P, sp, x, y, d, col, t, idn["ph"], awake=True, k=k)
            P.hit(x - 15 * k, y - 10 * k, x + 15 * k, y + 9 * k, a)
            if a["id"] in bars:
                v, done = bars[a["id"]]
                P.bar(x, y + 9.5 * k, 22 * k, 3.4, v, progress_colour(v, done))
                labels.append((x, y + 9.5 * k + 8, a["name"], a.get("sub"), col, a["id"]))
            else:
                labels.append((x, y + 11 * k + 3, a["name"], a.get("sub"), col, a["id"]))

        FK = self.FK
        n_fit = max(1, int((L - 10) // 46))
        rest = sleep[:n_fit]
        for j, a in enumerate(rest):
            idn = ident(a)
            sp, col = self.look(a, present)
            x = 28 + j * 46
            y = 141 + 0.6 * math.sin(t * 0.4 + idn["ph"] * 6)
            self.fish(P, sp, x, y, 1, col, t, idn["ph"], awake=False, k=FK)
            p = (t * 0.12 + idn["ph"]) % 1
            P.oval(x + 12 + p * 2, y - 8 - p * 18, 0.9 + p, 0.9 + p, outline="#d9f3ff", w=0.5)
            P.hit(x - 19, y - 11, x + 19, y + 10, a)
            if a["id"] in bars:
                P.bar(x, y + 11, 30, 3.4, bars[a["id"]][0], BAR_DONE)
            name_tag(P, x, y + 11, a["project"], "#5b4a2a", names)
        for j, a in enumerate(wait):
            idn = ident(a)
            sp, col = self.look(a, present)
            x, y = L / 2 + (j - (len(wait) - 1) / 2) * 46, 78 + math.sin(t * 1.5) * 2
            self.fish(P, sp, x, y, 1, col, t, idn["ph"], awake=True, k=1.6)
            alert(P, x + 19, y - 20, t)
            P.hit(x - 23, y - 13, x + 23, y + 13, a)
            if a["id"] in bars:
                P.bar(x, y + 15, 34, 3.4, bars[a["id"]][0], progress_colour(bars[a["id"]][0]))
            labels.append((x, y + 24, a["name"], False, col, a["id"]))
        for x, y, text, small, col, aid in labels:
            if aid not in self.hide_labels:
                P.tag(x, y, text, size=5.2 if small else 6.0, max_chars=14 if small else 18, L=L, dot=col)
        overflow(P, L, len(sleep) - len(rest))

    # ----- species -----
    def fish(self, P, sp, x, y, d, col, t, ph, awake, k=1.0):
        wag = math.sin(t * (4.5 if awake else 1.4) + ph * 6) * 1.6 * k
        dark = mix(col, "#000000", 0.22)
        light = mix(col, "#ffffff", 0.45)

        def X(u):
            return x + d * u * k

        def Y(v):
            return y + v * k

        if sp == "classic":
            P.poly([(X(-8), Y(0)), (X(-15), Y(-5.5) + wag), (X(-13.5), Y(0) + wag * .5), (X(-15), Y(5.5) + wag)], dark)
            P.poly([(X(-4), Y(-5)), (X(3), Y(-5.5)), (X(-6), Y(-10))], dark)
            P.oval(x, y, 10.5 * k, 6.2 * k, col)
            P.oval(X(1.5), Y(2.4), 7 * k, 2.6 * k, light)
            P.line([(X(-1), Y(-5.5)), (X(-2), Y(5.5))], mix(col, "#ffffff", .3), 1.4 * k)
            self.eye(P, X(6), Y(-1.6), 1.9 * k, d, awake, k)
        elif sp == "puffer":
            P.poly([(X(-7), Y(0)), (X(-12), Y(-4) + wag), (X(-12), Y(4) + wag)], dark)
            P.poly([(X(-2), Y(-7)), (X(2), Y(-7.2)), (X(-3), Y(-10.5))], dark)
            P.oval(x, y, 8.5 * k, 7.8 * k, col)
            P.oval(X(0.5), Y(3.2), 6.5 * k, 3.6 * k, light)
            for sx, sy in ((-4, -3), (-1, -5), (2, -3.5), (-5, 1)):
                P.oval(X(sx), Y(sy), 0.8 * k, 0.8 * k, dark)
            P.oval(X(8.3), Y(1.2), 0.9 * k, 0.9 * k, dark)
            self.eye(P, X(4.5), Y(-2), 2.4 * k, d, awake, k)
        elif sp == "angel":
            f = wag * 0.3
            P.poly([(X(-1), Y(-6)), (X(3), Y(-5)), (X(-7), Y(-17) + f)], dark)
            P.poly([(X(-1), Y(6)), (X(3), Y(5)), (X(-7), Y(17) + f)], dark)
            P.poly([(X(-7), Y(0)), (X(-12), Y(-4) + wag), (X(-12), Y(4) + wag)], dark)
            P.poly([(X(9), Y(0)), (X(1), Y(-8.5)), (X(-8), Y(0)), (X(1), Y(8.5))], col, smooth=True)
            P.line([(X(2.5), Y(-6.5)), (X(2.5), Y(6.5))], mix(col, "#2b2b2b", .55), 1.5 * k)
            P.line([(X(-3), Y(-5.5)), (X(-3), Y(5.5))], mix(col, "#2b2b2b", .55), 1.5 * k)
            self.eye(P, X(5.5), Y(-1.2), 1.6 * k, d, awake, k)
        elif sp == "tetra":
            P.poly([(X(-10), Y(0)), (X(-16), Y(-4) + wag), (X(-14), Y(0) + wag * .5), (X(-16), Y(4) + wag)], dark)
            P.poly([(X(-3), Y(-3.5)), (X(1), Y(-3.8)), (X(-4), Y(-7))], dark)
            P.oval(x, y, 12.5 * k, 4.2 * k, col)
            P.line([(X(9), Y(-0.6)), (X(-9), Y(-0.6))], "#7ff0ff", 1.3 * k)
            P.line([(X(1), Y(2.2)), (X(-9), Y(1.6))], "#ff5a6e", 1.4 * k)
            self.eye(P, X(8), Y(-1.2), 1.5 * k, d, awake, k)
        elif sp == "clown":
            P.oval(X(-11), Y(0) + wag * .3, 3.6 * k, 4.6 * k, dark)
            P.oval(X(-2), Y(-6), 4 * k, 2.2 * k, dark)
            P.oval(x, y, 10 * k, 6 * k, col)
            for bxx, hh in ((5, 5.2), (-1, 5.9), (-7, 3.8)):
                P.line([(X(bxx), Y(-hh)), (X(bxx), Y(hh))], "#1d1d1d", 3.2 * k)
                P.line([(X(bxx), Y(-hh + .5)), (X(bxx), Y(hh - .5))], "#ffffff", 2.1 * k)
            self.eye(P, X(7.3), Y(-1.6), 1.6 * k, d, awake, k)
        else:  # betta
            P.poly([(X(-5), Y(-2)), (X(-14), Y(-10) + wag), (X(-20), Y(0) + wag * 1.2),
                    (X(-14), Y(11) + wag), (X(-5), Y(2.5))], light, smooth=True)
            P.poly([(X(-1), Y(-3.5)), (X(-9), Y(-9) + wag * .5), (X(-7), Y(-3))], light, smooth=True)
            P.line([(X(0), Y(3.5)), (X(-2), Y(9) + wag * .4)], light, 1.2 * k, smooth=True)
            P.oval(x, y, 7.5 * k, 4.6 * k, col)
            self.eye(P, X(4.5), Y(-1), 1.5 * k, d, awake, k)

    def eye(self, P, x, y, r, d, awake, k):
        if awake:
            P.oval(x, y, r, r, "#ffffff")
            P.oval(x + d * r * 0.3, y, r * 0.52, r * 0.52, "#1b1b1b")
        else:
            P.line([(x - d * r * 0.7, y + 0.2), (x + d * r * 0.7, y + 0.5)], "#1b1b1b", 0.7 * k)


SCENES = {"slopes": Slopes, "desks": Desks, "build": Build, "aquarium": Aquarium}

try:  # the picture characters: cast.py adds its scene to SCENES when it loads
    import cast  # noqa: F401
except Exception:
    pass
