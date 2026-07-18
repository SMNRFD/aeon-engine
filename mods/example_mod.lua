-- Lua mod example for the Aeon Engine
-- Demonstrates how to define content using Lua syntax.
-- Requires the 'lupa' package: pip install lupa

-- This mod adds a custom weapon, creature, and spell via Lua.

local mod = {
    mod_id = "lua_content_pack",
    name = "Lua Content Pack",
    version = "0.1.0",
    description = "An example Lua mod.",
    author = "Aeon Team",
    tags = {"item_pack", "monster_pack"},
}

-- Define items
mod.items = {
    {
        archetype = "staff",
        name = "Archmage's Staff",
        material = "ebony",
        quality = "masterwork",
        rarity = "legendary",
        enchantments = {
            {type = "mana_regen", magnitude = 2.0},
            {type = "magic_power", magnitude = 0.5},
        },
        history = {"Once wielded by the archmage Velindra."},
    },
    {
        archetype = "amulet",
        name = "Amulet of Eternal Vigil",
        material = "gold",
        quality = "excellent",
        rarity = "epic",
        enchantments = {
            {type = "regen", magnitude = 1.0},
        },
    },
}

-- Define creatures
mod.creatures = {
    {
        id = "ancient_lich",
        name = "Ancient Lich",
        glyph = "L",
        color = 90,
        hp = 200,
        strength = 15,
        agility = 10,
        aggressive = true,
        tags = {"hostile", "undead", "magical"},
    },
    {
        id = "phoenix_wyrmling",
        name = "Phoenix Wyrmling",
        glyph = "p",
        color = 215,
        hp = 80,
        strength = 12,
        agility = 16,
        aggressive = false,
        tags = {"magical", "fire"},
    },
}

-- Define spells
mod.spells = {
    {
        id = "archmage_fireball",
        name = "Archmage's Fireball",
        school = "evocation",
        mana_cost = 60,
        cast_time = 2.0,
        target = "area",
        effects = {
            {kind = "damage", magnitude = 80.0, damage_type = "fire", area_radius = 6.0},
        },
        tags = {"fire", "destructive"},
    },
    {
        id = "lich_decay",
        name = "Decay",
        school = "necromancy",
        mana_cost = 30,
        cast_time = 1.5,
        target = "enemy",
        effects = {
            {kind = "damage", magnitude = 25.0, damage_type = "necrotic"},
            {kind = "debuff", duration = 10.0, status_effect = "weakened"},
        },
        tags = {"death", "debuff"},
    },
}

-- Define a custom skill
mod.skills = {
    {
        id = "ancient_lore",
        name = "Ancient Lore",
        category = "knowledge",
        governing_attribute = "intelligence",
        difficulty = 1.5,
        base_xp = 200,
        description = "Knowledge of forgotten ages.",
    },
}

-- Helper function: compute total power of an item
function mod.item_power(item)
    local power = 0
    if item.enchantments then
        for _, ench in ipairs(item.enchantments) do
            power = power + (ench.magnitude or 0)
        end
    end
    return power
end

-- Helper function: format creature stats
function mod.format_creature(creature)
    return string.format("%s (HP:%d, Str:%d, Agi:%d)",
        creature.name, creature.hp, creature.strength, creature.agility)
end

return mod
