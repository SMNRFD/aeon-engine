"""Economy — markets, trade goods, banks, loans, inflation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional

from engine.utils.rng import RNG


@dataclass
class TradeGood:
    """A trade-able commodity."""

    id: str
    name: str
    category: str   # food, raw_material, manufactured, luxury, magic
    base_price: int   # copper pieces per unit
    weight: float = 1.0
    perishable: bool = False
    base_demand: float = 1.0
    base_supply: float = 1.0
    description: str = ""
    tags: list[str] = field(default_factory=list)


class TradeGoodLibrary:
    """Registry of trade goods."""

    _goods: ClassVar[dict[str, TradeGood]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, good: TradeGood) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._goods[good.id] = good

    @classmethod
    def get(cls, good_id: str) -> Optional[TradeGood]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._goods.get(good_id)

    @classmethod
    def all(cls) -> list[TradeGood]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._goods.values())

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for g in DEFAULT_GOODS:
            cls._goods[g.id] = g
        cls._defaults_loaded = True


@dataclass
class MarketListing:
    """A single listing on a market."""

    good_id: str
    quantity: int
    price_per_unit: int
    seller_id: Optional[int] = None
    listed_at: float = 0.0


class Market:
    """A regional market with dynamic pricing."""

    def __init__(self, market_id: int, name: str, location: tuple[int, int]) -> None:
        self.id = market_id
        self.name = name
        self.location = location
        self.listings: list[MarketListing] = []
        # Supply / demand per good (dynamic)
        self.supply: dict[str, float] = {}
        self.demand: dict[str, float] = {}
        self.price_history: dict[str, list[int]] = {}
        self.inflation: float = 0.0
        self.wealth: int = 10000  # copper pieces of buying power
        self.population: int = 500

    def price_for(self, good_id: str) -> int:
        good = TradeGoodLibrary.get(good_id)
        if good is None:
            return 0
        supply = self.supply.get(good_id, good.base_supply)
        demand = self.demand.get(good_id, good.base_demand)
        # Standard supply/demand curve
        ratio = demand / max(0.01, supply)
        multiplier = ratio ** 0.5  # dampened
        multiplier = max(0.3, min(3.0, multiplier))
        # Apply inflation
        multiplier *= (1.0 + self.inflation)
        # Apply population-based demand
        pop_factor = self.population / 500.0
        return max(1, int(good.base_price * multiplier * pop_factor))

    def buy(self, good_id: str, quantity: int, buyer_gold: int) -> tuple[int, int]:
        """Buy `quantity` units. Returns (quantity bought, total cost)."""
        price = self.price_for(good_id)
        # Buy up to what buyer can afford and what market has
        affordable = buyer_gold // price if price > 0 else 0
        bought = min(quantity, affordable)
        # Reduce supply
        self.supply[good_id] = max(0.0, self.supply.get(good_id, 1.0) - bought * 0.1)
        # Increase demand slightly (more people want it)
        self.demand[good_id] = self.demand.get(good_id, 1.0) + bought * 0.05
        return bought, bought * price

    def sell(self, good_id: str, quantity: int) -> tuple[int, int]:
        """Sell `quantity` units. Returns (quantity sold, total revenue)."""
        price = self.price_for(good_id)
        # Sell up to market wealth
        sold = min(quantity, self.wealth // price if price > 0 else 0)
        # Increase supply
        self.supply[good_id] = self.supply.get(good_id, 1.0) + sold * 0.1
        # Reduce demand
        self.demand[good_id] = max(0.1, self.demand.get(good_id, 1.0) - sold * 0.05)
        self.wealth -= sold * price
        return sold, sold * price

    def update(self, dt: float) -> None:
        """Drift supply/demand back toward equilibrium."""
        for good_id in list(self.supply.keys()):
            base = TradeGoodLibrary.get(good_id)
            if base is None:
                continue
            self.supply[good_id] = (self.supply[good_id] * 0.995
                                    + base.base_supply * 0.005)
            self.demand[good_id] = (self.demand[good_id] * 0.995
                                    + base.base_demand * 0.005)
            # Record price history
            hist = self.price_history.setdefault(good_id, [])
            hist.append(self.price_for(good_id))
            if len(hist) > 60:
                hist.pop(0)
        # Wealth regenerates as population earns
        self.wealth = int(self.wealth * 1.001 + self.population * 0.5 * dt)


# ---------- Banking ----------

@dataclass
class Loan:
    """An outstanding loan."""

    principal: int
    interest_rate: float   # monthly
    remaining: int
    months_remaining: int
    monthly_payment: int
    borrower_id: int
    created_tick: float = 0.0


@dataclass
class Account:
    """A bank account."""

    account_id: int
    holder_id: int
    balance: int = 0
    loans: list[Loan] = field(default_factory=list)
    credit_limit: int = 1000


class Bank:
    """A banking institution."""

    def __init__(self, bank_id: int, name: str, location: tuple[int, int]) -> None:
        self.id = bank_id
        self.name = name
        self.location = location
        self.accounts: dict[int, Account] = {}
        self.reserve: int = 100000
        self.base_interest: float = 0.05  # monthly
        self.loan_interest: float = 0.10

    def open_account(self, holder_id: int) -> Account:
        if holder_id not in self.accounts:
            account_id = len(self.accounts) + 1
            self.accounts[holder_id] = Account(account_id=account_id, holder_id=holder_id)
        return self.accounts[holder_id]

    def deposit(self, holder_id: int, amount: int) -> int:
        acc = self.open_account(holder_id)
        acc.balance += amount
        self.reserve += amount
        return acc.balance

    def withdraw(self, holder_id: int, amount: int) -> int:
        acc = self.open_account(holder_id)
        withdraw_amount = min(amount, acc.balance)
        acc.balance -= withdraw_amount
        self.reserve -= withdraw_amount
        return withdraw_amount

    def take_loan(self, holder_id: int, amount: int, months: int = 12,
                  current_tick: float = 0.0) -> Optional[Loan]:
        acc = self.open_account(holder_id)
        total_debt = sum(l.remaining for l in acc.loans)
        if total_debt + amount > acc.credit_limit:
            return None
        if self.reserve < amount:
            return None
        monthly = max(1, int(amount * (1 + self.loan_interest) / months))
        loan = Loan(
            principal=amount, interest_rate=self.loan_interest,
            remaining=amount * (1 + int(self.loan_interest * months)),
            months_remaining=months, monthly_payment=monthly,
            borrower_id=holder_id, created_tick=current_tick,
        )
        acc.loans.append(loan)
        acc.balance += amount
        self.reserve -= amount
        return loan

    def monthly_tick(self) -> None:
        """Process monthly interest and loan payments."""
        # Pay interest on deposits
        for acc in self.accounts.values():
            if acc.balance > 0:
                interest = int(acc.balance * self.base_interest / 12)
                acc.balance += interest
                self.reserve -= interest
            # Auto-pay loans
            for loan in list(acc.loans):
                if acc.balance >= loan.monthly_payment:
                    acc.balance -= loan.monthly_payment
                    loan.remaining -= loan.monthly_payment
                    loan.months_remaining -= 1
                    self.reserve += loan.monthly_payment
                    if loan.months_remaining <= 0 or loan.remaining <= 0:
                        acc.loans.remove(loan)
                else:
                    # Default — penalty
                    loan.remaining = int(loan.remaining * 1.1)


class EconomySystem:
    """Top-level economy coordinator."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self.markets: dict[int, Market] = {}
        self.banks: dict[int, Bank] = {}
        self.inflation_rate: float = 0.0
        self.global_wealth: int = 1_000_000

    def create_market(self, market_id: int, name: str, location: tuple[int, int]) -> Market:
        m = Market(market_id, name, location)
        # Seed supply/demand with noise
        for good in TradeGoodLibrary.all():
            m.supply[good.id] = good.base_supply * self.rng.uniform(0.5, 2.0)
            m.demand[good.id] = good.base_demand * self.rng.uniform(0.5, 2.0)
        self.markets[market_id] = m
        return m

    def create_bank(self, bank_id: int, name: str, location: tuple[int, int]) -> Bank:
        b = Bank(bank_id, name, location)
        self.banks[bank_id] = b
        return b

    def update(self, dt: float) -> None:
        for market in self.markets.values():
            market.update(dt)
        # Inflation drifts based on global wealth
        target_inflation = max(-0.02, min(0.05, (self.global_wealth - 1_000_000) / 50_000_000))
        self.inflation_rate += (target_inflation - self.inflation_rate) * 0.01 * dt


