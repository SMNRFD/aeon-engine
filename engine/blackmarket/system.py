"""Black market system — illegal trade, fencing, smuggling.

Black markets are hidden markets where:
* Stolen goods can be fenced (sold for a fraction of value)
* Illegal substances (poisons, forbidden magic) can be purchased
* Contraband can be smuggled between regions
* Assassins and thieves can be hired
* Prices are higher but no questions asked
* Risk of being caught by guards
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.utils.rng import RNG


@dataclass
class BlackMarketListing:
    """A listing on a black market."""

    listing_id: int
    item_id: Optional[int] = None
    item_name: str = ""
    item_type: str = ""  # stolen_good, illegal_substance, poison, forbidden_spell, contract
    seller_id: Optional[int] = None  # might be anonymous
    is_anonymous: bool = True
    price_copper: int = 0
    legitimate_price_copper: int = 0  # for comparison
    risk_level: float = 0.5  # 0..1, chance of attracting attention
    quantity: int = 1
    description: str = ""
    is_stolen: bool = False
    original_owner_id: Optional[int] = None
    posted_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "BlackMarketListing":
        return cls(**data)


@dataclass
class BlackMarket:
    """A black market in a location."""

    market_id: int
    name: str
    location: tuple[int, int]
    is_hidden: bool = True  # must be discovered
    discovered_by: list[int] = field(default_factory=list)
    listings: list[BlackMarketListing] = field(default_factory=list)
    price_multiplier: float = 1.5  # items cost 1.5x normal
    fence_cut: float = 0.4  # fence takes 40% of stolen goods' value
    heat_level: float = 0.0  # 0..1, attention from law enforcement
    reputation: float = 0.0  # with the criminal underworld
    available_services: list[str] = field(default_factory=list)  # "fence", "assassin", "smuggler", "thief"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["location"] = list(self.location)
        d["listings"] = [l.to_dict() for l in self.listings]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BlackMarket":
        d = dict(data)
        d["location"] = tuple(d.get("location", [0, 0]))
        d["listings"] = [BlackMarketListing.from_dict(l) for l in d.get("listings", [])]
        return cls(**d)


@dataclass
class Fence:
    """A fence — buyer of stolen goods."""

    fence_id: int
    name: str
    market_id: int
    wealth_copper: int = 5000
    cut: float = 0.4
    specialties: list[str] = field(default_factory=list)
    suspicion_level: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "Fence":
        return cls(**data)


class BlackMarketSystem:
    """Manages all black markets."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._markets: dict[int, BlackMarket] = {}
        self._fences: dict[int, Fence] = {}
        self._next_market_id: int = 1
        self._next_listing_id: int = 1
        self._next_fence_id: int = 1

    def create_market(self, name: str, location: tuple[int, int],
                      **kwargs: Any) -> BlackMarket:
        market = BlackMarket(
            market_id=self._next_market_id,
            name=name, location=location, **kwargs,
        )
        self._next_market_id += 1
        self._markets[market.market_id] = market
        return market

    def discover_market(self, market_id: int, entity_id: int) -> bool:
        market = self._markets.get(market_id)
        if market is None:
            return False
        if entity_id not in market.discovered_by:
            market.discovered_by.append(entity_id)
            market.is_hidden = False
        return True

    def add_listing(self, market_id: int, item_name: str, item_type: str,
                    price: int, legitimate_price: int = 0,
                    is_stolen: bool = False, **kwargs: Any) -> Optional[BlackMarketListing]:
        market = self._markets.get(market_id)
        if market is None:
            return None
        listing = BlackMarketListing(
            listing_id=self._next_listing_id,
            item_name=item_name, item_type=item_type,
            price_copper=price,
            legitimate_price_copper=legitimate_price or int(price / market.price_multiplier),
            is_stolen=is_stolen,
            **kwargs,
        )
        self._next_listing_id += 1
        market.listings.append(listing)
        return listing

    def buy_from_market(self, market_id: int, listing_id: int,
                        buyer_id: int, buyer_wealth: int) -> dict[str, Any]:
        """Buy an item from a black market."""
        market = self._markets.get(market_id)
        if market is None:
            return {"success": False, "reason": "Market not found"}
        listing = next((l for l in market.listings if l.listing_id == listing_id), None)
        if listing is None:
            return {"success": False, "reason": "Listing not found"}
        if buyer_wealth < listing.price_copper:
            return {"success": False, "reason": "Insufficient funds"}
        # Risk of being caught
        catch_chance = listing.risk_level * 0.1 + market.heat_level * 0.2
        caught = self.rng.chance(catch_chance)
        # Remove listing
        market.listings.remove(listing)
        # Increase heat
        market.heat_level = min(1.0, market.heat_level + 0.05)
        return {
            "success": True,
            "item_name": listing.item_name,
            "price_paid": listing.price_copper,
            "caught": caught,
            "criminal_reputation_gain": 1,
        }

    def fence_item(self, market_id: int, item_id: int, item_value: int,
                   is_stolen: bool = True) -> dict[str, Any]:
        """Sell a stolen item to a fence."""
        market = self._markets.get(market_id)
        if market is None:
            return {"success": False, "reason": "Market not found"}
        if not is_stolen:
            return {"success": False, "reason": "Item is not stolen"}
        # Fence pays a fraction of the value
        payout = int(item_value * (1.0 - market.fence_cut))
        # Add to listings
        self.add_listing(
            market_id=market_id,
            item_name=f"Fenced Item #{item_id}",
            item_type="stolen_good",
            price=int(item_value * market.price_multiplier),
            legitimate_price=item_value,
            is_stolen=True,
        )
        market.heat_level = min(1.0, market.heat_level + 0.02)
        return {
            "success": True,
            "payout_copper": payout,
            "fence_cut": market.fence_cut,
        }

    def hire_assassin(self, market_id: int, target_id: int,
                      buyer_id: int, budget: int) -> dict[str, Any]:
        """Hire an assassin to kill a target."""
        market = self._markets.get(market_id)
        if market is None:
            return {"success": False, "reason": "Market not found"}
        if "assassin" not in market.available_services:
            return {"success": False, "reason": "No assassins available"}
        # Cost scales with target importance
        base_cost = 1000
        if budget < base_cost:
            return {"success": False, "reason": f"Need at least {base_cost}cp"}
        # Success chance based on budget
        success_chance = min(0.9, 0.3 + (budget - base_cost) / 5000)
        contract_id = self._next_listing_id
        self._next_listing_id += 1
        return {
            "success": True,
            "contract_id": contract_id,
            "target_id": target_id,
            "assassin_success_chance": success_chance,
            "cost_copper": budget,
            "time_to_complete_days": self.rng.randint(7, 30),
        }

    def update(self, dt_days: float) -> None:
        """Cool down market heat over time."""
        for market in self._markets.values():
            market.heat_level = max(0.0, market.heat_level - 0.01 * dt_days)

    def markets(self) -> list[BlackMarket]:
        return list(self._markets.values())

    def markets_known_to(self, entity_id: int) -> list[BlackMarket]:
        return [m for m in self._markets.values() if entity_id in m.discovered_by]

    def to_dict(self) -> dict[str, Any]:
        return {
            "markets": {str(mid): m.to_dict() for mid, m in self._markets.items()},
            "fences": {str(fid): f.to_dict() for fid, f in self._fences.items()},
            "next_market_id": self._next_market_id,
            "next_listing_id": self._next_listing_id,
            "next_fence_id": self._next_fence_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlackMarketSystem":
        sys = cls()
        sys._markets = {
            int(mid): BlackMarket.from_dict(m)
            for mid, m in data.get("markets", {}).items()
        }
        sys._fences = {
            int(fid): Fence.from_dict(f)
            for fid, f in data.get("fences", {}).items()
        }
        sys._next_market_id = data.get("next_market_id", 1)
        sys._next_listing_id = data.get("next_listing_id", 1)
        sys._next_fence_id = data.get("next_fence_id", 1)
        return sys
