# -*- coding: utf-8 -*-
"""
Comprehensive quality audit script for Nexus stories.
Checks against the Post-Write Self-Audit from the nexus-story-writer skill v4.
"""
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

stories_dir = r"c:\Antigravity help\main bot\Main-bot-with-corrected-stories-main\stories_only_bot\data\stories"

stories_to_check = [
    "fantasy_ash_throne.json",
    "fantasy_cursed_heir.json",
    "fantasy_third_story.json"
]

def count_json_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return len(f.readlines())

def shortest_path_to_node(nodes, start, target):
    """BFS shortest path from start to target."""
    from collections import deque
    visited = {start}
    queue = deque([(start, 0)])
    while queue:
        current, depth = queue.popleft()
        if current == target:
            return depth
        if current in nodes:
            for choice in nodes[current].get("choices", []):
                nxt = choice.get("next")
                if nxt and nxt not in visited and nxt in nodes:
                    visited.add(nxt)
                    queue.append((nxt, depth + 1))
    return float('inf')

def count_parents(nodes):
    """Count how many parent nodes point to each node."""
    parent_count = defaultdict(int)
    for node_id, node in nodes.items():
        for choice in node.get("choices", []):
            nxt = choice.get("next")
            if nxt:
                parent_count[nxt] += 1
    return parent_count