# ---------- Default trade goods ----------

DEFAULT_GOODS: list[TradeGood] = [
    TradeGood("grain", "Grain", "food", 5, 1.0, True, 2.0, 2.0, "A staple food."),
    TradeGood("bread", "Bread", "food", 12, 0.5, True, 1.5, 1.0, "Baked from grain."),
    TradeGood("meat", "Meat", "food", 20, 1.0, True, 1.0, 0.8, "Preserved meat."),
    TradeGood("fish", "Fish", "food", 10, 0.8, True, 1.2, 1.0, "Fresh-caught fish."),
    TradeGood("wine", "Wine", "luxury", 50, 1.0, False, 0.5, 0.6, "A fine vintage."),
    TradeGood("ale", "Ale", "food", 8, 1.0, False, 1.0, 1.2, "A common drink."),
    TradeGood("iron_ore", "Iron Ore", "raw_material", 15, 2.0, False, 1.0, 1.0, "Raw iron."),
    TradeGood("iron_ingot", "Iron Ingot", "raw_material", 40, 1.0, False, 0.5, 0.8, "Refined iron."),
    TradeGood("steel_ingot", "Steel Ingot", "raw_material", 80, 1.0, False, 0.3, 0.5, "Refined steel."),
    TradeGood("coal", "Coal", "raw_material", 8, 1.0, False, 0.8, 0.6, "Fuel for smelting."),
    TradeGood("wood", "Wood", "raw_material", 6, 1.0, False, 2.0, 2.0, "Timber."),
    TradeGood("leather_hide", "Leather Hide", "raw_material", 25, 1.5, False, 0.6, 0.5, "Untanned hide."),
    TradeGood("cotton", "Cotton", "raw_material", 10, 0.5, False, 0.8, 0.7, "Raw fibre."),
    TradeGood("silk_cloth", "Silk Cloth", "luxury", 200, 0.3, False, 0.2, 0.3, "Fine fabric."),
    TradeGood("wool_cloth", "Wool Cloth", "raw_material", 30, 0.5, False, 0.6, 0.8, "Woollen fabric."),
    TradeGood("gemstone", "Gemstone", "luxury", 500, 0.1, False, 0.1, 0.2, "A precious stone."),
    TradeGood("gold_ore", "Gold Ore", "raw_material", 100, 2.0, False, 0.1, 0.2, "Raw gold."),
    TradeGood("spice", "Spice", "luxury", 80, 0.2, False, 0.3, 0.4, "Exotic spice."),
    TradeGood("salt", "Salt", "food", 15, 0.5, False, 0.8, 1.0, "Preserves food."),
    TradeGood("magic_crystal", "Magic Crystal", "magic", 1000, 0.5, False, 0.05, 0.1,
              "A resonant arcane crystal."),
    TradeGood("potion_ingredients", "Alchemical Reagents", "magic", 60, 0.3, False,
              0.3, 0.4, "Herbs and reagents for potions."),
    TradeGood("rare_herb", "Rare Herb", "magic", 90, 0.1, True, 0.2, 0.3,
              "A sought-after herb."),
]
