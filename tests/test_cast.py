"""The 5 spots: who is shown, and who keeps which character."""
import cast


def agent(i, last):
    return {"id": f"a{i}", "seed": f"a{i}", "last_msg": last, "started": 0, "state": "sleeping"}


def make():
    c = cast.Cast()
    c.names = ["fox", "owl", "bear", "cat", "frog"]
    return c


def test_shows_the_five_most_recently_texted():
    c = make()
    agents = [agent(i, 100 + i) for i in range(8)]
    shown = c.pick_shown(agents, 0)
    assert sorted(a["id"] for a in shown) == ["a3", "a4", "a5", "a6", "a7"]


def test_scheduled_chats_rank_last():
    c = make()
    agents = [agent(i, 100 + i) for i in range(5)] + [dict(agent(9, 999), scheduled=True)]
    assert "a9" not in {a["id"] for a in c.pick_shown(agents, 0)}


def test_five_different_characters_and_they_stick():
    c = make()
    agents = [agent(i, 100 + i) for i in range(5)]
    first = c.unique(c.pick_shown(agents, 0))
    assert sorted(first.values()) == sorted(c.names)
    agents[0]["last_msg"] = 500  # texting a chat that's already shown changes nothing
    again = c.unique(c.pick_shown(agents, 0))
    assert again == first


def test_newcomer_takes_the_replaced_chats_spot_and_character():
    c = make()
    agents = [agent(i, 100 + i) for i in range(5)]
    before = c.unique(c.pick_shown(agents, 0))
    spot_of_a0 = c.rank["a0"]
    agents.append(agent(9, 900))  # a new chat pushes out a0, the least recently texted
    shown = c.pick_shown(agents, 0)
    after = c.unique(shown)
    assert "a0" not in after and after["a9"] == before["a0"]
    assert c.rank["a9"] == spot_of_a0
    for i in range(1, 5):  # nobody else moved or changed character
        assert after[f"a{i}"] == before[f"a{i}"]


def test_choose_swaps_with_whoever_had_it():
    c = make()
    agents = [agent(i, 100 + i) for i in range(5)]
    names = c.unique(c.pick_shown(agents, 0))
    other = next(i for i, n in names.items() if n == "owl")
    mine = next(i for i in names if i != other)
    old = names[mine]
    c.choose(mine, "owl")
    names = c.unique(c.pick_shown(agents, 0))
    assert names[mine] == "owl" and names[other] == old
    assert len(set(names.values())) == 5


def test_fewer_chats_than_spots():
    c = make()
    shown = c.pick_shown([agent(0, 1), agent(1, 2)], 0)
    assert len(c.unique(shown)) == 2
    assert c.unique(c.pick_shown([], 0)) == {}


def test_cast_file_is_optional_and_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(cast, "DIR", str(tmp_path))
    assert cast._load_cast() == ([], {}, {})  # no characters/cast.json
    (tmp_path / "cast.json").write_text('{"order": ["b", 3], "names": {"b": "Bee", "c": 1},'
                                        ' "scale": {"b": 1.2, "c": 99, "d": "big"}}')
    assert cast._load_cast() == (["b"], {"b": "Bee"}, {"b": 1.2})
    (tmp_path / "cast.json").write_text("[1, 2]")
    assert cast._load_cast() == ([], {}, {})
    assert cast.NAMES["sleepy_cat"] == "Sleepy Cat"  # no display name given: from the folder


def test_built_in_themes_are_complete():
    for key in ("wizards", "skiers", "animals"):
        d = cast.theme_dir(key)
        names = cast.available(d, [])
        assert len(names) == 5, key
        for n in names:
            assert (cast.os.path.exists(cast.os.path.join(d, n, "face.png"))), (key, n)
    assert cast.os.path.exists(cast.os.path.join(cast.THEMES_DIR, "star.png"))
    assert cast.os.path.exists(cast.os.path.join(cast.THEMES_DIR, "LICENSE-fluent-emoji.txt"))


def test_set_theme_falls_back_and_switches(monkeypatch, tmp_path):
    monkeypatch.setattr(cast, "MINE", str(tmp_path / "none-yet"))
    before = cast.THEME
    try:
        assert cast.set_theme("nope") == cast.DEFAULT_THEME  # no pictures of your own: the default
        assert cast.set_theme("mine") == cast.DEFAULT_THEME
        assert cast.set_theme("animals") == "animals"
        assert "sloth" in cast.available() and cast.NAMES["sloth"] == "Sloth"
        assert cast.star_path().endswith(cast.os.path.join("themes", "star.png"))
    finally:
        monkeypatch.undo()
        cast.set_theme(before)
