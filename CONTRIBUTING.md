# Contributing to The Nexus Stories

Thank you for contributing to The Nexus! To maintain the bot's high quality bar and ensure that stories parse correctly, all story contributions must adhere to the guidelines outlined in this document.

---

## 1. Naming Conventions

All story files must be placed in `data/stories/` and named according to the following template:
`{world_type}_{descriptive_slug}.json`

**Examples:**
- `solo_room_404.json`
- `fantasy_cursed_heir.json`
- `future_rented_memory.json`

Valid `world_type` values are: `solo`, `fantasy`, `past`, `future`, `alternate`, `multi`.

---

## 2. Technical Quality Bar

Before submitting a story, you must run the validation script:
```bash
python scripts/validate_story.py data/stories/your_story.json
```

To pass the quality check, a story must satisfy:
1.  **Valid JSON Format:** Well-formed JSON structure.
2.  **Required Top-Level Fields:** Must contain `id`, `title`, `summary`, `world`, `world_type`, `theme`, `game_mode`, `start_scene`, `spine`, and `nodes`.
3.  **Correct Spine Structure:** The `spine` object must have all 6 Arabic fields (`wound`, `lie`, `trigger`, `complication`, `revelation`, `verdict`).
4.  **No Trap Nodes:** Both choices in any node must lead to different destinations.
5.  **No Early Deaths:** No death endings can be reached in fewer than 5 choices from the start node.
6.  **Flag Integrity:** All flags must be fully functional. No orphaned flags (every set flag must be required somewhere, and vice versa).
7.  **Pacing Standards:** At least 3 breath nodes must exist, and there can be no run of 4+ escalation nodes in a row.
8.  **Ending Standards:** Every ending must have a retry message and implement flag-gated choices to act as moral verdicts.

---

## 3. Contribution Workflow

1.  **Read the Guides:** Ensure you are familiar with the **[STORY_WRITING_GUIDE.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/docs/STORY_WRITING_GUIDE.md)** and the **[STORY_JSON_SCHEMA.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/docs/STORY_JSON_SCHEMA.md)**.
2.  **Write the Story:** Generate the JSON structure.
3.  **Run Quality Checks:**
    - Run `python scripts/validate_story.py data/stories/your_story.json` to make sure it passes.
    - Run `python scripts/story_stats.py data/stories/your_story.json` to check path depth, death-to-survival ratios, and node type distributions.
4.  **Update Catalog:** Add your story to the `data/stories/STORY_CATALOG.md` (if applicable) with its title, theme, node count, and endings.
5.  **Submit PR:** Open a Pull Request on GitHub.

---

## 4. PR Checklist

- [ ] File is placed in `data/stories/` and named `{world_type}_{descriptive_slug}.json`.
- [ ] Story passes `python scripts/validate_story.py` with zero failures (warnings are allowed but should be minimized).
- [ ] The Arabic text is written in simple, clear grammar (readable by a 16-year-old).
- [ ] All choice labels are action verbs, under 40 characters, and do not start with questions (e.g. "هل").
- [ ] Good endings have a bittersweet tone and carry a real, named cost to Yusuf (or the protagonist).
- [ ] No engine Python code in `engine/` or `core/` was modified to accommodate the story.
