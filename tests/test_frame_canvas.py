"""FrameCanvas keeps unchanged items between frames and stacks them in drawing order."""
import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def canvas():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    root.withdraw()
    from frame_canvas import FrameCanvas
    c = FrameCanvas(root, width=100, height=100)
    yield c
    root.destroy()


def frame(c, draw):
    c.begin()
    ids = draw(c)
    c.end()
    return ids


def test_same_items_are_kept(canvas):
    def draw(c):
        return [c.create_rectangle(0, 0, 50, 50, fill="red"), c.create_oval(10, 10, 20, 20, fill="blue")]
    first = frame(canvas, draw)
    second = frame(canvas, draw)
    assert first == second
    assert list(canvas.find_all()) == first


def test_less_than_a_pixel_is_the_same(canvas):
    a = frame(canvas, lambda c: c.create_rectangle(0, 0, 50.2, 50))
    b = frame(canvas, lambda c: c.create_rectangle(0, 0, 49.9, 50))
    assert a == b


def test_changed_and_gone_items_are_replaced(canvas):
    frame(canvas, lambda c: [c.create_rectangle(0, 0, 50, 50), c.create_text(5, 5, text="a")])
    new = frame(canvas, lambda c: [c.create_rectangle(0, 0, 50, 50), c.create_text(9, 9, text="b")])
    assert list(canvas.find_all()) == sorted(new)
    assert canvas.itemcget(new[1], "text") == "b"
    assert len(canvas.find_all()) == 2


def test_stacking_follows_drawing_order(canvas):
    def draw(x):
        return lambda c: [c.create_rectangle(0, 0, 9, 9, tags="bottom"),
                          c.create_oval(x, 0, x + 5, 5, tags="moving"),  # new each frame
                          c.create_text(50, 50, text="top", tags="top")]
    for x in (0, 10, 20):
        frame(canvas, draw(x))
    order = [canvas.gettags(i)[0] for i in canvas.find_all()]  # find_all is bottom to top
    assert order == ["bottom", "moving", "top"]


def test_moved_items_are_not_reused(canvas):
    def draw(c):
        i = c.create_text(10, 10, text="x")
        c.move(i, 5, 0)
        return i
    for _ in range(3):
        i = frame(canvas, draw)
    assert canvas.coords(i) == [15.0, 10.0]  # moved once, not once per frame
    assert len(canvas.find_all()) == 1


def test_delete_all_starts_afresh(canvas):
    frame(canvas, lambda c: c.create_rectangle(0, 0, 5, 5))
    canvas.delete("all")
    i = frame(canvas, lambda c: c.create_rectangle(0, 0, 5, 5))
    assert list(canvas.find_all()) == [i]
