"""Network replication system.

Implements the four pillars of multiplayer game networking:
1. Replication — server state is propagated to clients
2. Prediction — clients predict their own state to hide latency
3. Rollback — when server state disagrees with prediction, roll back
4. Authority — server is the source of truth for game state

Architecture:
* Each entity has a NetworkPriority (low, medium, high, critical)
* Server snapshots are taken at a fixed rate (e.g., 20Hz)
* Clients predict their own movement and reconcile with server
* Rollback buffer keeps recent states for rewinding
* Critical events are sent reliably; non-critical are unreliable
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.core.ecs import Entity
from engine.core.logging import get_logger


log = get_logger("network.replication")


class NetworkPriority(IntEnum):
    LOW = 0       # ambient effects, decorations
    MEDIUM = 1    # NPCs, items
    HIGH = 2      # players, important NPCs
    CRITICAL = 3  # player avatar, projectiles


@dataclass
class ReplicatedState:
    """A snapshot of an entity's replicable state."""

    entity_id: int
    component_data: dict[str, Any] = field(default_factory=dict)
    priority: NetworkPriority = NetworkPriority.MEDIUM
    last_replicated: float = 0.0
    is_dirty: bool = True  # has changed since last replication

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "component_data": self.component_data,
            "priority": int(self.priority),
            "last_replicated": self.last_replicated,
            "is_dirty": self.is_dirty,
        }


@dataclass
class StateSnapshot:
    """A complete world state snapshot at a point in time."""

    tick: int
    timestamp: float
    states: dict[int, ReplicatedState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "timestamp": self.timestamp,
            "states": {str(eid): s.to_dict() for eid, s in self.states.items()},
        }


class ReplicationSystem:
    """Manages entity replication to clients."""

    def __init__(self, snapshot_rate_hz: float = 20.0) -> None:
        self.snapshot_rate = snapshot_rate_hz
        self._replicated: dict[int, ReplicatedState] = {}
        self._last_snapshot_time: float = 0.0
        self._current_tick: int = 0
        self._snapshot_history: deque[StateSnapshot] = deque(maxlen=100)
        self._priority_threshold = {
            NetworkPriority.LOW: 0.5,      # replicate every 0.5s
            NetworkPriority.MEDIUM: 0.1,
            NetworkPriority.HIGH: 0.05,
            NetworkPriority.CRITICAL: 0.02,
        }

    def register_entity(self, entity_id: int,
                        priority: NetworkPriority = NetworkPriority.MEDIUM) -> ReplicatedState:
        state = ReplicatedState(entity_id=entity_id, priority=priority)
        self._replicated[entity_id] = state
        return state

    def unregister_entity(self, entity_id: int) -> None:
        self._replicated.pop(entity_id, None)

    def mark_dirty(self, entity_id: int) -> None:
        state = self._replicated.get(entity_id)
        if state:
            state.is_dirty = True

    def update_state(self, entity_id: int, component_data: dict[str, Any]) -> None:
        state = self._replicated.get(entity_id)
        if state is None:
            state = self.register_entity(entity_id)
        # Check if anything actually changed
        for key, value in component_data.items():
            if state.component_data.get(key) != value:
                state.component_data[key] = value
                state.is_dirty = True

    def take_snapshot(self, current_tick: Optional[int] = None,
                      current_time: Optional[float] = None) -> StateSnapshot:
        """Take a snapshot of all dirty replicated states."""
        if current_tick is not None:
            self._current_tick = current_tick
        else:
            self._current_tick += 1
        timestamp = current_time if current_time is not None else time.time()
        snapshot = StateSnapshot(tick=self._current_tick, timestamp=timestamp)
        for entity_id, state in self._replicated.items():
            # Determine if we should replicate based on priority and time since last
            interval = self._priority_threshold.get(state.priority, 0.1)
            if state.is_dirty or (timestamp - state.last_replicated) >= interval:
                snapshot.states[entity_id] = ReplicatedState(
                    entity_id=entity_id,
                    component_data=dict(state.component_data),
                    priority=state.priority,
                    last_replicated=timestamp,
                    is_dirty=False,
                )
                state.is_dirty = False
                state.last_replicated = timestamp
        self._snapshot_history.append(snapshot)
        return snapshot

    def get_snapshot(self, tick: int) -> Optional[StateSnapshot]:
        """Retrieve a historical snapshot by tick."""
        for snapshot in self._snapshot_history:
            if snapshot.tick == tick:
                return snapshot
        return None

    def recent_snapshots(self, n: int = 10) -> list[StateSnapshot]:
        return list(self._snapshot_history)[-n:]

    def all_states(self) -> dict[int, ReplicatedState]:
        return dict(self._replicated)


