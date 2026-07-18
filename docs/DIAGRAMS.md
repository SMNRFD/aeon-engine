# Aeon Engine — Architecture Diagrams

Mermaid diagrams visualizing the engine architecture.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Engine Core"
        Engine[Engine Facade]
        ECS[ECS World]
        EventBus[Event Bus]
        Clock[Game Clock]
        Config[Config]
        Logging[Logging]
    end

    subgraph "World Layer"
        Gen[World Generator]
        Terrain[Terrain]
        Biomes[Biomes]
        Pathfinder[A* Pathfinder]
        Spatial[Spatial Grid]
        Streaming[Streaming World]
        Dimensions[Dimensions]
    end

    subgraph "Entity Layer"
        Factory[Entity Factory]
        Components[Components]
        Items[Items]
        Inventory[Inventory]
    end

    subgraph "NPC Layer"
        AI[AI Controllers]
        Needs[Needs]
        Memory[Memory]
        Schedule[Schedule]
        Personality[Personality]
        Behaviors[Behavior Trees]
        GOAP[GOAP Planner]
        AsyncSim[Async Simulator]
    end

    subgraph "Combat Layer"
        Combat[Turn-based Combat]
        Realtime[Real-time Combat]
        BodyParts[Body Parts]
        Mounted[Mounted Combat]
        Naval[Naval Combat]
        Aerial[Aerial Combat]
        Siege[Siege Combat]
        Space[Space Combat]
    end

    subgraph "Magic Layer"
        Spells[Spells]
        Schools[Schools]
        Research[Spell Research]
        Runes[Runes]
        Artifacts[Artifacts]
    end

    subgraph "Social Layer"
        Dialogue[Dialogue]
        Quests[Quests]
        Factions[Factions]
        Kingdoms[Kingdoms]
        Reputation[Reputation]
        Life[Life Simulation]
        Companies[Companies]
        Espionage[Espionage]
        Rebellions[Rebellions]
    end

    subgraph "Economic Layer"
        Economy[Economy]
        Markets[Markets]
        Trade[Trade Routes]
        Auctions[Auctions]
        BlackMarket[Black Market]
        Banks[Banks]
    end

    subgraph "Environment Layer"
        Weather[Weather]
        Survival[Survival]
        Animals[Animals]
        Dungeons[Dungeons]
        Structures[Structures]
        Stealth[Stealth]
    end

    subgraph "System Layer"
        Save[Save System]
        Commands[Commands]
        I18n[Localization]
        Audio[Audio]
        Performance[Performance]
        Scripting[Scripting]
        Background[Background Sim]
    end

    subgraph "UI Layer"
        Render[Renderer]
        Screens[Screens]
        Themes[Themes]
        Keys[Keybindings]
        Access[Accessibility]
        UIExt[UI Extensions]
        Bookmarks[Bookmarks]
    end

    subgraph "Plugin Layer"
        PluginMgr[Plugin Manager]
        Installer[Installer]
        Sandbox[Sandbox]
        Validator[Validator]
        Migrations[Migrations]
        Docs[Doc Generator]
        NetHooks[Network Hooks]
    end

    subgraph "Network Layer"
        Server[Server]
        Client[Client]
        Replication[Replication]
        Predictor[Client Predictor]
        Authority[Server Authority]
        Rollback[Rollback]
    end

    subgraph "Content Layer"
        ModLoader[Mod Loader]
        ContentPacks[Content Packs]
    end

    Engine --> ECS
    Engine --> EventBus
    Engine --> Clock
    Engine --> Gen
    Engine --> Factory
    Engine --> Combat
    Engine --> Spells
    Engine --> Dialogue
    Engine --> Quests
    Engine --> Economy
    Engine --> Factions
    Engine --> Kingdoms
    Engine --> Weather
    Engine --> Save
    Engine --> Commands
    Engine --> PluginMgr
    Engine --> Replication
    Engine --> Background
