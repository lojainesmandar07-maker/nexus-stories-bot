import discord
import os
import json
from discord.ext import commands
from engine.story_manager import StoryManager
from engine.event_manager import EventManager


class StoryBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True

        # This bot currently uses slash/app commands only.
        # Using mention-only prefix avoids requiring privileged message content intent.
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

        self.story_manager = StoryManager()
        self.event_manager = EventManager(self, self.story_manager)

    async def _get_intent_diagnostics(self) -> tuple[list[str], list[str]]:
        required_privileged = {}
        optional_privileged = {
            "members": "not required",
            "presences": "not required",
            "message_content": "not required (slash commands + components only)",
        }

        missing_required: list[str] = []
        notes: list[str] = []

        try:
            app_info = await self.application_info()
            flags = app_info.flags
        except Exception as e:
            notes.append(f"Could not fetch application flags for intent diagnostics: {e}")
            return missing_required, notes

        flag_values = {
            "members": bool(getattr(flags, "gateway_guild_members", False) or getattr(flags, "gateway_guild_members_limited", False)),
            "presences": bool(getattr(flags, "gateway_presence", False) or getattr(flags, "gateway_presence_limited", False)),
            "message_content": bool(getattr(flags, "gateway_message_content", False) or getattr(flags, "gateway_message_content_limited", False)),
        }

        for intent_name, reason in required_privileged.items():
            if getattr(self.intents, intent_name, False) and not flag_values[intent_name]:
                missing_required.append(
                    f"- {intent_name}: enabled in code but disabled in Discord Developer Portal ({reason})"
                )

        for intent_name, reason in optional_privileged.items():
            if getattr(self.intents, intent_name, False) and not flag_values[intent_name]:
                notes.append(f"- {intent_name}: enabled in code but disabled in portal ({reason})")

        return missing_required, notes

    async def setup_hook(self):
        missing_required_intents, _ = await self._get_intent_diagnostics()
        if missing_required_intents:
            joined = "\n".join(missing_required_intents)
            raise RuntimeError(
                "Startup aborted: privileged gateway intent mismatch detected.\n"
                f"{joined}\n"
                "Enable the required intent(s) in Discord Developer Portal -> Bot -> Privileged Gateway Intents."
            )

        # Consolidated database initialization before loading cogs
        from core.db import init_db
        await init_db()

        # Re-register persistent views BEFORE loading cogs
        from ui.listing_view import SoloLibraryView, MultiLibraryView
        from ui.world_browser import (
            WorldBrowserPersistentRouter,
            WorldSelectView,
        )

        self.add_view(SoloLibraryView({}, timeout=None))
        self.add_view(MultiLibraryView({}, timeout=None))

        # Register world-browser persistent handlers once.
        self._world_browser_router = WorldBrowserPersistentRouter()
        self.add_view(WorldSelectView())

        # Load cogs here. Keep startup resilient: one broken extension should not crash the bot.
        extensions = [
            "cogs.event_cog",
            "cogs.solo_cog",
            "cogs.admin_cog",
        ]
        loaded_extensions = []
        failed_extensions = []

        for extension in extensions:
            try:
                await self.load_extension(extension)
                loaded_extensions.append(extension)
            except Exception as e:
                failed_extensions.append((extension, str(e)))
                print(f"Failed to load extension {extension}: {e}")

        # Sync commands (environment-driven policy with backoff/cadence guards)
        from core.config import GUILD_ID
        import time

        sync_mode = os.getenv("COMMAND_SYNC_MODE", "dev" if GUILD_ID else "prod").strip().lower()
        global_sync_enabled = os.getenv("ENABLE_GLOBAL_COMMAND_SYNC", "false").strip().lower() in {"1", "true", "yes", "on"}
        global_sync_interval_seconds = int(os.getenv("GLOBAL_COMMAND_SYNC_INTERVAL_SECONDS", "21600"))
        sync_state_path = "data/command_sync_state.json"

        def load_sync_state() -> dict:
            try:
                if os.path.exists(sync_state_path):
                    with open(sync_state_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                print(f"[Sync] Failed reading sync state, using defaults: {e}")
            return {}

        def save_sync_state(state: dict) -> None:
            try:
                os.makedirs(os.path.dirname(sync_state_path), exist_ok=True)
                with open(sync_state_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[Sync] Failed writing sync state: {e}")

        async def guarded_sync(sync_scope: str, sync_call):
            try:
                synced = await sync_call()
                print(f"[Sync] Synced {sync_scope} commands ({len(synced)} commands).")
                state = load_sync_state()
                state["last_successful_sync_at"] = int(time.time())
                state["last_successful_sync_scope"] = sync_scope
                save_sync_state(state)
            except discord.HTTPException as e:
                retry_after = getattr(e, "retry_after", None)
                if retry_after is not None:
                    print(f"[Sync] Sync rate-limited for {sync_scope}; retry_after={retry_after}s. Startup continues.")
                else:
                    print(f"[Sync] HTTP sync failure for {sync_scope}: {e}. Startup continues.")
            except Exception as e:
                print(f"[Sync] Unexpected sync failure for {sync_scope}: {e}. Startup continues.")

        if sync_mode == "dev":
            if GUILD_ID:
                guild_ids = [gid.strip() for gid in str(GUILD_ID).split(",") if gid.strip()]
                for gid in guild_ids:
                    guild = discord.Object(id=int(gid))
                    self.tree.copy_global_to(guild=guild)
                    await guarded_sync(f"guild {gid}", lambda: self.tree.sync(guild=guild))
            else:
                print("[Sync] Skipped sync: COMMAND_SYNC_MODE=dev but GUILD_ID is not set.")
        else:
            if global_sync_enabled:
                await guarded_sync("global", self.tree.sync)
            else:
                print("[Sync] Skipped global sync: ENABLE_GLOBAL_COMMAND_SYNC is false.")

        print(f"Bot setup complete. Loaded {len(loaded_extensions)}/{len(extensions)} extensions.")
        if failed_extensions:
            print("Failed extensions:")
            for extension, error in failed_extensions:
                print(f"- {extension}: {error}")


    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            router = getattr(self, "_world_browser_router", None)
            if router and await router.handle_component_interaction(interaction):
                return

    async def on_application_command_error(self, interaction: discord.Interaction, error):
        msg = "⚠️ حدث خطأ غير متوقع، يرجى المحاولة لاحقاً."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass
        import traceback
        print(f"[ERROR] {traceback.format_exc()}")

    # Welcoming members has been removed since personality tests and setup configurations are deprecated.

    async def on_ready(self):
        print(f"Logged in as {self.user.name} (ID: {self.user.id})")
        print(f"Gateway intents: guilds={self.intents.guilds}, members={self.intents.members}, message_content={self.intents.message_content}, presences={self.intents.presences}")
        missing_required, notes = await self._get_intent_diagnostics()
        if missing_required:
            print("⚠️ Missing required privileged intent grants:")
            for issue in missing_required:
                print(issue)
            print("⚠️ Fix in Developer Portal: Applications -> [Your App] -> Bot -> Privileged Gateway Intents.")
        elif notes:
            print("Intent diagnostics:")
            for note in notes:
                print(note)
        print("Ready to run interactive stories!")
