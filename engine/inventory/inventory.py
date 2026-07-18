"""Inventory implementation with weight, slots, and equipment."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional

from engine.core.logging import get_logger
from engine.items.item import Item


log = get_logger("inventory")


class EquipmentSlot(Enum):
    MAIN_HAND = "main_hand"
    OFF_HAND = "off_hand"
    HEAD = "head"
    CHEST = "chest"
    LEGS = "legs"
    FEET = "feet"
    HANDS = "hands"
    CLOAK = "cloak"
    NECK = "neck"
    FINGER_LEFT = "finger_left"
    FINGER_RIGHT = "finger_right"
    AMMO = "ammo"


# Item property "slot" maps to EquipmentSlot:
SLOT_PROPERTY_MAP = {
    0: EquipmentSlot.CHEST,
    1: EquipmentSlot.HEAD,
    2: EquipmentSlot.LEGS,
    3: EquipmentSlot.FEET,
    4: EquipmentSlot.FINGER_LEFT,
    5: EquipmentSlot.NECK,
}


@dataclass
class InventorySlot:
    item_id: int
    count: int = 1


class Inventory:
    """A per-entity inventory with backpack slots and equipment slots."""

    def __init__(self, capacity: int = 30, max_weight: float = 50.0) -> None:
        self.capacity = capacity
        self.max_weight = max_weight
        self._slots: list[Optional[InventorySlot]] = [None] * capacity
        self._equipment: dict[EquipmentSlot, Optional[int]] = {
            slot: None for slot in EquipmentSlot
        }
        # Items are stored in the ItemRegistry — inventory only holds IDs.

    # ---------- backpack ----------

    def add(self, item: Item, count: int = 1) -> bool:
        """Add an item to the inventory. Returns True on success."""
        if item.stackable:
            # Try to merge with existing stack
            for slot in self._slots:
                if slot is not None and slot.item_id == item.id:
                    slot.count += count
                    return True
        if self._first_empty_slot() is None:
            log.debug("Inventory full — cannot add %s", item.name)
            return False
        idx = self._first_empty_slot()
        self._slots[idx] = InventorySlot(item_id=item.id, count=count)
        return True

    def remove(self, item_id: int, count: int = 1) -> bool:
        for i, slot in enumerate(self._slots):
            if slot and slot.item_id == item_id:
                if slot.count > count:
                    slot.count -= count
                    return True
                elif slot.count == count:
                    self._slots[i] = None
                    return True
                else:
                    return False
        return False

    def remove_at(self, slot_idx: int) -> Optional[InventorySlot]:
        if 0 <= slot_idx < self.capacity:
            slot = self._slots[slot_idx]
            self._slots[slot_idx] = None
            return slot
        return None

    def _first_empty_slot(self) -> Optional[int]:
        for i, s in enumerate(self._slots):
            if s is None:
                return i
        return None

    def slots(self) -> list[Optional[InventorySlot]]:
        return list(self._slots)

    def find(self, item_id: int) -> Optional[tuple[int, InventorySlot]]:
        """Find the slot containing item_id. Returns (index, slot)."""
        for i, slot in enumerate(self._slots):
            if slot and slot.item_id == item_id:
                return i, slot
        return None

    def count_of(self, item_id: int) -> int:
        total = 0
        for slot in self._slots:
            if slot and slot.item_id == item_id:
                total += slot.count
        return total

    def total_weight(self, registry) -> float:
        total = 0.0
        for slot in self._slots:
            if slot is None:
                continue
            item = registry.get(slot.item_id)
            if item:
                total += item.weight * slot.count
        for item_id in self._equipment.values():
            if item_id is not None:
                item = registry.get(item_id)
                if item:
                    total += item.weight
        return total

    def used_slots(self) -> int:
        return sum(1 for s in self._slots if s is not None)

    def free_slots(self) -> int:
        return self.capacity - self.used_slots()

    # ---------- equipment ----------

    def equip(self, item: Item, slot: Optional[EquipmentSlot] = None) -> Optional[Item]:
        """Equip an item. If `slot` is None, infer from item properties.
        Returns the previously-equipped item (or None)."""
        if slot is None:
            slot = self._infer_slot(item)
            if slot is None:
                return None
        # Remove from backpack if present.
        self.remove(item.id, 1)
        old_id = self._equipment.get(slot)
        self._equipment[slot] = item.id
        if old_id is not None:
            old_item = item  # placeholder
            return old_item
        return None

    def unequip(self, slot: EquipmentSlot, registry) -> Optional[Item]:
        item_id = self._equipment.get(slot)
        if item_id is None:
            return None
        item = registry.get(item_id)
        self._equipment[slot] = None
        if item:
            self.add(item, 1)
        return item

    def equipped(self, slot: EquipmentSlot) -> Optional[int]:
        return self._equipment.get(slot)

    def all_equipped(self) -> dict[EquipmentSlot, Optional[int]]:
        return dict(self._equipment)

    def _infer_slot(self, item: Item) -> Optional[EquipmentSlot]:
        # Check explicit slot property
        slot_prop = item.properties.get("slot")
        if slot_prop:
            slot_value = int(slot_prop.value)
            if slot_value in SLOT_PROPERTY_MAP:
                # For rings, alternate left/right
                if SLOT_PROPERTY_MAP[slot_value] == EquipmentSlot.FINGER_LEFT:
                    if self._equipment[EquipmentSlot.FINGER_LEFT] is None:
                        return EquipmentSlot.FINGER_LEFT
                    return EquipmentSlot.FINGER_RIGHT
                return SLOT_PROPERTY_MAP[slot_value]
        # Category-based fallback
        if item.category == "weapon":
            if item.two_handed:
                return EquipmentSlot.MAIN_HAND  # also occupies off-hand
            if self._equipment[EquipmentSlot.MAIN_HAND] is None:
                return EquipmentSlot.MAIN_HAND
            return EquipmentSlot.OFF_HAND
        return None

    # ---------- iteration ----------

    def iter_items(self, registry) -> Iterator[tuple[int, Item, int]]:
        """Yield (slot_index, item, count) for each filled slot."""
        for i, slot in enumerate(self._slots):
            if slot is None:
                continue
            item = registry.get(slot.item_id)
            if item:
                yield i, item, slot.count

    def iter_equipment(self, registry) -> Iterator[tuple[EquipmentSlot, Item]]:
        for slot, item_id in self._equipment.items():
            if item_id is None:
                continue
            item = registry.get(item_id)
            if item:
                yield slot, item

    # ---------- serialization ----------

    def to_dict(self) -> dict:
        return {
            "capacity": self.capacity,
            "max_weight": self.max_weight,
            "slots": [
                {"item_id": s.item_id, "count": s.count} if s else None
                for s in self._slots
            ],
            "equipment": {slot.value: item_id for slot, item_id in self._equipment.items()
                          if item_id is not None},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        inv = cls(capacity=data.get("capacity", 30),
                  max_weight=data.get("max_weight", 50.0))
        for i, slot_data in enumerate(data.get("slots", [])):
            if slot_data and i < inv.capacity:
                inv._slots[i] = InventorySlot(
                    item_id=slot_data["item_id"],
                    count=slot_data.get("count", 1),
                )
        for slot_name, item_id in data.get("equipment", {}).items():
            try:
                slot = EquipmentSlot(slot_name)
                inv._equipment[slot] = item_id
            except ValueError:
                continue
        return inv
