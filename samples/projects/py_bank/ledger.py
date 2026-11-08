class InsufficientFunds(Exception):
    def __init__(self, account: str, needed: int):
        super().__init__(f"{account} needs {needed} more")
        self.account = account
        self.needed = needed


class Account:
    def __init__(self, owner: str, balance: int = 0):
        self.owner = owner
        self.balance = balance
        self.history: list[int] = []

    def deposit(self, amount: int) -> None:
        self.balance += amount
        self.history.append(amount)

    def withdraw(self, amount: int) -> None:
        if amount > self.balance:
            raise InsufficientFunds(self.owner, amount - self.balance)
        self.balance -= amount
        self.history.append(-amount)

    def interest(self, rate_bp: int) -> int:
        # basis points, floored like the bank does (also for negative balances)
        return self.balance * rate_bp // 10000

    def __lt__(self, other: "Account") -> bool:
        return (self.balance, self.owner) < (other.balance, other.owner)
