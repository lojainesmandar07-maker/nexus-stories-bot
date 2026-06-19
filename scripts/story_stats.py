#!/usr/bin/env python3
"""
story_stats.py — Nexus Bot Story Statistics
============================================
Generates quick statistics for story JSON files.

Usage:
    python scripts/story_stats.py data/stories/my_story.json   # one file
    python scripts/story_stats.py data/stories/                 # all files
"""

import json
import os
import sys
from collections import Counter, deque
from typing import Any, Dict, List, Optional, Set, Tuple

# Reconfigure stdout to force UTF-8 (handles Windows Console encoding issues)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ── ANSI helpers ────────────────────────────────────────────────────────
class _C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"

# ── Death-ending heuristic ──────────────────────────────────────────────
DEATH_KEYWORDS = [
    "تموت", "الموت", "تسقط ميتاً", "تلقى حتفك", "مات", "يموت",
    "تفارق الحياة", "الهلاك", "هلك", "قتل", "تُقتل", "تقتل",
    "تسقط جثة", "تفقد حياتك", "تتهاوى", "تلفظ أنفاسك",
]

def _is_death_ending(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in DEATH_KEYWORDS)

# ── Graph helpers ───────────────────────────────────────────────────────

def _reachable_from(start: str, nodes: Dict[str, Any]) -> Set[str]:
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


