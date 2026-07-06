(define (greet name)
  (display "Hello, ")
  (display name)
  (display "!")
  (newline))

(greet "world")

(define (fact n)
  (if (<= n 1) 1 (* n (fact (- n 1)))))

(display (fact 10))
(newline)
