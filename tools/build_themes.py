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
    "skiers": [("skier", "Skier", "Skier", None),
               ("boarder_1", "Snowboarder", "Snowboarder", "Light"),
               ("boarder_2", "Snowboarder", "Snowboarder", "Medium-Dark"),
               ("boarder_3", "Snowboarder", "Snowboarder", "Medium"),
               ("snowman", "Snowman", "Snowman", None)],
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
    """Round face for the status cards: a square from the top of the picture."""
    side = min(im.width, im.height)
    x0 = (im.width - side) // 2
    sq = im.crop((x0, 0, x0 + side, side)).resize((size * 4, size * 4), Image.LANCZOS)
    bg = Image.new("RGBA", sq.size, (255, 255, 255, 255))
    bg.alpha_composite(sq)
    mask = Image.new("L", sq.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, sq.width - 1, sq.height - 1), fill=255)
    bg.putalpha(mask)
    return bg.resize((size, size), Image.LANCZOS)


def main():
    for theme, chars in THEMES.items():
        tdir = os.path.join(OUT, theme)
        for folder, _, name, tone in chars:
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
