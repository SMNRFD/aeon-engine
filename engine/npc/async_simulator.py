"""Async NPC simulation with threading.

Runs NPC AI ticks in a thread pool for better performance with many NPCs.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from engine.core.ecs import Entity, World
from engine.core.logging import get_logger


log = get_logger("async_npc")


@dataclass
class NPCBatch:
    """A batch of NPCs to simulate."""

    batch_id: int
    entity_ids: list[int] = field(default_factory=list)
    is_processing: bool = False
    last_processed: float = 0.0


class AsyncNPCSimulator:
    """Runs NPC AI in a thread pool.

    Divides NPCs into batches and processes them concurrently.
    Each batch is processed by a separate thread.
    """

    def __init__(self, num_workers: int = 4,
                 batch_size: int = 50) -> None:
        self.num_workers = num_workers
        self.batch_size = batch_size
        self._executor: Optional[ThreadPoolExecutor] = None
        self._batches: dict[int, NPCBatch] = {}
        self._next_batch_id: int = 1
        self._is_running: bool = False
        self._lock = threading.RLock()
        self._pending_futures: dict[int, Future] = {}
        self._stats: dict[str, Any] = {
            "total_processed": 0,
            "total_errors": 0,
            "avg_processing_time": 0.0,
        }

    def start(self) -> None:
        if self._is_running:
            return
        self._executor = ThreadPoolExecutor(max_workers=self.num_workers,
                                             thread_name_prefix="npc-sim")
        self._is_running = True
        log.info("Async NPC simulator started with %d workers", self.num_workers)

    def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
        log.info("Async NPC simulator stopped")

    @property
    def is_running(self) -> bool:
        return self._is_running

    def register_npc(self, entity_id: int) -> None:
        """Register an NPC for async simulation."""
        with self._lock:
            # Find or create a batch with space
            for batch in self._batches.values():
                if len(batch.entity_ids) < self.batch_size:
                    batch.entity_ids.append(entity_id)
                    return
            # Create new batch
            batch = NPCBatch(batch_id=self._next_batch_id,
                              entity_ids=[entity_id])
            self._batches[self._next_batch_id] = batch
            self._next_batch_id += 1

    def unregister_npc(self, entity_id: int) -> None:
        """Remove an NPC from async simulation."""
        with self._lock:
            for batch in self._batches.values():
                if entity_id in batch.entity_ids:
                    batch.entity_ids.remove(entity_id)
                    return

    def tick(self, world: World, dt: float,
             process_fn: Optional[Callable[[Entity, float], None]] = None) -> int:
        """Process all NPCs in batches.

        Args:
            world: The ECS world
            dt: Delta time
            process_fn: Function to call for each NPC (entity, dt) -> None.
                       If None, a no-op is used.

        Returns:
            Number of NPCs processed.
        """
        if not self._is_running or self._executor is None:
            return 0
        if process_fn is None:
            process_fn = lambda e, dt: None  # noqa: E731
        # Submit each batch
        futures: list[tuple[int, Future]] = []
        with self._lock:
            batches_snapshot = list(self._batches.items())
        for batch_id, batch in batches_snapshot:
            if batch.is_processing or not batch.entity_ids:
                continue
            batch.is_processing = True
            batch.last_processed = time.time()
            future = self._executor.submit(
                self._process_batch, batch, world, dt, process_fn,
            )
            futures.append((batch_id, future))
            self._pending_futures[batch_id] = future
        # Wait for all to complete
        total_processed = 0
        for batch_id, future in futures:
            try:
                count = future.result(timeout=10.0)
                total_processed += count
            except Exception as exc:  # noqa: BLE001
                log.error("Batch %d failed: %s", batch_id, exc)
                self._stats["total_errors"] += 1
            finally:
                with self._lock:
                    batch = self._batches.get(batch_id)
                    if batch:
                        batch.is_processing = False
                    self._pending_futures.pop(batch_id, None)
        self._stats["total_processed"] += total_processed
        return total_processed

    def _process_batch(self, batch: NPCBatch, world: World, dt: float,
                        process_fn: Callable[[Entity, float], None]) -> int:
        """Process a single batch of NPCs."""
        count = 0
        for entity_id in batch.entity_ids:
            # Find the entity
            entity = None
            for ent in list(world._components.keys()):
                if ent.id == entity_id:
                    entity = ent
                    break
            if entity is None:
                continue
            try:
                process_fn(entity, dt)
                count += 1
            except Exception as exc:  # noqa: BLE001
                log.error("NPC %d processing failed: %s", entity_id, exc)
                self._stats["total_errors"] += 1
        return count

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "num_batches": len(self._batches),
            "num_workers": self.num_workers,
            "batch_size": self.batch_size,
            "is_running": self._is_running,
            "pending_futures": len(self._pending_futures),
        }
