import sys


def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def digit_sum(x):
    return sum(int(c) for c in str(x))


for token in sys.stdin.read().split():
    n = int(token)
    if n < 0:
        print("negative")
        continue
    f = factorial(n)
    print(n, digit_sum(f), len(str(f)), fib(n) % 1000000007, 2 ** n)
