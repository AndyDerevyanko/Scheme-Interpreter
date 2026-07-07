;;; Complex Scheme Demo

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Utilities

(define (foldl f acc lst)
  (if (null? lst)
      acc
      (foldl f (f acc (car lst)) (cdr lst))))

(define (foldr f acc lst)
  (if (null? lst)
      acc
      (f (car lst)
         (foldr f acc (cdr lst)))))

(define (filter pred lst)
  (cond ((null? lst) '())
        ((pred (car lst))
         (cons (car lst)
               (filter pred (cdr lst))))
        (else
         (filter pred (cdr lst)))))

(define (range a b)
  (if (> a b)
      '()
      (cons a (range (+ a 1) b))))

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Quicksort

(define (quicksort lst)
  (if (or (null? lst) (null? (cdr lst)))
      lst
      (let* ((pivot (car lst))
             (rest (cdr lst))
             (less (filter (lambda (x) (< x pivot)) rest))
             (more (filter (lambda (x) (>= x pivot)) rest)))
        (append (quicksort less)
                (list pivot)
                (quicksort more)))))

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Fibonacci (memoized)

(define memo '())

(define (memo-get n)
  (assoc n memo))

(define (fib n)
  (let ((entry (memo-get n)))
    (if entry
        (cdr entry)
        (let ((value
               (if (< n 2)
                   n
                   (+ (fib (- n 1))
                      (fib (- n 2))))))
          (set! memo (cons (cons n value) memo))
          value))))

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Binary Tree

(define (node value left right)
  (list value left right))

(define (value t) (car t))
(define (left t) (cadr t))
(define (right t) (caddr t))

(define (tree-sum t)
  (if (null? t)
      0
      (+ (value t)
         (tree-sum (left t))
         (tree-sum (right t)))))

(define tree
  (node 8
        (node 3
              (node 1 '() '())
              (node 6
                    (node 4 '() '())
                    (node 7 '() '())))
        (node 10
              '()
              (node 14
                    (node 13 '() '())
                    '()))))

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Closure

(define (make-counter)
  (let ((count 0))
    (lambda ()
      (set! count (+ count 1))
      count)))

(define counter (make-counter))

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Macro

(define-syntax unless
  (syntax-rules ()
    ((_ cond body ...)
     (if (not cond)
         (begin body ...)))))

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Streams

(define-syntax stream-cons
  (syntax-rules ()
    ((_ a b)
     (cons a (delay b)))))

(define (stream-car s)
  (car s))

(define (stream-cdr s)
  (force (cdr s)))

(define (integers-from n)
  (stream-cons n
               (integers-from (+ n 1))))

(define (stream-take s n)
  (if (= n 0)
      '()
      (cons (stream-car s)
            (stream-take
             (stream-cdr s)
             (- n 1)))))

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Main

(display "Sorted: ")
(display (quicksort '(8 4 9 1 6 7 3 5 2)))
(newline)

(display "Fib 35: ")
(display (fib 35))
(newline)

(display "Tree Sum: ")
(display (tree-sum tree))
(newline)

(display "Counter: ")
(display (counter))
(display ", ")
(display (counter))
(display ", ")
(display (counter))
(newline)

(unless #f
  (display "Unless macro works!")
  (newline))

(display "First 20 integers: ")
(display (stream-take (integers-from 1) 20))
(newline)

(display "Factorial 10: ")
(display
 (foldl *
        1
        (range 1 10)))
(newline)

(display "Done.")
(newline)