import sys

from ledger import Account, InsufficientFunds


def main() -> None:
    accounts: dict[str, Account] = {}
    for line in sys.stdin:
        p = line.split()
        if len(p) < 2:
            continue
        op, name = p[0], p[1]
        acc = accounts.setdefault(name, Account(name))
        amount = int(p[2]) if len(p) > 2 else 0
        if op == "dep":
            acc.deposit(amount)
        elif op == "wd":
            try:
                acc.withdraw(amount)
            except InsufficientFunds as e:
                print(f"denied: {e.account} short by {e.needed}")
        elif op == "int":
            acc.deposit(acc.interest(amount))
        elif op == "loan":
            acc.balance -= amount
    for acc in sorted(accounts.values()):
        print(acc.owner, acc.balance, len(acc.history))


if __name__ == "__main__":
    main()