```

## ECS Component Flow

```mermaid
graph LR
    subgraph "Entity Lifecycle"
        Create[Create Entity] --> AddComp[Add Components]
        AddComp --> Tag[Add Tags]
        Tag --> Active[Active Entity]
        Active --> Destroy[Destroy Entity]
        Destroy --> GenBump[Bump Generation]
    end

    subgraph "Component Storage"
        World[ECS World]
        ByType[By-Type Index]
        Tags[Tag Index]
    end

    subgraph "Queries"
        View[World.view]
        EntitiesWith[entities_with]
        EntitiesWithTag[entities_with_tag]
    end

    Create --> World
    AddComp --> ByType
    Tag --> Tags
    View --> ByType
    EntitiesWith --> ByType
    EntitiesWithTag --> Tags
```

## Event Bus Flow

```mermaid
sequenceDiagram
    participant Publisher
    participant EventBus
    participant Handler1 as High Priority Handler
    participant Handler2 as Normal Handler
    participant Handler3 as Monitor Handler

    Publisher->>EventBus: dispatch(Event)
    EventBus->>Handler1: call(event)
    Handler1->>EventBus: return (may cancel)
    alt Not Cancelled
        EventBus->>Handler2: call(event)
        Handler2->>EventBus: return
    end
    Note over EventBus: MONITOR always runs
    EventBus->>Handler3: call(event)
    Handler3->>EventBus: return
    EventBus->>Publisher: return (cancelled?)
```

## Plugin Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Discovered
    Discovered --> Loading: load_all()
    Loading --> Loaded: on_load()
    Loading --> Error: on_load failed
    Loaded --> Enabling: enable()
    Enabling --> Enabled: on_enable()
    Enabling --> Error: on_enable failed
    Enabled --> Disabling: disable()
    Disabling --> Loaded: on_disable()
    Loaded --> Unloading: unload()
    Unloading --> [*]: on_unload()
    Enabled --> Reloading: reload()
    Reloading --> Loaded: on_reload()
    Error --> [*]
```

## Combat Resolution

```mermaid
graph TD
    Start[Attack Initiated] --> CheckRange{In Range?}
    CheckRange -- No --> Miss[Attack Misses]
    CheckRange -- Yes --> RollHit[Roll Hit Chance]
    RollHit --> HitCheck{Hit?}
    HitCheck -- No --> Miss
    HitCheck -- Yes --> RollBlock[Roll Block]
    RollBlock --> BlockCheck{Blocked?}
    BlockCheck -- Yes --> Blocked[No Damage]
    BlockCheck -- No --> RollCrit[Roll Crit]
    RollCrit --> CritCheck{Critical?}
    CritCheck -- Yes --> CritDamage[2x Damage]
    CritCheck -- No --> NormalDamage[Normal Damage]
    CritDamage --> ApplyArmor[Apply Armor]
    NormalDamage --> ApplyArmor
    ApplyArmor --> ApplyResist[Apply Resistances]
    ApplyResist --> DealDamage[Deal Damage]
    DealDamage --> CheckDeath{Target Dead?}
    CheckDeath -- Yes --> Death[Handle Death]
    CheckDeath -- No --> ApplyEffects[Apply Status Effects]
    Blocked --> End[End Attack]
    Miss --> End
    Death --> End
    ApplyEffects --> End
```

## World Generation Pipeline

```mermaid
graph LR
    subgraph "Noise Generation"
        Height[Heightmap Noise]
        Moisture[Moisture Noise]
        Temperature[Temperature Noise]
    end

    subgraph "Climate"
        LatTemp[Latitude Temperature]
        AltCool[Altitude Cooling]
        Combine[Combine Climate]
    end

    subgraph "Classification"
        BiomeClass[Biome Classification]
        TerrainPick[Terrain Selection]
    end

    subgraph "Features"
        Rivers[River Tracing]
        Settlements[Settlement Placement]
        Roads[Road Network]
        Encounters[Encounter Rates]
    end

    Height --> BiomeClass
    Moisture --> BiomeClass
    Temperature --> Combine
    LatTemp --> Combine
    AltCool --> Combine
    Combine --> BiomeClass
    BiomeClass --> TerrainPick
    TerrainPick --> Rivers
    Rivers --> Settlements
    Settlements --> Roads
    Roads --> Encounters
```

## NPC AI Decision Flow

