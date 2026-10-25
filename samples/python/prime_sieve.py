import sys


def sieve(n):
    if n < 2:
        return []
    flags = [True] * (n + 1)
    flags[0] = flags[1] = False
    for i in range(2, int(n ** 0.5) + 1):
        if flags[i]:
            for j in range(i * i, n + 1, i):
                flags[j] = False
    return [i for i, f in enumerate(flags) if f]


n = int(sys.stdin.readline())
print(" ".join(map(str, sieve(n))))
