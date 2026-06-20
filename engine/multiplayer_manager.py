import asyncio
import random
import json
import time
from typing import Dict, List, Optional, Set
import discord
from engine.models import MultiplayerSession, Story, Role, Vote
from core.db import save_multiplayer_session, load_multiplayer_session

class MultiplayerManager:
    def __init__(self, bot):
        self.bot = bot
        # In-memory store of active sessions
        self.active_sessions: Dict[str, MultiplayerSession] = {}
        # Votes tracking per session (session_id -> dict(role_id -> Vote))
        self.session_votes: Dict[str, Dict[str, Vote]] = {}
        # Map channel id -> session_id for easy lookup
        self.channel_to_session: Dict[int, str] = {}
        # Wait locks for synchronization
        self.wait_locks: Dict[str, asyncio.Event] = {}
        # Track sessions currently resolving to prevent race conditions
        self.resolving_sessions = set()
        # Track last activity timestamp per session to clean up idle ones (session_id -> epoch timestamp)
        self.session_last_activity: Dict[str, float] = {}
        # Cleanup background task
        self.cleanup_task: Optional[asyncio.Task] = None

    def update_activity(self, session_id: str):
        self.session_last_activity[session_id] = time.time()

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(600)  # Check every 10 minutes
            try:
                now = time.time()
                idle_sessions = []
                # Clean sessions idle for more than 1 hour (3600 seconds)
                for s_id, last_act in list(self.session_last_activity.items()):
                    if now - last_act > 3600.0:
                        idle_sessions.append(s_id)

                for s_id in idle_sessions:
                    session = self.active_sessions.get(s_id)
                    if session:
                        print(f"[Multiplayer Cleanup] Session {s_id} is idle. Ending session.")
                        # Attempt to notify channel
                        try:
                            channel = self.bot.get_channel(session.channel_id)
                            if channel:
                                await channel.send("⚠️ تم إنهاء هذه الجلسة التفاعلية تلقائياً بسبب عدم النشاط لأكثر من ساعة.")
                        except Exception:
                            pass
                        self.end_session(s_id)
                    else:
                        if s_id in self.session_last_activity:
                            del self.session_last_activity[s_id]
            except Exception as e:
                print(f"Error in multiplayer session cleanup: {e}")

    def create_session(self, channel_id: int, story_id: str, host_id: str) -> str:
        session_id = f"sess_{random.randint(100000, 999999)}"
        session = MultiplayerSession(
            session_id=session_id,
            story_id=story_id,
            status="lobby",
            players={},
            current_node_states={},
            flags=[],
            host_id=host_id,
            channel_id=channel_id
        )
        self.active_sessions[session_id] = session
        self.channel_to_session[channel_id] = session_id
        self.session_votes[session_id] = {}
        
        self.update_activity(session_id)
        
        # Start cleanup task if not already started
        if not self.cleanup_task:
            try:
                self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            except Exception as e:
                print(f"Failed to start cleanup loop task: {e}")
                
        # Persist session in DB initially
        asyncio.create_task(self._persist_session(session))
        return session_id

    def get_session_by_channel(self, channel_id: int) -> Optional[MultiplayerSession]:
        session_id = self.channel_to_session.get(channel_id)
        if session_id:
            return self.active_sessions.get(session_id)
        return None

    def add_player(self, session_id: str, user_id: str, role_id: str) -> bool:
        session = self.active_sessions.get(session_id)
        if not session or session.status != "lobby":
            return False

        # Check if role already taken by someone else
        for existing_user, existing_role in session.players.items():
            if existing_role == role_id and existing_user != user_id:
                return False

        # Remove user from any previous role
        if user_id in session.players:
            del session.players[user_id]

        session.players[user_id] = role_id
        self.update_activity(session_id)
        return True

    def remove_player(self, session_id: str, user_id: str) -> bool:
        session = self.active_sessions.get(session_id)
        if not session or session.status != "lobby":
            return False
        if user_id in session.players:
            del session.players[user_id]
            self.update_activity(session_id)
            return True
        return False

    def fill_vacant_roles_with_npcs(self, session_id: str, story: Story):
        session = self.active_sessions.get(session_id)
        if not session:
            return

        taken_roles = set(session.players.values())
        npc_count = 1
        for role_id in story.roles.keys():
            if role_id not in taken_roles:
                npc_user_id = f"npc_{npc_count}_{role_id}"
                session.players[npc_user_id] = role_id
                npc_count += 1

    async def start_session(self, session_id: str, story: Story) -> bool:
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        self.fill_vacant_roles_with_npcs(session_id, story)
        session.status = "active"

        # Initialize node states to start scene
        for role_id in story.roles.keys():
            session.current_node_states[role_id] = story.start_scene

        self.update_activity(session_id)
        await self._persist_session(session)
        return True

    async def _persist_session(self, session: MultiplayerSession):
        await save_multiplayer_session(
            session_id=session.session_id,
            story_id=session.story_id,
            status=session.status,
            players=session.players,
            current_node_states=session.current_node_states,
            flags=session.flags,
            host_id=session.host_id,
            channel_id=session.channel_id
        )

    def start_resolution(self, session_id: str) -> bool:
        if session_id in self.resolving_sessions:
            return False
        self.resolving_sessions.add(session_id)
        return True

    def finish_resolution(self, session_id: str):
        if session_id in self.resolving_sessions:
            self.resolving_sessions.remove(session_id)

    def is_npc(self, user_id: str) -> bool:
        return user_id.startswith("npc_")

    def get_role_by_user(self, session_id: str, user_id: str) -> Optional[str]:
        session = self.active_sessions.get(session_id)
        if session:
            return session.players.get(user_id)
        return None

    def get_user_by_role(self, session_id: str, role_id: str) -> Optional[str]:
        session = self.active_sessions.get(session_id)
        if session:
            for u_id, r_id in session.players.items():
                if r_id == role_id:
                    return u_id
        return None

    def register_vote(self, session_id: str, user_id: str, choice_index: int, node_id: str) -> bool:
        session = self.active_sessions.get(session_id)
        if not session or session.status != "active":
            return False

        role_id = self.get_role_by_user(session_id, user_id)
        if not role_id:
            return False

        if session_id not in self.session_votes:
            self.session_votes[session_id] = {}

        self.session_votes[session_id][role_id] = Vote(player_id=user_id, choice_index=choice_index, node_id=node_id)
        self.update_activity(session_id)
        return True

    def get_vote_count(self, session_id: str, node_id: str) -> int:
        votes = self.session_votes.get(session_id, {})
        return sum(1 for v in votes.values() if v.node_id == node_id)

    def has_everyone_voted(self, session_id: str, node_id: str) -> bool:
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        return self.get_vote_count(session_id, node_id) >= len(session.players)

    def resolve_group_vote(self, session_id: str, node_id: str, story: Story) -> Optional[int]:
        votes = self.session_votes.get(session_id, {})
        if not votes:
            return None

        # Filter votes matching node_id
        node_votes = {rid: v for rid, v in votes.items() if v.node_id == node_id}
        if not node_votes:
            return None

        counts = {}
        for vote in node_votes.values():
            counts[vote.choice_index] = counts.get(vote.choice_index, 0) + 1

        max_votes = max(counts.values())
        winners = [idx for idx, count in counts.items() if count == max_votes]

        if len(winners) == 1:
            return winners[0]

        # Tie-breaker logic:
        # Check if leader_role is defined or default to first role
        leader_role = getattr(story, "leader_role", None)
        if not leader_role and story.roles:
            leader_role = list(story.roles.keys())[0]

        if leader_role and leader_role in node_votes:
            leader_vote = node_votes[leader_role]
            if leader_vote.choice_index in winners:
                return leader_vote.choice_index

        return random.choice(winners)

    def calculate_npc_vote(self, role: Role, choices: List) -> int:
        scores = []
        for choice in choices:
            score = 0.0
            for trait, weight in choice.npc_weights.items():
                npc_trait_val = role.npc_traits.get(trait, 0.0)
                score += npc_trait_val * weight
            scores.append(max(score, 0.0))

        total_score = sum(scores)
        if total_score <= 0.0:
            # Fallback to random if no traits match or all scores clamped to 0
            return random.randint(0, len(choices) - 1)

        # Weighted random selection
        r = random.uniform(0, total_score)
        cumulative = 0.0
        for i, score in enumerate(scores):
            cumulative += score
            if r <= cumulative:
                return i

        return len(choices) - 1

    async def execute_npc_turns(self, session_id: str, story: Story, channel: discord.TextChannel):
        session = self.active_sessions.get(session_id)
        if not session or session.status != "active":
            return

        npc_roles = []
        for user_id, role_id in session.players.items():
            if self.is_npc(user_id):
                npc_roles.append((user_id, role_id))

        if not npc_roles:
            return

        for user_id, role_id in npc_roles:
            current_node_id = session.current_node_states.get(role_id)
            if not current_node_id:
                continue

            scene = story.get_scene(current_node_id)
            if not scene:
                continue

            # NPC acts if it's a group decision (any non-solo decision with choices) or their assigned solo decision
            if scene.choices and not getattr(scene, "is_ending", False) and (scene.type != "solo_decision" or scene.assigned_to == role_id):
                # Check if NPC has already voted
                votes = self.session_votes.get(session_id, {})
                if role_id in votes and votes[role_id].node_id == current_node_id:
                    continue

                # Random thinking delay
                await asyncio.sleep(random.uniform(2.0, 5.0))

                # Re-verify session active
                session = self.active_sessions.get(session_id)
                if not session or session.status != "active":
                    return

                role = story.roles.get(role_id)
                if not role:
                    continue

                available_choices = [c for c in scene.choices if not c.requires_flag or c.requires_flag in session.flags]
                if not available_choices:
                    available_choices = scene.choices

                choice_idx_in_available = self.calculate_npc_vote(role, available_choices)
                winning_choice = available_choices[choice_idx_in_available]
                choice_idx = scene.choices.index(winning_choice)
                
                self.register_vote(session_id, user_id, choice_idx, current_node_id)

                dialogue_map = scene.npc_dialogues.get(role_id, {})
                dialogue = dialogue_map.get(winning_choice.next_scene)
                if dialogue:
                    await self.send_npc_dialogue_via_webhook(session_id, role_id, dialogue, channel, story)

    async def send_npc_dialogue_via_webhook(
        self, session_id: str, role_id: str, dialogue: str, channel: discord.TextChannel, story: Story
    ):
        role = story.roles.get(role_id)
        role_title = role.title if role else role_id

        avatar_url = None
        if role and hasattr(role, "avatar_url") and role.avatar_url:
            avatar_url = role.avatar_url

        if not hasattr(channel, "webhooks"):
            await channel.send(f"💬 **{role_title}**: {dialogue}")
            return

        try:
            webhooks = await channel.webhooks()
            webhook = discord.utils.get(webhooks, name="Nexus NPC")
            if not webhook:
                webhook = await channel.create_webhook(name="Nexus NPC", reason="Nexus RPG NPC Dialogue")
            
            await webhook.send(
                content=dialogue,
                username=role_title,
                avatar_url=avatar_url
            )
        except Exception as e:
            print(f"[Webhook Failure] Fallback to normal send: {e}")
            await channel.send(f"💬 **{role_title}**: {dialogue}")

    async def recover_session(self, session_id: str) -> Optional[MultiplayerSession]:
        session_data = await load_multiplayer_session(session_id)
        if not session_data:
            return None

        session = MultiplayerSession(
            session_id=session_id,
            story_id=session_data["story_id"],
            status=session_data["status"],
            players=session_data["players"],
            current_node_states=session_data["current_node_states"],
            flags=session_data["flags"],
            host_id=session_data["host_id"],
            channel_id=session_data["channel_id"]
        )

        self.active_sessions[session_id] = session
        self.channel_to_session[session.channel_id] = session_id
        self.session_votes[session_id] = {}
        self.update_activity(session_id)

        if not self.cleanup_task:
            try:
                self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            except Exception as e:
                print(f"Failed to start cleanup loop task: {e}")

        return session

    async def advance_node(self, session_id: str, role_id: str, next_node_id: str, story: Story) -> bool:
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        session.current_node_states[role_id] = next_node_id
        self.update_activity(session_id)
        await self._persist_session(session)
        return True

    def is_convergence_waiting(self, session_id: str, node_id: str) -> bool:
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        for r_id, n_id in session.current_node_states.items():
            if n_id != node_id:
                return True
        return False

    def clear_votes(self, session_id: str, node_id: str = None):
        if session_id in self.session_votes:
            if node_id:
                # Clear only votes for this node
                self.session_votes[session_id] = {
                    rid: v for rid, v in self.session_votes[session_id].items() if v.node_id != node_id
                }
            else:
                self.session_votes[session_id] = {}

    def end_session(self, session_id: str):
        session = self.active_sessions.get(session_id)
        if session:
            session.status = "finished"
            asyncio.create_task(self._persist_session(session))

        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        if session_id in self.session_votes:
            del self.session_votes[session_id]
        if session_id in self.session_last_activity:
            del self.session_last_activity[session_id]

        # Clean channel map
        ch_to_del = [ch for ch, s_id in self.channel_to_session.items() if s_id == session_id]
        for ch in ch_to_del:
            del self.channel_to_session[ch]
