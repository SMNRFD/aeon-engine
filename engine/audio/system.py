"""Audio system — descriptive audio cues for accessibility and atmosphere.

In a text-based game, "audio" is primarily:
* Descriptive audio cues (printed text describing sounds for accessibility)
* Terminal bell / system beep for important events
* Optional WAV/OGG playback via OS commands if available
* Sound packs loaded from JSON for modders
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.core.logging import get_logger


log = get_logger("audio")


class AudioChannel(IntEnum):
    MASTER = 0
    MUSIC = 1
    SFX = 2
    AMBIENT = 3
    VOICE = 4
    UI = 5


@dataclass
class SoundEffect:
    """A sound effect definition."""

    id: str
    name: str
    description: str         # textual description for screen readers
    onomatopoeia: str = ""   # e.g. "clang!", "whoosh"
    file_path: Optional[str] = None  # path to audio file (wav/ogg)
    volume: float = 1.0
    pitch: float = 1.0
    loop: bool = False
    duration: float = 0.0    # seconds
    category: str = "sfx"
    tags: list[str] = field(default_factory=list)


@dataclass
class AudioCue:
    """A textual audio cue for screen-reader accessibility."""

    sound_id: str
    text: str
    priority: int = 0  # 0=low, 1=normal, 2=high, 3=critical


class AudioLibrary:
    """Registry of sound effects."""

    _sounds: ClassVar[dict[str, SoundEffect]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, sound: SoundEffect) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._sounds[sound.id] = sound

    @classmethod
    def get(cls, sound_id: str) -> Optional[SoundEffect]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._sounds.get(sound_id)

    @classmethod
    def all(cls) -> list[SoundEffect]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._sounds.values())

    @classmethod
    def by_tag(cls, tag: str) -> list[SoundEffect]:
        return [s for s in cls.all() if tag in s.tags]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for s in DEFAULT_SOUNDS:
            cls._sounds[s.id] = s
        cls._defaults_loaded = True


class AudioSystem:
    """Manages audio playback and audio cues.

    Falls back gracefully:
    * If `play_files` is True and an audio file is available, plays it via
      the OS-default audio command.
    * Otherwise, emits a terminal bell character and prints the descriptive
      text + onomatopoeia.
    * If `silent` is True, only prints the textual description.
    """

    def __init__(self, play_files: bool = False,
                 silent: bool = False,
                 enable_bell: bool = True,
                 volumes: Optional[dict[AudioChannel, float]] = None) -> None:
        self.play_files = play_files
        self.silent = silent
        self.enable_bell = enable_bell
        self.volumes: dict[AudioChannel, float] = volumes or {
            AudioChannel.MASTER: 1.0,
            AudioChannel.MUSIC: 0.7,
            AudioChannel.SFX: 1.0,
            AudioChannel.AMBIENT: 0.5,
            AudioChannel.VOICE: 1.0,
            AudioChannel.UI: 0.6,
        }
        self._muted_channels: set[AudioChannel] = set()
        self._currently_playing: dict[int, str] = {}  # channel -> sound_id
        self._cue_history: list[AudioCue] = []
        self._max_cue_history = 100
        # Detect available audio player
        self._player_cmd = self._detect_player()

    def _detect_player(self) -> Optional[str]:
        """Find an available command-line audio player."""
        if not self.play_files:
            return None
        candidates = []
        system = platform.system().lower()
        if system == "linux":
            candidates = ["paplay", "aplay", "mpv", "ffplay", "cvlc"]
        elif system == "darwin":
            candidates = ["afplay", "mpv"]
        elif system == "windows":
            candidates = []
        for cmd in candidates:
            if shutil.which(cmd):
                return cmd
        return None

    # ---------- playback ----------

    def play(self, sound_id: str, channel: AudioChannel = AudioChannel.SFX,
             volume: Optional[float] = None) -> bool:
        """Play a sound by id. Returns True if playback was initiated."""
        sound = AudioLibrary.get(sound_id)
        if sound is None:
            log.warning("Unknown sound: %s", sound_id)
            return False
        if channel in self._muted_channels:
            return False
        # Always emit a textual cue
        cue = AudioCue(
            sound_id=sound_id,
            text=sound.description,
            priority=2 if sound.category == "ui" else 1,
        )
        self._cue_history.append(cue)
        if len(self._cue_history) > self._max_cue_history:
            self._cue_history = self._cue_history[-self._max_cue_history:]
        # Compute effective volume
        eff_vol = (volume if volume is not None else sound.volume)
        eff_vol *= self.volumes.get(AudioChannel.MASTER, 1.0)
        eff_vol *= self.volumes.get(channel, 1.0)
        # Try file playback
        if sound.file_path and self._player_cmd:
            return self._play_file(sound.file_path, eff_vol)
        # Fallback: terminal bell + onomatopoeia
        if self.enable_bell and not self.silent:
            sys.stdout.write("\a")
            sys.stdout.flush()
        if not self.silent and sound.onomatopoeia:
            sys.stdout.write(f"[{sound.onomatopoeia}]\n")
            sys.stdout.flush()
        return True

    def _play_file(self, file_path: str, volume: float) -> bool:
        """Play an audio file using the detected player."""
        if not os.path.exists(file_path):
            log.warning("Audio file not found: %s", file_path)
            return False
        cmd = self._player_cmd
        if cmd is None:
            return False
        args: list[str] = [cmd]
        if cmd in ("aplay",):
            args.append("-q")
        elif cmd in ("paplay",):
            pass
        elif cmd in ("mpv",):
            args.extend(["--no-video", "--really-quiet",
                         f"--volume={int(volume * 100)}"])
        elif cmd in ("ffplay",):
            args.extend(["-nodisp", "-autoexit", "-loglevel", "quiet"])
        elif cmd in ("afplay",):
            args.extend(["-v", str(volume)])
        elif cmd in ("cvlc",):
            args.extend(["--play-and-exit", "--quiet"])
        args.append(file_path)
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("Audio playback failed: %s", exc)
            return False

    def stop_channel(self, channel: AudioChannel) -> None:
        self._currently_playing.pop(int(channel), None)

    def mute(self, channel: AudioChannel) -> None:
        self._muted_channels.add(channel)

    def unmute(self, channel: AudioChannel) -> None:
        self._muted_channels.discard(channel)

    def set_volume(self, channel: AudioChannel, volume: float) -> None:
        self.volumes[channel] = max(0.0, min(1.0, volume))

    # ---------- cues ----------

    def cue(self, sound_id: str, text: Optional[str] = None,
            priority: int = 1) -> None:
        """Emit a textual audio cue (for screen readers)."""
        sound = AudioLibrary.get(sound_id)
        cue_text = text or (sound.description if sound else sound_id)
        cue = AudioCue(sound_id=sound_id, text=cue_text, priority=priority)
        self._cue_history.append(cue)
        if len(self._cue_history) > self._max_cue_history:
            self._cue_history = self._cue_history[-self._max_cue_history:]
        if not self.silent:
            sys.stdout.write(f"♪ {cue_text}\n")
            sys.stdout.flush()

    def recent_cues(self, n: int = 10) -> list[AudioCue]:
        return list(self._cue_history[-n:])

    def to_dict(self) -> dict[str, Any]:
        return {
            "play_files": self.play_files,
            "silent": self.silent,
            "enable_bell": self.enable_bell,
            "volumes": {int(c): v for c, v in self.volumes.items()},
            "muted_channels": [int(c) for c in self._muted_channels],
        }


# ---------- Default sounds ----------

DEFAULT_SOUNDS: list[SoundEffect] = [
    # Combat
    SoundEffect("sword_hit", "Sword Hit", "The sharp clang of steel on steel.",
                "clang!", category="combat", tags=["weapon", "metal"]),
    SoundEffect("sword_swing", "Sword Swing", "A blade cutting through air.",
                "whoosh", category="combat", tags=["weapon"]),
    SoundEffect("arrow_hit", "Arrow Hit", "An arrow striking flesh.",
                "thwack!", category="combat", tags=["ranged"]),
    SoundEffect("arrow_fire", "Arrow Fire", "A bowstring releasing.",
                "twang", category="combat", tags=["ranged"]),
    SoundEffect("shield_block", "Shield Block", "A blow deflected by a shield.",
                "thunk!", category="combat", tags=["defense"]),
    SoundEffect("spell_cast", "Spell Cast", "Arcane energies gathering.",
                "fwoosh", category="magic", tags=["spell"]),
    SoundEffect("fireball", "Fireball", "A roaring explosion of flame.",
                "KRAKOOOM!", category="magic", tags=["fire"]),
    SoundEffect("lightning", "Lightning", "A crackling bolt of electricity.",
                "ZZZAP!", category="magic", tags=["electric"]),
    SoundEffect("death", "Death", "A final, dying gasp.",
                "...", category="combat", tags=["death"]),
    # UI
    SoundEffect("menu_open", "Menu Open", "A menu appears.",
                "...", category="ui", tags=["interface"]),
    SoundEffect("menu_close", "Menu Close", "A menu closes.",
                "...", category="ui", tags=["interface"]),
    SoundEffect("select", "Select", "An item is selected.",
                "click", category="ui", tags=["interface"]),
    SoundEffect("error", "Error", "An error occurred.",
                "buzz", category="ui", tags=["interface"]),
    SoundEffect("confirm", "Confirm", "An action is confirmed.",
                "ding!", category="ui", tags=["interface"]),
    SoundEffect("level_up", "Level Up", "A triumphant fanfare.",
                "TA-DAA!", category="ui", tags=["progression"]),
    # Environment
    SoundEffect("footstep_grass", "Footsteps on Grass", "Soft footsteps on grass.",
                "swish", category="ambient", tags=["movement"]),
    SoundEffect("footstep_stone", "Footsteps on Stone", "Hard footsteps on stone.",
                "click-clack", category="ambient", tags=["movement"]),
    SoundEffect("footstep_water", "Footsteps in Water", "Splashing footsteps.",
                "splash", category="ambient", tags=["movement"]),
    SoundEffect("rain", "Rain", "Gentle rainfall.",
                "pitter-patter", category="ambient", tags=["weather"], loop=True),
    SoundEffect("thunder", "Thunder", "A distant rumble of thunder.",
                "rumble...", category="ambient", tags=["weather"]),
    SoundEffect("wind", "Wind", "Wind howling.",
                "whoosh", category="ambient", tags=["weather"], loop=True),
    SoundEffect("fire_crackle", "Fire Crackling", "A campfire crackling.",
                "crackle", category="ambient", tags=["fire"], loop=True),
    SoundEffect("river", "River", "Flowing water.",
                "babble", category="ambient", tags=["water"], loop=True),
    SoundEffect("ocean", "Ocean Waves", "Waves crashing on shore.",
                "crash", category="ambient", tags=["water"], loop=True),
    # Creatures
    SoundEffect("wolf_howl", "Wolf Howl", "A wolf howls in the distance.",
                "Aaaaroo!", category="creature", tags=["wolf"]),
    SoundEffect("bird_chirp", "Bird Chirp", "Birds singing.",
                "tweet tweet", category="creature", tags=["bird"]),
    SoundEffect("dragon_roar", "Dragon Roar", "A terrifying dragon's roar.",
                "RAAAAWR!", category="creature", tags=["dragon"]),
    SoundEffect("horse_neigh", "Horse Neigh", "A horse neighs.",
                "neiiigh", category="creature", tags=["horse"]),
    SoundEffect("cow_moo", "Cow Moo", "A cow moos.",
                "moooo", category="creature", tags=["cow"]),
    # Items
    SoundEffect("coin", "Coin", "Coins clinking together.",
                "clink", category="item", tags=["money"]),
    SoundEffect("potion_drink", "Potion Drink", "Drinking a potion.",
                "glug glug", category="item", tags=["consumable"]),
    SoundEffect("door_open", "Door Open", "A door creaking open.",
                "creeeak", category="item", tags=["door"]),
    SoundEffect("door_close", "Door Close", "A door thudding shut.",
                "thud", category="item", tags=["door"]),
    SoundEffect("chest_open", "Chest Open", "A chest opening.",
                "click-whir", category="item", tags=["container"]),
    # Music
    SoundEffect("music_town", "Town Music", "Peaceful town ambience.",
                "♪", category="music", tags=["town"], loop=True),
    SoundEffect("music_combat", "Combat Music", "Tense combat music.",
                "♪♪", category="music", tags=["combat"], loop=True),
    SoundEffect("music_dungeon", "Dungeon Music", "Eerie dungeon ambience.",
                "♪", category="music", tags=["dungeon"], loop=True),
    SoundEffect("music_boss", "Boss Music", "Epic boss battle music.",
                "♪♪♪", category="music", tags=["boss"], loop=True),
]
