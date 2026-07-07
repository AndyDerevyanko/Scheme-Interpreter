# Scheme-Interpreter

A small, embeddable Scheme interpreter in pure Python (no dependencies)

## Quick start

```
python -m pyscheme              # REPL
python -m pyscheme file.scm     # run a script
```

```scheme
scheme> (define (fact n) (if (<= n 1) 1 (* n (fact (- n 1)))))
scheme> (fact 50)
30414093201713378043612608166064768844377641568960512000000000000
```

## Embedding (the LilyPond use case)

```python
from pyscheme import Interpreter

interp = Interpreter()

@interp.native("note")                      # expose host functions
def note(pitch, duration):
    return MyNoteObject(pitch, duration)

interp.eval_string('(note "c" 1/4)')        # host objects flow through Scheme
interp.call("some-scheme-proc", arg1, arg2) # call Scheme from the host
```

See [examples/music_host.py](examples/music_host.py) for a working demo.
The language core (`reader`, `evaluator`, `builtins`) knows nothing about
music; host bindings are plugged in per-application via `Interpreter`.

## What's implemented

- **Reader**: lists, dotted pairs, vectors `#(...)`, bytevectors `#u8(...)`,
  strings with escapes, characters, `'` `` ` `` `,` `,@`, line/block/datum
  comments, radix & exactness prefixes (`#x` `#b` `#o` `#e` `#i`),
  rationals (`1/3`), complex literals (`1+2i`), `|piped symbols|`
- **Numbers**: unlimited-precision integers, exact rationals
  (`fractions.Fraction`), reals, complex
- **Special forms**: `quote quasiquote if define set! lambda begin
  let let* letrec` (incl. named `let`), `cond case and or define-macro`
- **Semantics**: lexical closures, proper tail calls (loops run in constant
  stack), variadic & curried defines, non-hygienic macros, escape-only
  `call/cc`
- **~150 builtins**: list/vector/string/char ops, `map for-each apply
  filter assoc member equal?` etc., `display write error gensym`

Garbage collection is Python's (host GC handles cycles); errors subclass
Python's `SyntaxError`/`TypeError`/`NameError` so hosts can catch either.

## Not yet implemented (roadmap)

`syntax-rules` (hygienic macros), full re-entrant continuations,
`dynamic-wind`, `values`/`call-with-values`, ports & string I/O, `do`,
`delay`/`force`, `define-record-type`, `guard`/exceptions, string mutation.

## Tests

```
python tests/test_basics.py    # hand-written core semantics (99 cases)
python tests/run_norvig.py     # Peter Norvig's lispy suite (81 cases, all pass)
python tests/run_r7rs.py       # chibi-scheme R7RS suite — compatibility metric
```
## Layout

| Module | Role |
|---|---|
| [pyscheme/reader.py](pyscheme/reader.py) | source text → S-expressions |
| [pyscheme/types.py](pyscheme/types.py) | value representation (Pair, Symbol, Char, ...) |
| [pyscheme/evaluator.py](pyscheme/evaluator.py) | trampolined eval loop, special forms, tail calls |
| [pyscheme/environment.py](pyscheme/environment.py) | lexical environments |
| [pyscheme/builtins.py](pyscheme/builtins.py) | native procedures, global environment |
| [pyscheme/interpreter.py](pyscheme/interpreter.py) | embeddable facade / host-binding API |
| [pyscheme/__main__.py](pyscheme/__main__.py) | REPL & script runner |
