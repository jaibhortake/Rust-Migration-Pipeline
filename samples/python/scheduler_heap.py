import heapq
import sys
from dataclasses import dataclass, field


@dataclass(order=True)
class Job:
    priority: int
    seq: int
    name: str = field(compare=False)
    cost: int = field(compare=False, default=1)


def main():
    heap = []
    seq = 0
    clock = 0
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "add" and len(parts) >= 4:
            heapq.heappush(heap, Job(int(parts[2]), seq, parts[1], int(parts[3])))
            seq += 1
        elif parts[0] == "run":
            if not heap:
                print("idle")
                continue
            job = heapq.heappop(heap)
            clock += job.cost
            print(f"{job.name} done at {clock}")
        elif parts[0] == "peek":
            print(heap[0].name if heap else "none")
    print("left", len(heap), "clock", clock)


if __name__ == "__main__":
    main()
