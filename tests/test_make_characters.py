"""Your own pictures: one or two per character, any sensible background."""
import json

import pytest

Image = pytest.importorskip("PIL.Image")
import make_characters as mc  # noqa: E402


def draw(path, bg, size=(300, 400), fmt="PNG"):
    from PIL import ImageDraw
    im = Image.new("RGBA" if bg is None else "RGB", size, (0, 0, 0, 0) if bg is None else bg)
    ImageDraw.Draw(im).ellipse((80, 80, 220, 340), fill=(200, 40, 40, 255) if bg is None else (200, 40, 40))
    im.save(path, fmt)


@pytest.mark.parametrize("files,expect", [
    (["fox.png"], {"fox": ("fox.png", None)}),
    (["Fox Awake.png", "Fox Asleep.png"], {"Fox": ("Fox Awake.png", "Fox Asleep.png")}),
    (["owl_awake.jpg", "owl-sleeping.jpg"], {"owl": ("owl_awake.jpg", "owl-sleeping.jpg")}),
    (["cat asleep.png"], {"cat": ("cat asleep.png", "cat asleep.png")}),
    (["notes.txt", "awake.png"], {"awake": ("awake.png", None)}),
])
def test_find_pictures(tmp_path, files, expect):
    for f in files:
        (tmp_path / f).write_bytes(b"")
    got = mc.find_pictures(str(tmp_path))
    assert {k: (v["awake"], v["asleep"]) for k, v in got.items()} == expect


def test_build_one_or_two_pictures(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    draw(src / "fox.png", None)                          # transparent, awake only
    draw(src / "owl awake.png", (255, 255, 255))         # white background
    draw(src / "owl asleep.png", (255, 255, 255))
    draw(src / "photo.jpg", (30, 90, 160), fmt="JPEG")   # a photo: kept as a rectangle
    made = mc.build(str(src), str(out), log=lambda line: None)
    assert sorted(made) == ["fox", "owl", "photo"]
    for n in made:
        for pose in ("awake", "asleep", "face"):
            assert (out / n / f"{pose}.png").exists(), (n, pose)
    fox = Image.open(out / "fox" / "awake.png")
    assert fox.height == 256 and fox.getpixel((0, 0))[3] == 0          # still see-through
    owl = Image.open(out / "owl" / "awake.png")
    assert owl.getpixel((0, 0))[3] == 0                                  # white cut away
    awake = Image.open(out / "fox" / "awake.png").convert("RGB").getpixel((fox.width // 2, 128))
    asleep = Image.open(out / "fox" / "asleep.png").convert("RGB").getpixel((fox.width // 2, 128))
    assert asleep != awake and sum(asleep) < sum(awake)                  # greyed copy
    cast = json.loads((out / "cast.json").read_text())
    assert cast["names"]["owl"] == "owl" and set(cast["order"]) == {"fox", "owl", "photo"}


def test_removed_pictures_go_but_other_characters_stay(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    (out / "mine_by_hand").mkdir(parents=True)
    (out / "cast.json").write_text(json.dumps({"order": ["mine_by_hand"], "names": {"mine_by_hand": "Hand"},
                                               "scale": {"mine_by_hand": 1.2}}))
    draw(src / "fox.png", None)
    mc.build(str(src), str(out), log=lambda line: None)
    (src / "fox.png").unlink()
    mc.build(str(src), str(out), log=lambda line: None)
    assert not (out / "fox").exists() and (out / "mine_by_hand").exists()
    cast = json.loads((out / "cast.json").read_text())
    assert cast == {"order": ["mine_by_hand"], "names": {"mine_by_hand": "Hand"}, "scale": {"mine_by_hand": 1.2}}


def test_broken_picture_is_skipped(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    (src / "broken.png").write_bytes(b"not a picture")
    draw(src / "fox.png", None)
    assert mc.build(str(src), str(out), log=lambda line: None) == ["fox"]


def test_empty_folder_touches_nothing(tmp_path):
    out = tmp_path / "out"
    assert mc.build(str(tmp_path / "missing"), str(out), log=lambda line: None) == []
    assert not out.exists() or not any(out.iterdir())


def test_slug():
    assert mc.slug("My Fox!") == "my_fox"
    assert mc.slug(r"..\..\evil") == "evil"
    assert mc.slug("???") == "character"
