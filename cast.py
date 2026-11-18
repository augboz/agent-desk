"""Picture characters for the taskbar strip and the big window.

A character is a folder with awake.png and asleep.png (and optionally face.png).
They come from a theme:
  - "mine": your own pictures in characters/ (made by make_characters.py), and
  - the basic built-in themes in themes/ (wizards, skiers, animals), placeholders
    made from Microsoft's Fluent Emoji, with a single pose each.
Every session gets its own character, sitting in its own fixed spot: asleep
when idle, bouncing when it's working.
"""
import json
import math
import os

import scenes

try:
    from PIL import Image, ImageTk
except ImportError:  # no Pillow: the strip falls back to fish
    Image = ImageTk = None

HERE = os.path.dirname(os.path.abspath(__file__))
MINE = os.path.join(HERE, "characters")  # your own pictures (git-ignored)
THEMES_DIR = os.path.join(HERE, "themes")  # the basic built-in ones
THEME_LABELS = {"mine": "My own pictures", "wizards": "Wizards", "skiers": "Skiers", "animals": "Animals"}
DEFAULT_THEME = "wizards"
SLOTS = 5
ANIMATE = False  # hops, drifting z's and clouds; off = lightest on the PC (right-click → Animations)
# A pinned character's star floats above its head, clear of it:
STAR, STAR_GAP = 8.5, 2.0  # star height and the gap under it, logical px
STAR_ROOM = STAR + STAR_GAP + 1.0  # headroom a pinned character keeps free above itself


def theme_dir(key):
    return MINE if key == "mine" else os.path.join(THEMES_DIR, key)


