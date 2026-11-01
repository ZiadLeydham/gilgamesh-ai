"""
FastAPI Server for Gilgamesh AI Companion.
Provides:
- Groq Llama 3.3 70B dialogue generation with Fate Canon Persona (Archer + Caster)
- The Royal Tablet: Persistent Long-Term Memory & Relationship Recall
- Dual Voice Engine Support: Local RTX 4050 RVC (Free) & Fish Audio Cloud
- Groq Whisper-large-v3-turbo speech-to-text transcription
- Static web interface (Character.AI style + Live Call mode + Persistent Chat)
"""

import os
import uuid
import asyncio
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from groq import Groq

from persona import GILGAMESH_SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from tts_engine import voice_engine, detect_emotion, DEFAULT_FISH_MODEL_ID
from memory_engine import (
    load_chat_history,
    save_chat_history,
    load_memories,
    save_memories,
    reset_all_memories,
    format_memory_for_system_prompt,
    extract_and_update_memories
)
from cloud_vault import (
    pull_vault_from_github,
    push_vault_to_github
)

# Load environment
ENV_PATH = Path(".env")
load_dotenv(dotenv_path=ENV_PATH)

app = FastAPI(title="Gilgamesh - The King of Heroes")

# Audio cache folder
AUDIO_CACHE = Path("audio_cache")
AUDIO_CACHE.mkdir(exist_ok=True)

class Message(BaseModel):
    role: str
    content: str
    audio_url: Optional[str] = None
    emotion: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Message]] = []
    profile: Optional[str] = "guest"
    pin: Optional[str] = None

class VaultUnlockRequest(BaseModel):
    pin: str

class VaultSyncRequest(BaseModel):
    pin: str
    history: List[dict] = []
    memories: Optional[dict] = None

class SettingsRequest(BaseModel):
    groq_api_key: Optional[str] = None
    voice_engine: Optional[str] = None
    fish_api_key: Optional[str] = None
    fish_model_id: Optional[str] = None
    noise_filter: Optional[bool] = None

def save_env_values(values: dict):
    env_data = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_data[k.strip()] = v.strip()
    
    for k, v in values.items():
        if v is not None:
            env_data[k] = str(v)
            os.environ[k] = str(v)

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for k, v in env_data.items():
            f.write(f"{k}={v}\n")

def get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="GROQ_API_KEY is not set. Please provide it in the settings or .env file."
        )
    return Groq(api_key=api_key)

@app.get("/api/status")
async def get_status():
    groq_key = os.getenv("GROQ_API_KEY", "")
    fish_key = os.getenv("FISH_API_KEY", "")
    engine = os.getenv("VOICE_ENGINE", "rvc")
    fish_model = os.getenv("FISH_MODEL_ID", DEFAULT_FISH_MODEL_ID)
    noise_filter = os.getenv("NOISE_FILTER", "true").lower() == "true"
    return {
        "configured": bool(groq_key and groq_key.strip()),
        "character": "Gilgamesh (Archer & Caster)",
        "voice_engine": engine,
        "has_fish_key": bool(fish_key and fish_key.strip()),
        "fish_model": fish_model,
        "noise_filter": noise_filter,
        "model": "qwen/qwen3.8-27b"
    }

class SyncChronicleRequest(BaseModel):
    history: List[dict] = []
    memories: Optional[dict] = None

@app.get("/api/history")
async def get_history():
    return load_chat_history()

@app.get("/api/export-chronicle")
async def export_chronicle():
    return {
        "history": load_chat_history(),
        "memories": load_memories()
    }

@app.post("/api/sync-chronicle")
async def sync_chronicle(req: SyncChronicleRequest):
    if req.history:
        save_chat_history(req.history)
    if req.memories:
        save_memories(req.memories)
    return {
        "status": "success",
        "message": "The Royal Chronicle has been restored to the Throne.",
        "history_count": len(req.history),
        "has_memories": bool(req.memories)
    }

@app.post("/api/vault/unlock")
async def unlock_vault(req: VaultUnlockRequest):
    ok, data, msg = pull_vault_from_github(req.pin)
    if not ok:
        raise HTTPException(status_code=401, detail=msg)
    return {
        "success": True,
        "message": msg,
        "history": data.get("history", []),
        "memories": data.get("memories", {}),
        "initialized": data.get("initialized", False)
    }

@app.post("/api/vault/sync")
async def sync_vault(req: VaultSyncRequest):
    ok, msg = push_vault_to_github({"history": req.history, "memories": req.memories}, req.pin)
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"success": True, "message": msg}

@app.post("/api/reset-chat")
async def reset_chat():
    reset_all_memories()
    return {"status": "success", "message": "The Royal Vault has sealed the previous audience."}

@app.post("/api/set-settings")
async def set_settings(req: SettingsRequest):
    updates = {}
    if req.groq_api_key is not None and req.groq_api_key.strip():
        updates["GROQ_API_KEY"] = req.groq_api_key.strip()
    if req.voice_engine:
        updates["VOICE_ENGINE"] = req.voice_engine.strip()
    if req.fish_api_key is not None:
        updates["FISH_API_KEY"] = req.fish_api_key.strip()
    if req.fish_model_id is not None:
        updates["FISH_MODEL_ID"] = req.fish_model_id.strip()
    if req.noise_filter is not None:
        updates["NOISE_FILTER"] = "true" if req.noise_filter else "false"

    save_env_values(updates)
    return {"status": "success", "message": "Settings updated successfully."}

