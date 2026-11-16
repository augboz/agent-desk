"""Turn your own pictures into Agent Desk characters.

The easy way: drop pictures into the character-sources folder (right-click the
strip → "Use your own pictures…" opens it) and pick Characters → My own
pictures. The app runs this for you, and again whenever the folder changes.

    One picture per character:   fox.png             (asleep = the same, greyed)
    Or two:                      fox awake.png  +  fox asleep.png
                                 (also fox_awake / fox-asleep / "fox sleeping")

PNG, JPG, WEBP, BMP or GIF. A transparent background is used as it is; a plain
white background is cut away; anything else is kept as a rectangle. The file
name (without "awake"/"asleep") is the character's name.

From a terminal:  python make_characters.py [FOLDER]   (default: character-sources)

Advanced: a characters.json in the folder (see characters.example.json) can
pick halves of a picture, a face crop, a size tweak or a stricter white.

Writes characters/<name>/awake.png, asleep.png and face.png plus
characters/cast.json. Both folders are git-ignored: your pictures stay on your
machine.
"""
import json
import os
import re
import sys
from collections import deque

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "characters")
SOURCES = os.path.join(HERE, "character-sources")
MADE = ".made-from-folder.json"  # which characters/ folders this tool made from SOURCES
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse absurdly large pictures (decompression bombs)
FORMATS = ["PNG", "JPEG", "WEBP", "BMP", "GIF"]
EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
MAX_SIDE = 900  # big photos are shrunk first: cutting out stays quick
_POSE = re.compile(r"^(?P<base>.*?)[\s_\-.]*(?P<pose>awake|asleep|sleeping|sleep|idle|working)$", re.I)


class PictureError(Exception):
    pass


def _open(src_dir, name):
    """Open a picture inside src_dir (no paths that climb out of it)."""
    root = os.path.realpath(src_dir)
    path = os.path.realpath(os.path.join(src_dir, name))
    if os.path.commonpath([path, root]) != root:
        raise PictureError(f"{name}: pictures must be inside {src_dir}")
    im = Image.open(path, formats=FORMATS)
    im.load()
    return im


def slug(text):
    """A safe folder name for a character: letters, digits, - and _."""
    s = re.sub(r"[^a-z0-9_-]+", "_", text.strip().lower()).strip("_-")
    return s[:40] or "character"


def find_pictures(src_dir):
    """{character name: {"awake": file, "asleep": file or None}} from the file names."""
    found = {}
    try:
        files = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(EXTS))
    except OSError:
        return {}
    for f in files:
        stem = os.path.splitext(f)[0].strip()
        m = _POSE.match(stem)
        base, pose = (m.group("base"), m.group("pose").lower()) if m and m.group("base") else (stem, "awake")
        pose = "asleep" if pose in ("asleep", "sleeping", "sleep", "idle") else "awake"
        c = found.setdefault(base.strip() or stem, {"awake": None, "asleep": None})
        c[pose] = c[pose] or f
    for name, c in list(found.items()):
        if not c["awake"]:  # only an asleep picture: use it awake too (not greyed)
            c["awake"] = c["asleep"]
    return found


def shrink(im):
    if max(im.size) > MAX_SIDE:
        s = MAX_SIDE / max(im.size)
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    return im


def prepare(im, bg_min=233):
    """Transparent pictures as they are; white backgrounds cut away; others kept whole."""
    im = shrink(im)
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        if rgba.getchannel("A").getextrema()[0] < 250:  # really has see-through parts
            box = rgba.getbbox()
            return rgba.crop(box) if box else rgba
    rgb = im.convert("RGB")
    w, h = rgb.size
    corners = [rgb.getpixel(p) for p in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2))]
    if all(min(c) >= bg_min - 8 for c in corners):
        return cut_out(rgb, bg_min)
    return rgb.convert("RGBA")


def greyed(im):
    """The asleep pose when you only gave an awake picture: the same, a bit dimmer and greyer."""
    a = im.getchannel("A")
    rgb = ImageEnhance.Brightness(ImageEnhance.Color(im.convert("RGB")).enhance(0.5)).enhance(0.88)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


def round_face(im, size=128, box=None):
    """Round face for the status cards: the given square, or the top of the picture."""
    if box:
        sq = im.crop(tuple(box))
    else:
        side = min(im.width, im.height)
        x0 = (im.width - side) // 2
        sq = im.crop((x0, 0, x0 + side, side))
    big = size * 4
    sq = sq.convert("RGBA").resize((big, big), Image.LANCZOS)
    bg = Image.new("RGBA", (big, big), (255, 255, 255, 255))
    bg.alpha_composite(sq)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    bg.putalpha(mask)
    return bg.resize((size, size), Image.LANCZOS)


def tall(im, h=256):
    return im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)


