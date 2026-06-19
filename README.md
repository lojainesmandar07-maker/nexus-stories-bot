# The Nexus Bot (النكسس) — Story Branch

**The Nexus (النكسس)** is an Arabic-language Discord RPG bot where players navigate dark, interactive branching stories, make decisions that set flags, and earn endings representing moral verdicts on their choices.

This repository contains the bot codebase and the story catalog located in `data/stories/`.

---

## 🚀 How to Run the Bot

### Prerequisites
- Python 3.10+
- SQLite3

### Setup & Installation
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your Discord Bot Token and database settings.
3. Start the bot:
   ```bash
   python main.py
   ```

---

## ✍️ Story Writing & Contributing

Any AI assistant or human writer connecting to this repository must follow the official writing standards to maintain the bot's high quality bar.

### 📚 Documentation
- **[STORY_WRITING_GUIDE.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/docs/STORY_WRITING_GUIDE.md):** Complete narrative design rules, the Darkness Doctrine, and character guidelines. **Must-read before writing.**
- **[STORY_JSON_SCHEMA.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/docs/STORY_JSON_SCHEMA.md):** The technical JSON field specification, valid worlds, and theme catalog.
- **[STORY_EXAMPLES.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/docs/STORY_EXAMPLES.md):** Walkthrough and analysis of `solo_room_404.json` showing flags, branching, and pacing.

---

## 🛠️ Validation & Tooling

To ensure a new story doesn't break the bot engine and maintains the required depth, you must run the automated validation script before committing.

### Run Story Validation
```bash
# Validate a specific story
python scripts/validate_story.py data/stories/your_story.json

# Validate all stories in the catalog
python scripts/validate_story.py data/stories/

# Run validation in warn-only mode (softer checks during development)
python scripts/validate_story.py data/stories/ --warn-only
```

### View Story Statistics
To get a breakdown of node distribution, path lengths, death ratios, and flags:
```bash
# Get stats for a specific story
python scripts/story_stats.py data/stories/your_story.json

# Get stats for all stories
python scripts/story_stats.py data/stories/
```

For guidelines on making PRs and file naming conventions, see **[CONTRIBUTING.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/CONTRIBUTING.md)**.
