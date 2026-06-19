# Nexus Multiplayer Design Specification (نظام اللعب الجماعي)

This document outlines the architecture, JSON schema, and game loop specifications for the Nexus RPG Multiplayer Engine.

---

## 1. Core Mechanics

The multiplayer engine supports cooperative and competitive branching RPG stories.

1. **Role-Based Play**: Each story defines a set of unique Roles. Real players select a role in the lobby. Any vacant roles are controlled by the Bot as NPCs.
2. **Hybrid Decision Types**:
   - **Group Decisions (`group_decision`)**: Resolved by majority vote in the public server channel.
   - **Solo/Secret Decisions (`solo_decision`)**: Ephemeral interactions targetable to a specific role. The result is only shown to that player, but its consequences affect the story.
3. **Asymmetric Information**: Displaying different narrative text blocks for the same node depending on the player's role.
4. **NPC Autonomy**: NPCs make decisions based on personality weights defined in the JSON. If an NPC votes, it prints dialogue in the channel justifying its choice.
5. **Synchronized Pacing**: A synchronization lock ensures that players on parallel tracks wait for each other at convergence nodes before proceeding.

---

## 2. JSON Schema Specification (`data/stories/`)

Multiplayer stories must follow the schema below. Filename format: `multi_{slug}.json`

### A. Top-Level Additions
```json
{
  "id": "multi_palace_betrayal",
  "title": "مؤامرة القصر",
  "summary": "قصة خيانة ومكائد جماعية...",
  "world": "الواقع البديل",
  "world_type": "alternate",
  "game_mode": "multi",
  "min_players": 2,
  "max_players": 3,
  "roles": {
    "prince_heir": {
      "title": "الأمير الوريث",
      "description": "يريد حماية العرش واستقرار المملكة.",
      "npc_traits": { "greedy": 0.2, "loyal": 0.8, "ruthless": 0.4 }
    },
    "bodyguard": {
      "title": "الحارس الشخصي",
      "description": "يحمل سراً قد يدمر الأمير.",
      "npc_traits": { "greedy": 0.4, "loyal": 0.9, "ruthless": 0.6 }
    },
    "spy": {
      "title": "الجاسوس المغترب",
      "description": "يسعى لإحداث فوضى وسرقة الختم.",
      "npc_traits": { "greedy": 0.9, "loyal": 0.1, "ruthless": 0.8 }
    }
  }
}
```

### B. Node-Level Additions
Nodes in a multiplayer story can be typed as `group_decision` or `solo_decision`.

#### 1) Group Decision Node
```json
"node_entrance": {
  "type": "group_decision",
  "text": {
    "default": "تقفون أمام البوابة المغلقة للقصر.",
    "asymmetric": {
      "spy": "تقفون أمام البوابة. تلمح مفتاح صيانة سري مخفي تحت التمثال الأيسر."
    }
  },
  "choices": [
    {
      "label": "تفجير البوابة",
      "next": "node_blown_gate",
      "sets_flag": "gate_destroyed",
      "npc_weights": { "ruthless": 0.8 }
    },
    {
      "label": "البحث عن آلية فتح",
      "next": "node_solved_gate",
      "npc_weights": { "loyal": 0.6 }
    }
  ],
  "npc_dialogues": {
    "spy": {
      "node_blown_gate": "يهمس الجاسوس: 'الضجة ستلفت الانتباه، ولكن لا وقت لدينا!'",
      "node_solved_gate": "يقول الجاسوس: 'دعوني أتفحص القفل أولاً...'"
    }
  }
}
```

#### 2) Solo Decision Node
```json
"node_poison_draft": {
  "type": "solo_decision",
  "assigned_to": "spy",
  "text": "أنت بمفردك الآن قرب كأس الأمير. السم في جيبك.",
  "choices": [
    {
      "label": "تسميم الكأس",
      "next": "node_poison_active",
      "sets_flag": "role:prince_heir:is_poisoned",
      "ephemeral_text": "سكبت السم ببطء في الكأس دون أن يراك أحد."
    },
    {
      "label": "التراجع",
      "next": "node_poison_ignored",
      "ephemeral_text": "قررت تأجيل خطتك."
    }
  ]
}
```

---

## 3. Game Loops & Synchronization

```
[ Lobby Setup ] ──> [ Role Selection ] ──> [ Node Resolution Loop ]
                                                    │
                                                    ▼
                                            [ decision_type? ]
                                            /              \
                                     (Group)                (Solo)
                                       /                      \
                     [ Collect Votes from All ]        [ Send Ephemeral to Target ]
                     [ Resolves by Majority   ]        [ Update Role-Scoped State ]
                                       \                      /
                                        ▼                    ▼
                                     [ Check if Convergence Point ]
                                     - If Yes: Wait for all players to arrive.
                                     - If No: Proceed to next node.
                                                    │
                                                    ▼
                                            [ Ending Node? ]
```

### Path Synchronization (التزامن)
When the story branches into solo/asymmetrical paths:
1. The engine tracks the current node of **each player** in the session.
2. If a node is marked as a **convergence point** (e.g. `is_convergence: true`), the player who arrives first is put in a `WAIT` state with a Discord status message: *"في انتظار بقية اللاعبين..."*
3. Once all players have caught up to this node, the engine displays the group text and resumes unified play.
