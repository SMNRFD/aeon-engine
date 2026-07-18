# Aeon Engine — Package Summary

**The world's most advanced, production-grade text-based open-world RPG engine in Python.**

## Package Contents

- `engine/` — 47 subsystem packages, ~19,000 lines of production Python
- `plugins/` — Sample fishing plugin
- `mods/` — 4 sample mods (JSON, YAML, Lua, directory)
- `tests/` — 118 tests (unit, integration, performance)
- `docs/` — 5 documentation files
- `main.py` — Entry point
- `engine.toml` — Configuration
- `pyproject.toml` — Python project config
- `README.md` — Project overview
- `worklog.md` — Development log

## Quick Start

```bash
# Unpack
unzip aeon-engine.zip
cd aeon-engine

# Run tests (118 tests, ~30 seconds)
python -m pytest tests/ -v

# Headless verification
python main.py --headless --seed 42 --width 60 --height 40

# Full game (terminal UI)
python main.py --seed 42 --width 80 --height 50

# Debug mode
python main.py --debug
```

## Statistics

- **Code**: ~19,000 lines of production Python across 124 files
- **Subsystems**: 47 packages
- **Tests**: 118 passing (unit, integration, performance)
- **Documentation**: 5 docs (architecture, plugin guide, modding guide, developer guide, API reference)

## Content Catalogue

- 22 terrain types, 15 biomes
- 27 materials, 29 affixes, 15 item archetypes → millions of unique items
- 58 skills, 12 spells, 8 magic schools
- 10 crafting recipes, 8 diseases, 14 weather types, 6 climates
- 8 kingdoms, 6 factions, 22 trade goods
- 22+ animal species, 8 default dialogue trees
- 51 structure types, 10 dungeon types
- 36 sound effects, 8 themes, 50+ keybinding actions
- 13 default commands, 3 default quests

## Subsystems

1. **Core** (ECS, EventBus, GameClock, Config, Logging)
2. **Plugins** (manager, registry, sandbox, installer, validator, docs, migrations)
3. **World** (terrain, biomes, generator, pathfinding, spatial grid)
4. **Entities** (components, factory)
5. **NPC** (AI, needs, memory, schedule, personality)
6. **Items** (materials, affixes, generator, registry)
7. **Inventory** (slots, equipment)
8. **Combat** (resolution, damage, status effects)
9. **Skills** (58 skills, XP, decay, checks)
10. **Crafting** (recipes, research)
11. **Magic** (schools, spells, research)
12. **Dialogue** (trees, persuasion)
13. **Quests** (branching, procedural)
14. **Economy** (markets, trade goods, banks)
15. **Factions** (diplomacy, wars, laws)
16. **Kingdoms** (politics, succession, territory)
17. **Reputation** (10 dimensions)
18. **Life** (marriage, family, inheritance)
19. **Animals** (species, populations, domestication)
20. **Weather** (seasons, climate)
21. **Survival** (disease, exposure, poison)
22. **Dungeons** (10 types, 3 algorithms)
23. **Structures** (51 types)
24. **Stealth** (sneaking, detection)
25. **Trade** (routes, caravans, ships)
26. **Auctions** (bidding, reserve, buyout)
27. **Companies** (companies, guilds, employment)
28. **Espionage** (spies, missions)
29. **Behaviors** (behavior trees)
30. **GOAP** (goal-oriented action planning)
31. **Scripting** (sandboxed Python)
32. **Audio** (sound effects, cues)
33. **Performance** (pool, profiler, caches)
34. **Commands** (parser, aliases, macros)
35. **Serialization** (versioned saves, integrity)
36. **Localization** (i18n, pluralization, RTL)
37. **Render** (ANSI terminal renderer)
38. **UI** (5 screens)
39. **Themes** (8 themes)
40. **Keybindings** (50+ actions)
41. **Accessibility** (screen reader, colorblindness)
42. **Network** (client/server protocol)
43. **Mods Loader** (JSON, YAML, Lua, Python)
44. **Engine** (top-level facade)

## License

MIT