def load(src_dir, spec):
    """A picture, or "file:L" / "file:R" for its left / right half."""
    name, _, half = spec.partition(":")
    im = _open(src_dir, name)
    w, h = im.size
    if half == "L":
        im = im.crop((12, 12, w // 2 - 12, h - 12))
    elif half == "R":
        im = im.crop((w // 2 + 12, 12, w - 12, h - 12))
    return im


def cut_out(im, bg_min=233):
    """White background -> transparent; keep only the biggest blob (drops the zzz)."""
    w, h = im.size
    sw, sh = w // 2, h // 2  # find blobs on a half-size mask (fast enough in pure Python)
    small = im.resize((sw, sh))
    px = small.load()

    def is_bg(x, y):
        r, g, b = px[x, y]
        return min(r, g, b) >= bg_min and max(r, g, b) - min(r, g, b) < 18

    fg = [[not is_bg(x, y) for x in range(sw)] for y in range(sh)]
    seen = [[False] * sw for _ in range(sh)]
    best = []
    for y0 in range(sh):
        for x0 in range(sw):
            if fg[y0][x0] and not seen[y0][x0]:
                blob, q = [], deque([(x0, y0)])
                seen[y0][x0] = True
                while q:
                    x, y = q.popleft()
                    blob.append((x, y))
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < sw and 0 <= ny < sh and fg[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            q.append((nx, ny))
                if len(blob) > len(best):
                    best = blob
    mask = Image.new("L", (sw, sh), 0)
    mp = mask.load()
    for x, y in best:
        mp[x, y] = 255
    # fill holes (e.g. white gloves, eyes) that aren't connected to the outside background
    outside = Image.new("L", (sw + 2, sh + 2), 0)
    op = outside.load()
    q = deque([(0, 0)])
    op[0, 0] = 255
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < sw + 2 and 0 <= ny < sh + 2 and not op[nx, ny]:
                inside = 0 < nx <= sw and 0 < ny <= sh and mp[nx - 1, ny - 1]
                if not inside:
                    op[nx, ny] = 255
                    q.append((nx, ny))
    solid = Image.new("L", (sw, sh), 255)
    sp = solid.load()
    for y in range(sh):
        for x in range(sw):
            if op[x + 1, y + 1]:
                sp[x, y] = 0
    # back to full size with a soft edge, then trim
    alpha = solid.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.8))
    alpha = alpha.point(lambda v: 0 if v < 40 else min(255, int((v - 40) * 255 / 175)))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    return out.crop(out.getbbox())


def _specs(src_dir):
    """What to make: from characters.json if there is one, else from the file names."""
    path = os.path.join(src_dir, "characters.json")
    chars = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                spec = json.load(f)
            chars = spec.get("characters") if isinstance(spec, dict) else None
            chars = {k: v for k, v in chars.items() if isinstance(v, dict) and v.get("awake")} \
                if isinstance(chars, dict) else None
        except (OSError, ValueError):
            chars = None
    if not chars:  # the easy way: just the pictures
        return {slug(name): {"name": name, **c} for name, c in find_pictures(src_dir).items()}
    return {slug(k): {"name": v.get("name") or k.replace("_", " ").title(), **v} for k, v in chars.items()}


def signature(src_dir=SOURCES):
    """Changes whenever a picture (or characters.json) is added, removed or edited."""
    try:
        return tuple(sorted((e.name, e.stat().st_mtime, e.stat().st_size) for e in os.scandir(src_dir)
                            if e.is_file() and e.name.lower().endswith((*EXTS, ".json"))))
    except OSError:
        return ()


def build(src_dir=SOURCES, out=OUT, log=print):
    """Make characters from every picture in src_dir. Returns the names made.

    Characters you made another way (already in characters/) are kept; ones this
    made earlier from pictures you've since removed are taken away again.
    """
    chars = _specs(src_dir)
    os.makedirs(out, exist_ok=True)
    made_file = os.path.join(out, MADE)
    try:
        with open(made_file, encoding="utf-8") as f:
            before = set(json.load(f))
    except (OSError, ValueError, TypeError):
        before = set()
    if not chars and not before:
        return []  # nothing to do, and nothing of yours to tidy up
    made = []
    for key, c in chars.items():
        try:
            bg = int(c.get("bg_min", 233))
            awake = prepare(load(src_dir, c["awake"]), bg)
            asleep = prepare(load(src_dir, c["asleep"]), bg) if c.get("asleep") else greyed(awake)
            d = os.path.join(out, key)
            os.makedirs(d, exist_ok=True)
            tall(awake).save(os.path.join(d, "awake.png"))
            tall(asleep).save(os.path.join(d, "asleep.png"))
            face = c.get("face")
            if isinstance(face, list) and len(face) == 2:
                round_face(prepare(load(src_dir, face[0])), box=face[1]).save(os.path.join(d, "face.png"))
            else:
                round_face(awake).save(os.path.join(d, "face.png"))
            made.append(key)
            log(f"{c['name']}: awake" + (" + asleep" if c.get("asleep") else " (asleep = greyed copy)"))
        except (OSError, PictureError, ValueError) as e:
            log(f"{c.get('name', key)}: skipped ({e})")
    import shutil
    for gone in before - set(made):  # pictures you took out of the folder
        if gone and os.path.isdir(os.path.join(out, gone)):
            shutil.rmtree(os.path.join(out, gone), ignore_errors=True)
    with open(made_file, "w", encoding="utf-8") as f:
        json.dump(made, f)

    cast_file = os.path.join(out, "cast.json")  # keep what's there for other characters
    try:
        with open(cast_file, encoding="utf-8") as f:
            cast = json.load(f)
        if not isinstance(cast, dict):
            cast = {}
    except (OSError, ValueError):
        cast = {}
    order = [n for n in cast.get("order", []) if isinstance(n, str) and n not in before - set(made)]
    names = {k: v for k, v in (cast.get("names") or {}).items() if k not in before - set(made)}
    scale = {k: v for k, v in (cast.get("scale") or {}).items() if k not in before - set(made)}
    for key in made:
        if key not in order:
            order.append(key)
        names[key] = chars[key]["name"]
        if isinstance(chars[key].get("scale"), (int, float)):
            scale[key] = chars[key]["scale"]
    with open(cast_file, "w", encoding="utf-8") as f:
        json.dump({"order": order, "names": names, "scale": scale}, f, indent=2)
    return made


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else SOURCES
    if not os.path.isdir(src):
        sys.exit(f"No folder {src}: put your pictures there first")
    made = build(src)
    print(f"{len(made)} character(s) ready. Right-click the strip → Characters → My own pictures.")


if __name__ == "__main__":
    main()
