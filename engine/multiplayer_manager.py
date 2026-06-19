import asyncio
import random
import json
from typing import Dict, List, Optional
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

    def create_session(self, channel_id: int, story_id: str, host_id: str) -> str:
        session_id = f"sess_{channel_id}_{random.randint(1000, 9999)}"
        session = MultiplayerSession(
            session_id=session_id,
            story_id=story_id,
            status="lobby",
            players={},
            current_node_states={},
            flags=[]
        )
        self.active_sessions[session_id] = session
        self.channel_to_session[channel_id] = session_id
        self.session_votes[session_id] = {}
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
        return True

    def remove_player(self, session_id: str, user_id: str) -> bool:
        session = self.active_sessions.get(session_id)
        if not session or session.status != "lobby":
            return False
        if user_id in session.players:
            del session.players[user_id]
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

        await self._persist_session(session)
        return True

    async def _persist_session(self, session: MultiplayerSession):
        await save_multiplayer_session(
            session_id=session.session_id,
            story_id=session.story_id,
            status=session.status,
            players=session.players,
            current_node_states=session.current_node_states,
            flags=session.flags
        )

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

    def register_vote(self, session_id: str, user_id: str, choice_index: int) -> bool:
        session = self.active_sessions.get(session_id)
        if not session or session.status != "active":
            return False

        role_id = self.get_role_by_user(session_id, user_id)
        if not role_id:
            return False

        if session_id not in self.session_votes:
            self.session_votes[session_id] = {}

        self.session_votes[session_id][role_id] = Vote(player_id=user_id, choice_index=choice_index)
        return True

    def get_vote_count(self, session_id: str) -> int:
        return len(self.session_votes.get(session_id, {}))

    def has_everyone_voted(self, session_id: str) -> bool:
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        return self.get_vote_count(session_id) >= len(session.players)

    def resolve_group_vote(self, session_id: str, story: Story) -> Optional[int]:
        votes = self.session_votes.get(session_id, {})
        if not votes:
            return None

        counts = {}
        for vote in votes.values():
            counts[vote.choice_index] = counts.get(vote.choice_index, 0) + 1

        max_votes = max(counts.values())
        winners = [idx for idx, count in counts.items() if count == max_votes]

        # Tie break: random (could be enhanced to prefer leader's choice)
        return random.choice(winners)

    def calculate_npc_vote(self, role: Role, choices: List) -> int:
        scores = []
        for choice in choices:
            score = 0.0
            for trait, weight in choice.npc_weights.items():
                npc_trait_val = role.npc_traits.get(trait, 0.0)
                score += npc_trait_val * weight
            scores.append(score)

        total_score = sum(scores)
        if total_score <= 0.0:
            # Fallback to random if no traits match
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

        # Find NPCs for the current group decision node
        # Assuming group decisions mean everyone is on the same node
        # In a real sync scenario, we'd check each NPC's node

        npc_roles = []
        for user_id, role_id in session.players.items():
            if self.is_npc(user_id):
                npc_roles.append(role_id)

        if not npc_roles:
            return

        # Get arbitrary player's node as they should all be synced
        sample_role = list(session.players.values())[0]
        current_node_id = session.current_node_states.get(sample_role)
        scene = story.get_scene(current_node_id)

        if not scene or scene.type != "group_decision":
            return

        for role_id in npc_roles:
            role = story.roles.get(role_id)
            if not role:
                continue

            # Random thinking delay
            await asyncio.sleep(random.uniform(2.0, 5.0))

            choice_idx = self.calculate_npc_vote(role, scene.choices)
            user_id = self.get_user_by_role(session_id, role_id)
            self.register_vote(session_id, user_id, choice_idx)

            winning_choice = scene.choices[choice_idx]

            # Print dialogue if available
            dialogue_map = scene.npc_dialogues.get(role_id, {})
            dialogue = dialogue_map.get(winning_choice.next_scene)
            if dialogue:
                await channel.send(f"💬 {dialogue}")

    async def advance_node(self, session_id: str, role_id: str, next_node_id: str, story: Story) -> bool:
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        session.current_node_states[role_id] = next_node_id
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

    def clear_votes(self, session_id: str):
        if session_id in self.session_votes:
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

        # Clean channel map
        ch_to_del = [ch for ch, s_id in self.channel_to_session.items() if s_id == session_id]
        for ch in ch_to_del:
            del self.channel_to_session[ch]
