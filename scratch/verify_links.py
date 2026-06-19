import json
import os
import sys

# Reconfigure stdout to use UTF-8
sys.stdout.reconfigure(encoding='utf-8')

stories_to_check = [
    "fantasy_ash_throne.json",
    "fantasy_cursed_heir.json",
    "fantasy_third_story.json"
]

stories_dir = r"c:\Antigravity help\main bot\Main-bot-with-corrected-stories-main\stories_only_bot\data\stories"

for filename in stories_to_check:
    path = os.path.join(stories_dir, filename)
    print(f"\n--- Checking {filename} ---")
    if not os.path.exists(path):
        print(f"ERROR: {filename} does not exist at {path}!")
        continue
    
    with open(path, "r", encoding="utf-8") as f:
        try:
            story = json.load(f)
        except Exception as e:
            print(f"ERROR parsing JSON: {e}")
            continue
            
    title = story.get("title", "No Title")
    start_scene = story.get("start_scene", "start")
    nodes = story.get("nodes", {})
    
    print(f"Title: {title}")
    print(f"Start Scene: {start_scene}")
    print(f"Number of nodes: {len(nodes)}")
    
    # 1. Check start scene exists
    if start_scene not in nodes:
        print(f"ERROR: Start scene '{start_scene}' not found in nodes!")
        
    # 2. Check for missing/broken targets
    broken_links = 0
    endings_count = 0
    for node_id, node in nodes.items():
        is_ending = node.get("is_ending", False) or node.get("type") == "ending"
        if is_ending:
            endings_count += 1
            
        choices = node.get("choices", [])
        for choice in choices:
            next_node = choice.get("next")
            if not next_node:
                print(f"ERROR in {node_id}: choice lacks 'next' key!")
                broken_links += 1
            elif next_node not in nodes:
                print(f"ERROR in {node_id}: points to missing node '{next_node}'!")
                broken_links += 1
                
    print(f"Endings: {endings_count}")
    print(f"Broken links: {broken_links}")
    
    # 3. Reachability analysis
    visited = set()
    queue = [start_scene]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        if current in nodes:
            choices = nodes[current].get("choices", [])
            for choice in choices:
                next_node = choice.get("next")
                if next_node and next_node in nodes:
                    queue.append(next_node)
                    
    unreachable = [n for n in nodes if n not in visited]
    print(f"Reachable nodes: {len(visited)} / {len(nodes)}")
    if unreachable:
        print(f"WARNING: {len(unreachable)} unreachable nodes: {unreachable[:10]}...")
    else:
        print("SUCCESS: All nodes are reachable from start!")

print("\nValidation complete.")
