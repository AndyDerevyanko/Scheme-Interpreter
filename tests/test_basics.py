"""Hand-written core-semantics tests for pyscheme.

Usage: python tests/test_basics.py    (or pytest tests/test_basics.py)

Each case is (source, expected_repr): the source is evaluated in a shared
interpreter and the result rendered with scm_repr must match.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pyscheme import Interpreter, scm_repr  # noqa: E402

CASES = [
    # literals & reader
    ("42", "42"),
    ("-3.5", "-3.5"),
    ("1/3", "1/3"),
    ("(+ 1/3 1/6)", "1/2"),
    ("#t", "#t"),
    ("#f", "#f"),
    ('"hi\\nthere"', '"hi\\nthere"'),
    ("#\\a", "#\\a"),
    ("#\\space", "#\\space"),
    ("'foo", "foo"),
    ("'(1 2 3)", "(1 2 3)"),
    ("'(1 . 2)", "(1 . 2)"),
    ("'(1 2 . 3)", "(1 2 . 3)"),
    ("#(1 2 3)", "#(1 2 3)"),
    ("#x10", "16"),
    ("#b101", "5"),
    ("#o17", "15"),
    ("#e1.5", "3/2"),
    ("#i3", "3.0"),

    # arithmetic
    ("(+ 1 2 3 4)", "10"),
    ("(- 10 1 2)", "7"),
    ("(- 5)", "-5"),
    ("(* 2 3 4)", "24"),
    ("(/ 8 2)", "4"),
    ("(/ 7 2)", "7/2"),
    ("(/ 7.0 2)", "3.5"),
    ("(quotient 7 2)", "3"),
    ("(remainder 7 2)", "1"),
    ("(modulo -7 2)", "1"),
    ("(expt 2 10)", "1024"),
    ("(sqrt 16)", "4"),
    ("(abs -7)", "7"),
    ("(max 1 5 3)", "5"),
    ("(min 1 5 3)", "1"),
    ("(= 2 2 2)", "#t"),
    ("(< 1 2 3)", "#t"),
    ("(< 1 3 2)", "#f"),

    # booleans / truthiness (only #f is false)
    ("(if 0 'yes 'no)", "yes"),
    ("(if '() 'yes 'no)", "yes"),
    ('(if "" (quote yes) (quote no))', "yes"),
    ("(if #f 'yes 'no)", "no"),
    ("(not #f)", "#t"),
    ("(not 0)", "#f"),
    ("(and 1 2 3)", "3"),
    ("(and #f 2)", "#f"),
    ("(or #f #f 7)", "7"),
    ("(or)", "#f"),

    # pairs & lists
    ("(cons 1 2)", "(1 . 2)"),
    ("(car '(a b c))", "a"),
    ("(cdr '(a b c))", "(b c)"),
    ("(list 1 2 3)", "(1 2 3)"),
    ("(length '(a b c))", "3"),
    ("(append '(1 2) '(3) '(4 5))", "(1 2 3 4 5)"),
    ("(reverse '(1 2 3))", "(3 2 1)"),
    ("(list-ref '(a b c) 1)", "b"),
    ("(assq 'b '((a 1) (b 2)))", "(b 2)"),
    ("(member 2 '(1 2 3))", "(2 3)"),
    ("(map (lambda (x) (* x x)) '(1 2 3))", "(1 4 9)"),
    ("(map + '(1 2) '(10 20))", "(11 22)"),
    ("(apply + 1 2 '(3 4))", "10"),
    ("(filter odd? '(1 2 3 4 5))", "(1 3 5)"),
    ("(equal? '(1 (2 3)) '(1 (2 3)))", "#t"),
    ("(eq? 'a 'a)", "#t"),
    ("(eqv? 1.5 1.5)", "#t"),
    ("(eqv? 1 1.0)", "#f"),

    # define / set! / closures
    ("(begin (define x 10) x)", "10"),
    ("(begin (set! x 11) x)", "11"),
    ("(begin (define (sq n) (* n n)) (sq 7))", "49"),
    ("(begin (define (make-counter) (define n 0) (lambda () (set! n (+ n 1)) n)) (define c (make-counter)) (c) (c) (c))", "3"),
    ("((lambda args args) 1 2 3)", "(1 2 3)"),
    ("((lambda (a . rest) rest) 1 2 3)", "(2 3)"),

    # let family
    ("(let ((a 2) (b 3)) (* a b))", "6"),
    ("(let* ((a 2) (b (* a a))) b)", "4"),
    ("(letrec ((even2? (lambda (n) (if (= n 0) #t (odd2? (- n 1))))) (odd2? (lambda (n) (if (= n 0) #f (even2? (- n 1)))))) (even2? 10))", "#t"),
    ("(let loop ((i 0) (acc '())) (if (= i 3) (reverse acc) (loop (+ i 1) (cons i acc))))", "(0 1 2)"),

    # cond / case
    ("(cond ((= 1 2) 'a) ((= 1 1) 'b) (else 'c))", "b"),
    ("(cond ((assv 2 '((1 a) (2 b))) => cadr) (else 'nope))", "b"),
    ("(case 3 ((1 2) 'low) ((3 4) 'mid) (else 'high))", "mid"),

    # tail calls: must not blow the stack
    ("(begin (define (count n) (if (= n 0) 'done (count (- n 1)))) (count 500000))", "done"),
    ("(let loop ((i 0)) (if (< i 200000) (loop (+ i 1)) i))", "200000"),

    # quasiquote
    ("`(1 ,(+ 1 1) ,@(list 3 4))", "(1 2 3 4)"),
    ("`(a `(b ,(c ,(+ 1 2))))", "(a (quasiquote (b (unquote (c 3)))))"),

    # strings, chars, vectors, symbols
    ('(string-append "foo" "bar")', '"foobar"'),
    ('(string-length "hello")', "5"),
    ('(substring "hello" 1 3)', '"el"'),
    ("(symbol->string 'abc)", '"abc"'),
    ('(string->symbol "abc")', "abc"),
    ('(string->number "2.5")', "2.5"),
    ("(number->string 255 16)", '"ff"'),
    ('(string-ref "abc" 1)', "#\\b"),
    ("(char->integer #\\A)", "65"),
    ("(integer->char 97)", "#\\a"),
    ("(vector-ref #(a b c) 2)", "c"),
    ("(begin (define v (make-vector 3 0)) (vector-set! v 1 'x) v)", "#(0 x 0)"),
    ("(vector->list #(1 2 3))", "(1 2 3)"),
    ("(list->vector '(1 2 3))", "#(1 2 3)"),

    # call/cc as escape
    ("(call/cc (lambda (k) (+ 1 (k 42))))", "42"),
    ("(+ 1 (call/cc (lambda (k) 10)))", "11"),

    # macros
    ("(begin (define-macro (swap! a b) `(let ((tmp ,a)) (set! ,a ,b) (set! ,b tmp))) (define p 1) (define q 2) (swap! p q) (list p q))", "(2 1)"),
]


def run(verbose=False):
    interp = Interpreter()
    failures = []
    for source, expected in CASES:
        try:
            got = scm_repr(interp.eval_string(source))
        except Exception as exc:
            got = f"raised {type(exc).__name__}: {exc}"
        ok = got == expected
        if verbose or not ok:
            print(f"{'ok  ' if ok else 'FAIL'}  {source}\n      => {got}"
                  + ("" if ok else f"  (expected {expected})"))
        if not ok:
            failures.append(source)
    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} basic tests pass.")
    return failures


def test_basics():
    assert run() == []


if __name__ == "__main__":
    sys.exit(1 if run(verbose="-v" in sys.argv) else 0)
