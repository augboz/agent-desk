"""A Tk canvas that only repaints what changed between animation frames.

The scenes redraw everything every frame with plain create_*() calls. Deleting
every item and making it again makes Tk repaint the whole canvas each time,
which is most of Agent Desk's CPU use. FrameCanvas keeps that simple drawing
code but, between begin() and end(), keeps any item that is exactly the same
as one from the last frame, so the sky, the grass and the sleeping characters
stay put and only the moving bits are made again.
"""
import tkinter as tk


def _plain(v):
    if isinstance(v, float):
        return round(v)  # Tk draws on whole pixels: a move of less than one isn't redrawn
    if isinstance(v, (int, str)):
        return v
    return str(v)  # images, fonts and the like, by name


class FrameCanvas(tk.Canvas):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._prev = {}  # what an item looked like -> its ids, from the last frame
        self._now = None  # the same for this frame (None between frames)
        self._key = {}  # id -> what it looks like
        self._order = []  # (id, kept from the last frame), in drawing order
        self._spare = 0

    def begin(self):
        """Start a frame: draw it with the usual create_*() calls, then call end()."""
        if self._now is not None:
            self.end()
        self._now, self._order = {}, []

    def end(self):
        """Finish the frame: drop what wasn't drawn again, and fix the stacking order."""
        if self._now is None:
            return
        for ids in self._prev.values():
            for i in ids:
                self._key.pop(i, None)
                super().delete(i)
        # New items are made on top of everything. Slide each one under the first
        # kept item drawn after it, so everything stacks in drawing order.
        under, nxt = {}, None
        for i, kept in reversed(self._order):
            if kept:
                nxt = i
            elif nxt is not None:
                under[i] = nxt
        for i, kept in self._order:
            if i in under:
                super().tag_lower(i, under[i])
        self._prev, self._now, self._order = self._now, None, []

    def _create(self, itemType, args, kw):
        if self._now is None:
            return super()._create(itemType, args, kw)
        key = (itemType, tuple(_plain(v) for v in tk._flatten(args)),
               tuple(sorted((k, _plain(v)) for k, v in kw.items())))
        ids = self._prev.get(key)
        if ids:
            i, kept = ids.pop(), True
        else:
            i, kept = super()._create(itemType, args, kw), False
        self._now.setdefault(key, []).append(i)
        self._key[i] = key
        self._order.append((i, kept))
        return i

    def _changed(self, tag):
        """An item was moved or changed after it was made: don't reuse it next frame."""
        for i in self.find_withtag(tag):
            key = self._key.pop(i, None)
            for table in (self._now, self._prev):
                if table and key in table and i in table[key]:
                    table[key].remove(i)
                    self._spare += 1
                    table[("changed", self._spare)] = [i]  # never matches: goes at the next end()

    def move(self, tag, *args):
        self._changed(tag)
        return super().move(tag, *args)

    def coords(self, tag, *args):
        if args:
            self._changed(tag)
        return super().coords(tag, *args)

    def itemconfigure(self, tag, cnf=None, **kw):
        if cnf or kw:
            self._changed(tag)
        return super().itemconfigure(tag, cnf, **kw)

    itemconfig = itemconfigure

    def tag_raise(self, tag, *args):
        self._changed(tag)
        return super().tag_raise(tag, *args)

    lift = tkraise = tag_raise

    def tag_lower(self, tag, *args):
        self._changed(tag)
        return super().tag_lower(tag, *args)

    lower = tag_lower

    def delete(self, *tags):
        gone = {i for t in tags for i in self.find_withtag(t)}
        for table in (self._now, self._prev):
            for ids in (table or {}).values():
                ids[:] = [i for i in ids if i not in gone]
        self._order = [(i, k) for i, k in self._order if i not in gone]
        for i in gone:
            self._key.pop(i, None)
        return super().delete(*tags)
