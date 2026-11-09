import sys


def numbers(lines):
    for line in lines:
        for tok in line.split():
            try:
                yield int(tok)
            except ValueError:
                continue


def running_max(stream):
    best = None
    for x in stream:
        if best is None or x > best:
            best = x
        yield best


def windows(stream, size):
    buf = []
    for x in stream:
        buf.append(x)
        if len(buf) > size:
            buf.pop(0)
        if len(buf) == size:
            yield sum(buf) // size


data = list(numbers(sys.stdin.read().splitlines()))
print("count", len(data))
print("running max", list(running_max(data)))
print("window avg", list(windows(data, 3)))
print("negative halves", [x // 2 for x in data if x < 0])