def _path_lengths(start: str, nodes: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """Return (shortest, longest) path from start to any ending."""
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

    # Longest via bounded DFS
    longest: Optional[int] = None
    stack: List[Tuple[str, int, Set[str]]] = [(start, 0, {start})]
    iterations = 0
    max_iterations = 200_000
    while stack and iterations < max_iterations:
        iterations += 1
        cur, depth, visited = stack.pop()
        node = nodes.get(cur)
        if node is None:
            continue
        if node.get("is_ending", False):
            if longest is None or depth > longest:
                longest = depth
            continue
        for ch in node.get("choices", []):
            nxt = ch.get("next", ch.get("next_scene", ""))
            if nxt and nxt not in visited and nxt in nodes:
                stack.append((nxt, depth + 1, visited | {nxt}))

    return shortest, longest

# ── Stats collector ─────────────────────────────────────────────────────

def compute_stats(filepath: str) -> Optional[Dict[str, Any]]:
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  {_C.RED}Error loading {filepath}: {exc}{_C.RESET}")
        return None

    nodes: Dict[str, Any] = data.get("nodes", {})
    node_keys = list(nodes.keys())
    total_nodes = len(node_keys)

    # -- Basic info --
    title = data.get("title", "—")
    story_id = data.get("id", "—")

    # -- Endings --
    ending_keys = [k for k, v in nodes.items() if v.get("is_ending", False)]
    ending_count = len(ending_keys)

    death_count = sum(1 for k in ending_keys if _is_death_ending(nodes[k].get("text", "")))
    survival_count = ending_count - death_count

    # -- Flags --
    all_flags: Set[str] = set()
    for nd in nodes.values():
        for ch in nd.get("choices", []):
            sf = ch.get("sets_flag")
            if sf:
                all_flags.add(sf)

    # -- Reachability --
    start_scene = data.get("start_scene", "start")
    effective_start = start_scene if start_scene in nodes else ("start" if "start" in nodes else (node_keys[0] if node_keys else ""))
    reachable = _reachable_from(effective_start, nodes)
    unreachable_count = total_nodes - len(reachable)

    # -- Branch depth --
    shortest, longest = _path_lengths(effective_start, nodes)

    # -- Node type distribution --
    type_counter: Counter = Counter()
    for nd in nodes.values():
        ntype = nd.get("type", "unknown")
        type_counter[ntype] += 1

    # -- Text length stats --
    text_lengths = [len(nd.get("text", "")) for nd in nodes.values()]
    avg_text = sum(text_lengths) / max(len(text_lengths), 1)

    # -- Choice label length stats --
    label_lengths: List[int] = []
    for nd in nodes.values():
        for ch in nd.get("choices", []):
            label = ch.get("label", ch.get("text", ""))
            label_lengths.append(len(label))

    if label_lengths:
        min_label = min(label_lengths)
        max_label = max(label_lengths)
        avg_label = sum(label_lengths) / len(label_lengths)
    else:
        min_label = max_label = 0
        avg_label = 0.0

    return {
        "file": os.path.basename(filepath),
        "title": title,
        "id": story_id,
        "node_count": total_nodes,
        "ending_count": ending_count,
        "death_endings": death_count,
        "survival_endings": survival_count,
        "flag_count": len(all_flags),
        "flags": sorted(all_flags),
        "shortest_path": shortest,
        "longest_path": longest,
        "unreachable_count": unreachable_count,
        "type_distribution": dict(type_counter.most_common()),
        "avg_text_length": avg_text,
        "min_label_length": min_label,
        "max_label_length": max_label,
        "avg_label_length": avg_label,
    }

# ── Pretty printer ──────────────────────────────────────────────────────

def print_stats(stats: Dict[str, Any]):
    def row(label: str, value: Any, color: str = ""):
        c = color or ""
        r = _C.RESET if color else ""
        print(f"  {_C.DIM}│{_C.RESET}  {label:<30s} {c}{value}{r}")

    print(f"  {_C.BOLD}{_C.CYAN}┌{'─' * 58}┐{_C.RESET}")
    print(f"  {_C.BOLD}{_C.CYAN}│{_C.RESET}  {_C.BOLD}{stats['title']}{_C.RESET}")
    print(f"  {_C.BOLD}{_C.CYAN}│{_C.RESET}  {_C.DIM}ID: {stats['id']}  •  File: {stats['file']}{_C.RESET}")
    print(f"  {_C.BOLD}{_C.CYAN}├{'─' * 58}┤{_C.RESET}")

    row("Node count",          stats["node_count"])
    row("Ending count",        stats["ending_count"])

    # Death ratio
    d, s = stats["death_endings"], stats["survival_endings"]
    if s > 0:
        ratio_str = f"{d}:{s} ({d/s:.1f}:1)"
    elif d > 0:
        ratio_str = f"{d}:0 (all death)"
    else:
        ratio_str = "0:0 (no death)"
    row("Death ratio (D:S)",   ratio_str)

    row("Unique flags",        f"{stats['flag_count']}  {_C.DIM}{stats['flags']}{_C.RESET}" if stats["flags"] else "0")

    sp = stats["shortest_path"]
    lp = stats["longest_path"]
    row("Shortest path",       sp if sp is not None else "—")
    row("Longest path",        lp if lp is not None else "—")
    row("Unreachable nodes",   stats["unreachable_count"],
        _C.YELLOW if stats["unreachable_count"] > 0 else _C.GREEN)

    print(f"  {_C.DIM}│{_C.RESET}")
    print(f"  {_C.DIM}│  {_C.BOLD}Node type distribution:{_C.RESET}")
    for ntype, count in sorted(stats["type_distribution"].items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        print(f"  {_C.DIM}│{_C.RESET}    {ntype:<16s} {count:>3d}  {_C.CYAN}{bar}{_C.RESET}")

    print(f"  {_C.DIM}│{_C.RESET}")
    row("Avg text length",     f"{stats['avg_text_length']:.0f} chars")
    row("Choice label length", f"min={stats['min_label_length']}, max={stats['max_label_length']}, avg={stats['avg_label_length']:.1f}")

    print(f"  {_C.BOLD}{_C.CYAN}└{'─' * 58}┘{_C.RESET}")


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <story.json | stories_dir/>")
        sys.exit(1)

    target = sys.argv[1]

    # Enable ANSI on Windows
    if sys.platform == "win32":
        os.system("")

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

    for fp in files:
        print()
        stats = compute_stats(fp)
        if stats:
            print_stats(stats)

    print()


if __name__ == "__main__":
    main()
