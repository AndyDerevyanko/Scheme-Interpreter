"""REPL and script runner: python -m pyscheme [file.scm ...]"""

import sys

from .errors import SchemeError
from .interpreter import Interpreter
from .types import scm_repr


def _balanced(text):
    """True when parens are balanced outside strings/comments (roughly)."""
    depth = 0
    in_string = False
    escape = False
    in_comment = False
    for c in text:
        if in_comment:
            if c == "\n":
                in_comment = False
        elif in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == ";":
            in_comment = True
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
    return depth <= 0 and not in_string


def repl(interp):
    print(f"pyscheme 0.1.0 on Python {sys.version.split()[0]}")
    print("Type expressions; Ctrl-Z + Enter (Windows) or Ctrl-D to exit.")
    while True:
        try:
            lines = [input("scheme> ")]
            while not _balanced("\n".join(lines)):
                lines.append(input("   ...> "))
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print()
            continue
        source = "\n".join(lines).strip()
        # Windows pipes may deliver a UTF-8 BOM as raw bytes/mojibake.
        source = source.lstrip("﻿\xef\xbb\xbf")
        if not source:
            continue
        try:
            value = interp.eval_string(source, filename="<repl>")
            if value is not None:
                print(scm_repr(value))
        except SchemeError as exc:
            print(f"error: {exc}", file=sys.stderr)
        except RecursionError:
            print("error: maximum recursion depth exceeded", file=sys.stderr)
        except Exception as exc:  # keep the REPL alive
            print(f"error ({type(exc).__name__}): {exc}", file=sys.stderr)


def main(argv):
    interp = Interpreter()
    if argv:
        for path in argv:
            interp.eval_file(path)
    else:
        repl(interp)


if __name__ == "__main__":
    main(sys.argv[1:])
