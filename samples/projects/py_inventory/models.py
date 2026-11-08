from abc import ABC, abstractmethod
from dataclasses import dataclass


class Item(ABC):
    def __init__(self, name: str, cents: int):
        self.name = name
        self.cents = cents

    @abstractmethod
    def price(self, qty: int) -> int:
        raise NotImplementedError

    def __str__(self) -> str:
        return f"{self.name}@{self.cents}"


class Book(Item):
    def price(self, qty: int) -> int:
        # every third book is free
        return self.cents * (qty - qty // 3)


class Food(Item):
    def __init__(self, name: str, cents: int, discount_pct: int):
        super().__init__(name, cents)
        self.discount_pct = discount_pct

    def price(self, qty: int) -> int:
        total = self.cents * qty
        return total - total * self.discount_pct // 100


@dataclass
class Line:
    item: Item
    qty: int
