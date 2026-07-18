# Aeon Engine — Package Summary

**The world's most advanced, production-grade text-based open-world RPG engine in Python.**

## Package Contents

- `engine/` — 70+ subsystem packages, ~25,000 lines of production Python
- `plugins/` — Sample fishing plugin
- `mods/` — 4 sample mods (JSON, YAML, Lua, directory)
- `tests/` — 172 tests (unit, integration, performance, async, networking)
- `docs/` — 6 documentation files including Mermaid diagrams
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

# Run tests (172 tests, ~50 seconds)
python -m pytest tests/ -v

# Headless verification
python main.py --headless --seed 42 --width 60 --height 40

# Full game (terminal UI)
python main.py --seed 42 --width 80 --height 50

# Debug mode
python main.py --debug
```

## Statistics

- **Code**: ~25,000 lines of production Python
- **Subsystems**: 70+ packages
- **Tests**: 172 passing
- **Documentation**: 6 docs (architecture, diagrams, plugin guide, modding guide, developer guide, API reference)

## Complete Subsystem List

1. **Core** (ECS, EventBus, GameClock, Config, Logging)
2. **Plugins** (manager, registry, sandbox, installer, validator, docs, migrations, networking hooks)
3. **World** (terrain, biomes, generator, pathfinding, spatial grid)
4. **Dimensions** (12 dimensions, 5 planets, 3 galaxies, floating islands, underground civs, ancient ruins)
5. **Streaming** (chunk-based streaming with async loading)
6. **Entities** (components, factory)
7. **NPC** (AI, needs, memory, schedule, personality, async simulator)
8. **Items** (materials, affixes, generator, registry)
9. **Inventory** (slots, equipment)
10. **Combat** (turn-based, damage, status effects)
11. **Realtime Combat** (cooldowns, cast times, action priority)
12. **Body Parts** (19 part types, hit locations, crippling)
13. **Mounted Combat** (horses, charge bonuses)
14. **Naval Combat** (9 ship types, bombardment, boarding)
15. **Aerial Combat** (flying mounts, maneuvers, altitude)
16. **Siege Combat** (8 siege engines, walls, assaults)
17. **Space Combat** (starships, 7 weapon types, shields)
18. **Skills** (58 skills, XP, decay, checks)
19. **Crafting** (recipes, research)
20. **Magic** (schools, spells, research)
21. **Runes** (17 rune types, inscription)
22. **Artifacts** (7 unique artifacts, sentience, curses)
23. **Dialogue** (trees, persuasion)
24. **Procedural Dialogue** (template-based generation)
25. **Quests** (branching, procedural)
26. **Quest Consequences** (chains, delayed effects)
27. **Economy** (markets, trade goods, banks)
28. **Factions** (diplomacy, wars, laws)
29. **Kingdoms** (politics, succession, territory)
30. **Reputation** (10 dimensions)
31. **Life** (marriage, family, inheritance)
32. **Animals** (species, populations, domestication)
33. **Rebellions** (rebellions, civil wars, succession crises)
34. **Black Market** (fencing, assassination contracts)
35. **Weather** (seasons, climate)
36. **Survival** (disease, exposure, poison)
37. **Dungeons** (10 types, 3 algorithms)
38. **Structures** (51 types)
39. **Stealth** (sneaking, detection)
40. **Trade** (routes, caravans, ships)
41. **Auctions** (bidding, reserve, buyout)
42. **Companies** (companies, guilds, employment)
43. **Espionage** (spies, missions)
44. **Behaviors** (behavior trees)
45. **GOAP** (goal-oriented action planning)
46. **Scripting** (sandboxed Python)
47. **Audio** (sound effects, cues)
48. **Performance** (pool, profiler, caches)
49. **Commands** (parser, aliases, macros)
50. **Serialization** (versioned saves, integrity)
51. **Localization** (i18n, pluralization, RTL)
52. **Render** (ANSI terminal renderer)
53. **UI** (5 screens)
54. **UI Extensions** (search, filtering, mouse, sortable lists)
55. **Themes** (8 themes)
56. **Keybindings** (50+ actions)
57. **Accessibility** (screen reader, colorblindness)
58. **Bookmarks** (map bookmarks, pins, markers)
59. **Network** (client/server protocol)
60. **Replication** (replication, prediction, rollback, authority)
61. **Content Packs** (25 pack types)
62. **Mods Loader** (JSON, YAML, Lua, Python)
63. **Background Sim** (persistent world simulation)
64. **Skill Books** (books, discovery, procedural progression)

## Content Catalogue

- 22 terrain types, 15 biomes
- 27 materials, 29 affixes, 15 item archetypes
- 58 skills, 12 spells, 8 magic schools, 17 runes, 7 artifacts
- 10 crafting recipes, 8 diseases, 14 weather types, 6 climates
- 8 kingdoms, 6 factions, 22 trade goods
- 22+ animal species, 14 skill books
- 51 structure types, 10 dungeon types
- 12 dimensions, 5 planets, 3 galaxies
- 36 sound effects, 8 themes, 50+ keybinding actions
- 13 default commands, 3 default quests
- 7 combat variants (turn-based, real-time, mounted, naval, aerial, siege, space)
- Sample plugin (fishing), 4 sample mods

## License

MIT