```mermaid
graph TD
    Tick[AI Tick] --> CheckControlled{Controlled?}
    CheckControlled -- Yes --> Skip[Skip Action]
    CheckControlled -- No --> CheckNeeds{Critical Needs?}
    CheckNeeds -- Hunger > 80 --> Eat[Find Food]
    CheckNeeds -- Thirst > 80 --> Drink[Find Water]
    CheckNeeds -- Sleep > 85 --> Sleep[Sleep]
    CheckNeeds -- No --> CheckHostiles{Hostiles Nearby?}
    CheckHostiles -- Yes --> CheckBrave{Brave Enough?}
    CheckBrave -- Yes --> Attack[Attack]
    CheckBrave -- No --> Flee[Flee]
    CheckHostiles -- No --> CheckSchedule{Schedule Activity?}
    CheckSchedule -- Sleep --> DoSleep[Go Sleep]
    CheckSchedule -- Eat --> DoEat[Eat Meal]
    CheckSchedule -- Work --> DoWork[Go to Work]
    CheckSchedule -- Wander --> Wander[Wander]
    CheckSchedule -- Drink --> DoDrink[Go to Tavern]
    CheckSchedule -- None --> Social{Nearby Friend?}
    Social -- Yes --> Talk[Talk]
    Social -- No --> Idle[Idle]
```

## Skill Progression

```mermaid
graph LR
    UseSkill[Use Skill] --> GainXP[Gain XP]
    GainXP --> CheckLevel{XP Enough?}
    CheckLevel -- Yes --> LevelUp[Level Up]
    CheckLevel -- No --> DecayCheck[Decay Timer]
    LevelUp --> CheckMilestone{Milestone?}
    CheckMilestone -- Yes --> DiscoverSkill[Discover Related Skill]
    CheckMilestone -- No --> Continue[Continue]
    DecayCheck --> UnusedLong{Unused Long?}
    UnusedLong -- Yes --> LoseXP[Lose XP]
    UnusedLong -- No --> Continue
    LoseXP --> CheckLevelDown{Level Down?}
    CheckLevelDown -- Yes --> LevelDown[Level Down]
    CheckLevelDown -- No --> Continue
```

## Save System Architecture

```mermaid
graph TB
    subgraph "Save Process"
        Snapshot[Take Snapshot]
        Serialize[Serialize to Dict]
        Compress[Compress with zlib]
        Hash[Compute SHA-256]
        Write[Write to File]
    end

    subgraph "Load Process"
        Read[Read File]
        VerifyHash[Verify Hash]
        Decompress[Decompress]
        Deserialize[Deserialize from Dict]
        Migrate[Apply Migrations]
        Restore[Restore State]
    end

    subgraph "Migration System"
        V1[Version 1]
        V2[Version 2]
        V3[Version 3]
        Migrator[Migrator]
    end

    Snapshot --> Serialize
    Serialize --> Compress
    Compress --> Hash
    Hash --> Write

    Read --> VerifyHash
    VerifyHash --> Decompress
    Decompress --> Deserialize
    Deserialize --> Migrate
    Migrate --> Restore

    V1 --> Migrator
    V2 --> Migrator
    V3 --> Migrator
    Migrator --> Restore
```

## Networking Architecture

```mermaid
graph TB
    subgraph "Client"
        CInput[Player Input]
        CPredict[Client Predictor]
        CState[Local State]
        CRender[Renderer]
    end

    subgraph "Network"
        Upload[Outgoing Messages]
        PluginHooksOut[Plugin Hooks]
        Download[Incoming Messages]
        PluginHooksIn[Plugin Hooks]
    end

    subgraph "Server"
        SAuth[Server Authority]
        SValidate[Action Validation]
        SSim[Simulation]
        SReplicate[Replication System]
        SRollback[Rollback Buffer]
    end

    CInput --> CPredict
    CPredict --> CState
    CState --> CRender
    CInput --> Upload
    Upload --> PluginHooksOut
    PluginHooksOut --> SAuth
    SAuth --> SValidate
    SValidate --> SSim
    SSim --> SRollback
    SSim --> SReplicate
    SReplicate --> Download
    Download --> PluginHooksIn
    PluginHooksIn --> CState
```

