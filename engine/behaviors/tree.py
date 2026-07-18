"""Behavior trees — composable AI decision-making structures.

A behavior tree is a tree of nodes where each node returns one of:
* SUCCESS — the node completed its task
* FAILURE — the node could not complete its task
* RUNNING — the node is in progress

Node types:
* SequenceNode  — runs children in order; fails on first failure
* SelectorNode  — runs children in order; succeeds on first success
* ActionNode    — leaf node that performs an action
* ConditionNode — leaf node that checks a condition
* InverterNode  — inverts the result of its child
* RepeaterNode  — repeats its child N times
* ParallelNode  — runs all children simultaneously
* DelayNode     — waits N ticks before returning success
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Optional


class NodeStatus(IntEnum):
    SUCCESS = 0
    FAILURE = 1
    RUNNING = 2
    ERROR = 3


class BehaviorNode:
    """Base class for behavior tree nodes."""

    def tick(self, context: Any) -> NodeStatus:
        raise NotImplementedError

    def reset(self) -> None:
        pass


@dataclass
class SequenceNode(BehaviorNode):
    """Runs children in order; fails on first failure."""

    children: list[BehaviorNode] = field(default_factory=list)
    _current: int = 0

    def tick(self, context: Any) -> NodeStatus:
        while self._current < len(self.children):
            status = self.children[self._current].tick(context)
            if status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            if status == NodeStatus.FAILURE:
                self._current = 0
                return NodeStatus.FAILURE
            self._current += 1
        self._current = 0
        return NodeStatus.SUCCESS

    def reset(self) -> None:
        self._current = 0
        for child in self.children:
            child.reset()


@dataclass
class SelectorNode(BehaviorNode):
    """Runs children in order; succeeds on first success."""

    children: list[BehaviorNode] = field(default_factory=list)
    _current: int = 0

    def tick(self, context: Any) -> NodeStatus:
        while self._current < len(self.children):
            status = self.children[self._current].tick(context)
            if status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            if status == NodeStatus.SUCCESS:
                self._current = 0
                return NodeStatus.SUCCESS
            self._current += 1
        self._current = 0
        return NodeStatus.FAILURE

    def reset(self) -> None:
        self._current = 0
        for child in self.children:
            child.reset()


@dataclass
class ActionNode(BehaviorNode):
    """A leaf node that performs an action."""

    action_fn: Callable[[Any], NodeStatus] = field(default=lambda ctx: NodeStatus.SUCCESS)
    name: str = ""

    def tick(self, context: Any) -> NodeStatus:
        return self.action_fn(context)


@dataclass
class ConditionNode(BehaviorNode):
    """A leaf node that checks a condition."""

    condition_fn: Callable[[Any], bool] = field(default=lambda ctx: True)
    name: str = ""

    def tick(self, context: Any) -> NodeStatus:
        return NodeStatus.SUCCESS if self.condition_fn(context) else NodeStatus.FAILURE


@dataclass
class InverterNode(BehaviorNode):
    """Inverts the result of its child (SUCCESS <-> FAILURE)."""

    child: Optional[BehaviorNode] = None

    def tick(self, context: Any) -> NodeStatus:
        if self.child is None:
            return NodeStatus.FAILURE
        status = self.child.tick(context)
        if status == NodeStatus.SUCCESS:
            return NodeStatus.FAILURE
        if status == NodeStatus.FAILURE:
            return NodeStatus.SUCCESS
        return status

    def reset(self) -> None:
        if self.child:
            self.child.reset()


@dataclass
class RepeaterNode(BehaviorNode):
    """Repeats its child N times."""

    child: Optional[BehaviorNode] = None
    repeat_count: int = 3
    _current_repeat: int = 0

    def tick(self, context: Any) -> NodeStatus:
        if self.child is None:
            return NodeStatus.FAILURE
        while self._current_repeat < self.repeat_count:
            status = self.child.tick(context)
            if status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            self._current_repeat += 1
        self._current_repeat = 0
        return NodeStatus.SUCCESS

    def reset(self) -> None:
        self._current_repeat = 0
        if self.child:
            self.child.reset()


@dataclass
class RepeatUntilFailNode(BehaviorNode):
    """Repeats its child until it fails."""

    child: Optional[BehaviorNode] = None

    def tick(self, context: Any) -> NodeStatus:
        if self.child is None:
            return NodeStatus.FAILURE
        while True:
            status = self.child.tick(context)
            if status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            if status == NodeStatus.FAILURE:
                return NodeStatus.SUCCESS
            # Success — repeat

    def reset(self) -> None:
        if self.child:
            self.child.reset()


@dataclass
class ParallelNode(BehaviorNode):
    """Runs all children simultaneously.

    `success_policy`: how many children must succeed for the node to succeed.
    `failure_policy`: how many children must fail for the node to fail.
    """

    children: list[BehaviorNode] = field(default_factory=list)
    success_policy: int = 0  # 0 = all
    failure_policy: int = 0  # 0 = any

    def tick(self, context: Any) -> NodeStatus:
        if not self.children:
            return NodeStatus.SUCCESS
        successes = 0
        failures = 0
        running = 0
        for child in self.children:
            status = child.tick(context)
            if status == NodeStatus.SUCCESS:
                successes += 1
            elif status == NodeStatus.FAILURE:
                failures += 1
            elif status == NodeStatus.RUNNING:
                running += 1
        # Check failure first
        if self.failure_policy == 0 and failures > 0:
            return NodeStatus.FAILURE
        if self.failure_policy > 0 and failures >= self.failure_policy:
            return NodeStatus.FAILURE
        # Then success
        required = len(self.children) if self.success_policy == 0 else self.success_policy
        if successes >= required:
            return NodeStatus.SUCCESS
        if running > 0:
            return NodeStatus.RUNNING
        return NodeStatus.FAILURE

    def reset(self) -> None:
        for child in self.children:
            child.reset()


@dataclass
class DelayNode(BehaviorNode):
    """Wits N ticks before returning success."""

    delay_ticks: int = 1
    _elapsed: int = 0

    def tick(self, context: Any) -> NodeStatus:
        self._elapsed += 1
        if self._elapsed >= self.delay_ticks:
            self._elapsed = 0
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    def reset(self) -> None:
        self._elapsed = 0


class BehaviorTree:
    """A complete behavior tree."""

    def __init__(self, root: Optional[BehaviorNode] = None) -> None:
        self.root = root

    def tick(self, context: Any) -> NodeStatus:
        if self.root is None:
            return NodeStatus.SUCCESS
        return self.root.tick(context)

    def reset(self) -> None:
        if self.root:
            self.root.reset()
