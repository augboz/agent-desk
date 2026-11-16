"""Rebuild the default character themes in themes/ from Microsoft's Fluent Emoji 3D.

    python tools/build_themes.py

Fluent Emoji (https://github.com/microsoft/fluentui-emoji) is MIT-licensed,
see themes/LICENSE-fluent-emoji.txt. These are deliberately basic
placeholders: every character has a single pose, so "asleep" is just the
awake picture, dimmed. Your own pictures (make_characters.py) look far better.
"""
import io
import json
import os
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageEnhance

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "themes")
BASE = "https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@main/assets/"

# theme -> [(character folder, display name, Fluent emoji name, skin tone or None)]
THEMES = {
    "wizards": [("wizard_1", "Wizard", "Woman mage", "Medium-Light"),
                ("wizard_2", "Wizard", "Man mage", "Dark"),
                ("wizard_3", "Wizard", "Woman mage", "Default"),
                ("wizard_4", "Wizard", "Man mage", "Light"),
                ("wizard_5", "Wizard", "Woman mage", "Medium-Dark")],
    # skiers: five different faces, each with ski goggles pushed up (a goggle colour each)
    "skiers": [("skier_1", "Skier", "Man red hair", "Light", 0),
               ("skier_2", "Skier", "Woman curly hair", "Medium-Dark", 120),
               ("skier_3", "Skier", "Man beard", "Medium", 60),
               ("skier_4", "Skier", "Woman white hair", "Light", 200),
               ("skier_5", "Skier", "Man curly hair", "Dark", 30)],
    "animals": [("sloth", "Sloth", "Sloth", None), ("otter", "Otter", "Otter", None),
                ("fox", "Fox", "Fox", None), ("frog", "Frog", "Frog", None), ("cat", "Cat", "Cat", None)],
}
STAR = ("Glowing star", None)


def url(name, tone):
    f = name.lower().replace(" ", "_")
    path = f"{name}/{tone}/3D/{f}_3d_{tone.lower()}.png" if tone else f"{name}/3D/{f}_3d.png"
    return BASE + urllib.parse.quote(path)


def fetch(name, tone):
    with urllib.request.urlopen(url(name, tone), timeout=30) as r:
        data = r.read(5_000_000)
    im = Image.open(io.BytesIO(data), formats=["PNG"]).convert("RGBA")
    return im.crop(im.getbbox())


def hue(im, shift):
    """Rotate the colours of a picture (0-255 around the colour wheel), keeping transparency."""
    a = im.getchannel("A")
    h, s, v = im.convert("RGB").convert("HSV").split()
    out = Image.merge("HSV", (h.point(lambda x: (x + shift) % 256), s, v)).convert("RGB").convert("RGBA")
    out.putalpha(a)
    return out


def with_goggles(head, goggles, shift):
    """A face with ski goggles pushed up on the forehead."""
    c = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    c.alpha_composite(head.resize((256, 256), Image.LANCZOS), (22, 44))
    lens = hue(goggles.crop((16, 108, 240, 240)), shift).resize((176, 104), Image.LANCZOS)
    c.alpha_composite(lens, (62, 34))
    return c.crop(c.getbbox())


def fetch_full(name, tone):
    with urllib.request.urlopen(url(name, tone), timeout=30) as r:
        data = r.read(5_000_000)
    return Image.open(io.BytesIO(data), formats=["PNG"]).convert("RGBA")


def tall(im, h=256):
    return im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)


def asleep(im):
    """The basic stand-in for a sleeping pose: the same picture, a bit dimmer and greyer."""
    rgb, a = im.convert("RGB"), im.getchannel("A")
    rgb = ImageEnhance.Brightness(ImageEnhance.Color(rgb).enhance(0.5)).enhance(0.88)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


def face(im, size=128):
    """Round face for the status cards: a square from the top of the picture
    (for a picture that's only a face, the whole face)."""
    side = min(im.width, im.height)
    x0, y0 = (im.width - side) // 2, (im.height - side) // 2 if im.height <= im.width * 1.15 else 0
    sq = im.crop((x0, y0, x0 + side, y0 + side)).resize((size * 4, size * 4), Image.LANCZOS)
    bg = Image.new("RGBA", sq.size, (255, 255, 255, 255))
    bg.alpha_composite(sq)
    mask = Image.new("L", sq.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, sq.width - 1, sq.height - 1), fill=255)
    bg.putalpha(mask)
    return bg.resize((size, size), Image.LANCZOS)


def main():
    for theme, chars in THEMES.items():
        tdir = os.path.join(OUT, theme)
        for folder, _, name, tone, *goggle_hue in chars:
            if goggle_hue:  # a face wearing ski goggles
                im = with_goggles(fetch_full(name, tone), fetch_full("Goggles", None), goggle_hue[0])
            else:
                im = fetch(name, tone)
            d = os.path.join(tdir, folder)
            os.makedirs(d, exist_ok=True)
            tall(im).save(os.path.join(d, "awake.png"), optimize=True)
            tall(asleep(im)).save(os.path.join(d, "asleep.png"), optimize=True)
            face(im).save(os.path.join(d, "face.png"), optimize=True)
            print(theme, folder)
        cast = {"order": [c[0] for c in chars], "names": {c[0]: c[1] for c in chars}, "scale": {}}
        with open(os.path.join(tdir, "cast.json"), "w", encoding="utf-8") as f:
            json.dump(cast, f, indent=2)
    tall(fetch(*STAR), 128).save(os.path.join(OUT, "star.png"), optimize=True)
    print("star")


if __name__ == "__main__":
    main()
