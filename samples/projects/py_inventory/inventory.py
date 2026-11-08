from models import Book, Food, Item, Line


class Inventory:
    def __init__(self):
        self.items: dict[str, Item] = {}
        self.cart: list[Line] = []

    def add(self, kind: str, name: str, cents: int, extra: int = 0) -> None:
        if kind == "book":
            self.items[name] = Book(name, cents)
        elif kind == "food":
            self.items[name] = Food(name, cents, extra)
        else:
            raise ValueError(f"unknown kind {kind}")

    def buy(self, name: str, qty: int) -> bool:
        if name not in self.items or qty <= 0:
            return False
        self.cart.append(Line(self.items[name], qty))
        return True

    def total(self) -> int:
        return sum(line.item.price(line.qty) for line in self.cart)

    def summary(self) -> list[str]:
        per_item: dict[str, int] = {}
        for line in self.cart:
            per_item[line.item.name] = per_item.get(line.item.name, 0) + line.item.price(line.qty)
        return [f"{name}: {cents // 100}.{cents % 100:02d}" for name, cents in per_item.items()]
