"""ECS components used by the engine.

Components are plain dataclasses; systems operate over them. Subsystems
(items, npc, combat, ...) may declare their own components in their
subpackages — they are all registered in the world uniformly.
"""

from engine.entities.components import *
from engine.entities.factory import EntityFactory