def audit_story(filename):
    path = os.path.join(stories_dir, filename)
    print(f"\n{'='*80}")
    print(f"  QUALITY AUDIT: {filename}")
    print(f"{'='*80}")
    
    with open(path, "r", encoding="utf-8") as f:
        story = json.load(f)
    
    nodes = story.get("nodes", {})
    start = story.get("start_scene", "start")
    spine = story.get("spine", {})
    flags_def = story.get("flags", [])
    total_nodes = len(nodes)
    json_lines = count_json_lines(path)
    
    issues = []
    warnings = []
    passes = []
    
    # ==================== STRUCTURAL ====================
    print("\n--- STRUCTURAL CHECKS ---")
    
    # Node count
    if total_nodes >= 100:
        passes.append(f"✅ Node count: {total_nodes} (Flagship: 100+ required)")
    elif total_nodes >= 55:
        passes.append(f"✅ Node count: {total_nodes} (Medium: 55+ required)")
    elif total_nodes >= 30:
        passes.append(f"✅ Node count: {total_nodes} (Short: 30+ required)")
    else:
        issues.append(f"❌ Node count: {total_nodes} (minimum 30 required)")
    
    # JSON lines
    if json_lines >= 1000:
        passes.append(f"✅ JSON lines: {json_lines} (Flagship: 1000+ required)")
    elif json_lines >= 750:
        passes.append(f"✅ JSON lines: {json_lines} (Medium: 750+ required)")
    elif json_lines >= 600:
        passes.append(f"✅ JSON lines: {json_lines} (Short: 600+ required)")
    else:
        issues.append(f"❌ JSON lines: {json_lines} (minimum 600 required)")
    
    # Type field
    missing_type = [nid for nid, n in nodes.items() if "type" not in n]
    if missing_type:
        issues.append(f"❌ Nodes missing 'type' field: {missing_type[:5]}")
    else:
        passes.append("✅ All nodes have 'type' field")
    
    # Empty text
    empty_text = [nid for nid, n in nodes.items() if not n.get("text", "").strip()]
    if empty_text:
        issues.append(f"❌ Nodes with empty text: {empty_text[:5]}")
    else:
        passes.append("✅ All nodes have non-empty text")
    
    # Choice label length (under 40 chars)
    long_labels = []
    for nid, n in nodes.items():
        for c in n.get("choices", []):
            label = c.get("label", "")
            if len(label) > 40:
                long_labels.append((nid, label, len(label)))
    if long_labels:
        issues.append(f"❌ {len(long_labels)} choice labels over 40 chars:")
        for nid, label, ln in long_labels[:5]:
            issues.append(f"   → {nid}: \"{label[:50]}...\" ({ln} chars)")
    else:
        passes.append("✅ All choice labels are under 40 characters")
    
    # Spine check
    spine_fields = ["wound", "lie", "trigger", "complication", "revelation", "verdict"]
    missing_spine = [f for f in spine_fields if not spine.get(f)]
    if missing_spine:
        issues.append(f"❌ Missing spine fields: {missing_spine}")
    else:
        passes.append("✅ Full spine present (wound, lie, trigger, complication, revelation, verdict)")
    
    # ==================== FLAGS ====================
    print("\n--- FLAG CHECKS ---")
    
    flags_set = {}  # flag_name -> [nodes that set it]
    flags_required = {}  # flag_name -> [nodes that require it]
    
    for nid, n in nodes.items():
        for c in n.get("choices", []):
            sf = c.get("sets_flag")
            if sf:
                flags_set.setdefault(sf, []).append(nid)
            rf = c.get("requires_flag")
            if rf:
                flags_required.setdefault(rf, []).append(nid)
    
    # Orphan flags (set but never required)
    orphan_flags = [f for f in flags_set if f not in flags_required]
    if orphan_flags:
        warnings.append(f"⚠️ Flags set but never required (orphans): {orphan_flags}")
    else:
        if flags_set:
            passes.append(f"✅ All {len(flags_set)} set flags are required somewhere")
        else:
            warnings.append("⚠️ No flags are set at all in this story")
    
    # Required but never set
    unset_flags = [f for f in flags_required if f not in flags_set]
    if unset_flags:
        issues.append(f"❌ Flags required but never set: {unset_flags}")
    else:
        if flags_required:
            passes.append("✅ All required flags are set somewhere")
    
    # ==================== BRANCHES ====================
    print("\n--- BRANCH CHECKS ---")
    
    # Trap nodes (both choices → same destination)
    trap_nodes = []
    for nid, n in nodes.items():
        choices = n.get("choices", [])
        if len(choices) >= 2:
            targets = set(c.get("next") for c in choices)
            if len(targets) == 1:
                trap_nodes.append(nid)
    if trap_nodes:
        issues.append(f"❌ Trap nodes (all choices → same destination): {trap_nodes}")
    else:
        passes.append("✅ No trap nodes found")
    
    # Death timing check
    endings = {nid: n for nid, n in nodes.items() 
               if n.get("is_ending") or n.get("type") == "ending"}
    death_endings = {nid: n for nid, n in endings.items() 
                     if "موت" in n.get("text", "") or "تموت" in n.get("text", "") 
                     or "يموت" in n.get("text", "") or "death" in nid.lower()
                     or "صريع" in n.get("text", "") or "مقتل" in n.get("text", "")}
    survival_endings = {nid: n for nid, n in endings.items() if nid not in death_endings}
    
    early_deaths = []
    for death_id in death_endings:
        dist = shortest_path_to_node(nodes, start, death_id)
        if dist < 5:
            early_deaths.append((death_id, dist))
    
    if early_deaths:
        issues.append(f"❌ Death endings reachable in < 5 choices:")
        for did, d in early_deaths:
            issues.append(f"   → {did}: reachable in {d} choices")
    else:
        passes.append(f"✅ No death ending reachable in fewer than 5 choices")
    
    # Death ratio
    num_deaths = len(death_endings)
    num_survivals = len(survival_endings)
    if num_survivals > 0 and num_deaths > 2 * num_survivals:
        issues.append(f"❌ Death ratio too high: {num_deaths} deaths vs {num_survivals} survivals (max 2:1)")
    else:
        passes.append(f"✅ Death ratio OK: {num_deaths} deaths, {num_survivals} survivals")
    
    # Convergence check: nodes reachable from >3 parents in first 70%
    parent_counts = count_parents(nodes)
    # Estimate first 70% by BFS order
    from collections import deque
    bfs_order = []
    visited = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        bfs_order.append(current)
        if current in nodes:
            for c in nodes[current].get("choices", []):
                nxt = c.get("next")
                if nxt and nxt not in visited and nxt in nodes:
                    visited.add(nxt)
                    queue.append(nxt)
    
    cutoff_70 = int(len(bfs_order) * 0.7)
    first_70 = set(bfs_order[:cutoff_70])
    mega_hubs = [nid for nid in first_70 if parent_counts.get(nid, 0) > 3]
    if mega_hubs:
        warnings.append(f"⚠️ Mega-hub nodes in first 70% (>3 parents): {mega_hubs[:5]}")
        for mh in mega_hubs[:3]:
            warnings.append(f"   → {mh}: {parent_counts[mh]} parent nodes")
    else:
        passes.append("✅ No mega-hub convergence nodes in first 70%")
    
    # ==================== PACING ====================
    print("\n--- PACING CHECKS ---")
    
    type_counts = defaultdict(int)
    for nid, n in nodes.items():
        type_counts[n.get("type", "unknown")] += 1
    
    breath_count = type_counts.get("breath", 0)
    if breath_count >= 3:
        passes.append(f"✅ Breath nodes: {breath_count} (minimum 3)")
    else:
        warnings.append(f"⚠️ Only {breath_count} breath nodes found (minimum 3 recommended)")
    
    revelation_count = type_counts.get("revelation", 0)
    passes.append(f"ℹ️ Node type distribution: {dict(type_counts)}")
    
    # ==================== NARRATIVE ====================
    print("\n--- NARRATIVE CHECKS ---")
    
    # Retry message check
    endings_missing_retry = []
    retry_msg = "يمكنك المحاولة مجدداً"
    for nid, n in endings.items():
        text = n.get("text", "")
        if retry_msg not in text:
            endings_missing_retry.append(nid)
    if endings_missing_retry:
        issues.append(f"❌ {len(endings_missing_retry)} endings missing retry message: {endings_missing_retry[:5]}")
    else:
        passes.append(f"✅ All {len(endings)} endings contain the retry message")
    
    # Text length check (sentences per node)
    short_nodes = []
    for nid, n in nodes.items():
        if n.get("is_ending") or n.get("type") == "ending":
            continue
        text = n.get("text", "")
        # Rough sentence count by splitting on Arabic period/full stop
        sentences = [s.strip() for s in text.replace(".", ".").split(".") if s.strip()]
        if len(sentences) < 3:
            short_nodes.append((nid, len(sentences)))
    if short_nodes:
        warnings.append(f"⚠️ {len(short_nodes)} non-ending nodes with fewer than 3 sentences:")
        for nid, sc in short_nodes[:5]:
            warnings.append(f"   → {nid}: {sc} sentences")
    else:
        passes.append("✅ All non-ending nodes have 3+ sentences")
    
    # ==================== ENDING QUALITY ====================
    print("\n--- ENDING QUALITY CHECKS ---")
    
    # Check for flag callbacks in endings (looking for conditional patterns)
    endings_without_callbacks = []
    for nid, n in endings.items():
        text = n.get("text", "")
        # Since our JSON doesn't use conditional text, check if the ending
        # references player actions meaningfully
        has_callback = False
        callback_words = ["لأنك", "بسبب", "تتذكر", "تركت", "اخترت", "رفضت", "قبلت", 
                         "ضحيت", "خيانتك", "جبنك", "شجاعتك", "تضحيتك", "قرارك"]
        for word in callback_words:
            if word in text:
                has_callback = True
                break
        if not has_callback:
            endings_without_callbacks.append(nid)
    
    if endings_without_callbacks:
        warnings.append(f"⚠️ {len(endings_without_callbacks)} endings may lack choice-reference callbacks: {endings_without_callbacks[:5]}")
    else:
        passes.append("✅ All endings appear to reference player choices")
    
    # ==================== SUMMARY ====================
    print("\n--- RESULTS ---")
    for p in passes:
        print(f"  {p}")
    for w in warnings:
        print(f"  {w}")
    for i in issues:
        print(f"  {i}")
    
    total_issues = len([x for x in issues if x.startswith("❌")])
    total_warnings = len([x for x in warnings if x.startswith("⚠️")])
    total_passes = len([x for x in passes if x.startswith("✅")])
    
    print(f"\n  SCORE: {total_passes} passes, {total_warnings} warnings, {total_issues} critical issues")
    return total_issues, total_warnings

# Run audit on all stories
grand_issues = 0
grand_warnings = 0
for f in stories_to_check:
    i, w = audit_story(f)
    grand_issues += i
    grand_warnings += w

print(f"\n{'='*80}")
print(f"  GRAND TOTAL: {grand_issues} critical issues, {grand_warnings} warnings")
print(f"{'='*80}")
