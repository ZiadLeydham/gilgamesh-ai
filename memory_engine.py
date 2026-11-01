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

def format_memory_for_system_prompt(custom_memories: Optional[dict] = None) -> str:
    memories = custom_memories if custom_memories is not None else load_memories()
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
        for fact in facts[-8:]:
            lines.append(f"- {fact}")

    if judgments:
        lines.append("\n**Your Decrees & Past Judgments Upon Them**:")
        for j in judgments[-8:]:
            lines.append(f"- {j}")

    lines.append(
        "\n*Instruction*: Seamlessly weave these past memories and relationship history into your dialogue. "
        "Reference their past boldness, their struggles, or past commands naturally like an emperor who forgets nothing."
    )
    return "\n".join(lines)

async def extract_and_update_memories(
    groq_client,
    messages: List[dict],
    existing_memories: Optional[dict] = None,
    on_updated = None
) -> Optional[dict]:
    """
    Background asynchronous task that analyzes recent dialogue and distills long-term memories.
    """
    if len(messages) < 2:
        return None

    memories_to_update = existing_memories if existing_memories is not None else load_memories()

    # Build prompt for memory distillation
    recent_dialogue = []
    for m in messages[-14:]:
        role = "User" if m.get("role") == "user" else "Gilgamesh"
        content = m.get("content", "").replace("\n", " ").strip()
        recent_dialogue.append(f"{role}: {content}")

    dialogue_str = "\n".join(recent_dialogue)
    current_json = json.dumps(memories_to_update, indent=2)

    prompt = f"""You are the royal chronicler of Gilgamesh, King of Heroes.
Analyze the ongoing conversation between Gilgamesh and the mortal User, and update the long-term memory record (The Royal Tablet of Destinies).

Current Memory Record:
{current_json}

Recent Dialogue:
{dialogue_str}

Output a strictly valid JSON object with these 3 keys:
1. "user_facts": Array of up to 8 concise, persistent facts about the user (their life situation, struggles, desires, personality traits, secrets shared). Preserve existing valid ones, update or add new ones.
2. "gilgamesh_judgments": Array of up to 8 concise decrees, tough-love advice, challenges, or personal judgments Gilgamesh made about this user.
3. "relationship_status": A single evocative sentence describing Gilgamesh's current personal view of this mortal (e.g. "An audacious mortal whose spine has proven worthy of royal amusement and guidance").

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
            if existing_memories is None:
                save_memories(new_data)
            if on_updated and callable(on_updated):
                res = on_updated(new_data)
                if asyncio.iscoroutine(res):
                    await res
            print("The Royal Tablet of Destinies updated successfully.")
            return new_data
        return None
    except Exception as e:
        print(f"Memory extraction background note: {e}")
        return None
