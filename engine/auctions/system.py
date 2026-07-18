"""Auction system — bidding wars for rare items and bulk goods."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class AuctionState(IntEnum):
    SCHEDULED = 0
    OPEN = 1
    CLOSED = 2
    CANCELLED = 3
    RESOLVED = 4


@dataclass
class AuctionBid:
    """A single bid in an auction."""

    bidder_id: int
    amount: int
    timestamp: float
    is_anonymous: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "bidder_id": self.bidder_id, "amount": self.amount,
            "timestamp": self.timestamp, "is_anonymous": self.is_anonymous,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AuctionBid":
        return cls(
            bidder_id=data["bidder_id"], amount=data["amount"],
            timestamp=data["timestamp"],
            is_anonymous=data.get("is_anonymous", False),
        )


@dataclass
class Auction:
    """A single auction."""

    auction_id: int
    title: str
    description: str
    seller_id: Optional[int]
    item_id: Optional[int] = None      # for single-item auctions
    item_name: str = ""
    starting_price: int = 0
    reserve_price: int = 0
    buyout_price: Optional[int] = None
    minimum_increment: int = 1
    bids: list[AuctionBid] = field(default_factory=list)
    state: AuctionState = AuctionState.SCHEDULED
    opens_at: float = 0.0
    closes_at: float = 0.0
    location: Optional[tuple[int, int]] = None
    faction_id: Optional[int] = None  # restrict to faction members
    is_black_market: bool = False
    tags: list[str] = field(default_factory=list)

    @property
    def highest_bid(self) -> Optional[AuctionBid]:
        return max(self.bids, key=lambda b: b.amount, default=None)

    @property
    def current_price(self) -> int:
        hb = self.highest_bid
        if hb is not None:
            return hb.amount
        return self.starting_price

    @property
    def bid_count(self) -> int:
        return len(self.bids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "auction_id": self.auction_id, "title": self.title,
            "description": self.description, "seller_id": self.seller_id,
            "item_id": self.item_id, "item_name": self.item_name,
            "starting_price": self.starting_price,
            "reserve_price": self.reserve_price,
            "buyout_price": self.buyout_price,
            "minimum_increment": self.minimum_increment,
            "bids": [b.to_dict() for b in self.bids],
            "state": int(self.state),
            "opens_at": self.opens_at, "closes_at": self.closes_at,
            "location": self.location, "faction_id": self.faction_id,
            "is_black_market": self.is_black_market,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Auction":
        return cls(
            auction_id=data["auction_id"], title=data["title"],
            description=data.get("description", ""),
            seller_id=data.get("seller_id"),
            item_id=data.get("item_id"),
            item_name=data.get("item_name", ""),
            starting_price=data.get("starting_price", 0),
            reserve_price=data.get("reserve_price", 0),
            buyout_price=data.get("buyout_price"),
            minimum_increment=data.get("minimum_increment", 1),
            bids=[AuctionBid.from_dict(b) for b in data.get("bids", [])],
            state=AuctionState(data.get("state", 0)),
            opens_at=data.get("opens_at", 0.0),
            closes_at=data.get("closes_at", 0.0),
            location=tuple(data["location"]) if data.get("location") else None,
            faction_id=data.get("faction_id"),
            is_black_market=data.get("is_black_market", False),
            tags=list(data.get("tags", [])),
        )


class AuctionHouse:
    """Manages auctions across the world."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._auctions: dict[int, Auction] = {}
        self._next_id: int = 1

    def schedule_auction(self, title: str, description: str,
                         seller_id: Optional[int], item_id: Optional[int] = None,
                         item_name: str = "",
                         starting_price: int = 100,
                         reserve_price: int = 0,
                         buyout_price: Optional[int] = None,
                         minimum_increment: int = 1,
                         duration_seconds: float = 3600.0,
                         current_tick: float = 0.0,
                         opens_at: Optional[float] = None,
                         location: Optional[tuple[int, int]] = None,
                         faction_id: Optional[int] = None,
                         is_black_market: bool = False,
                         tags: Optional[list[str]] = None) -> Auction:
        auction = Auction(
            auction_id=self._next_id,
            title=title, description=description,
            seller_id=seller_id, item_id=item_id, item_name=item_name,
            starting_price=starting_price, reserve_price=reserve_price,
            buyout_price=buyout_price,
            minimum_increment=minimum_increment,
            opens_at=opens_at if opens_at is not None else current_tick,
            closes_at=(opens_at if opens_at is not None else current_tick) + duration_seconds,
            state=AuctionState.SCHEDULED,
            location=location, faction_id=faction_id,
            is_black_market=is_black_market,
            tags=list(tags or []),
        )
        self._next_id += 1
        self._auctions[auction.auction_id] = auction
        return auction

    def place_bid(self, auction_id: int, bidder_id: int, amount: int,
                  current_tick: float = 0.0,
                  is_anonymous: bool = False) -> tuple[bool, str]:
        auction = self._auctions.get(auction_id)
        if auction is None:
            return False, "Auction not found."
        if auction.state not in (AuctionState.OPEN,):
            return False, f"Auction is {auction.state.name.lower()}."
        if current_tick < auction.opens_at:
            return False, "Auction has not opened yet."
        if current_tick >= auction.closes_at:
            auction.state = AuctionState.CLOSED
            return False, "Auction has closed."
        current = auction.current_price
        if amount < current + auction.minimum_increment:
            return False, f"Bid must be at least {current + auction.minimum_increment}."
        if auction.faction_id is not None:
            # We'd check faction membership here; assume OK for now.
            pass
        bid = AuctionBid(
            bidder_id=bidder_id, amount=amount,
            timestamp=current_tick, is_anonymous=is_anonymous,
        )
        auction.bids.append(bid)
        # Buyout?
        if auction.buyout_price is not None and amount >= auction.buyout_price:
            auction.state = AuctionState.RESOLVED
            return True, f"Buyout accepted — you won for {amount}cp."
        return True, f"Bid placed: {amount}cp."

    def cancel_auction(self, auction_id: int, requester_id: int) -> tuple[bool, str]:
        auction = self._auctions.get(auction_id)
        if auction is None:
            return False, "Auction not found."
        if auction.seller_id != requester_id:
            return False, "Only the seller can cancel."
        if auction.state == AuctionState.RESOLVED:
            return False, "Auction already resolved."
        auction.state = AuctionState.CANCELLED
        return True, "Auction cancelled."

    def update(self, current_tick: float) -> list[Auction]:
        """Tick all auctions: open scheduled ones, close expired ones."""
        resolved: list[Auction] = []
        for auction in self._auctions.values():
            if auction.state == AuctionState.SCHEDULED and current_tick >= auction.opens_at:
                auction.state = AuctionState.OPEN
            elif auction.state == AuctionState.OPEN and current_tick >= auction.closes_at:
                auction.state = AuctionState.CLOSED
                # Auto-resolve
                hb = auction.highest_bid
                if hb is not None and hb.amount >= auction.reserve_price:
                    auction.state = AuctionState.RESOLVED
                    resolved.append(auction)
                else:
                    # Reserve not met — auction fails
                    auction.state = AuctionState.CANCELLED
        return resolved

    def all(self) -> list[Auction]:
        return list(self._auctions.values())

    def active(self) -> list[Auction]:
        return [a for a in self._auctions.values() if a.state == AuctionState.OPEN]

    def get(self, auction_id: int) -> Optional[Auction]:
        return self._auctions.get(auction_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "auctions": {str(aid): a.to_dict() for aid, a in self._auctions.items()},
            "next_id": self._next_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AuctionHouse":
        house = cls()
        house._auctions = {
            int(aid): Auction.from_dict(a) for aid, a in data.get("auctions", {}).items()
        }
        house._next_id = data.get("next_id", 1)
        return house
