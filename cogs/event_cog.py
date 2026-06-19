import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import random
from typing import Optional, Dict, List, Any
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
                embed = discord.Embed(
                    title=f"🎭 تم اختيار دورك: {role.title}",
                    description=(
                        f"**📖 خلفية عن شخصيتك:**\n{role.description}\n\n"
                        f"📊 **صفات الشخصية:**\n"
                        f"• 🛡️ الرغبة في الحماية والإنقاذ: `{int(role.npc_traits.get('protective', 0.5) * 100)}%`\n"
                        f"• 👁️ الحذر والمراقبة المستمرة: `{int(role.npc_traits.get('cautious', 0.5) * 100)}%`\n"
                        f"• 🔍 الشك وعدم الثقة بالآخرين: `{int(role.npc_traits.get('suspicious', 0.5) * 100)}%`"
                    ),
                    color=discord.Color.gold()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await self.update_lobby_message(interaction.message)
            else:
                await interaction.response.send_message(f"❌ هذا الدور محجوز أو أنت منضم بالفعل.", ephemeral=True)
        return callback

    async def start_game_callback(self, interaction: discord.Interaction):
        session = self.manager.active_sessions.get(self.session_id)
        if not session:
            await interaction.response.send_message("❌ لم يتم العثور على الجلسة.", ephemeral=True)
            return

        # Enforce host check
        if str(interaction.user.id) != session.host_id:
            await interaction.response.send_message("❌ بدء اللعبة متاح فقط لمستضيف الجلسة.", ephemeral=True)
            return

        current_players = len(session.players)
        if current_players < self.story.min_players:
            await interaction.response.send_message(f"❌ يجب أن ينضم {self.story.min_players} لاعبين على الأقل للبدء.", ephemeral=True)
            return

        await interaction.response.send_message("✅ جاري بدء اللعبة...", ephemeral=False)

        # Disable buttons
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        await self.manager.start_session(self.session_id, self.story)

        # Start the loop
        asyncio.create_task(self.run_turn(interaction.channel))

    async def update_lobby_message(self, message: discord.Message):
        session = self.manager.active_sessions.get(self.session_id)
        if not session: return

        players_text = []
        for uid, rid in session.players.items():
            role = self.story.roles.get(rid)
            players_text.append(f"<@{uid}>: {role.title}")

        text = "اللاعبون المنضمون:\n" + "\n".join(players_text) if players_text else "لا أحد بعد."
        embed = discord.Embed(title=f"غرفة الانتظار: {self.story.title}", description=text)
        try:
            await message.edit(embed=embed)
        except Exception:
            pass

    async def run_turn(self, channel):
        session = self.manager.active_sessions.get(self.session_id)
        if not session or session.status != "active": return

        # We assume group is synced at this point. Take arbitrary role's node.
        sample_role = list(session.players.values())[0]
        current_node_id = session.current_node_states.get(sample_role)
        scene = self.story.get_scene(current_node_id)

        if not scene:
            await channel.send("❌ خطأ: المشهد غير موجود.")
            self.manager.end_session(self.session_id)
            return

        # Announce the game start if on the start node
        if current_node_id == self.story.start_scene and not getattr(session, "_intro_announced", False):
            session._intro_announced = True
            players_intro = []
            for uid, rid in session.players.items():
                role_info = self.story.roles.get(rid)
                role_title = role_info.title if role_info else rid
                players_intro.append(f"• <@{uid}> في دور: **{role_title}**")

            intro_embed = discord.Embed(
                title=f"🎭 تبدأ الآن قصة: {self.story.title}",
                description=(
                    f"✨ **الملخص:**\n{self.story.description}\n\n"
                    f"👥 **توزيع الأدوار:**\n" + "\n".join(players_intro) +
                    f"\n\n⚠️ **توجيهات هامة للعب:**\n"
                    f"• هذه قصة تفاعلية جماعية؛ ستتخذون القرارات معاً بالتصويت.\n"
                    f"• بعض المشاهد تحتوي على **معلومات ومهمات سرية** لا يعرفها غيرك! "
                    f"عندما يظهر زر **`👁️ معلوماتي السرية`** بالأسفل، اضغط عليه فوراً لقراءة أسرار دورك ومهمتك."
                ),
                color=discord.Color.gold()
            )
            await channel.send(embed=intro_embed)
            await asyncio.sleep(2)

        # Clear votes
        self.manager.clear_votes(self.session_id)

        # Start voting timeout task (default to 30.0s)
        asyncio.create_task(self.voting_timeout_task(channel, current_node_id))

        if scene.type == "solo_decision":
            await self.handle_solo_decision(channel, scene, session)
        else:
            await self.handle_group_decision(channel, scene, session)

    async def voting_timeout_task(self, channel, node_id, timeout=30.0):
        await asyncio.sleep(timeout)
        session = self.manager.active_sessions.get(self.session_id)
        if not session or session.status != "active":
            return

        # Check if they are still on the same node
        sample_role = list(session.players.values())[0]
        current_node_id = session.current_node_states.get(sample_role)
        if current_node_id == node_id:
            votes = self.manager.session_votes.get(self.session_id, {})
            scene = self.story.get_scene(node_id)
            if not scene:
                return

            if scene.type == "solo_decision":
                # Pick a random choice for solo decision if none made
                await channel.send("⏳ انتهى الوقت المخصص لاتخاذ القرار الفردي! تم اختيار خيار عشوائي للاستمرار.")
                if scene.choices:
                    choice = random.choice(scene.choices)
                    await self.apply_decision(choice, scene.assigned_to, channel)
            else:
                # Group decision
                if votes:
                    await channel.send("⏳ انتهى وقت التصويت! سيتم اعتماد الأصوات الحالية.")
                    await self.resolve_group(channel, scene)
                else:
                    await channel.send("⏳ انتهى وقت التصويت ولم يصوت أحد! تم اختيار خيار عشوائي للاستمرار.")
                    if scene.choices:
                        choice = random.choice(scene.choices)
                        await self.advance_story(choice, channel)

    def build_turn_embed(self, scene, session):
        description_text = scene.text
        if scene.asymmetric_text:
            description_text += (
                "\n\n⚠️ **تنبيه:** يحتوي هذا المشهد على **معلومات أو مهمة سرية مخصصة لدورك!** "
                "اضغط على زر **`👁️ معلوماتي السرية`** في الأسفل لقراءتها."
            )

        embed = discord.Embed(
            title=scene.title if (scene.title and scene.title != scene.id) else "المشهد الحالي",
            description=description_text,
            color=discord.Color.blue()
        )
        if scene.image_url:
            embed.set_image(url=scene.image_url)

        # Add vote progress field
        votes = self.manager.session_votes.get(session.session_id, {})
        voters_text = []
        for uid, rid in session.players.items():
            role = self.story.roles.get(rid)
            role_name = role.title if role else rid
            status = "🟢 تم التصويت" if rid in votes else "🟡 يفكر الآن..."
            if self.manager.is_npc(uid):
                voters_text.append(f"• **{role_name}** (البوت): {status}")
            else:
                voters_text.append(f"• <@{uid}> (**{role_name}**): {status}")

        embed.add_field(
            name=f"🗳️ الأصوات المسجلة ({len(votes)}/{len(session.players)})",
            value="\n".join(voters_text) if voters_text else "لا يوجد لاعبين.",
            inline=False
        )

        embed.set_footer(text=f"معرف الجلسة: {session.session_id} | اختر زرًا أدناه للتصويت.")
        return embed

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

                # Filter choices based on flags
                filtered_choices = [c for c in scene.choices if not c.requires_flag or c.requires_flag in session.flags]
                if not filtered_choices:
                    filtered_choices = scene.choices

                for i, choice in enumerate(filtered_choices):
                    orig_idx = scene.choices.index(choice)
                    c_btn = discord.ui.Button(label=choice.text, custom_id=f"choice_{orig_idx}")

                    async def make_choice(i_cb: discord.Interaction):
                        idx = int(i_cb.data['custom_id'].split('_')[1])
                        c = scene.choices[idx]
                        await i_cb.response.send_message(c.ephemeral_text or "تم اتخاذ القرار.", ephemeral=True)
                        await self.apply_decision(c, target_role, channel)

                    c_btn.callback = make_choice
                    solo_view.add_item(c_btn)

                # Show asymmetric text for that role
                await interaction.response.send_message(scene.get_text_for_role(target_role), view=solo_view, ephemeral=True)

            btn.callback = open_solo_menu
            view.add_item(btn)

        embed = discord.Embed(
            title=scene.title if (scene.title and scene.title != scene.id) else "قرار فردي",
            description=f"يقوم **{role_obj.title}** باتخاذ قرار فردي الآن..." if not is_npc else f"يقوم **{role_obj.title}** (البوت) باتخاذ قرار فردي...",
            color=discord.Color.orange()
        )
        if scene.image_url:
            embed.set_image(url=scene.image_url)

        try:
            await channel.send(embed=embed, view=view if not is_npc else None)
        except Exception as e:
            print(f"Error sending solo decision message: {e}")

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
        await self.advance_story(choice, channel)

    async def advance_story(self, choice, channel):
        session = self.manager.active_sessions.get(self.session_id)
        if not session:
            return

        if choice.sets_flag:
            session.flags.append(choice.sets_flag)

        # Synchronize all players to the next scene
        for r_id in session.current_node_states.keys():
            session.current_node_states[r_id] = choice.next_scene

        await self.manager._persist_session(session)

        next_scene = self.story.get_scene(choice.next_scene)
        if not next_scene or next_scene.is_ending:
            if next_scene:
                embed = discord.Embed(
                    title=next_scene.title if next_scene.title != next_scene.id else "النهاية",
                    description=next_scene.text,
                    color=discord.Color.dark_red()
                )
                if next_scene.image_url:
                    embed.set_image(url=next_scene.image_url)
                await channel.send(embed=embed)
            await channel.send("🏁 انتهت القصة!")
            self.manager.end_session(self.session_id)
        else:
            await asyncio.sleep(2)
            asyncio.create_task(self.run_turn(channel))

    async def handle_group_decision(self, channel, scene, session):
        # We show public view with voting buttons
        view = discord.ui.View()

        # Filter choices based on flags
        filtered_choices = [c for c in scene.choices if not c.requires_flag or c.requires_flag in session.flags]
        if not filtered_choices:
            filtered_choices = scene.choices

        for i, choice in enumerate(filtered_choices):
            orig_idx = scene.choices.index(choice)
            btn = discord.ui.Button(label=choice.text, custom_id=f"vote_{orig_idx}")

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
                else:
                    # Update progress embed
                    try:
                        new_embed = self.build_turn_embed(scene, session)
                        await interaction.message.edit(embed=new_embed)
                    except Exception as e:
                        print(f"Error editing message for vote progress: {e}")

            btn.callback = vote_callback
            view.add_item(btn)

        # Add asymmetric secret info button if defined
        if scene.asymmetric_text:
            secret_btn = discord.ui.Button(
                label="👁️ معلوماتي السرية", 
                style=discord.ButtonStyle.secondary, 
                custom_id="reveal_secret",
                row=1
            )
            
            async def reveal_secret_callback(interaction: discord.Interaction):
                user_id = str(interaction.user.id)
                role_id = self.manager.get_role_by_user(self.session_id, user_id)
                if not role_id:
                    await interaction.response.send_message("❌ أنت لست لاعباً في هذا الحدث.", ephemeral=True)
                    return
                
                custom_text = scene.get_text_for_role(role_id)
                if custom_text == scene.text:
                    await interaction.response.send_message("لا توجد معلومات إضافية سرية لدورك في هذا المشهد.", ephemeral=True)
                else:
                    await interaction.response.send_message(f"📜 **معلومات دورك السرية:**\n\n{custom_text}", ephemeral=True)
            
            secret_btn.callback = reveal_secret_callback
            view.add_item(secret_btn)

        embed = self.build_turn_embed(scene, session)
        try:
            await channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error sending group decision message: {e}")
            return

        # Trigger NPCs
        asyncio.create_task(self.run_npcs_and_check(channel, scene))

    async def run_npcs_and_check(self, channel, scene):
        await self.manager.execute_npc_turns(self.session_id, self.story, channel)
        if self.manager.has_everyone_voted(self.session_id):
            await self.resolve_group(channel, scene)

    async def resolve_group(self, channel, scene):
        if not self.manager.start_resolution(self.session_id):
            return

        try:
            winner_idx = self.manager.resolve_group_vote(self.session_id, self.story)
            if winner_idx is None: return

            choice = scene.choices[winner_idx]
            await channel.send(f"🥁 الأغلبية اختارت: **{choice.text}**")
            await self.advance_story(choice, channel)
        finally:
            self.manager.finish_resolution(self.session_id)


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
