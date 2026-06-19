# Jules AI Multiplayer Implementation Guide (دليل المبرمج جوليان)

Hey Jules! You are tasked with implementing the backend engine and Discord cogs to support **Multiplayer Mode (`game_mode: "multi"`)** in the Nexus bot.

Follow this technical plan exactly to integrate it with the existing code structure.

---

## 1. Codebase Architecture Modifications

You will need to modify or create the following files:

```
stories_only_bot/
├── core/
│   └── db.py                 # Modify: Add table 'multiplayer_sessions'
├── engine/
│   ├── models.py             # Modify: Add MultiplayerSession, Vote, and Role models
│   └── multiplayer_manager.py # NEW: Manages active multiplayer lobbies, votes, and NPC decisions
└── cogs/
    └── event_cog.py          # Modify/Rewrite: Handle discord interactions, votes, and ephemeral buttons
```

---

## 2. Technical Specs & Implementations

### A. Database Updates (`core/db.py`)
Add a schema initialization for multiplayer sessions:
```python
# In init_db()
await db.execute("""
    CREATE TABLE IF NOT EXISTS multiplayer_sessions (
        session_id TEXT PRIMARY KEY,
        story_id TEXT,
        status TEXT, -- 'lobby', 'active', 'finished'
        players TEXT, -- JSON mapping of discord_id -> role_id
        current_node_states TEXT, -- JSON mapping of role_id -> current_node_id
        flags TEXT, -- JSON mapping of flags set in session
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
```

### B. Core Event Loop (`engine/multiplayer_manager.py`)
Create a manager that keeps track of active multiplayer sessions:
1. **Lobby Management**:
   - `create_session(story_id) -> session_id`
   - `add_player(session_id, user_id, role_id) -> bool`
   - `fill_vacant_roles_with_npcs(session_id)`
2. **Voting Engine**:
   - For `group_decision` nodes: Keep track of `Vote` objects (`player_id`, `choice_index`).
   - Resolves once `len(votes) == len(roles)`.
   - Ties resolved by selecting the choice favored by the Prince/Leader (or random default).
3. **NPC Decision Engine**:
   - If a role is an NPC, automatically select their choice based on trait weights:
     $$P(\text{choice}) \propto \sum (\text{npc\_trait} \times \text{choice\_npc\_weight})$$
   - Trigger the NPC dialogue output to Discord if `npc_dialogues` is defined.
4. **Path Synchronization**:
   - Keep a dict of `role_id -> current_node_id`.
   - When a player triggers `next`, update their location.
   - If they hit a node where `is_convergence: true`, block their buttons and wait until all other `role_id` keys in the dict match this `current_node_id`.

### C. Discord Interaction Handler (`cogs/event_cog.py`)
1. **The Lobby View**:
   - A message with buttons for each available role.
   - Click to join/leave that role.
   - "Start Game" button (only clickable by the host when `min_players` is met).
2. **The Turn View**:
   - Displays the node's public text (or asymmetric text if role matches).
   - If `decision_type == "group"`:
     - Render buttons representing the choices.
     - On click, store the vote and respond with an ephemeral confirmation: *"تم تسجيل تصويتك."*
     - Update the public message embed with a progress counter: *"الأصوات: (2/3)"*.
   - If `decision_type == "solo"`:
     - Render a single public button: `[ اتخاذ القرار الفردي لـ {Role_Title} ]`.
     - When clicked by the authorized player: Send the private choices inside an **ephemeral message**.
     - When clicked by other players: Show ephemeral: *"هذا الخيار خاص بـ {Role_Title} فقط."*
3. **NPC Messages**:
   - Post dialogue using the bot or webhooks to give NPCs a voice.

---

## 3. Checklist for Jules

- [ ] **Database**: Update `core/db.py` to add `multiplayer_sessions` table.
- [ ] **Models**: Update `engine/models.py` to add `MultiplayerSession` tracking schemas.
- [ ] **Manager**: Implement `engine/multiplayer_manager.py` with lobby, vote collections, and NPC trait solvers.
- [ ] **Discord UI**: Rewrite `cogs/event_cog.py` to handle the dynamic multiplayer lobby, vote counter updates, and ephemeral solo menu interactions.
- [ ] **Tests**: Create `scripts/test_mp_logic.py` to simulate a mock game session locally before deployment.
