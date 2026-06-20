#!/usr/bin/env python3
"""
validate_story.py — Nexus Bot Story Quality Validator
======================================================
Validates story JSON files against structural, flag, branch, pacing,
ending, and language quality rules.

Usage:
    python scripts/validate_story.py data/stories/my_story.json        # one file
    python scripts/validate_story.py data/stories/                     # all files
    python scripts/validate_story.py data/stories/ --warn-only         # warn instead of fail
"""

import json
import os
import sys
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

# Reconfigure stdout to force UTF-8 (handles Windows Console encoding issues)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ── ANSI color helpers ──────────────────────────────────────────────────
class _C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"

def _pass(msg: str) -> str:
    return f"  {_C.GREEN}✅ PASS{_C.RESET}  {msg}"

def _fail(msg: str) -> str:
    return f"  {_C.RED}❌ FAIL{_C.RESET}  {msg}"

def _warn(msg: str) -> str:
    return f"  {_C.YELLOW}⚠️  WARN{_C.RESET}  {msg}"

# ── Constants ───────────────────────────────────────────────────────────
VALID_NODE_TYPES = {
    "opening", "discovery", "decision", "consequence",
    "escalation", "revelation", "breath", "climax", "ending",
    "group_decision", "solo_decision",
}
VALID_WORLD_TYPES = {"solo", "fantasy", "past", "future", "alternate", "multi"}
VALID_GAME_MODES  = {"single", "multi"}
REQUIRED_TOP_FIELDS = {
    "id", "title", "summary", "world", "world_type",
    "theme", "game_mode", "start_scene", "nodes",
}
SPINE_FIELDS = {"wound", "lie", "trigger", "complication", "revelation", "verdict"}
DEATH_KEYWORDS = [
    "تموت", "الموت", "تسقط ميتاً", "تلقى حتفك", "مات", "يموت",
    "تفارق الحياة", "الهلاك", "هلك", "قتل", "تُقتل", "تقتل",
    "تسقط جثة", "تفقد حياتك", "تتهاوى", "تلفظ أنفاسك",
]
NODE_COUNT_THRESHOLDS = {"solo": 30, "medium": 55, "flagship": 100}

# ── Result collector ────────────────────────────────────────────────────
class ValidationResult:
    def __init__(self):
        self.passed:   List[str] = []
        self.failed:   List[str] = []
        self.warnings: List[str] = []

    def ok(self, msg: str):
        self.passed.append(msg)

    def fail(self, msg: str):
        self.failed.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed) + len(self.warnings)

    def print_all(self, warn_only: bool = False):
        for m in self.passed:
            print(_pass(m))
        for m in self.warnings:
            print(_warn(m))
        for m in self.failed:
            if warn_only:
                print(_warn(m))
            else:
                print(_fail(m))

    def print_summary(self, warn_only: bool = False):
        f_count = 0 if warn_only else len(self.failed)
        w_count = len(self.warnings) + (len(self.failed) if warn_only else 0)
        p_count = len(self.passed)
        parts = [
            f"{_C.GREEN}{p_count} passed{_C.RESET}",
            f"{_C.RED}{f_count} failed{_C.RESET}",
            f"{_C.YELLOW}{w_count} warnings{_C.RESET}",
        ]
        print(f"\n  {_C.BOLD}Summary:{_C.RESET} {', '.join(parts)}")

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0

# ── Graph helpers ───────────────────────────────────────────────────────

def _reachable_from(start: str, nodes: Dict[str, Any]) -> Set[str]:
    """BFS from *start*, return set of reachable node keys."""
    visited: Set[str] = set()
    queue: deque = deque()
    if start in nodes:
        queue.append(start)
        visited.add(start)
    while queue:
        cur = queue.popleft()
        node = nodes.get(cur)
        if node is None:
            continue
        for ch in node.get("choices", []):
            nxt = ch.get("next", ch.get("next_scene", ""))
            if nxt and nxt not in visited and nxt in nodes:
                visited.add(nxt)
                queue.append(nxt)
    return visited


