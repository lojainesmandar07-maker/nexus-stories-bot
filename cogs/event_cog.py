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
        self.active_timeout_tasks = {}

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

        # Clean up done timeout tasks
        self.active_timeout_tasks = {nid: t for nid, t in self.active_timeout_tasks.items() if not t.done()}

        # Group players (roles) by their current node states
        active_nodes = {}
        for role_id, node_id in session.current_node_states.items():
            if node_id not in active_nodes:
                active_nodes[node_id] = []
            active_nodes[node_id].append(role_id)

        # Process each active node
        for node_id, roles_at_node in active_nodes.items():
            scene = self.story.get_scene(node_id)
            if not scene:
                continue

            # Announce the game start if on the start node
            if node_id == self.story.start_scene and not getattr(session, "_intro_announced", False):
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

            # Check if this scene is a convergence point
            if scene.is_convergence:
                total_roles = set(self.story.roles.keys())
                roles_here = set(roles_at_node)
                if not total_roles.issubset(roles_here):
                    # Some roles have not arrived yet. Display waiting status
                    if not getattr(session, f"_wait_announced_{node_id}", False):
                        setattr(session, f"_wait_announced_{node_id}", True)
                        waiting_roles_names = [self.story.roles[r].title for r in roles_here]
                        missing_roles_names = [self.story.roles[r].title for r in total_roles if r not in roles_here]
                        
                        waiting_str = ", ".join(waiting_roles_names)
                        missing_str = ", ".join(missing_roles_names)
                        
                        embed = discord.Embed(
                            title="⏳ في انتظار بقية اللاعبين",
                            description=(
                                f"وصل كل من: **{waiting_str}** إلى نقطة تلاقي المسارات.\n"
                                f"في انتظار وصول: **{missing_str}** للمتابعة معاً."
                            ),
                            color=discord.Color.light_grey()
                        )
                        await channel.send(embed=embed)
                    continue
                else:
                    if hasattr(session, f"_wait_announced_{node_id}"):
                        delattr(session, f"_wait_announced_{node_id}")

            # Start voting timeout task
            self.manager.clear_votes(self.session_id, node_id)
            
            if node_id in self.active_timeout_tasks:
                old_task = self.active_timeout_tasks.pop(node_id)
                if not old_task.done():
                    old_task.cancel()
            
            timeout = getattr(scene, "voting_timeout", None) or getattr(self.story, "voting_timeout", 30.0)
            self.active_timeout_tasks[node_id] = asyncio.create_task(self.voting_timeout_task(channel, node_id, timeout=timeout))

            if scene.type == "solo_decision":
                await self.handle_solo_decision(channel, scene, session)
            else:
                await self.handle_group_decision(channel, scene, session, roles_at_node)

    async def voting_timeout_task(self, channel, node_id, timeout=30.0):
        await asyncio.sleep(timeout)
        session = self.manager.active_sessions.get(self.session_id)
        if not session or session.status != "active":
            return

        # Group players (roles) by their current node states to see who is at this node
        active_nodes = {}
        for role_id, n_id in session.current_node_states.items():
            if n_id not in active_nodes:
                active_nodes[n_id] = []
            active_nodes[n_id].append(role_id)

        roles_at_node = active_nodes.get(node_id, [])
        if not roles_at_node:
            return

        votes = self.manager.session_votes.get(self.session_id, {})
        scene = self.story.get_scene(node_id)
        if not scene:
            return

            if scene.type == "solo_decision":
                # Pick a random choice for solo decision if none made
                await channel.send("⏳ انتهى الوقت المخصص لاتخاذ القرار الفردي! تم اختيار خيار عشوائي للاستمرار.")
                if scene.choices:
                    choice = random.choice(scene.choices)
                    await self.apply_decision(choice, scene.assigned_to, channel, source_node_id=node_id)
            else:
                # Group decision
                if votes:
                    await channel.send("⏳ انتهى وقت التصويت! سيتم اعتماد الأصوات الحالية.")
                    await self.resolve_group(channel, scene, roles_at_node)
                else:
                    await channel.send("⏳ انتهى وقت التصويت ولم يصوت أحد! تم اختيار خيار عشوائي للاستمرار.")
                    if scene.choices:
                        choice = random.choice(scene.choices)
                        await self.advance_story(choice, channel, roles_at_node, source_node_id=node_id)

    def build_turn_embed(self, scene, session, roles_at_node=None):
        from engine.story_manager import resolve_conditional_text
        description_text = resolve_conditional_text(scene.text, session.flags)
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
        votes = {rid: v for rid, v in self.manager.session_votes.get(session.session_id, {}).items() if v.node_id == scene.id}
        voters_text = []
        allowed_roles = set(roles_at_node) if roles_at_node else set(session.players.values())

        for uid, rid in session.players.items():
            if rid not in allowed_roles:
                continue
            role = self.story.roles.get(rid)
            role_name = role.title if role else rid
            status = "🟢 تم التصويت" if rid in votes else "🟡 يفكر الآن..."
            if self.manager.is_npc(uid):
                voters_text.append(f"• **{role_name}** (البوت): {status}")
            else:
                voters_text.append(f"• <@{uid}> (**{role_name}**): {status}")

        embed.add_field(
            name=f"🗳️ الأصوات المسجلة ({len(votes)}/{len(allowed_roles)})",
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
                        await self.apply_decision(c, target_role, channel, source_node_id=scene.id)

                    c_btn.callback = make_choice
                    solo_view.add_item(c_btn)

                # Show asymmetric text for that role
                from engine.story_manager import resolve_conditional_text
                resolved_target_text = resolve_conditional_text(scene.get_text_for_role(target_role), session.flags)
                await interaction.response.send_message(resolved_target_text, view=solo_view, ephemeral=True)

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
                await self.manager.send_npc_dialogue_via_webhook(self.session_id, target_role, dialogue, channel, self.story)
            await self.apply_decision(choice, target_role, channel, source_node_id=scene.id)

    async def apply_decision(self, choice, role_id, channel, source_node_id=None):
        await self.advance_story(choice, channel, [role_id], source_node_id=source_node_id)

    async def advance_story(self, choice, channel, target_roles=None, source_node_id=None):
        session = self.manager.active_sessions.get(self.session_id)
        if not session:
            return

        # Cancel the active timeout task for this node
        if source_node_id and source_node_id in self.active_timeout_tasks:
            task = self.active_timeout_tasks.pop(source_node_id)
            if not task.done():
                task.cancel()

        if choice.sets_flag:
            session.flags.append(choice.sets_flag)

        # Synchronize only target players to the next scene
        roles_to_advance = target_roles if target_roles is not None else list(session.current_node_states.keys())
        for r_id in roles_to_advance:
            session.current_node_states[r_id] = choice.next_scene

        await self.manager._persist_session(session)

        next_scene = self.story.get_scene(choice.next_scene)
        if not next_scene or next_scene.is_ending:
            if next_scene:
                from engine.story_manager import resolve_conditional_text
                resolved_ending_text = resolve_conditional_text(next_scene.text, session.flags)
                embed = discord.Embed(
                    title=next_scene.title if next_scene.title != next_scene.id else "النهاية",
                    description=resolved_ending_text,
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

    async def handle_group_decision(self, channel, scene, session, roles_at_node=None):
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

                if roles_at_node is not None and role_id not in roles_at_node:
                    await interaction.response.send_message("❌ دورك ليس متواجداً في هذا المشهد حالياً.", ephemeral=True)
                    return

                idx = int(interaction.data['custom_id'].split('_')[1])
                self.manager.register_vote(self.session_id, user_id, idx, scene.id)
                await interaction.response.send_message("✅ تم تسجيل تصويتك.", ephemeral=True)

                # Check if all voted
                allowed_voters_count = len(roles_at_node) if roles_at_node else len(session.players)
                if self.manager.get_vote_count(self.session_id, scene.id) >= allowed_voters_count:
                    await self.resolve_group(channel, scene, roles_at_node)
                else:
                    # Update progress embed
                    try:
                        new_embed = self.build_turn_embed(scene, session, roles_at_node)
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
                
                from engine.story_manager import resolve_conditional_text
                custom_text = resolve_conditional_text(scene.get_text_for_role(role_id), session.flags)
                resolved_base_text = resolve_conditional_text(scene.text, session.flags)
                if custom_text == resolved_base_text:
                    await interaction.response.send_message("لا توجد معلومات إضافية سرية لدورك في هذا المشهد.", ephemeral=True)
                else:
                    await interaction.response.send_message(f"📜 **معلومات دورك السرية:**\n\n{custom_text}", ephemeral=True)
            
            secret_btn.callback = reveal_secret_callback
            view.add_item(secret_btn)

        embed = self.build_turn_embed(scene, session, roles_at_node)
        try:
            await channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error sending group decision message: {e}")
            return

        # Trigger NPCs
        asyncio.create_task(self.run_npcs_and_check(channel, scene, roles_at_node))

    async def run_npcs_and_check(self, channel, scene, roles_at_node=None):
        await self.manager.execute_npc_turns(self.session_id, self.story, channel)
        session = self.manager.active_sessions.get(self.session_id)
        if not session:
            return
        allowed_voters_count = len(roles_at_node) if roles_at_node else len(session.players)
        if self.manager.get_vote_count(self.session_id, scene.id) >= allowed_voters_count:
            await self.resolve_group(channel, scene, roles_at_node)

    async def resolve_group(self, channel, scene, roles_at_node=None):
        if not self.manager.start_resolution(self.session_id):
            return

        try:
            winner_idx = self.manager.resolve_group_vote(self.session_id, scene.id, self.story)
            if winner_idx is None: return

            choice = scene.choices[winner_idx]
            await channel.send(f"🥁 الأغلبية اختارت: **{choice.text}**")
            await self.advance_story(choice, channel, roles_at_node, source_node_id=scene.id)
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

    @app_commands.command(name="استئناف_حدث", description="استئناف حدث تفاعلي جماعي بعد إعادة تشغيل البوت أو انقطاع الجلسة")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def resume_event(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        session = self.bot.multiplayer_manager.get_session_by_channel(interaction.channel.id)
        session_id = session.session_id if session else None
        
        if not session_id:
            from core.db import get_connection
            async with get_connection() as db:
                cursor = await db.execute(
                    "SELECT session_id FROM multiplayer_sessions WHERE channel_id = ? AND status != 'finished' ORDER BY created_at DESC LIMIT 1",
                    (interaction.channel.id,)
                )
                row = await cursor.fetchone()
                if row:
                    session_id = row[0]
        
        if not session_id:
            await interaction.followup.send("❌ لا توجد جلسة نشطة مسجلة لهذه القناة.")
            return
            
        session = await self.bot.multiplayer_manager.recover_session(session_id)
        if not session:
            await interaction.followup.send("❌ فشل استعادة تفاصيل الجلسة.")
            return
            
        story = self.bot.story_manager.resolve_story(session.story_id, game_mode="multi")
        if not story:
            await interaction.followup.send("❌ لم يتم العثور على القصة المرتبطة بهذه الجلسة.")
            return
            
        await interaction.followup.send(f"🔄 تم استعادة الجلسة بنجاح! القصة: **{story.title}**")
        
        view = RoleSelectView(self.bot, session.session_id, story)
        
        if session.status == "lobby":
            players_text = []
            for uid, rid in session.players.items():
                role = story.roles.get(rid)
                players_text.append(f"<@{uid}>: {role.title}")
            text = "اللاعبون المنضمون:\n" + "\n".join(players_text) if players_text else "لا أحد بعد."
            embed = discord.Embed(title=f"غرفة الانتظار (مستأنفة): {story.title}", description=text)
            await interaction.channel.send(embed=embed, view=view)
        else:
            asyncio.create_task(view.run_turn(interaction.channel))

    @app_commands.command(name="قصص_جماعية", description="تصفح مكتبة القصص الجماعية المتاحة")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_multi_stories(self, interaction: discord.Interaction):
        stories = self.bot.story_manager.get_stories_by_mode("multi")
        categories = {}
        for story in stories.values():
            theme = story.theme or "عام"
            if theme not in categories:
                categories[theme] = []
            categories[theme].append(story)

        from ui.listing_view import MultiLibraryView
        view = MultiLibraryView(categories)
        embed = view.render_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot: StoryBot):
    await bot.add_cog(EventCog(bot))
