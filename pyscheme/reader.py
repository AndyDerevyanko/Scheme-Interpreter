"""Reader: turns source text into Scheme data (S-expressions).

Supports: lists, dotted pairs, vectors #(...), bytevectors #u8(...),
strings with escapes, characters #\\x, booleans #t/#f, quote family
(' ` , ,@), line comments (;), block comments (#| ... |#, nesting),
datum comments (#;), radix/exactness prefixes (#x #b #o #d #e #i),
integers, rationals (n/d), reals, and complex literals (1+2i).
"""

from fractions import Fraction

from .errors import SchemeSyntaxError
from .types import (Char, CHAR_BY_NAME, Pair, intern, nil, normalize_number,
                    slist)

_EOF = object()

_DELIMITERS = set(' \t\n\r()";')

_QUOTE_SUGAR = {
    "'": "quote",
    "`": "quasiquote",
    ",": "unquote",
    ",@": "unquote-splicing",
}

_NAMED_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "a": "\x07", "b": "\x08",
    "0": "\x00", "\\": "\\", '"': '"',
}


class Reader:
    def __init__(self, text, filename="<string>"):
        self.text = text
        self.n = len(text)
        self.i = 0
        self.filename = filename

    # ------------------------------------------------------------ helpers

    def _position(self, index=None):
        index = self.i if index is None else index
        line = self.text.count("\n", 0, index) + 1
        col = index - (self.text.rfind("\n", 0, index) + 1) + 1
        return line, col

    def _error(self, message, index=None):
        line, col = self._position(index)
        return SchemeSyntaxError(message, line, col)

    def _peek(self, offset=0):
        j = self.i + offset
        return self.text[j] if j < self.n else ""

    def _skip_atmosphere(self):
        """Skip whitespace and comments (line, block, directives)."""
        text, n = self.text, self.n
        whitespace = " \t\n\r\f\ufeff"  # tolerate a stray byte-order mark
        while self.i < n:
            c = text[self.i]
            if c in whitespace:
                self.i += 1
            elif c == ";":
                j = text.find("\n", self.i)
                self.i = n if j < 0 else j + 1
            elif c == "#" and self._peek(1) == "|":
                depth = 1
                self.i += 2
                while self.i < n and depth:
                    if text.startswith("#|", self.i):
                        depth += 1
                        self.i += 2
                    elif text.startswith("|#", self.i):
                        depth -= 1
                        self.i += 2
                    else:
                        self.i += 1
                if depth:
                    raise self._error("unterminated block comment #| ... |#")
            elif c == "#" and self._peek(1) == "!":
                # #!fold-case and friends: treat as a directive and ignore.
                self.i += 2
                while self.i < n and text[self.i] not in _DELIMITERS:
                    self.i += 1
            else:
                return

    # ------------------------------------------------------------ reading

    def read_all(self):
        forms = []
        while True:
            form = self.read()
            if form is _EOF:
                return forms
            forms.append(form)

    def read(self):
        self._skip_atmosphere()
        if self.i >= self.n:
            return _EOF
        c = self.text[self.i]

        if c == "(" or c == "[":
            self.i += 1
            return self._read_list(")" if c == "(" else "]")
        if c == ")" or c == "]":
            raise self._error(f"unexpected '{c}'")
        if c == "'" or c == "`":
            self.i += 1
            return self._sugar(_QUOTE_SUGAR[c])
        if c == ",":
            if self._peek(1) == "@":
                self.i += 2
                return self._sugar(",@")
            self.i += 1
            return self._sugar(",")
        if c == '"':
            return self._read_string()
        if c == "#":
            return self._read_hash()
        if c == "|":
            return self._read_piped_symbol()
        return self._read_atom()

    def _sugar(self, key):
        head = intern(_QUOTE_SUGAR.get(key, key))
        datum = self.read()
        if datum is _EOF:
            raise self._error(f"unexpected end of input after {key}")
        return Pair(head, Pair(datum, nil))

    def _read_list(self, closer):
        items = []
        tail = nil
        start = self.i - 1
        while True:
            self._skip_atmosphere()
            if self.i >= self.n:
                raise self._error("unterminated list", start)
            c = self.text[self.i]
            if c == closer:
                self.i += 1
                return slist(items, tail)
            if c in ")]":
                raise self._error(f"mismatched '{c}'")
            if (c == "." and (self.i + 1 >= self.n
                              or self.text[self.i + 1] in _DELIMITERS)):
                if not items:
                    raise self._error("dot '.' with no preceding datum")
                self.i += 1
                tail = self.read()
                if tail is _EOF:
                    raise self._error("unterminated dotted pair", start)
                self._skip_atmosphere()
                if self.i >= self.n or self.text[self.i] != closer:
                    raise self._error("expected exactly one datum after '.'")
                self.i += 1
                return slist(items, tail)
            item = self.read()
            if item is _EOF:
                raise self._error("unterminated list", start)
            items.append(item)

    def _read_string(self):
        start = self.i
        self.i += 1  # opening quote
        chars = []
        text, n = self.text, self.n
        while self.i < n:
            c = text[self.i]
            if c == '"':
                self.i += 1
                return "".join(chars)
            if c == "\\":
                self.i += 1
                if self.i >= n:
                    break
                e = text[self.i]
                if e == "x":
                    self.i += 1
                    j = text.find(";", self.i)
                    if j < 0:
                        # tolerate two-digit \xNN without semicolon
                        j = self.i + 2
                        chars.append(chr(int(text[self.i:j], 16)))
                        self.i = j
                    else:
                        chars.append(chr(int(text[self.i:j], 16)))
                        self.i = j + 1
                elif e == "\n" or e in " \t":
                    # line continuation: skip whitespace through newline
                    while self.i < n and text[self.i] in " \t":
                        self.i += 1
                    if self.i < n and text[self.i] == "\n":
                        self.i += 1
                    while self.i < n and text[self.i] in " \t":
                        self.i += 1
                else:
                    chars.append(_NAMED_ESCAPES.get(e, e))
                    self.i += 1
            else:
                chars.append(c)
                self.i += 1
        raise self._error("unterminated string", start)

    def _read_piped_symbol(self):
        start = self.i
        self.i += 1
        chars = []
        text, n = self.text, self.n
        while self.i < n:
            c = text[self.i]
            if c == "|":
                self.i += 1
                return intern("".join(chars))
            if c == "\\":
                self.i += 1
                if self.i >= n:
                    break
                e = text[self.i]
                if e == "x":
                    self.i += 1
                    j = text.find(";", self.i)
                    if j < 0:
                        raise self._error("bad \\x escape in |symbol|", start)
                    chars.append(chr(int(text[self.i:j], 16)))
                    self.i = j + 1
                else:
                    chars.append(_NAMED_ESCAPES.get(e, e))
                    self.i += 1
            else:
                chars.append(c)
                self.i += 1
        raise self._error("unterminated |symbol|", start)

    def _read_hash(self):
        c1 = self._peek(1)
        if c1 == "(":
            self.i += 2
            vec = self._read_list(")")
            return list(vec)
        if self.text.startswith("#u8(", self.i):
            self.i += 4
            items = self._read_list(")")
            return bytearray(list(items))
        if c1 == ";":
            self.i += 2
            discarded = self.read()  # datum comment: drop next datum
            if discarded is _EOF:
                raise self._error("expected datum after #;")
            return self.read()
        if c1 == "\\":
            return self._read_char()
        token = self._read_token()
        lowered = token.lower()
        if lowered in ("#t", "#true"):
            return True
        if lowered in ("#f", "#false"):
            return False
        return self._parse_prefixed_number(token)

    def _read_char(self):
        self.i += 2  # skip #\
        if self.i >= self.n:
            raise self._error("unterminated character literal")
        first = self.text[self.i]
        self.i += 1
        name = first
        while self.i < self.n and self.text[self.i] not in _DELIMITERS:
            name += self.text[self.i]
            self.i += 1
        if len(name) == 1:
            return Char(name)
        lowered = name.lower()
        if lowered in CHAR_BY_NAME:
            return Char(CHAR_BY_NAME[lowered])
        if lowered.startswith("x"):
            try:
                return Char(chr(int(name[1:], 16)))
            except ValueError:
                pass
        raise self._error(f"unknown character literal #\\{name}")

    def _read_token(self):
        start = self.i
        while self.i < self.n and self.text[self.i] not in _DELIMITERS:
            self.i += 1
        return self.text[start:self.i]

    def _parse_prefixed_number(self, token):
        radixes = {"x": 16, "b": 2, "o": 8, "d": 10}
        exactness = None
        base = None
        body = token
        while body.startswith("#") and len(body) > 1:
            p = body[1].lower()
            if p in radixes and base is None:
                base = radixes[p]
            elif p in "ei" and exactness is None:
                exactness = p
            else:
                raise self._error(f"unknown # syntax: {token}")
            body = body[2:]

        if base is not None and base != 10:
            value = self._parse_radix_body(body, base, token)
        else:
            value = parse_number(body)
            if value is None:
                raise self._error(f"bad number literal {token}")
        if exactness == "e" and isinstance(value, float):
            return normalize_number(Fraction(value).limit_denominator(10**12))
        if exactness == "i" and isinstance(value, (int, Fraction)):
            return float(value)
        return value

    def _parse_radix_body(self, body, base, token):
        try:
            if body.lower().endswith("i"):
                inner = body[:-1]
                split = max(inner.rfind("+", 1), inner.rfind("-", 1))
                if split > 0:
                    real = int(inner[:split], base)
                    imag_text = inner[split:]
                    imag = 1 if imag_text == "+" else -1 if imag_text == "-" \
                        else int(imag_text, base)
                    return complex(real, imag)
            if "/" in body:
                num, _, den = body.partition("/")
                return normalize_number(Fraction(int(num, base), int(den, base)))
            return int(body, base)
        except (ValueError, ZeroDivisionError):
            raise self._error(f"bad number literal {token}")

    def _read_atom(self):
        start = self.i
        token = self._read_token()
        if not token:
            raise self._error(f"unexpected character {self.text[self.i]!r}", start)
        value = parse_number(token)
        if value is not None:
            return value
        return intern(token)


def parse_number(token):
    """Parse a bare numeric token; return None if it isn't a number."""
    if not token:
        return None
    low = token.lower()
    if low in ("+inf.0", "+inf"):
        return float("inf")
    if low in ("-inf.0", "-inf"):
        return float("-inf")
    if low in ("+nan.0", "-nan.0", "+nan", "-nan"):
        return float("nan")
    try:
        return int(token)
    except ValueError:
        pass
    if "/" in token:
        num, _, den = token.partition("/")
        try:
            return normalize_number(Fraction(int(num), int(den)))
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(token)
    except ValueError:
        pass
    if low.endswith("i") and token not in ("+i", "-i", "i"):
        try:
            return complex(low[:-1] + "j")
        except ValueError:
            return None
    if token == "+i":
        return complex(0, 1)
    if token == "-i":
        return complex(0, -1)
    return None


def parse(text, filename="<string>"):
    """Parse source text into a Python list of top-level forms."""
    return Reader(text, filename).read_all()


def parse_one(text, filename="<string>"):
    """Parse exactly one datum from the text."""
    reader = Reader(text, filename)
    form = reader.read()
    if form is _EOF:
        raise SchemeSyntaxError("no expression found")
    return form