def _all_paths_lengths(start: str, nodes: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """Return (shortest, longest) path length from *start* to any ending node.
    Uses BFS for shortest and bounded DFS for longest (cap at 500 to avoid
    exponential blow-up on large graphs).
    """
    # Shortest via BFS
    shortest: Optional[int] = None
    dist: Dict[str, int] = {start: 0}
    queue: deque = deque([start])
    while queue:
        cur = queue.popleft()
        node = nodes.get(cur)
        if node is None:
            continue
        if node.get("is_ending", False):
            if shortest is None or dist[cur] < shortest:
                shortest = dist[cur]
        for ch in node.get("choices", []):
            nxt = ch.get("next", ch.get("next_scene", ""))
            if nxt and nxt not in dist and nxt in nodes:
                dist[nxt] = dist[cur] + 1
                queue.append(nxt)

    # Longest via bounded DFS (iterative)
    longest: Optional[int] = None
    stack: List[Tuple[str, int, Set[str]]] = [(start, 0, {start})]
    iterations = 0
    max_iterations = 200_000  # safety cap
    while stack and iterations < max_iterations:
        iterations += 1
        cur, depth, visited = stack.pop()
        node = nodes.get(cur)
        if node is None:
            continue
        if node.get("is_ending", False):
            if longest is None or depth > longest:
                longest = depth
            continue  # don't extend past endings
        for ch in node.get("choices", []):
            nxt = ch.get("next", ch.get("next_scene", ""))
            if nxt and nxt not in visited and nxt in nodes:
                new_visited = visited | {nxt}
                stack.append((nxt, depth + 1, new_visited))

    return shortest, longest


def _has_escalation_run(start: str, nodes: Dict[str, Any], max_run: int = 4) -> bool:
    """Return True if any path from *start* has *max_run* or more consecutive
    'escalation' type nodes."""
    # BFS tracking current escalation streak
    queue: deque = deque()  # (node_key, current_escalation_streak)
    visited_states: Set[Tuple[str, int]] = set()
    init_streak = 1 if nodes.get(start, {}).get("type") == "escalation" else 0
    queue.append((start, init_streak))
    visited_states.add((start, init_streak))
    while queue:
        cur, streak = queue.popleft()
        if streak >= max_run:
            return True
        node = nodes.get(cur)
        if node is None:
            continue
        for ch in node.get("choices", []):
            nxt = ch.get("next", ch.get("next_scene", ""))
            if nxt and nxt in nodes:
                nxt_type = nodes[nxt].get("type", "")
                new_streak = (streak + 1) if nxt_type == "escalation" else 0
                state = (nxt, new_streak)
                if state not in visited_states:
                    visited_states.add(state)
                    queue.append(state)
    return False


def _is_death_ending(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in DEATH_KEYWORDS)

# ── Core validator ──────────────────────────────────────────────────────

def validate_story(filepath: str, warn_only: bool = False) -> ValidationResult:
    """Run all validation checks on a single story file."""
    res = ValidationResult()

    # ── Load JSON ───────────────────────────────────────────────────────
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            raw_text = fh.read()
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        res.fail(f"Invalid JSON: {exc}")
        return res
    except OSError as exc:
        res.fail(f"Cannot read file: {exc}")
        return res

    nodes: Dict[str, Any] = data.get("nodes", {})
    node_keys = list(nodes.keys())
    total_nodes = len(node_keys)

    # ================================================================
    #  STRUCTURAL CHECKS
    # ================================================================

    # -- Required top-level fields --
    missing_top = REQUIRED_TOP_FIELDS - set(data.keys())
    if missing_top:
        res.fail(f"Missing top-level fields: {', '.join(sorted(missing_top))}")
    else:
        res.ok("All required top-level fields present")

    # -- Multiplayer-specific top-level fields --
    game_mode = data.get("game_mode", "single")
    roles_dict = {}
    if game_mode == "multi":
        mp_required = {"min_players", "max_players", "roles"}
        missing_mp = mp_required - set(data.keys())
        if missing_mp:
            res.fail(f"Multiplayer story missing top-level fields: {', '.join(sorted(missing_mp))}")
        else:
            min_p = data.get("min_players")
            max_p = data.get("max_players")
            if not isinstance(min_p, int) or min_p <= 0:
                res.fail(f"Invalid min_players: {min_p} (must be a positive integer)")
            if not isinstance(max_p, int) or max_p <= 0:
                res.fail(f"Invalid max_players: {max_p} (must be a positive integer)")
            if isinstance(min_p, int) and isinstance(max_p, int) and min_p > max_p:
                res.fail(f"min_players ({min_p}) cannot be greater than max_players ({max_p})")
            
            roles_raw = data.get("roles")
            if not isinstance(roles_raw, dict):
                res.fail("roles must be a dictionary")
            else:
                roles_dict = roles_raw
                if not roles_dict:
                    res.fail("roles dictionary cannot be empty")
                else:
                    for r_id, r_data in roles_dict.items():
                        if not isinstance(r_data, dict):
                            res.fail(f"Role '{r_id}' must be a dictionary")
                        else:
                            if not r_data.get("title", "").strip():
                                res.fail(f"Role '{r_id}' missing or empty title")
                            if not r_data.get("description", "").strip():
                                res.fail(f"Role '{r_id}' missing or empty description")
                            npc_traits = r_data.get("npc_traits", {})
                            if not isinstance(npc_traits, dict):
                                res.fail(f"Role '{r_id}' npc_traits must be a dictionary")
                            else:
                                for trait, val in npc_traits.items():
                                    if not isinstance(val, (int, float)):
                                        res.fail(f"Role '{r_id}' trait '{trait}' value must be a number")

    # -- Spine --
    spine = data.get("spine")
    if not spine or not isinstance(spine, dict):
        res.fail("Missing 'spine' object")
    else:
        missing_spine = SPINE_FIELDS - set(spine.keys())
        if missing_spine:
            res.fail(f"Spine missing fields: {', '.join(sorted(missing_spine))}")
        else:
            empty_spine = [k for k in SPINE_FIELDS if not spine.get(k)]
            if empty_spine:
                res.warn(f"Spine fields are empty: {', '.join(sorted(empty_spine))}")
            else:
                res.ok("Spine object complete with all 6 fields")

    # -- Node count thresholds --
    wt = data.get("world_type", "solo")
    threshold = NODE_COUNT_THRESHOLDS.get(wt, 30)
    if total_nodes < threshold:
        res.warn(f"Node count ({total_nodes}) below recommended minimum ({threshold}) for '{wt}'")
    else:
        res.ok(f"Node count ({total_nodes}) meets minimum for '{wt}'")

    # -- JSON line count --
    line_count = raw_text.count("\n") + 1
    if line_count < 600:
        res.warn(f"JSON line count ({line_count}) below recommended 600")
    else:
        res.ok(f"JSON line count ({line_count}) ≥ 600")

    # -- Duplicate node keys (JSON spec only keeps last, detect via raw scan) --
    import re as _re
    key_pattern = _re.compile(r'^\s*"([^"]+)"\s*:\s*\{', _re.MULTILINE)
    # We look inside the "nodes" section only
    nodes_start = raw_text.find('"nodes"')
    if nodes_start != -1:
        nodes_text = raw_text[nodes_start:]
        found_keys = key_pattern.findall(nodes_text)
        # Filter: keep only keys that appear as actual node keys (skip nested)
        # Heuristic: count occurrences at the expected indent level
        seen: Dict[str, int] = {}
        for k in found_keys:
            if k in nodes:
                seen[k] = seen.get(k, 0) + 1
        dupes = {k: c for k, c in seen.items() if c > 1}
        if dupes:
            res.fail(f"Duplicate node keys detected: {', '.join(dupes.keys())}")
        else:
            res.ok("No duplicate node keys")

    # -- start_scene / 'start' node exists --
    start_scene = data.get("start_scene", "start")
    if start_scene in nodes:
        res.ok(f"start_scene '{start_scene}' exists in nodes")
    elif "start" in nodes:
        res.warn(f"start_scene '{start_scene}' not found, but 'start' node exists")
    else:
        res.fail("No start_scene node and no 'start' node found")

    # -- Node-level structural checks --
    nodes_missing_type = []
    nodes_invalid_type = []
    nodes_empty_text = []
    long_labels = []
    broken_nexts = []
    trap_nodes = []

    for nk, nd in nodes.items():
        # type field
        ntype = nd.get("type")
        if not ntype:
            nodes_missing_type.append(nk)
        elif ntype not in VALID_NODE_TYPES:
            nodes_invalid_type.append((nk, ntype))

        # text field
        text_raw = nd.get("text", "")
        if isinstance(text_raw, dict):
            default_text = text_raw.get("default", "")
            if not isinstance(default_text, str) or not default_text.strip():
                nodes_empty_text.append(f"{nk} (missing/empty default text in dict)")
            asym = text_raw.get("asymmetric", {})
            if asym:
                if not isinstance(asym, dict):
                    nodes_empty_text.append(f"{nk} (asymmetric text must be a dictionary)")
                else:
                    for r_id, r_txt in asym.items():
                        if game_mode == "multi" and r_id not in roles_dict:
                            res.fail(f"Node '{nk}' asymmetric text references undefined role: '{r_id}'")
                        if not isinstance(r_txt, str) or not r_txt.strip():
                            nodes_empty_text.append(f"{nk} (empty asymmetric text for role '{r_id}')")
        elif isinstance(text_raw, str):
            if not text_raw.strip():
                nodes_empty_text.append(nk)
        else:
            nodes_empty_text.append(f"{nk} (invalid text type: {type(text_raw).__name__})")

        # Validate assigned_to for solo decisions
        if ntype == "solo_decision":
            assigned_to = nd.get("assigned_to")
            if not assigned_to:
                res.fail(f"Solo decision node '{nk}' missing required 'assigned_to' field")
            elif game_mode == "multi" and assigned_to not in roles_dict:
                res.fail(f"Solo decision node '{nk}' assigned_to role '{assigned_to}' is not defined in roles")
        
        # Validate npc_dialogues if present
        npc_dialogues = nd.get("npc_dialogues", {})
        if npc_dialogues:
            if not isinstance(npc_dialogues, dict):
                res.fail(f"Node '{nk}' npc_dialogues must be a dictionary")
            elif game_mode == "multi":
                for r_id, d_map in npc_dialogues.items():
                    if r_id not in roles_dict:
                        res.fail(f"Node '{nk}' npc_dialogues references undefined role: '{r_id}'")
                    if not isinstance(d_map, dict):
                        res.fail(f"Node '{nk}' npc_dialogues for role '{r_id}' must be a dictionary mapping next nodes to dialogue text")
                    else:
                        for next_scene_key, diag_text in d_map.items():
                            if next_scene_key not in nodes:
                                res.fail(f"Node '{nk}' npc_dialogues for role '{r_id}' references non-existent node: '{next_scene_key}'")
                            if not isinstance(diag_text, str) or not diag_text.strip():
                                res.fail(f"Node '{nk}' npc_dialogues for role '{r_id}' at '{next_scene_key}' is empty")

        # choices
        choices = nd.get("choices", [])
        nexts_in_node: List[str] = []
        for ci, ch in enumerate(choices):
            label = ch.get("label", ch.get("text", ""))
            if len(label) > 40:
                long_labels.append((nk, ci, len(label), label[:50]))
            nxt = ch.get("next", ch.get("next_scene", ""))
            if nxt and nxt not in nodes:
                broken_nexts.append((nk, ci, nxt))
            nexts_in_node.append(nxt)

            # Validate npc_weights if present
            npc_weights = ch.get("npc_weights", {})
            if npc_weights:
                if not isinstance(npc_weights, dict):
                    res.fail(f"Node '{nk}' choice '{label}' npc_weights must be a dictionary")
                else:
                    for trait, weight in npc_weights.items():
                        if not isinstance(weight, (int, float)):
                            res.fail(f"Node '{nk}' choice '{label}' weight for trait '{trait}' must be a number")

        # trap node: both choices lead to same destination
        if len(nexts_in_node) == 2 and nexts_in_node[0] and nexts_in_node[0] == nexts_in_node[1]:
            trap_nodes.append(nk)

    if nodes_missing_type:
        res.fail(f"Nodes missing 'type': {', '.join(nodes_missing_type)}")
    else:
        res.ok("All nodes have a 'type' field")

    if nodes_invalid_type:
        details = ", ".join(f"{k}='{t}'" for k, t in nodes_invalid_type)
        res.fail(f"Nodes with invalid type: {details}")
    else:
        res.ok("All node types are valid")

    if nodes_empty_text:
        res.fail(f"Nodes with empty text: {', '.join(nodes_empty_text)}")
    else:
        res.ok("All nodes have non-empty text")

    if long_labels:
        details = "; ".join(
            f"{nk}[{ci}] ({ln} chars): \"{lbl}…\"" for nk, ci, ln, lbl in long_labels
        )
        res.warn(f"Choice labels over 40 chars: {details}")
    else:
        res.ok("All choice labels ≤ 40 characters")

    if broken_nexts:
        details = "; ".join(f"{nk}[{ci}] → '{tgt}'" for nk, ci, tgt in broken_nexts)
        res.fail(f"Choices pointing to non-existent nodes: {details}")
    else:
        res.ok("All choice 'next' targets exist")

    if trap_nodes:
        res.fail(f"Trap nodes (both choices lead to same target): {', '.join(trap_nodes)}")
    else:
        res.ok("No trap nodes found")

    # ================================================================
    #  FLAGS
    # ================================================================
    all_sets: Set[str]     = set()
    all_requires: Set[str] = set()
    late_threshold = max(1, int(total_nodes * 0.8))
    late_flags: Set[str]   = set()

    for idx, (nk, nd) in enumerate(nodes.items()):
        for ch in nd.get("choices", []):
            sf = ch.get("sets_flag")
            rf = ch.get("requires_flag")
            if sf:
                all_sets.add(sf)
                if idx >= late_threshold:
                    late_flags.add(sf)
            if rf:
                all_requires.add(rf)

    # Extract flags from inline conditionals {IF flag} in texts
    if_pattern = _re.compile(r'\{IF\s+([A-Za-z0-9_:]+)\}')
    for nk, nd in nodes.items():
        text_raw = nd.get("text", "")
        texts_to_check = []
        if isinstance(text_raw, str):
            texts_to_check.append(text_raw)
        elif isinstance(text_raw, dict):
            if isinstance(text_raw.get("default"), str):
                texts_to_check.append(text_raw["default"])
            asym = text_raw.get("asymmetric", {})
            if isinstance(asym, dict):
                for r_val in asym.values():
                    if isinstance(r_val, str):
                        texts_to_check.append(r_val)
        
        npc_dialogues = nd.get("npc_dialogues", {})
        if isinstance(npc_dialogues, dict):
            for r_id, d_map in npc_dialogues.items():
                if isinstance(d_map, dict):
                    for diag_text in d_map.values():
                        if isinstance(diag_text, str):
                            texts_to_check.append(diag_text)

        for text in texts_to_check:
            for flag in if_pattern.findall(text):
                all_requires.add(flag)

    orphan_set   = all_sets - all_requires
    orphan_req   = all_requires - all_sets

    if orphan_set:
        res.warn(f"Flags set but never required (orphaned): {', '.join(sorted(orphan_set))}")
    else:
        if all_sets:
            res.ok("Every sets_flag appears in at least one requires_flag")
        else:
            res.ok("No flags used (none to validate)")

    if orphan_req:
        res.fail(f"Flags required but never set: {', '.join(sorted(orphan_req))}")
    else:
        if all_requires:
            res.ok("Every requires_flag has a corresponding sets_flag")
        else:
            res.ok("No requires_flag used (none to validate)")

    only_late = late_flags - (all_sets - late_flags)
    if only_late:
        res.warn(f"Flags set only in the last 20% of nodes: {', '.join(sorted(only_late))}")

    # ================================================================
    #  BRANCHES
    # ================================================================

    # -- Unreachable nodes --
    effective_start = start_scene if start_scene in nodes else ("start" if "start" in nodes else (node_keys[0] if node_keys else ""))
    reachable = _reachable_from(effective_start, nodes)
    unreachable = set(node_keys) - reachable
    if unreachable:
        res.warn(f"Unreachable nodes ({len(unreachable)}): {', '.join(sorted(unreachable))}")
    else:
        res.ok("All nodes reachable from start")

    # -- Min path length --
    shortest, longest = _all_paths_lengths(effective_start, nodes)
    if shortest is not None and shortest < 5:
        if game_mode == "multi":
            res.warn(f"❌ CRITICAL PACING RULE: Multiplayer stories must NOT contain any early endings. The shortest path to an ending is only {shortest} steps (must be ≥ 5 to prevent players' sessions from being cut short).")
        else:
            res.warn(f"Shortest path to an ending is only {shortest} steps (recommended ≥ 5)")
    elif shortest is not None:
        res.ok(f"Shortest path to ending: {shortest} steps")
    else:
        res.warn("No ending reachable from start")

    # -- Death-to-survival ratio --
    death_count = 0
    survival_count = 0
    ending_nodes = [nk for nk, nd in nodes.items() if nd.get("is_ending", False)]
    for nk in ending_nodes:
        txt = nodes[nk].get("text", "")
        if _is_death_ending(txt):
            death_count += 1
        else:
            survival_count += 1
    if survival_count > 0:
        ratio = death_count / survival_count
        if ratio > 2.0:
            res.warn(f"Death-to-survival ratio {death_count}:{survival_count} ({ratio:.1f}:1) exceeds 2:1")
        else:
            res.ok(f"Death-to-survival ratio {death_count}:{survival_count} ({ratio:.1f}:1) within limits")
    elif death_count > 0:
        res.warn(f"All {death_count} endings are death endings (no survival endings)")
    else:
        if ending_nodes:
            res.ok("No death endings detected")
        # If no endings at all, caught below

    # ================================================================
    #  PACING
    # ================================================================

    # -- Breath nodes --
    breath_count = sum(1 for nd in nodes.values() if nd.get("type") == "breath")
    if breath_count < 3:
        res.warn(f"Only {breath_count} 'breath' nodes (recommended ≥ 3)")
    else:
        res.ok(f"Breath nodes: {breath_count} (≥ 3)")

    # -- Escalation runs --
    if _has_escalation_run(effective_start, nodes, max_run=4):
        res.warn("Found run of 4+ consecutive 'escalation' nodes on a path")
    else:
        res.ok("No run of 4+ escalation nodes on any path")

    # ================================================================
    #  ENDINGS
    # ================================================================

    if not ending_nodes:
        res.fail("No node with is_ending: true found")
    else:
        res.ok(f"Ending nodes found: {len(ending_nodes)}")

    # -- Endings must have empty choices --
    endings_with_choices = [
        nk for nk in ending_nodes
        if nodes[nk].get("choices") and len(nodes[nk]["choices"]) > 0
    ]
    if endings_with_choices:
        res.fail(f"Ending nodes with non-empty choices: {', '.join(endings_with_choices)}")
    else:
        if ending_nodes:
            res.ok("All ending nodes have empty choices")

    # -- Ending text should contain retry message --
    RETRY_MSG = "يمكنك المحاولة مجدداً"
    endings_no_retry = [
        nk for nk in ending_nodes
        if RETRY_MSG not in nodes[nk].get("text", "")
    ]
    if endings_no_retry:
        res.warn(f"Ending nodes missing retry message: {', '.join(endings_no_retry)}")
    else:
        if ending_nodes:
            res.ok("All endings contain retry message")

    # ================================================================
    #  LANGUAGE CHECKS
    # ================================================================

    # -- Choice labels starting with 'هل' --
    hal_labels = []
    for nk, nd in nodes.items():
        for ci, ch in enumerate(nd.get("choices", [])):
            label = ch.get("label", ch.get("text", "")).strip()
            if label.startswith("هل"):
                hal_labels.append((nk, ci, label[:40]))
    if hal_labels:
        details = "; ".join(f"{nk}[{ci}]: \"{lbl}\"" for nk, ci, lbl in hal_labels)
        res.warn(f"Choice labels starting with 'هل' (question format): {details}")
    else:
        res.ok("No choice labels start with 'هل'")

    # -- world_type --
    wt_val = data.get("world_type", "")
    if wt_val not in VALID_WORLD_TYPES:
        res.fail(f"Invalid world_type: '{wt_val}' (expected one of {', '.join(sorted(VALID_WORLD_TYPES))})")
    else:
        res.ok(f"world_type '{wt_val}' is valid")

    # -- game_mode --
    gm_val = data.get("game_mode", "")
    if gm_val not in VALID_GAME_MODES:
        res.fail(f"Invalid game_mode: '{gm_val}' (expected 'single' or 'multi')")
    else:
        res.ok(f"game_mode '{gm_val}' is valid")

    return res


# ── CLI entry point ─────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <story.json | stories_dir/> [--warn-only]")
        sys.exit(1)

    target = sys.argv[1]
    warn_only = "--warn-only" in sys.argv

    # Enable ANSI on Windows
    if sys.platform == "win32":
        os.system("")  # triggers ANSI support on Windows 10+

    files: List[str] = []
    if os.path.isdir(target):
        for fn in sorted(os.listdir(target)):
            if fn.endswith(".json"):
                files.append(os.path.join(target, fn))
    elif os.path.isfile(target):
        files.append(target)
    else:
        print(f"{_C.RED}Error:{_C.RESET} '{target}' is not a file or directory.")
        sys.exit(1)

    if not files:
        print(f"{_C.YELLOW}No JSON files found.{_C.RESET}")
        sys.exit(0)

    overall_pass = 0
    overall_fail = 0
    overall_warn = 0
    any_failure = False

    for fp in files:
        basename = os.path.basename(fp)
        print(f"\n{_C.BOLD}{_C.CYAN}{'─' * 60}{_C.RESET}")
        print(f"  {_C.BOLD}Validating:{_C.RESET} {basename}")
        print(f"{_C.BOLD}{_C.CYAN}{'─' * 60}{_C.RESET}")

        result = validate_story(fp, warn_only=warn_only)
        result.print_all(warn_only=warn_only)
        result.print_summary(warn_only=warn_only)

        overall_pass += len(result.passed)
        overall_fail += (0 if warn_only else len(result.failed))
        overall_warn += len(result.warnings) + (len(result.failed) if warn_only else 0)
        if result.failed and not warn_only:
            any_failure = True

    # Grand total
    if len(files) > 1:
        print(f"\n{_C.BOLD}{'═' * 60}{_C.RESET}")
        print(f"  {_C.BOLD}GRAND TOTAL ({len(files)} files):{_C.RESET}")
        parts = [
            f"{_C.GREEN}{overall_pass} passed{_C.RESET}",
            f"{_C.RED}{overall_fail} failed{_C.RESET}",
            f"{_C.YELLOW}{overall_warn} warnings{_C.RESET}",
        ]
        print(f"  {', '.join(parts)}")
        print(f"{_C.BOLD}{'═' * 60}{_C.RESET}")

    sys.exit(1 if any_failure else 0)


if __name__ == "__main__":
    main()
