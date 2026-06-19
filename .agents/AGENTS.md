# The Nexus Bot (النكسس) — AI Agent Context

> This file provides context for AI coding agents (Jules AI, GitHub Copilot, Cursor, etc.) working on this repository.

## Project Overview

**The Nexus (النكسس)** is an Arabic-language Discord RPG bot that plays interactive branching stories. Players make choices that affect the narrative, set flags that gate future options, and reach different endings based on their accumulated decisions.

The bot is built with Python + discord.py and reads story content from JSON files in `data/stories/`.

## Architecture

```
stories_only_bot/
├── main.py              # Bot entry point
├── core/                # Bot configuration, database, category catalog
│   ├── bot.py           # Bot class and setup
│   ├── config.py        # Configuration management
│   ├── db.py            # SQLite database
│   ├── async_data.py    # Async data loading
│   └── category_catalog.py  # Valid world types and theme categories
├── engine/              # Story engine (parsing, state management)
│   ├── models.py        # Data models: Story, Scene, Choice, Perspective
│   ├── story_manager.py # Loads and resolves stories from JSON files
│   ├── solo_manager.py  # Solo play session management
│   └── event_manager.py # Multiplayer event management
├── cogs/                # Discord command handlers
│   ├── solo_cog.py      # Solo story commands
│   ├── event_cog.py     # Multiplayer event commands
│   └── admin_cog.py     # Admin commands
├── ui/                  # Discord UI components (embeds, views, buttons)
├── data/
│   ├── stories/         # ← Story JSON files go here
│   └── config.json      # Bot configuration
├── docs/                # Documentation
│   ├── STORY_WRITING_GUIDE.md   # ★ MUST READ: Complete story writing instructions
│   ├── STORY_JSON_SCHEMA.md     # Complete JSON schema reference
│   └── STORY_EXAMPLES.md        # Annotated example walkthrough
└── scripts/             # Tooling
    ├── validate_story.py        # ★ Run this to validate stories before committing
    └── story_stats.py           # Quick story statistics
```

## Critical Rules for AI Agents

### Rule 1: Follow the Writing Guide
**All story writing MUST follow `docs/STORY_WRITING_GUIDE.md`.** This is a comprehensive 1300+ line guide covering narrative design, Arabic style, node architecture, flag systems, ending design, pacing, and more. Read it completely before writing any story.

### Rule 2: Validate Before Committing
**All stories MUST pass `scripts/validate_story.py` before being committed.**
```bash
python scripts/validate_story.py data/stories/my_story.json
```
Fix all failures before submitting. Use `--warn-only` during development for a softer check.

### Rule 3: Story Content Language
- All story content (title, summary, text, choice labels, spine, flags) must be in **Arabic**
- All code, file names, and documentation must be in **English**
- Arabic text must be simple, clear, and readable by a 16-year-old Arabic speaker

### Rule 4: JSON Format
- Stories are JSON files placed in `data/stories/`
- File naming: `{world_type}_{descriptive_slug}.json` (e.g., `solo_room_404.json`, `fantasy_cursed_heir.json`)
- See `docs/STORY_JSON_SCHEMA.md` for the complete field reference
- The engine in `engine/story_manager.py` must be able to parse the story

### Rule 5: Quality Bar
Every story must meet these minimums:
- **30+ nodes** for short stories, **55+** for medium, **100+** for flagship
- **600+ lines** of formatted JSON
- **All flags must be functional** — every `sets_flag` must have a `requires_flag`, and vice versa
- **No trap nodes** — both choices must lead to different destinations
- **No death before 5 choices** from start
- **3+ breath nodes** for pacing
- **Every ending** must have flag-conditional callbacks and the retry message
- **A `spine` object** with all 6 fields (wound, lie, trigger, complication, revelation, verdict)

### Rule 6: Do Not Modify Engine Code for Stories
Stories are pure data (JSON files). Do not modify any Python code in `engine/`, `core/`, `cogs/`, or `ui/` to accommodate a story. If the JSON schema doesn't support what you need, flag it as a feature request.

### Rule 7: Valid World Types and Themes
Valid `world_type` values: `solo`, `fantasy`, `past`, `future`, `alternate`, `multi`
Valid `world` (Arabic) values: `القصص الفردية`, `الفانتازيا`, `الماضي`, `المستقبل`, `الواقع البديل`

Themes must match one of the categories defined in `core/category_catalog.py`.

## Workflow for Writing a New Story

1. Read `docs/STORY_WRITING_GUIDE.md` completely
2. Design the Story Spine (wound, lie, trigger, complication, revelation, verdict)
3. Complete the Flag Registry Table
4. Complete the Foreshadowing Map
5. Map the full node tree before writing
6. Write the story JSON following `docs/STORY_JSON_SCHEMA.md`
7. Run `python scripts/validate_story.py data/stories/your_story.json`
8. Fix all failures
9. Run `python scripts/story_stats.py data/stories/your_story.json` to verify stats
10. Place the file in `data/stories/` and update `data/stories/STORY_CATALOG.md`

## Existing Stories (Reference)

Check `data/stories/STORY_CATALOG.md` for the current catalog of stories with node counts and ending counts. Use existing stories as reference for format and quality expectations.

## Multiplayer System Design & Tasks

For coding agents working on the Multiplayer Engine:
1. **Multiplayer Design Spec**: See [docs/MULTIPLAYER_DESIGN.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/docs/MULTIPLAYER_DESIGN.md) for JSON schemas, role mappings, and synchronization specifications.
2. **Jules AI Tasks**: See [docs/JULES_MULTIPLAYER_IMPLEMENTATION.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/docs/JULES_MULTIPLAYER_IMPLEMENTATION.md) for the coding checklist, database modifications, and event manager blueprints.
