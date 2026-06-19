import asyncio
import sys
import os

# Ensure the app can import engine
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from engine.models import Story, Scene, Choice, Role
from engine.multiplayer_manager import MultiplayerManager
from core.db import init_db

class MockBot:
    class MockLoop:
        def create_task(self, coro):
            return asyncio.create_task(coro)

    def __init__(self):
        self.loop = self.MockLoop()

class MockChannel:
    async def send(self, text, embed=None, view=None):
        print(f"[CHANNEL MSG] {text}")

async def main():
    if os.path.exists("data/nexus.db"):
        os.remove("data/nexus.db")
    await init_db()

    bot = MockBot()
    manager = MultiplayerManager(bot)

    story = Story(
        id="mock_story_1",
        title="مؤامرة القصر",
        theme="fantasy",
        description="A mock story.",
        game_mode="multi",
        min_players=2,
        max_players=3,
        start_scene="node_entrance"
    )

    story.roles = {
        "prince_heir": Role(title="الأمير الوريث", description="", npc_traits={"loyal": 0.8, "ruthless": 0.4}),
        "spy": Role(title="الجاسوس", description="", npc_traits={"greedy": 0.9, "ruthless": 0.8})
    }

    story.scenes = {
        "node_entrance": Scene(
            id="node_entrance",
            title="Entrance",
            text="You stand before the gate.",
            type="group_decision",
            choices=[
                Choice(text="Blow gate", next_scene="node_blown", npc_weights={"ruthless": 0.8}),
                Choice(text="Find mechanism", next_scene="node_solved", npc_weights={"loyal": 0.8})
            ],
            npc_dialogues={
                "spy": {"node_blown": "Spy: Blow it up!"}
            }
        ),
        "node_blown": Scene(
            id="node_blown",
            title="Blown",
            text="The gate is gone.",
            is_ending=True
        ),
        "node_solved": Scene(
            id="node_solved",
            title="Solved",
            text="You got in quietly.",
            is_ending=True
        )
    }

    channel = MockChannel()

    # Create session
    session_id = manager.create_session(channel_id=123, story_id=story.id, host_id="player1")
    print(f"Created session {session_id}")

    # Add player
    success = manager.add_player(session_id, "player1", "prince_heir")
    print(f"Player 1 joined as prince: {success}")

    # Start Session (fills spy as NPC)
    started = await manager.start_session(session_id, story)
    print(f"Session started: {started}")

    # Vote
    manager.register_vote(session_id, "player1", 0) # Prince wants to blow it up
    print("Player 1 voted to blow gate")

    # Run NPC turn
    print("Running NPC turn for spy...")
    await manager.execute_npc_turns(session_id, story, channel)

    if manager.has_everyone_voted(session_id):
        print("Everyone voted! Resolving...")
        winner_idx = manager.resolve_group_vote(session_id, story)
        choice = story.get_scene("node_entrance").choices[winner_idx]
        print(f"Group decided: {choice.text}")
    else:
        print("Waiting on votes...")

if __name__ == "__main__":
    asyncio.run(main())
