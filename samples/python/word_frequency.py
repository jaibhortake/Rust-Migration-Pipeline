import sys

counts = {}
for line in sys.stdin:
    for word in line.lower().split():
        counts[word] = counts.get(word, 0) + 1

for word, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
    print(word, c)
