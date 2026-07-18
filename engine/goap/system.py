"""GOAP — Goal-Oriented Action Planning.

GOAP plans a sequence of actions to reach a goal state from the current
world state. Each action has preconditions and effects.

A* search is used over the state-space graph to find the lowest-cost plan.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Optional

from engine.core.logging import get_logger


log = get_logger("goap")


@dataclass
class GOAPAction:
    """A single action in the GOAP planner."""

    name: str
    cost: float = 1.0
    preconditions: dict[str, Any] = field(default_factory=dict)
    effects: dict[str, Any] = field(default_factory=dict)
    requires_target: bool = False
    description: str = ""

    def is_applicable(self, world_state: "GOAPWorldState") -> bool:
        for key, value in self.preconditions.items():
            if world_state.get(key) != value:
                return False
        return True

    def apply(self, world_state: "GOAPWorldState") -> "GOAPWorldState":
        new_state = GOAPWorldState(dict(world_state.facts))
        for key, value in self.effects.items():
            new_state.set(key, value)
        return new_state

    def __repr__(self) -> str:
        return f"GOAPAction({self.name}, cost={self.cost})"


class GOAPWorldState:
    """A world state for GOAP — a dict of facts."""

    def __init__(self, facts: Optional[dict[str, Any]] = None) -> None:
        self.facts: dict[str, Any] = dict(facts or {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.facts.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.facts[key] = value

    def matches(self, goal: "GOAPWorldState") -> bool:
        """Check if this state satisfies the goal."""
        for key, value in goal.facts.items():
            if self.facts.get(key) != value:
                return False
        return True

    def signature(self) -> str:
        """A hashable signature for visited-state tracking."""
        return ",".join(f"{k}={v}" for k, v in sorted(self.facts.items()))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, GOAPWorldState):
            return False
        return self.facts == other.facts

    def __hash__(self) -> int:
        return hash(self.signature())


@dataclass
class GOAPPlanner:
    """A* planner over the GOAP state space."""

    max_iterations: int = 1000
    max_plan_length: int = 20

    def plan(self, current_state: GOAPWorldState, goal: GOAPWorldState,
             actions: list[GOAPAction]) -> Optional[list[GOAPAction]]:
        """Plan a sequence of actions to reach `goal` from `current_state`.

        Returns the plan as a list of actions, or None if no plan found.
        """
        if current_state.matches(goal):
            return []
        # A* search
        counter = 0
        # Priority queue: (f_score, counter, g_score, state, plan_so_far)
        open_heap: list[tuple[float, int, float, GOAPWorldState, list[GOAPAction]]] = []
        heapq.heappush(open_heap, (self._heuristic(current_state, goal), counter,
                                   0.0, current_state, []))
        visited: dict[str, float] = {}
        iterations = 0
        while open_heap and iterations < self.max_iterations:
            iterations += 1
            f, _, g, state, plan = heapq.heappop(open_heap)
            if state.matches(goal):
                return plan
            if len(plan) >= self.max_plan_length:
                continue
            sig = state.signature()
            if sig in visited and visited[sig] <= g:
                continue
            visited[sig] = g
            for action in actions:
                if not action.is_applicable(state):
                    continue
                new_state = action.apply(state)
                new_g = g + action.cost
                new_plan = plan + [action]
                new_f = new_g + self._heuristic(new_state, goal)
                counter += 1
                heapq.heappush(open_heap, (new_f, counter, new_g, new_state, new_plan))
        log.debug("GOAP plan failed after %d iterations", iterations)
        return None

    def _heuristic(self, state: GOAPWorldState, goal: GOAPWorldState) -> float:
        """Count of unmet goal facts — admissible if all actions cost >= 1."""
        unmet = 0
        for key, value in goal.facts.items():
            if state.get(key) != value:
                unmet += 1
        return float(unmet)
