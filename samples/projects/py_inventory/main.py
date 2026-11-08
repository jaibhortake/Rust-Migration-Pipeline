import sys

from inventory import Inventory


def main() -> None:
    inv = Inventory()
    errors = 0
    for raw in sys.stdin.read().splitlines():
        parts = raw.split()
        if not parts:
            continue
        cmd = parts[0]
        try:
            if cmd == "add":
                extra = int(parts[4]) if len(parts) > 4 else 0
                inv.add(parts[1], parts[2], int(parts[3]), extra)
            elif cmd == "buy":
                if not inv.buy(parts[1], int(parts[2])):
                    print(f"cannot buy {parts[1]}")
            else:
                errors += 1
        except (ValueError, IndexError):
            errors += 1
    for line in inv.summary():
        print(line)
    total = inv.total()
    print(f"total: {total // 100}.{total % 100:02d}")
    print(f"errors: {errors}")


if __name__ == "__main__":
    main()
