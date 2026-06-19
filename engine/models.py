from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class Role:
    title: str
    description: str
    npc_traits: Dict[str, float] = field(default_factory=dict)

@dataclass
class Vote:
    player_id: str
    choice_index: int

@dataclass
class MultiplayerSession:
    session_id: str
    story_id: str
    status: str # 'lobby', 'active', 'finished'
    players: Dict[str, str] # discord_id -> role_id
    current_node_states: Dict[str, str] # role_id -> current_node_id
    flags: List[str]
    host_id: str = ""
    channel_id: int = 0

@dataclass
class Choice:
    text: str
    next_scene: str
    color: str = "primary" # primary, secondary, success, danger
    points_reward: int = 0
    required_points: Optional[int] = None
    sets_flag: Optional[str] = None
    requires_flag: Optional[str] = None
    reputation: Optional[str] = None
    npc_weights: Dict[str, float] = field(default_factory=dict)
    ephemeral_text: Optional[str] = None

@dataclass
class Scene:
    id: str
    title: str
    text: str
    choices: List[Choice] = field(default_factory=list)
    is_ending: bool = False
    image_url: Optional[str] = None

    # Multiplayer extensions
    type: str = "group_decision" # 'group_decision', 'solo_decision'
    assigned_to: Optional[str] = None
    is_convergence: bool = False
    npc_dialogues: Dict[str, Dict[str, str]] = field(default_factory=dict)
    asymmetric_text: Optional[Dict[str, str]] = None

    def get_text_for_role(self, role_id: Optional[str]) -> str:
        if self.asymmetric_text and role_id and role_id in self.asymmetric_text:
            return self.asymmetric_text[role_id]
        return self.text

@dataclass
class Perspective:
    id: str
    label: str
    emoji: str
    description: str
    start_node: str

@dataclass
class Story:
    id: int | str
    title: str
    theme: str # acts as category
    description: str
    series: int = 1
    game_mode: str = "single" # "single" or "multi"
    scenes: Dict[str, Scene] = field(default_factory=dict)
    start_scene: str = "start"
    image_url: Optional[str] = None
    world_type: Optional[str] = None
    perspectives: List[Perspective] = field(default_factory=list)

    # Multiplayer extensions
    min_players: int = 1
    max_players: int = 1
    roles: Dict[str, Role] = field(default_factory=dict)

    def get_scene(self, scene_id: str) -> Optional[Scene]:
        return self.scenes.get(scene_id)