@app.post("/api/set-key")
async def set_key(api_key: str = Form(...)):
    api_key = api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Key cannot be empty.")
    save_env_values({"GROQ_API_KEY": api_key})
    return {"status": "success", "message": "Groq API key saved successfully."}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    client = get_groq_client()
    
    profile = (request.profile or "guest").lower()
    is_master = (profile == "master")
    pin = request.pin

    master_memories = None
    if is_master:
        if not pin:
            raise HTTPException(status_code=401, detail="Master Profile requires Royal PIN.")
        ok, vault_data, _ = pull_vault_from_github(pin)
        if ok and isinstance(vault_data, dict):
            master_memories = vault_data.get("memories")

    # 1. Inject persistent long-term memories into system persona
    system_content = GILGAMESH_SYSTEM_PROMPT
    memory_context = format_memory_for_system_prompt(master_memories if is_master else None)
    if memory_context:
        system_content += memory_context

    messages = [{"role": "system", "content": system_content}]
    messages.extend(FEW_SHOT_EXAMPLES)
    
    # 2. Add expanded conversation history (up to last 24 turns)
    for msg in request.history[-24:]:
        messages.append({"role": msg.role, "content": msg.content})
        
    # 3. Add current message
    messages.append({"role": "user", "content": request.message})
    
    try:
        completion = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=messages,
            temperature=0.85,
            max_tokens=600,
            top_p=0.95
        )
        reply_text = completion.choices[0].message.content
        clean_reply, emotion = detect_emotion(reply_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq API Error: {str(e)}")

    # 4. Generate speech
    audio_id = f"gil_{uuid.uuid4().hex[:10]}.mp3"
    audio_path = AUDIO_CACHE / audio_id
    
    engine = os.getenv("VOICE_ENGINE", "rvc")
    fish_key = os.getenv("FISH_API_KEY")
    fish_model = os.getenv("FISH_MODEL_ID")

    noise_filter = os.getenv("NOISE_FILTER", "true").lower() == "true"
    try:
        await voice_engine.synthesize(
            clean_reply,
            str(audio_path),
            emotion=emotion,
            engine=engine,
            fish_api_key=fish_key,
            fish_model_id=fish_model,
            noise_filter=noise_filter
        )
        audio_url = f"/api/audio/{audio_id}"
    except Exception as e:
        print(f"TTS Error: {e}")
        audio_url = None

    # 5. Persist updated chat history
    full_history = []
    for m in request.history:
        full_history.append(m.model_dump())
    full_history.append({"role": "user", "content": request.message})
    full_history.append({"role": "assistant", "content": clean_reply, "audio_url": audio_url, "emotion": emotion})

    if is_master and pin:
        async def on_master_updated(new_memories):
            push_vault_to_github({"history": full_history, "memories": new_memories}, pin)

        asyncio.create_task(extract_and_update_memories(
            client, full_history, existing_memories=master_memories, on_updated=on_master_updated
        ))
    else:
        save_chat_history(full_history)
        asyncio.create_task(extract_and_update_memories(client, full_history))

    return {
        "reply": clean_reply,
        "emotion": emotion,
        "audio_url": audio_url
    }

@app.get("/api/audio/{filename}")
async def get_audio(filename: str):
    file_path = AUDIO_CACHE / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(file_path, media_type="audio/mpeg")

@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Accepts user speech recording and transcribes via Groq Whisper-large-v3-turbo.
    """
    client = get_groq_client()
    
    suffix = Path(file.filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                language="en",
                response_format="json"
            )
        return {"text": transcription.text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Whisper STT Error: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# Static files for the frontend
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)

@app.get("/app-static/{file_path:path}")
async def get_app_static(file_path: str):
    p = static_dir / file_path
    if p.exists() and p.is_file():
        return FileResponse(p)
    return FileResponse(static_dir / "index.html")

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static_dir")
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static_root")

# ZeroGPU hook and Gradio wrapper for Hugging Face Spaces compatibility
try:
    import spaces
    HAS_SPACES = True
except ImportError:
    HAS_SPACES = False

def _zero_gpu_startup_hook(dummy: str) -> str:
    return dummy

if HAS_SPACES:
    _zero_gpu_startup_hook = spaces.GPU(duration=1)(_zero_gpu_startup_hook)

import gradio as gr

with gr.Blocks(title="Gilgamesh - King of Heroes") as demo:
    _inp = gr.Textbox(visible=False)
    _out = gr.Textbox(visible=False)
    _btn = gr.Button("init", visible=False)
    _btn.click(fn=_zero_gpu_startup_hook, inputs=_inp, outputs=_out)
    gr.HTML("""
    <style>
    body, html { margin: 0 !important; padding: 0 !important; height: 100vh !important; width: 100vw !important; overflow: hidden !important; }
    .gradio-container { max-width: 100% !important; margin: 0 !important; padding: 0 !important; border: none !important; }
    footer { display: none !important; }
    #custom-app-frame { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; border: none; z-index: 999999; }
    </style>
    <iframe id="custom-app-frame" src="/app-static/index.html"></iframe>
    """)

# Wrap Gradio's App.create_app to prepend all custom FastAPI endpoints before Gradio routes
_orig_create_app = gr.routes.App.create_app

def _custom_create_app(*args, **kwargs):
    created_app = _orig_create_app(*args, **kwargs)
    created_app.router.routes = app.router.routes + created_app.router.routes
    return created_app

gr.routes.App.create_app = _custom_create_app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        allowed_paths=[str(static_dir.resolve()), str(AUDIO_CACHE.resolve())]
    )