class ClientPredictor:
    """Client-side state prediction.

    The client predicts its own state by applying inputs locally
    before the server confirms them. When the server's authoritative
    state arrives, the client reconciles.
    """

    def __init__(self) -> None:
        self._predicted_states: dict[int, deque[tuple[int, dict[str, Any]]]] = {}
        self._last_confirmed_tick: int = 0
        self._reconciliation_count: int = 0

    def predict(self, entity_id: int, tick: int, state: dict[str, Any]) -> None:
        """Record a predicted state for an entity at a tick."""
        if entity_id not in self._predicted_states:
            self._predicted_states[entity_id] = deque(maxlen=100)
        self._predicted_states[entity_id].append((tick, dict(state)))

    def reconcile(self, entity_id: int, server_tick: int,
                  server_state: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Reconcile with server state. Returns (was_mismatch, predicted_state)."""
        self._last_confirmed_tick = server_tick
        history = self._predicted_states.get(entity_id)
        if history is None:
            return False, {}
        # Find the predicted state at server_tick
        predicted = None
        while history and history[0][0] <= server_tick:
            predicted = history.popleft()
        if predicted is None:
            return False, {}
        tick, predicted_state = predicted
        # Compare
        mismatch = False
        for key, server_value in server_state.items():
            if predicted_state.get(key) != server_value:
                mismatch = True
                predicted_state[key] = server_value  # correct to server value
        if mismatch:
            self._reconciliation_count += 1
            log.debug("Reconciliation mismatch for entity %d at tick %d",
                       entity_id, server_tick)
        return mismatch, predicted_state

    def stats(self) -> dict[str, Any]:
        return {
            "last_confirmed_tick": self._last_confirmed_tick,
            "reconciliation_count": self._reconciliation_count,
            "tracked_entities": len(self._predicted_states),
        }


class ServerAuthority:
    """Server-side authority resolution.

    The server is the source of truth. Client requests are validated
    and applied only if they pass server-side rules.
    """

    def __init__(self) -> None:
        self._authorized_actions: dict[str, set[int]] = {}  # action_type -> client_ids allowed
        self._rejected_actions: int = 0
        self._accepted_actions: int = 0

    def authorize_client(self, action_type: str, client_id: int) -> None:
        self._authorized_actions.setdefault(action_type, set()).add(client_id)

    def revoke_authorization(self, action_type: str, client_id: int) -> None:
        if action_type in self._authorized_actions:
            self._authorized_actions[action_type].discard(client_id)

    def validate_action(self, action_type: str, client_id: int,
                        action_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate a client action against server rules."""
        # Check authorization
        allowed = self._authorized_actions.get(action_type, set())
        if client_id not in allowed:
            self._rejected_actions += 1
            return False, "Not authorized"
        # Check rate limits (simple)
        if action_type == "move":
            new_x = action_data.get("x")
            new_y = action_data.get("y")
            old_x = action_data.get("old_x", 0)
            old_y = action_data.get("old_y", 0)
            # Movement must be reasonable
            distance = ((new_x - old_x) ** 2 + (new_y - old_y) ** 2) ** 0.5
            if distance > 10:
                self._rejected_actions += 1
                return False, "Movement too fast — possible speed hack"
        if action_type == "attack":
            damage = action_data.get("damage", 0)
            if damage > 1000:
                self._rejected_actions += 1
                return False, "Damage too high — possible hack"
        self._accepted_actions += 1
        return True, "OK"

    def stats(self) -> dict[str, Any]:
        return {
            "accepted": self._accepted_actions,
            "rejected": self._rejected_actions,
            "authorized_clients": sum(len(s) for s in self._authorized_actions.values()),
        }


class RollbackSystem:
    """Rollback netcode — rewind state to resolve conflicts.

    Used in fighting games and fast-paced games where every frame matters.
    The server keeps a buffer of recent states and can rewind to apply
    late-arriving inputs.
    """

    def __init__(self, buffer_size: int = 60) -> None:
        self._state_buffer: deque[tuple[int, dict[str, Any]]] = deque(maxlen=buffer_size)
        self._rollback_count: int = 0
        self._total_rollback_frames: int = 0

    def save_state(self, tick: int, state: dict[str, Any]) -> None:
        """Save a state at a specific tick."""
        self._state_buffer.append((tick, dict(state)))

    def rollback_to(self, tick: int) -> Optional[dict[str, Any]]:
        """Roll back to the state at the given tick. Returns the state or None."""
        for t, state in reversed(self._state_buffer):
            if t == tick:
                self._rollback_count += 1
                self._total_rollback_frames += (self._state_buffer[-1][0] - tick)
                return dict(state)
            if t < tick:
                break
        return None

    def stats(self) -> dict[str, Any]:
        return {
            "buffer_size": len(self._state_buffer),
            "rollback_count": self._rollback_count,
            "total_rollback_frames": self._total_rollback_frames,
        }