def _load_cast(d=None):
    """cast.json in a theme folder (make_characters.py writes yours): the order,
    display names and size tweaks of the characters. Missing or broken: folder
    names, A-Z."""
    try:
        with open(os.path.join(d or DIR, "cast.json"), encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            d = {}
    except (OSError, ValueError):
        d = {}
    order = [n for n in d.get("order") or [] if isinstance(n, str)] if isinstance(d.get("order"), list) else []
    names = {k: v for k, v in (d.get("names") or {}).items() if isinstance(v, str)} \
        if isinstance(d.get("names"), dict) else {}
    scale = {k: float(v) for k, v in (d.get("scale") or {}).items()
             if isinstance(v, (int, float)) and 0.3 <= v <= 3} if isinstance(d.get("scale"), dict) else {}
    return order, names, scale


class _Names(dict):
    def __missing__(self, key):
        return key.replace("_", " ").title()


def available(d=None, order=None):
    """Characters in folder d (default: the current theme) that have both an
    awake and an asleep picture."""
    d = d or DIR
    if Image is None or not os.path.isdir(d):
        return []
    try:
        folders = sorted(e.name for e in os.scandir(d) if e.is_dir())
    except OSError:
        return []
    order = ORDER if order is None else order
    names = [n for n in order if n in folders] + [n for n in folders if n not in order]
    return [n for n in names if all(os.path.exists(os.path.join(d, n, p + ".png"))
                                    for p in ("awake", "asleep"))]


def themes():
    """The themes you can pick, your own pictures first (if you've made any)."""
    return [k for k in THEME_LABELS if available(theme_dir(k), [])]


def star_path():
    """Your own star.png if you made one, else the built-in one."""
    mine = os.path.join(MINE, "star.png")
    return mine if THEME == "mine" and os.path.exists(mine) else os.path.join(THEMES_DIR, "star.png")


def set_theme(key):
    """Switch every character to another theme. Unknown or empty: your own
    pictures if there are any, else the default theme. Returns the theme used."""
    global THEME, DIR, ORDER, NAMES, SCALE
    have = themes()
    if key not in have:
        key = "mine" if "mine" in have else DEFAULT_THEME if DEFAULT_THEME in have else (have or ["mine"])[0]
    THEME, DIR = key, theme_dir(key)
    ORDER, names, SCALE = _load_cast(DIR)  # SCALE: size tweaks so the cast looks even side by side
    NAMES = _Names(names)
    if _SHARED is not None:
        _SHARED.reload()
    return key


THEME = DIR = None
ORDER, NAMES, SCALE = [], _Names(), {}


def _h(s):
    v = 0
    for ch in s or "":
        v = (v * 131 + ord(ch)) & 0xFFFFFFFF
    return v


_SHARED = None


def shared(choice=None):
    """One Cast for the whole app, so a session is the same character everywhere."""
    global _SHARED
    if _SHARED is None:
        _SHARED = Cast(choice)
    elif choice is not None and choice is not _SHARED.choice:
        for k, v in _SHARED.choice.items():  # adopt the app's dict so choices get saved
            choice.setdefault(k, v)
        _SHARED.choice = choice
    return _SHARED


class Cast:
    def __init__(self, choice=None):
        self.names = available()
        self.choice = choice if choice is not None else {}  # session name -> character
        self.who = {}  # agent id -> character (sticky)
        self.src = {}  # (name, pose) -> PIL image
        self.cache = {}  # (name, pose, w, h) -> PhotoImage

    def reload(self):
        """The theme changed: new characters, same spots."""
        self.names = available()
        self.who.clear()
        self.src.clear()
        self.cache.clear()
        if hasattr(self, "slot_char"):
            self.slot_char.clear()

    def ok(self):
        return bool(self.names)

    def character(self, a, present):
        """This chat's character: the one it has on the strip, else the least used."""
        key = a["id"]
        if key in self.who and self.who[key] in self.names:
            return self.who[key]
        used = [self.who[i] for i in present if i in self.who and i != key]
        h = _h(a.get("seed") or key)
        n = len(self.names)
        best = min(range(n), key=lambda i: (used.count(self.names[i]), (i - h) % n))
        self.who[key] = self.names[best]
        return self.who[key]

    def unique(self, shown):
        """Give the 5 chats on the strip 5 different characters, and keep them.

        Each of the 5 spots owns a character. A chat keeps its spot, and so its
        character, for as long as it is one of your 5 most recent chats. When a
        newer chat pushes it out, the newcomer takes over that spot and that
        character. Picking a character yourself (right-click) swaps it with
        whoever had it.
        """
        if not hasattr(self, "slot_char"):
            self.slot_char = {}  # spot (rank) -> character
        out = {}
        used = set()
        for a in sorted(shown, key=lambda a: self.rank[a["id"]]):
            r = self.rank[a["id"]]
            ch = self.slot_char.get(r)
            if ch not in self.names or ch in used:
                old = self.who.get(a["id"])
                ch = old if old in self.names and old not in used else None
            if ch is None:
                free = [n for n in self.names if n not in used and n not in self.slot_char.values()] \
                    or [n for n in self.names if n not in used] or self.names
                ch = free[_h(a.get("seed") or a["id"]) % len(free)]
            out[a["id"]] = ch
            used.add(ch)
            self.slot_char[r] = ch
            self.who[a["id"]] = ch
        for r in [r for r in self.slot_char if r not in {self.rank[a["id"]] for a in shown}]:
            if self.slot_char[r] in used:
                del self.slot_char[r]
        return out

    def choose(self, aid, ch):
        """You picked character ch for chat aid: swap with whoever had it."""
        if not hasattr(self, "slot_char"):
            self.slot_char = {}
        r = self.rank.get(aid)
        mine = self.who.get(aid)
        for rr, c in list(self.slot_char.items()):
            if c == ch and rr != r:
                self.slot_char[rr] = mine  # the other chat gets my old character
                for i, w in list(self.who.items()):
                    if w == ch and i != aid:
                        self.who[i] = mine
        if r is not None:
            self.slot_char[r] = ch
        self.who[aid] = ch

    def pick_shown(self, main, t):
        """Who gets the 5 spots: the 5 chats you sent a message to most recently.

        A chat keeps its place in the row while it stays shown. When a new chat
        (or one you just texted) comes in, it takes the exact spot of the chat
        you haven't texted for longest, so the others don't move.
        """
        if not hasattr(self, "rank"):
            self.rank = {}

        def last_active(a):
            # When you last typed in this chat yourself, or when you opened it if
            # later. Scheduled tasks' automated runs don't count.
            if a.get("scheduled"):
                return 0
            mine = a["last_msg"] if "last_msg" in a else a.get("turn_start")
            return max(mine or 0, (a.get("started") or 0) / 1000)

        def priority(a):  # the 5 chats you texted most recently
            return -last_active(a)
        want = {a["id"] for a in sorted(main, key=priority)[:SLOTS]}
        freed = sorted(self.rank.pop(i) for i in [i for i in self.rank if i not in want])
        for a in sorted(main, key=priority):
            if a["id"] in want and a["id"] not in self.rank:
                self.rank[a["id"]] = freed.pop(0) if freed else max(self.rank.values(), default=-1) + 1
        return sorted((a for a in main if a["id"] in want), key=lambda a: self.rank[a["id"]])

    def image(self, master, name, pose, max_w, max_h, flip=False, cap_h=None):
        """PhotoImage of a pose scaled to fit max_w x max_h (pixels), cached.

        SCALE then makes some characters bigger or smaller; cap_h is a hard
        limit on the final height so nobody pokes out of the strip.
        """
        src = self.src.get((name, pose))
        if src is None:
            src = self.src[(name, pose)] = Image.open(os.path.join(DIR, name, pose + ".png"), formats=["PNG"]).convert("RGBA")
        # Everyone the same height (times their size tweak), so the cast looks
        # even on any strip. Only when a picture is too wide for its spot does it
        # shrink to fit, and cap_h keeps everyone inside the strip.
        s = min(max_h / src.height * SCALE.get(name, 1.0), max_w / src.width)
        if cap_h:
            s = min(s, cap_h / src.height)
        w, h = max(1, round(src.width * s)), max(1, round(src.height * s))
        key = (DIR, name, pose, w, h, flip, str(master))
        if key not in self.cache:
            if len(self.cache) > 400:
                self.cache.clear()
            im = src.resize((w, h), Image.LANCZOS)
            if flip:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            self.cache[key] = ImageTk.PhotoImage(im, master=master)
        return self.cache[key]

    def draw(self, strip, P, L, H, agents, bars, t):
        """Draw the cast on the strip's canvas (P is a scenes.Pen in logical px)."""
        c, k = strip.c, strip.k
        t = t if ANIMATE else 0.0  # still: clouds, z's and hops stay where they are
        P.vgrad(0, 0, L, H, "#7cc8f4", "#d4efff", steps=12)
        for cx, cy, r in ((L * 0.18, 7, 4), (L * 0.62, 5, 3.4), (L * 0.88, 9, 3)):  # little clouds
            drift = (t * 0.2) % (L + 20) - 10
            x = round(((cx + drift) % (L + 20) - 10) * k) / k
            P.oval(x, cy, r * 1.8, r * 0.8, "#ffffff")
            P.oval(x + r * 0.6, cy - r * 0.5, r, r * 0.8, "#ffffff")
        P.rect(0, H - 3.5, L, H, "#58b94c")
        P.rect(0, H - 3.5, L, H - 2.6, "#7fd46b")

        main = [a for a in agents if not a.get("sub")]
        shown = self.pick_shown(main, t)
        names = self.unique(shown)
        self.last_names = names  # who is who on the strip, for the status cards
        n = len(shown)
        slot = (L - 6) / SLOTS  # five spots spread over the whole strip
        pad = (L - n * slot) / 2 if n else 0
        hits = []
        for j, a in enumerate(shown):
            name = names[a["id"]]
            cx = pad + (j + 0.5) * slot
            st = a["state"]
            ph = (_h(a["id"]) % 100) / 100
            if st == "sleeping":
                room = STAR_ROOM if a["id"] in strip.pins else 1.8
                img = self.image(c, name, "asleep", (slot - 6) * k, (H * 0.66) * k,
                                 cap_h=(H - 2.2 - room) * k)
                bottom = H - 2.2
                c.create_image(cx * k, bottom * k, image=img, anchor="s")
                for i in range(2):  # drifting z's
                    p = (t * 0.12 + ph + i / 2) % 1
                    P.text(cx + 2 + p * 2.5, max(3, bottom - img.height() / k - p * 4), "z",
                           "#ffffff", size=4.5 + p * 1.5, bold=True)
                top = bottom - img.height() / k
            else:
                hop_max = 1.6
                room = STAR_ROOM if a["id"] in strip.pins else 1.5  # pinned: space for the star
                hop = abs(math.sin(t * 1.1 + ph * 6)) * hop_max if st == "working" and ANIMATE else 0
                # fits with room for the hop: even the top of a jump stays inside
                img = self.image(c, name, "awake", (slot - 4) * k, (H - 11) * k,
                                 cap_h=(H - 3 - hop_max - room) * k)
                bottom = max(H - 3 - hop, img.height() / k + room)
                c.create_image(cx * k, bottom * k, image=img, anchor="s")
                top = bottom - img.height() / k
                if st == "waiting":
                    scenes.alert(P, cx + 10, max(5, top + 4), t, k=0.55)
            if a["id"] in bars:
                v, done = bars[a["id"]]
                P.bar(cx, H - 3.4, min(30, slot - 10), 2.6, v, scenes.progress_colour(v, done))
            w = img.width() / k
            hits.append(((cx - w / 2) * k, top * k, (cx + w / 2) * k, H * k, a))
        return hits


class CastScene(scenes.Aquarium):
    """The big pop-out window with the characters: a sunny meadow.

    The same 5 chats as the taskbar strip, as the same characters, in the
    same order, standing in one row on the grass. They never wander: idle
    ones nap where they stand, working ones wake up and hop gently on the
    spot, and one that needs you stands with a "!". Progress bars sit under
    their feet.
    """
    title = "Characters"

    def __init__(self):
        super().__init__()
        self.cast = shared()

    def draw(self, P, L, agents, t, names):
        if not self.cast.ok():
            return super().draw(P, L, agents, t, names)
        H, c, s = scenes.H, P.c, P.s
        bars = self.bars_now(agents, t)
        t = t if ANIMATE else 0.0  # still: clouds, z's and hops stay where they are
        P.vgrad(0, 0, L, H, "#68bff2", "#cdeeff", steps=24)
        for i, (cx, cy, r) in enumerate(((0.15, 26, 9), (0.55, 18, 7), (0.85, 34, 8))):
            x = round(((cx * L + t * (0.5 + i * 0.15)) % (L + 60) - 30) * s) / s
            P.oval(x, cy, r * 2, r * 0.9, "#ffffff")
            P.oval(x + r * 0.7, cy - r * 0.6, r * 1.1, r * 0.9, "#ffffff")
        P.oval(L * 0.2, 150, L * 0.32, 38, "#8fd27a")  # hills
        P.oval(L * 0.78, 152, L * 0.36, 44, "#7cc76a")
        P.rect(0, 140, L, H, "#5cb94e")
        P.rect(0, 140, L, 143, "#82d46c")
        for gx in range(6, int(L), 17):
            P.line([(gx, 152 + (gx * 7) % 20), (gx + 1.5, 149 + (gx * 7) % 20)], "#3f9b3c", 1)

        main = [a for a in agents if not a.get("sub")]
        # the same 5 chats, in the same spots, as the same characters as the strip
        shown = self.cast.pick_shown(main, t)
        names = self.cast.unique(shown)
        n = len(shown)
        slot = (L - 8) / SLOTS
        pad = (L - n * slot) / 2 if n else 0
        ground = 160  # everyone stands on the grass in one row
        for j, a in enumerate(shown):
            name = names[a["id"]]
            x = pad + (j + 0.5) * slot
            st = a["state"]
            ph = (_h(a["id"]) % 100) / 100
            if st == "sleeping":  # napping where they stand, z's drifting up
                img = self.cast.image(c, name, "asleep", (slot - 4) * s, 52 * s, cap_h=100 * s)
                bottom = ground
                c.create_image(x * s, bottom * s, image=img, anchor="s")
                top = bottom - img.height() / s
                for i in range(2):
                    q = (t * 0.12 + ph + i / 2) % 1
                    P.text(x + 4 + q * 4, top - 2 - q * 6, "z", "#ffffff", size=5.5 + q * 2, bold=True)
            else:  # awake: working ones hop gently on the spot, waiting ones stand still
                hop = abs(math.sin(t * 1.1 + ph * 6)) * 3.0 if st == "working" and ANIMATE else 0
                img = self.cast.image(c, name, "awake", (slot - 2) * s, 62 * s, cap_h=110 * s)
                P.oval(x, ground + 1, 11 * (1 - hop / 16), 2.2, "#4a9a40")  # shadow
                bottom = ground - hop
                c.create_image(x * s, bottom * s, image=img, anchor="s")
                top = bottom - img.height() / s
                if st == "waiting":
                    scenes.alert(P, x + img.width() / s / 2, top + 6, t)
            w = img.width() / s
            P.hit(x - w / 2, top, x + w / 2, ground, a)
            if a["id"] in bars:
                v, done = bars[a["id"]]
                P.bar(x, ground + 5, min(34, slot - 10), 3.4, v, scenes.progress_colour(v, done))


set_theme(None)

if available():  # offer it as the first scene in the window's Scene menu
    scenes.SCENES = {"cast": CastScene, **{k: v for k, v in scenes.SCENES.items() if k != "cast"}}
