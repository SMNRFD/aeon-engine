"""Trade system — routes, caravans, ships, and shipments.

Models overland and maritime trade with:
* Trade routes between markets (auto-computed distance & risk)
* Caravans that travel routes carrying goods
* Ships for maritime trade
* Risk events: bandits, storms, piracy, taxes
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class CaravanState(IntEnum):
    LOADING = 0
    TRAVELLING = 1
    ARRIVED = 2
    ATTACKED = 3
    LOST = 4
    RETURNING = 5


@dataclass
class TradeRoute:
    """A trade route between two markets."""

    route_id: int
    name: str
    origin_market_id: int
    destination_market_id: int
    distance_km: float
    travel_time_days: float
    risk_bandits: float = 0.1    # 0..1 chance per trip
    risk_storm: float = 0.05     # 0..1 (overland: storms, sea: pirates)
    risk_taxes: float = 0.05     # toll fraction
    is_maritime: bool = False
    waypoints: list[tuple[int, int]] = field(default_factory=list)
    active_caravans: int = 0
    trips_completed: int = 0
    trips_lost: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id, "name": self.name,
            "origin_market_id": self.origin_market_id,
            "destination_market_id": self.destination_market_id,
            "distance_km": self.distance_km,
            "travel_time_days": self.travel_time_days,
            "risk_bandits": self.risk_bandits, "risk_storm": self.risk_storm,
            "risk_taxes": self.risk_taxes, "is_maritime": self.is_maritime,
            "waypoints": [list(w) for w in self.waypoints],
            "active_caravans": self.active_caravans,
            "trips_completed": self.trips_completed,
            "trips_lost": self.trips_lost,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeRoute":
        return cls(
            route_id=data["route_id"], name=data["name"],
            origin_market_id=data["origin_market_id"],
            destination_market_id=data["destination_market_id"],
            distance_km=data["distance_km"],
            travel_time_days=data["travel_time_days"],
            risk_bandits=data.get("risk_bandits", 0.1),
            risk_storm=data.get("risk_storm", 0.05),
            risk_taxes=data.get("risk_taxes", 0.05),
            is_maritime=data.get("is_maritime", False),
            waypoints=[tuple(w) for w in data.get("waypoints", [])],
            active_caravans=data.get("active_caravans", 0),
            trips_completed=data.get("trips_completed", 0),
            trips_lost=data.get("trips_lost", 0),
        )


@dataclass
class Caravan:
    """An overland caravan."""

    caravan_id: int
    name: str
    route_id: int
    owner_id: Optional[int] = None
    cargo: dict[str, int] = field(default_factory=dict)  # good_id -> count
    cargo_value_copper: int = 0
    guard_count: int = 0
    state: CaravanState = CaravanState.LOADING
    progress: float = 0.0  # 0..1
    days_travelled: float = 0.0
    started_tick: float = 0.0
    arrived_tick: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "caravan_id": self.caravan_id, "name": self.name,
            "route_id": self.route_id, "owner_id": self.owner_id,
            "cargo": dict(self.cargo), "cargo_value_copper": self.cargo_value_copper,
            "guard_count": self.guard_count, "state": int(self.state),
            "progress": self.progress, "days_travelled": self.days_travelled,
            "started_tick": self.started_tick, "arrived_tick": self.arrived_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Caravan":
        return cls(
            caravan_id=data["caravan_id"], name=data["name"],
            route_id=data["route_id"], owner_id=data.get("owner_id"),
            cargo=dict(data.get("cargo", {})),
            cargo_value_copper=data.get("cargo_value_copper", 0),
            guard_count=data.get("guard_count", 0),
            state=CaravanState(data.get("state", 0)),
            progress=data.get("progress", 0.0),
            days_travelled=data.get("days_travelled", 0.0),
            started_tick=data.get("started_tick", 0.0),
            arrived_tick=data.get("arrived_tick"),
        )


@dataclass
class Ship:
    """A maritime trading vessel."""

    ship_id: int
    name: str
    route_id: int
    owner_id: Optional[int] = None
    ship_type: str = "cog"  # cog, caravel, galleon, dreadnought
    cargo_capacity: int = 1000
    cargo: dict[str, int] = field(default_factory=dict)
    cargo_value_copper: int = 0
    crew_count: int = 10
    cannon_count: int = 0
    state: CaravanState = CaravanState.LOADING
    progress: float = 0.0
    days_travelled: float = 0.0
    started_tick: float = 0.0
    arrived_tick: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ship_id": self.ship_id, "name": self.name, "route_id": self.route_id,
            "owner_id": self.owner_id, "ship_type": self.ship_type,
            "cargo_capacity": self.cargo_capacity,
            "cargo": dict(self.cargo),
            "cargo_value_copper": self.cargo_value_copper,
            "crew_count": self.crew_count, "cannon_count": self.cannon_count,
            "state": int(self.state), "progress": self.progress,
            "days_travelled": self.days_travelled,
            "started_tick": self.started_tick,
            "arrived_tick": self.arrived_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ship":
        return cls(
            ship_id=data["ship_id"], name=data["name"],
            route_id=data["route_id"], owner_id=data.get("owner_id"),
            ship_type=data.get("ship_type", "cog"),
            cargo_capacity=data.get("cargo_capacity", 1000),
            cargo=dict(data.get("cargo", {})),
            cargo_value_copper=data.get("cargo_value_copper", 0),
            crew_count=data.get("crew_count", 10),
            cannon_count=data.get("cannon_count", 0),
            state=CaravanState(data.get("state", 0)),
            progress=data.get("progress", 0.0),
            days_travelled=data.get("days_travelled", 0.0),
            started_tick=data.get("started_tick", 0.0),
            arrived_tick=data.get("arrived_tick"),
        )


class TradeSystem:
    """Manages trade routes and caravans."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._routes: dict[int, TradeRoute] = {}
        self._caravans: dict[int, Caravan] = {}
        self._ships: dict[int, Ship] = {}
        self._next_route_id: int = 1
        self._next_caravan_id: int = 1
        self._next_ship_id: int = 1

    def create_route(self, name: str, origin_market_id: int,
                     destination_market_id: int,
                     origin_location: tuple[int, int],
                     destination_location: tuple[int, int],
                     is_maritime: bool = False) -> TradeRoute:
        distance = math.hypot(destination_location[0] - origin_location[0],
                              destination_location[1] - origin_location[1])
        # Convert tiles to km (1 tile ≈ 5 km)
        distance_km = distance * 5.0
        travel_time_days = distance_km / (40.0 if not is_maritime else 80.0)
        route = TradeRoute(
            route_id=self._next_route_id, name=name,
            origin_market_id=origin_market_id,
            destination_market_id=destination_market_id,
            distance_km=distance_km, travel_time_days=travel_time_days,
            risk_bandits=0.0 if is_maritime else 0.1,
            risk_storm=0.05 if not is_maritime else 0.15,
            is_maritime=is_maritime,
            waypoints=[origin_location, destination_location],
        )
        self._next_route_id += 1
        self._routes[route.route_id] = route
        return route

    def dispatch_caravan(self, route_id: int, cargo: dict[str, int],
                         cargo_value: int, guard_count: int = 5,
                         owner_id: Optional[int] = None,
                         current_tick: float = 0.0) -> Optional[Caravan]:
        route = self._routes.get(route_id)
        if route is None or route.is_maritime:
            return None
        caravan = Caravan(
            caravan_id=self._next_caravan_id,
            name=f"Caravan #{self._next_caravan_id}",
            route_id=route_id, owner_id=owner_id,
            cargo=dict(cargo), cargo_value_copper=cargo_value,
            guard_count=guard_count, state=CaravanState.TRAVELLING,
            started_tick=current_tick,
        )
        self._next_caravan_id += 1
        self._caravans[caravan.caravan_id] = caravan
        route.active_caravans += 1
        return caravan

    def dispatch_ship(self, route_id: int, cargo: dict[str, int],
                      cargo_value: int, ship_type: str = "cog",
                      crew_count: int = 10, cannon_count: int = 0,
                      owner_id: Optional[int] = None,
                      current_tick: float = 0.0) -> Optional[Ship]:
        route = self._routes.get(route_id)
        if route is None or not route.is_maritime:
            return None
        ship = Ship(
            ship_id=self._next_ship_id,
            name=f"Ship #{self._next_ship_id}",
            route_id=route_id, owner_id=owner_id,
            ship_type=ship_type,
            cargo_capacity={"cog": 500, "caravel": 1500, "galleon": 3000,
                             "dreadnought": 5000}.get(ship_type, 500),
            cargo=dict(cargo), cargo_value_copper=cargo_value,
            crew_count=crew_count, cannon_count=cannon_count,
            state=CaravanState.TRAVELLING, started_tick=current_tick,
        )
        self._next_ship_id += 1
        self._ships[ship.ship_id] = ship
        route.active_caravans += 1
        return ship

    def update(self, dt_days: float, current_tick: float = 0.0) -> None:
        """Advance all caravans and ships."""
        for caravan in self._caravans.values():
            if caravan.state != CaravanState.TRAVELLING:
                continue
            route = self._routes.get(caravan.route_id)
            if route is None:
                caravan.state = CaravanState.LOST
                continue
            caravan.days_travelled += dt_days
            caravan.progress = min(1.0, caravan.days_travelled / route.travel_time_days)
            # Random events
            if self.rng.chance(route.risk_bandits * dt_days / route.travel_time_days):
                # Bandit attack — guards reduce loss
                loss_fraction = max(0.0, 0.5 - caravan.guard_count * 0.05)
                lost_value = int(caravan.cargo_value_copper * loss_fraction)
                caravan.cargo_value_copper -= lost_value
                caravan.state = CaravanState.ATTACKED
                if not caravan.cargo:
                    caravan.state = CaravanState.LOST
                    route.trips_lost += 1
                continue
            if caravan.progress >= 1.0:
                caravan.state = CaravanState.ARRIVED
                caravan.arrived_tick = current_tick
                route.trips_completed += 1
                route.active_caravans = max(0, route.active_caravans - 1)

        for ship in self._ships.values():
            if ship.state != CaravanState.TRAVELLING:
                continue
            route = self._routes.get(ship.route_id)
            if route is None:
                ship.state = CaravanState.LOST
                continue
            ship.days_travelled += dt_days
            ship.progress = min(1.0, ship.days_travelled / route.travel_time_days)
            if self.rng.chance(route.risk_storm * dt_days / route.travel_time_days):
                # Pirate attack or storm
                defense = ship.cannon_count * 0.05 + ship.crew_count * 0.01
                loss_fraction = max(0.0, 0.7 - defense)
                lost_value = int(ship.cargo_value_copper * loss_fraction)
                ship.cargo_value_copper -= lost_value
                ship.state = CaravanState.ATTACKED
                continue
            if ship.progress >= 1.0:
                ship.state = CaravanState.ARRIVED
                ship.arrived_tick = current_tick
                route.trips_completed += 1
                route.active_caravans = max(0, route.active_caravans - 1)

    def routes(self) -> list[TradeRoute]:
        return list(self._routes.values())

    def caravans(self) -> list[Caravan]:
        return list(self._caravans.values())

    def ships(self) -> list[Ship]:
        return list(self._ships.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "routes": {str(rid): r.to_dict() for rid, r in self._routes.items()},
            "caravans": {str(cid): c.to_dict() for cid, c in self._caravans.items()},
            "ships": {str(sid): s.to_dict() for sid, s in self._ships.items()},
            "next_route_id": self._next_route_id,
            "next_caravan_id": self._next_caravan_id,
            "next_ship_id": self._next_ship_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeSystem":
        sys = cls()
        sys._routes = {
            int(rid): TradeRoute.from_dict(r) for rid, r in data.get("routes", {}).items()
        }
        sys._caravans = {
            int(cid): Caravan.from_dict(c) for cid, c in data.get("caravans", {}).items()
        }
        sys._ships = {
            int(sid): Ship.from_dict(s) for sid, s in data.get("ships", {}).items()
        }
        sys._next_route_id = data.get("next_route_id", 1)
        sys._next_caravan_id = data.get("next_caravan_id", 1)
        sys._next_ship_id = data.get("next_ship_id", 1)
        return sys
