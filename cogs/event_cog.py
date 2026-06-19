import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from core.bot import StoryBot
from engine.multiplayer_manager import MultiplayerManager
from ui.embeds import EmbedBuilder

class RoleSelectView(discord.ui.View):
    def __init__(self, bot: StoryBot, session_id: str, story):
        super().__init__(timeout=None)
        self.bot = bot
        self.session_id = session_id
        self.story = story
        self.manager = bot.multiplayer_manager

        # Add a button for each role
        for role_id, role in story.roles.items():
            btn = discord.ui.Button(
                label=f"انضمام: {role.title}",
                custom_id=f"role_{role_id}",
                style=discord.ButtonStyle.primary
            )
            btn.callback = self.create_role_callback(role_id, role)
            self.add_item(btn)

        # Start button
        start_btn = discord.ui.Button(
            label="بدء اللعبة",
            custom_id="start_game",
            style=discord.ButtonStyle.success,
            row=2
        )
        start_btn.callback = self.start_game_callback
        self.add_item(start_btn)

    def create_role_callback(self, role_id, role):
        async def callback(interaction: discord.Interaction):
            user_id = str(interaction.user.id)
            success = self.manager.add_player(self.session_id, user_id, role_id)
            if success:
                await interaction.response.send_message(f"✅ انضممت بنجاح بدور: {role.title}", ephemeral=True)
                await self.update_lobby_message(interaction.message)
            else:
                await interaction.response.send_message(f"❌ هذا الدور محجوز أو أنت منضم بالفعل.", ephemeral=True)
        return callback

    async def start_game_callback(self, interaction: discord.Interaction):
        # We assume host check here could be added.
        # But we'll just check if minimum players reached.
        session = self.manager.active_sessions.get(self.session_id)
        if not session:
            return

        current_players = len(session.players)
        if current_players < self.story.min_players:
            await interaction.response.send_message(f"❌ يجب أن ينضم {self.story.min_players} لاعبين على الأقل للبدء.", ephemeral=True)
            return

        await interaction.response.send_message("✅ جاري بدء اللعبة...", ephemeral=False)

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        await self.manager.start_session(self.session_id, self.story)

        # Start the loop
        self.bot.loop.create_task(self.run_turn(interaction.channel))

    async def update_lobby_message(self, message: discord.Message):
        session = self.manager.active_sessions.get(self.session_id)
        if not session: return

        players_text = []
        for uid, rid in session.players.items():
            role = self.story.roles.get(rid)
            players_text.append(f"<@{uid}>: {role.title}")

        text = "اللاعبون المنضمون:\n" + "\n".join(players_text) if players_text else "لا أحد بعد."
        embed = discord.Embed(title=f"غرفة الانتظار: {self.story.title}", description=text)
        await message.edit(embed=embed)

    async def run_turn(self, channel):
        session = self.manager.active_sessions.get(self.session_id)
        if not session or session.status != "active": return

        # We assume group is synced at this point. Take arbitrary role's node.
        sample_role = list(session.players.values())[0]
        current_node_id = session.current_node_states.get(sample_role)
        scene = self.story.get_scene(current_node_id)

        if not scene:
            await channel.send("خطأ: المشهد غير موجود.")
            self.manager.end_session(self.session_id)
            return

        # Clear votes
        self.manager.clear_votes(self.session_id)

        if scene.type == "solo_decision":
            await self.handle_solo_decision(channel, scene, session)
        else:
            await self.handle_group_decision(channel, scene, session)

    async def handle_solo_decision(self, channel, scene, session):
        target_role = scene.assigned_to
        role_obj = self.story.roles.get(target_role)
        target_uid = self.manager.get_user_by_role(self.session_id, target_role)

        is_npc = target_uid and self.manager.is_npc(target_uid)

        view = discord.ui.View()

        if not is_npc:
            btn = discord.ui.Button(label=f"اتخاذ القرار الفردي لـ {role_obj.title}", style=discord.ButtonStyle.primary)

            async def open_solo_menu(interaction: discord.Interaction):
                if str(interaction.user.id) != target_uid:
                    await interaction.response.send_message(f"❌ هذا الخيار خاص بـ {role_obj.title} فقط.", ephemeral=True)
                    return

                solo_view = discord.ui.View()
                for i, choice in enumerate(scene.choices):
                    c_btn = discord.ui.Button(label=choice.text, custom_id=f"choice_{i}")

                    async def make_choice(i_cb: discord.Interaction):
                        idx = int(i_cb.data['custom_id'].split('_')[1])
                        c = scene.choices[idx]
                        await i_cb.response.send_message(c.ephemeral_text or "تم اتخاذ القرار.", ephemeral=True)

                        # Apply decision
                        await self.apply_decision(c, target_role, channel)

                    c_btn.callback = make_choice
                    solo_view.add_item(c_btn)

                await interaction.response.send_message(scene.text, view=solo_view, ephemeral=True)

            btn.callback = open_solo_menu
            view.add_item(btn)

        embed = discord.Embed(title=scene.title, description=scene.text)
        msg = await channel.send(embed=embed, view=view if not is_npc else None)

        if is_npc:
            # Execute NPC Solo
            await asyncio.sleep(random.uniform(2.0, 5.0))
            idx = self.manager.calculate_npc_vote(role_obj, scene.choices)
            choice = scene.choices[idx]
            dialogue = scene.npc_dialogues.get(target_role, {}).get(choice.next_scene)
            if dialogue:
                await channel.send(f"💬 {dialogue}")
            await self.apply_decision(choice, target_role, channel)

    async def apply_decision(self, choice, role_id, channel):
        session = self.manager.active_sessions.get(self.session_id)

        if choice.sets_flag:
            session.flags.append(choice.sets_flag)

        await self.manager.advance_node(self.session_id, role_id, choice.next_scene, self.story)

        # Check convergence
        if self.manager.is_convergence_waiting(self.session_id, choice.next_scene):
            # Tell user waiting
            pass
        else:
            # Proceed all
            # Hacky sync logic for MVP: just advance everyone
            for r_id in session.current_node_states.keys():
                if r_id != role_id:
                    session.current_node_states[r_id] = choice.next_scene

            await self.manager._persist_session(session)
            self.bot.loop.create_task(self.run_turn(channel))

    async def handle_group_decision(self, channel, scene, session):
        # We show public view with voting buttons
        view = discord.ui.View()

        for i, choice in enumerate(scene.choices):
            btn = discord.ui.Button(label=choice.text, custom_id=f"vote_{i}")

            async def vote_callback(interaction: discord.Interaction):
                user_id = str(interaction.user.id)
                role_id = self.manager.get_role_by_user(self.session_id, user_id)
                if not role_id:
                    await interaction.response.send_message("❌ أنت لست لاعباً في هذا الحدث.", ephemeral=True)
                    return

                idx = int(interaction.data['custom_id'].split('_')[1])
                self.manager.register_vote(self.session_id, user_id, idx)
                await interaction.response.send_message("✅ تم تسجيل تصويتك.", ephemeral=True)

                # Check if all voted
                if self.manager.has_everyone_voted(self.session_id):
                    await self.resolve_group(channel, scene)

            btn.callback = vote_callback
            view.add_item(btn)

        embed = discord.Embed(title=scene.title, description=scene.text)
        await channel.send(embed=embed, view=view)

        # Trigger NPCs
        self.bot.loop.create_task(self.run_npcs_and_check(channel, scene))

    async def run_npcs_and_check(self, channel, scene):
        await self.manager.execute_npc_turns(self.session_id, self.story, channel)
        if self.manager.has_everyone_voted(self.session_id):
            await self.resolve_group(channel, scene)

    async def resolve_group(self, channel, scene):
        winner_idx = self.manager.resolve_group_vote(self.session_id, self.story)
        if winner_idx is None: return

        choice = scene.choices[winner_idx]
        await channel.send(f"🥁 الأغلبية اختارت: **{choice.text}**")

        session = self.manager.active_sessions.get(self.session_id)
        if choice.sets_flag:
            session.flags.append(choice.sets_flag)

        for role_id in session.current_node_states.keys():
            session.current_node_states[role_id] = choice.next_scene

        await self.manager._persist_session(session)

        next_scene = self.story.get_scene(choice.next_scene)
        if not next_scene or next_scene.is_ending:
            await channel.send("🏁 انتهت القصة!")
            self.manager.end_session(self.session_id)
        else:
            await asyncio.sleep(2)
            self.bot.loop.create_task(self.run_turn(channel))


