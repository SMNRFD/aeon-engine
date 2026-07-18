"""Serialization — versioned saves with migration and integrity."""

from engine.serialization.save import (
    SaveManager, SaveData, SaveSlot, SAVE_FORMAT_VERSION,
)
