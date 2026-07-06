"""Example: embedding pyscheme in a LilyPond-style host application.

Run:  python examples/music_host.py

Demonstrates the host-binding API: native functions registered from
Python, host objects flowing through Scheme code, and Scheme procedures
called back from the host.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyscheme import Interpreter, pylist, scm_repr


class Note:
    def __init__(self, pitch, duration):
        self.pitch = pitch
        self.duration = duration

    def __repr__(self):
        return f"#<note {self.pitch}:{scm_repr(self.duration)}>"


class Score:
    def __init__(self, notes):
        self.notes = notes

    def __repr__(self):
        inner = " ".join(repr(n) for n in self.notes)
        return f"#<score {inner}>"


def main():
    interp = Interpreter()

    @interp.native("note")
    def note(pitch, duration):
        return Note(pitch, duration)

    @interp.native("score")
    def score(*notes):
        return Score(list(notes))

    @interp.native("transpose")
    def transpose(n, steps):
        scale = ["c", "d", "e", "f", "g", "a", "b"]
        idx = (scale.index(n.pitch) + steps) % len(scale)
        return Note(scale[idx], n.duration)

    result = interp.eval_string("""
        (define melody
          (list (note "c" 1/4) (note "e" 1/4) (note "g" 1/2)))

        (define (transpose-all notes steps)
          (map (lambda (n) (transpose n steps)) notes))

        (score (apply score melody)
               (apply score (transpose-all melody 2)))
    """)
    print("Scheme built:", result)

    # Host calling a Scheme procedure directly:
    third = interp.call("transpose-all",
                        interp.lookup("melody"),
                        4)
    print("Host call   :", pylist(third))


if __name__ == "__main__":
    main()
