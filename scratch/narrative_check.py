# -*- coding: utf-8 -*-
"""Sample narrative quality from each story - opening, midpoint, and ending nodes."""
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

stories_dir = r"c:\Antigravity help\main bot\Main-bot-with-corrected-stories-main\stories_only_bot\data\stories"

stories = [
    ("fantasy_ash_throne.json", "جنرال الرماد"),
    ("fantasy_cursed_heir.json", "قناع الطاغية"),
    ("fantasy_third_story.json", "وريث النشار"),
]

for filename, title in stories:
    with open(f"{stories_dir}\\{filename}", "r", encoding="utf-8") as f:
        story = json.load(f)
    nodes = story.get("nodes", {})
    
    print(f"\n{'='*80}")
    print(f"  NARRATIVE SAMPLES: {title} ({filename})")
    print(f"{'='*80}")
    
    # 1. Opening node
    start = nodes.get("start", {})
    print(f"\n[OPENING] (type: {start.get('type', '?')})")
    text = start.get("text", "")
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    print(f"  Sentence count: {len(sentences)}")
    print(f"  Text: {text[:300]}...")
    choices = start.get("choices", [])
    print(f"  Choices: {[c.get('label', '') for c in choices]}")
    
    # 2. Midpoint pivot
    midpoint = nodes.get("node_midpoint_pivot", {})
    if midpoint:
        print(f"\n[MIDPOINT PIVOT] (type: {midpoint.get('type', '?')})")
        text = midpoint.get("text", "")
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        print(f"  Sentence count: {len(sentences)}")
        print(f"  Text: {text[:300]}...")
    
    # 3. Sample ending
    ending_nodes = {nid: n for nid, n in nodes.items() if n.get("is_ending") or n.get("type") == "ending"}
    # Pick one death and one survival
    for nid, n in list(ending_nodes.items())[:2]:
        print(f"\n[ENDING: {nid}] (type: {n.get('type', '?')})")
        text = n.get("text", "")
        print(f"  Text: {text[:300]}...")
    
    # 4. Check for sensory details in first 5 non-ending nodes
    print(f"\n[SENSORY CHECK - first 5 nodes]")
    sensory_words = ["رائحة", "صوت", "بارد", "حار", "رطب", "صمت", "تنفس", "عرق", 
                     "يد", "قدم", "نبض", "قلب", "ملمس", "ظلام", "ضوء", "هواء"]
    count = 0
    for nid, n in nodes.items():
        if n.get("type") == "ending":
            continue
        text = n.get("text", "")
        found = [w for w in sensory_words if w in text]
        if count < 5:
            print(f"  {nid}: {found if found else 'NO SENSORY WORDS FOUND'}")
        count += 1