## Streaming World

```mermaid
graph TB
    Player[Player Position] --> Update[Update Center]
    Update --> CalcChunks[Calculate Needed Chunks]
    CalcChunks --> QueueLoad[Queue Chunks to Load]
    QueueLoad --> AsyncLoader{Async Loading?}
    AsyncLoader -- Yes --> ThreadPool[Thread Pool]
    AsyncLoader -- No --> SyncLoad[Synchronous Load]
    ThreadPool --> Loader[Chunk Loader]
    SyncLoad --> Loader
    Loader --> Generate[Generate Chunk]
    Generate --> Cache[Cache Manager]
    Cache --> Loaded[Loaded Chunks]

    CalcChunks --> UnloadFar[Unload Far Chunks]
    UnloadFar --> SaveChunk[Save Chunk to Disk]
    SaveChunk --> Evicted[Evicted]
```

## Dimensional Travel

```mermaid
graph LR
    Material[Material Plane] <-->|Portal| Shadow[Shadowfell]
    Material <-->|Portal| Fey[Feywild]
    Material <-->|Spell| Fire[Plane of Fire]
    Material <-->|Spell| Water[Plane of Water]
    Material <-->|Spell| Air[Plane of Air]
    Material <-->|Spell| Earth[Plane of Earth]
    Material <-->|Artifact| Abyss[The Abyss]
    Material <-->|Artifact| Heaven[Celestial Heavens]
    Material <-->|Spell| Dream[Dreamlands]
    Material <-->|Spell| Underworld[Underworld]
    Void[The Void] -.->|Forbidden| Material
```

## Quest Chain with Consequences

```mermaid
graph TD
    Quest1[Quest 1: Investigate] --> Complete1{Complete?}
    Complete1 -- Yes --> Conseq1[Consequences]
    Complete1 -- No --> Fail1[Fail Consequences]
    Conseq1 --> Unlock2[Unlock Quest 2]
    Fail1 --> Alt2[Alternative Quest 2']
    Unlock2 --> Quest2[Quest 2: Confront]
    Alt2 --> Quest2
    Quest2 --> Complete2{Complete?}
    Complete2 -- Yes --> Conseq2[Major Consequences]
    Complete2 -- No --> Fail2[Fail Consequences]
    Conseq2 --> Quest3[Quest 3: Resolve]
    Fail2 --> EndFail[Chain Failed]
    Quest3 --> Complete3{Complete?}
    Complete3 -- Yes --> FinalReward[Final Reward]
    Complete3 -- No --> EndFail
```

## Background Simulation

```mermaid
sequenceDiagram
    participant Player as Player
    participant Engine as Engine
    participant BG as Background Simulator
    participant World as World State

    Player->>Engine: Save and Quit
    Engine->>BG: Start Simulation
    loop Every Real Second
        BG->>World: Advance 1 Game Hour
        World->>BG: Generate Events
        BG->>BG: Record Events
    end
    Player->>Engine: Load Game
    Engine->>BG: Stop Simulation
    BG->>Engine: Generate Report
    Engine->>Player: Display Summary
```

## Replication Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant R as Replication

    C->>S: Action Request
    S->>S: Validate (Authority)
    S->>S: Apply to State
    S->>R: Update Replicated State
    R->>R: Take Snapshot (20Hz)
    R->>C: Send Snapshot
    C->>C: Reconcile with Prediction
    C->>C: Update Local State
```

## Content Pack Loading

```mermaid
graph TD
    Dir[Content Packs Directory] --> Scan[Scan for Packs]
    Scan --> Manifest[Load Manifest]
    Manifest --> Register[Register in Registry]
    Register --> Apply[Apply to Engine]
    Apply --> Items[Register Items]
    Apply --> Creatures[Register Creatures]
    Apply --> Spells[Register Spells]
    Apply --> Skills[Register Skills]
    Apply --> Recipes[Register Recipes]
    Apply --> Themes[Register Themes]
    Apply --> Sounds[Register Sounds]
    Apply --> Localization[Add Localization]
    Apply --> Diseases[Register Diseases]
```
