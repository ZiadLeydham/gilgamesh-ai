"""
The Royal Tablet of Destinies: Persistent Long-Term Memory Engine for Gilgamesh.
Maintains and evolves a persistent cognitive model of the mortal user across sessions:
- Key user facts, confessions, and life situation
- Gilgamesh's royal decrees, tough-love advice, and personal judgments
- The dynamic relationship tone (e.g., audacious companion, seeking wisdom, tested warrior)
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional

MEMORY_FILE = Path("memories.json")
CHAT_HISTORY_FILE = Path("chat_history.json")

DEFAULT_MEMORY = {
    "user_facts": [],
    "gilgamesh_judgments": [],
    "relationship_status": "A mortal granted royal audience before the Golden Throne."
}

def load_memories() -> dict:
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading memories: {e}")
    return DEFAULT_MEMORY.copy()

def save_memories(data: dict):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving memories: {e}")

def load_chat_history() -> List[dict]:
    if CHAT_HISTORY_FILE.exists():
        try:
            with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading chat history: {e}")
    return []

def save_chat_history(history: List[dict]):
    try:
        with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving chat history: {e}")

def reset_all_memories():
    save_memories(DEFAULT_MEMORY.copy())
    save_chat_history([])

def format_memory_for_system_prompt() -> str:
    memories = load_memories()
    facts = memories.get("user_facts", [])
    judgments = memories.get("gilgamesh_judgments", [])
    relationship = memories.get("relationship_status", DEFAULT_MEMORY["relationship_status"])

    if not facts and not judgments:
        return ""

    lines = [
        "\n---",
        "### The Royal Tablet of Destinies (Your Long-Term Memories of this Mortal):",
        f"**Dynamic Standing**: {relationship}"
    ]

    if facts:
        lines.append("\n**Known Facts & Desires of this Mortal**:")
        for fact in facts[-6:]:
            lines.append(f"- {fact}")

    if judgments:
        lines.append("\n**Your Decrees & Past Judgments Upon Them**:")
        for j in judgments[-6:]:
            lines.append(f"- {j}")

    lines.append(
        "\n*Instruction*: Seamlessly weave these past memories and relationship history into your dialogue. "
        "Reference their past boldness, their struggles, or past commands naturally like an emperor who forgets nothing."
    )
    return "\n".join(lines)

async def extract_and_update_memories(groq_client, messages: List[dict]):
    """
    Background asynchronous task that analyzes recent dialogue and distills long-term memories.
    """
    if len(messages) < 4:
        return

    existing_memories = load_memories()

    # Build prompt for memory distillation
    recent_dialogue = []
    for m in messages[-10:]:
        role = "User" if m.get("role") == "user" else "Gilgamesh"
        content = m.get("content", "").replace("\n", " ").strip()
        recent_dialogue.append(f"{role}: {content}")

    dialogue_str = "\n".join(recent_dialogue)
    current_json = json.dumps(existing_memories, indent=2)

    prompt = f"""You are the chronicler of Gilgamesh, King of Heroes.
Analyze the ongoing conversation between Gilgamesh and the mortal User, and update the long-term memory record.

Current Memory Record:
{current_json}

Recent Dialogue:
{dialogue_str}

Output a strictly valid JSON object with these 3 keys:
1. "user_facts": Array of 3-6 concise, persistent facts about the user (their life situation, struggles, desires, personality traits). Preserve existing valid ones, update or add new ones.
2. "gilgamesh_judgments": Array of 3-6 concise decrees, tough-love advice, or personal judgments Gilgamesh made about this user.
3. "relationship_status": A single evocative sentence describing Gilgamesh's current personal view of this mortal (e.g. "An audacious mortal who proved their spine and was granted kingly mentorship").

Respond ONLY with the JSON object, with no markdown code fences or conversational filler."""

    try:
        loop = asyncio.get_running_loop()
        def call_groq():
            return groq_client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400
            )

        resp = await loop.run_in_executor(None, call_groq)
        raw_text = resp.choices[0].message.content.strip()
        
        # Clean potential markdown fences
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        new_data = json.loads(raw_text)
        if isinstance(new_data, dict) and "user_facts" in new_data:
            save_memories(new_data)
            print("The Royal Tablet of Destinies updated successfully.")
    except Exception as e:
        print(f"Memory extraction background note: {e}")