class EventCog(commands.Cog):
    def __init__(self, bot: StoryBot):
        self.bot = bot
        # Ensure the bot has a multiplayer manager attached.
        if not hasattr(self.bot, 'multiplayer_manager'):
            self.bot.multiplayer_manager = MultiplayerManager(bot)

    async def multi_story_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        stories = self.bot.story_manager.get_stories_by_mode("multi").values()
        needle = (current or "").strip().casefold()
        out: list[app_commands.Choice[str]] = []
        for story in stories:
            sid = str(story.id)
            label = f"{story.title} ({sid})"
            if needle and needle not in label.casefold():
                continue
            out.append(app_commands.Choice(name=label[:100], value=sid))
            if len(out) >= 25:
                break
        return out

    @app_commands.command(name="حدث", description="بدء حدث قصة تفاعلي جماعي")
    @app_commands.describe(story_ref="اسم القصة الجماعية أو معرّفها")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.autocomplete(story_ref=multi_story_autocomplete)
    async def start_event(self, interaction: discord.Interaction, story_ref: str):
        await interaction.response.defer(ephemeral=False)

        story = self.bot.story_manager.resolve_story(story_ref, game_mode="multi")
        if not story:
            await interaction.followup.send(f"❌ لم يتم العثور على قصة جماعية مطابقة.")
            return

        session_id = self.bot.multiplayer_manager.create_session(
            channel_id=interaction.channel.id,
            story_id=str(story.id),
            host_id=str(interaction.user.id)
        )

        view = RoleSelectView(self.bot, session_id, story)
        embed = discord.Embed(title=f"غرفة الانتظار: {story.title}", description="اللاعبون المنضمون:\nلا أحد بعد.")

        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="إيقاف", description="إيقاف الحدث التفاعلي الحالي")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stop_event(self, interaction: discord.Interaction):
        session = self.bot.multiplayer_manager.get_session_by_channel(interaction.channel.id)
        if not session:
            await interaction.response.send_message("❌ لا يوجد حدث جارٍ في هذه القناة.", ephemeral=True)
            return

        self.bot.multiplayer_manager.end_session(session.session_id)
        await interaction.response.send_message("✅ تم إيقاف الحدث الجماعي.", ephemeral=False)

async def setup(bot: StoryBot):
    await bot.add_cog(EventCog(bot))
