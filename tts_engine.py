"""
TTS Engine for Gilgamesh Voice Synthesis.
Features:
1. ElevenLabs-style Multi-Emotion Synthesis:
   - Parses inline emotion directives like (angry), (calm), (amused), (solemn), (haughty), (whispering).
   - Synthesizes each sentence chunk with targeted prosody & RVC pitch/volume dynamics.
   - Stitches chunks together with tight, natural human pacing (no awkward or robotic pauses).
2. Dual Engine Support:
   - Local RTX 4050 GPU (Applio RVC v2 + Edge-TTS) - 100% Free & Infinite.
   - Fish Audio Cloud Engine (fish.audio Gilgamesh models).
"""

import re
import os
import io
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple

import edge_tts
import soundfile as sf
import numpy as np
from scipy import signal
from fishaudio import AsyncFishAudio
from fishaudio.types.tts import TTSConfig, Prosody

ROOT_DIR = Path(__file__).parent.resolve()
APPLIO_PYTHON = ROOT_DIR / "Applio" / "env" / "python.exe"
APPLIO_CORE = ROOT_DIR / "Applio" / "core.py"
MODEL_PTH = ROOT_DIR / "models" / "david_vincent" / "david_vincent.pth"
MODEL_INDEX = ROOT_DIR / "models" / "david_vincent" / "david_vincent.index"

DEFAULT_FISH_MODEL_ID = "c8f17f6f069a44c2a0b617a3f3d9298f"

# Emotion Profiles tailored for David Vincent's Gilgamesh performance
EMOTION_PROFILES = {
    "angry": {
        "voice": "en-US-GuyNeural",
        "rate": "+14%",
        "pitch_tts": "+4Hz",
        "volume": "+25%",
        "rvc_pitch": 2,          # Shifts pitch up into aggressive shouting register
        "volume_envelope": 0.85  # Dynamic shouting peaks
    },
    "furious": {
        "voice": "en-US-GuyNeural",
        "rate": "+18%",
        "pitch_tts": "+6Hz",
        "volume": "+35%",
        "rvc_pitch": 3,
        "volume_envelope": 0.92
    },
    "amused": {
        "voice": "en-US-GuyNeural",
        "rate": "+8%",
        "pitch_tts": "+2Hz",
        "volume": "+12%",
        "rvc_pitch": 1,
        "volume_envelope": 0.65
    },
    "calm": {
        "voice": "en-US-GuyNeural",
        "rate": "+0%",
        "pitch_tts": "-1Hz",
        "volume": "+0%",
        "rvc_pitch": 0,
        "volume_envelope": 0.35
    },
    "haughty": {
        "voice": "en-US-GuyNeural",
        "rate": "+2%",
        "pitch_tts": "+0Hz",
        "volume": "+6%",
        "rvc_pitch": 0,
        "volume_envelope": 0.45
    },
    "solemn": {
        "voice": "en-US-GuyNeural",
        "rate": "-4%",
        "pitch_tts": "-3Hz",
        "volume": "-4%",
        "rvc_pitch": -1,         # Deep sovereign baritone
        "volume_envelope": 0.35
    },
    "whispering": {
        "voice": "en-US-GuyNeural",
        "rate": "-4%",
        "pitch_tts": "-2Hz",
        "volume": "-8%",
        "rvc_pitch": -1,
        "volume_envelope": 0.25
    },
    "neutral": {
        "voice": "en-US-GuyNeural",
        "rate": "+0%",
        "pitch_tts": "+0Hz",
        "volume": "+0%",
        "rvc_pitch": 0,
        "volume_envelope": 0.35
    }
}

def strip_roleplay_actions_only(text: str) -> str:
    """
    Cleverly strips roleplay stage directions (e.g. *He sighs softly.*) while
    preserving words with asterisks used for emphasis/italics (e.g. *see*, *exist*, *is*).
    """
    # 1. Any asterisks inside quotes are strictly emphasis: strip the asterisks, keep the words
    def de_asterisk_quotes(m):
        return re.sub(r"\*+", "", m.group(0))

    cleaned = re.sub(r'"[^"]*"', de_asterisk_quotes, text)
    cleaned = re.sub(r'“[^”]*”', de_asterisk_quotes, cleaned)

    action_indicators = [
        'he ', 'she ', 'his ', 'her ', 'smirk', 'laugh', 'chuckle', 'sigh',
        'recline', 'gaze', 'glance', 'look', 'stand', 'turn', 'nod', 'frown',
        'wave', 'closes', 'eyes', 'sets down', 'swirling'
    ]

    def handle_outer_asterisks(m):
        inner = m.group(1).strip()
        words = inner.split()
        lower = inner.lower()
        if len(words) <= 2 and not any(v in lower for v in action_indicators):
            return inner  # It's an emphasized word: keep it for speech!
        return ''  # It's a stage direction: omit it for speech

    cleaned = re.sub(r"\*+(.*?)\*+", handle_outer_asterisks, cleaned)

    # 3. Handle unclosed asterisks (e.g. truncated generation: *He looks at you...)
    if cleaned.strip().startswith("*"):
        match = re.search(r'["\[\(]', cleaned)
        if match:
            cleaned = cleaned[match.start():]
        else:
            cleaned = ""

    return cleaned.strip()

def clean_spoken_line(text: str) -> str:
    """
    Cleans an individual spoken line for tight, fluid, natural cadence:
    - Removes roleplay actions in asterisks (*smirks*) while keeping emphasized words (*see* -> see).
    - Removes all quotes.
    - Replaces dramatic ellipses with a simple single comma or space to prevent dead pauses.
    - Normalizes double punctuation (!! -> !).
    """
    cleaned = strip_roleplay_actions_only(text)
    cleaned = re.sub(r'["\'`]', '', cleaned)
    
    # Replace ellipses with a natural short breath (comma) or space
    cleaned = re.sub(r"\.{2,}", ",", cleaned)
    
    # Avoid duplicate punctuation that causes artificial TTS gaps
    cleaned = re.sub(r"!{2,}", "!", cleaned)
    cleaned = re.sub(r"\?{2,}", "?", cleaned)
    cleaned = re.sub(r",+", ",", cleaned)
    
    # Trim and normalize spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def parse_emotional_segments(text: str) -> List[Tuple[str, str]]:
    """
    Parses text with inline emotion tags in either [...] or (...):
    e.g. *He laughs.* [laughing] "FUHAHAHA!" [calm] "Speak." [angry] "Silence!"
    Returns list of (emotion, clean_spoken_text).
    """
    pattern = r'[\(\[]([a-zA-Z\s,]+)[\)\]]'
    
    # Strip asterisks actions while preserving emphasized words (*see* -> see)
    speech_text = strip_roleplay_actions_only(text)
    
    splits = re.split(pattern, speech_text)
    segments = []
    
    first_chunk = clean_spoken_line(splits[0])
    idx = 1
    current_emotion = "haughty"
    
    if first_chunk:
        segments.append((current_emotion, first_chunk))
        
    while idx < len(splits):
        tag = splits[idx].strip().lower()
        content = clean_spoken_line(splits[idx+1]) if idx+1 < len(splits) else ""
        
        if any(k in tag for k in ["ang", "furi", "rage", "mad"]):
            emo = "angry"
        elif any(k in tag for k in ["amus", "laugh", "cheer", "chuckle"]):
            emo = "amused"
        elif any(k in tag for k in ["calm", "neut", "peace"]):
            emo = "calm"
        elif any(k in tag for k in ["solemn", "sad", "weary", "sigh"]):
            emo = "solemn"
        elif any(k in tag for k in ["whisp", "tempt"]):
            emo = "whispering"
        elif any(k in tag for k in ["haught", "disdain", "arrog", "proud"]):
            emo = "haughty"
        else:
            emo = None
            
        if emo:
            if content:
                segments.append((emo, content))
        else:
            if segments and content:
                last_emo, last_txt = segments[-1]
                segments[-1] = (last_emo, f"{last_txt} {content}")
            elif content:
                segments.append((current_emotion, content))
        idx += 2
        
    # If no tags matched or empty, fallback
    if not segments:
        cleaned_fallback = clean_spoken_line(speech_text)
        if not cleaned_fallback:
            cleaned_fallback = "Hmph."
        # Auto-detect general mood
        lower_raw = speech_text.lower()
        if any(w in lower_raw for w in ["fuhahaha", "hahaha", "laugh"]):
            emo = "amused"
        elif any(w in lower_raw for w in ["you dare", "insolent", "cur", "bastard", "wretch", "die"]):
            emo = "angry"
        elif any(w in lower_raw for w in ["enkidu", "weariness", "five thousand years"]):
            emo = "solemn"
        else:
            emo = "haughty"
        segments.append((emo, cleaned_fallback))
        
    return segments

def detect_emotion(text: str) -> Tuple[str, str]:
    """
    Returns (cleaned_display_text, dominant_emotion).
    Leaves inline emotion tags intact for rich UI formatting, while identifying dominant emotion.
    """
    lower = text.lower()
    if any(k in lower for k in ["[furious]", "[angry]", "(furious)", "(angry)", "you dare", "insolent", "cur!", "bastard"]):
        dominant = "angry"
    elif any(k in lower for k in ["[amused]", "[laughing]", "[laughter]", "(amused)", "(laughing)", "fuhahaha"]):
        dominant = "amused"
    elif any(k in lower for k in ["[solemn]", "(solemn)", "[sigh]", "enkidu", "weariness"]):
        dominant = "solemn"
    elif any(k in lower for k in ["[whispering]", "[whisper]", "(whispering)", "pleasure and sin"]):
        dominant = "whispering"
    elif any(k in lower for k in ["[calm]", "(calm)"]):
        dominant = "calm"
    else:
        dominant = "haughty"

    return text.strip(), dominant

async def generate_base_speech(text: str, output_path: str, profile: dict):
    """
    Generates clean base speech via Edge-TTS with natural human pacing.
    """
    spoken = clean_spoken_line(text)
    if not spoken:
        spoken = "Hmph."

    communicate = edge_tts.Communicate(
        text=spoken,
        voice=profile["voice"],
        rate=profile.get("rate", "+0%"),
        pitch=profile.get("pitch_tts", "+0Hz"),
        volume=profile.get("volume", "+0%")
    )
    await communicate.save(output_path)
    return output_path

def convert_with_rvc(input_wav: str, output_mp3: str, profile: dict, export_format: str = "MP3") -> bool:
    """
    Executes Applio's core.py infer CLI using embedded CUDA environment on RTX 4050.
    """
    if not (APPLIO_PYTHON.exists() and APPLIO_CORE.exists() and MODEL_PTH.exists() and MODEL_INDEX.exists()):
        return False

    pitch = str(profile.get("rvc_pitch", 0))
    volume_envelope = str(profile.get("volume_envelope", 0.45))

    cmd = [
        str(APPLIO_PYTHON),
        str(APPLIO_CORE),
        "infer",
        "--input-path", str(input_wav),
        "--output-path", str(output_mp3),
        "--pth-path", str(MODEL_PTH),
        "--index-path", str(MODEL_INDEX),
        "--f0-method", "rmvpe",
        "--protect", "0.33",
        "--index-rate", "0.68",
        "--volume-envelope", volume_envelope,
        "--pitch", pitch,
        "--export-format", export_format
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        return os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000
    except Exception as e:
        print(f"RVC Inference error: {e}")
        return False

def clean_and_master_audio(audio_bytes: bytes, output_path: str, noise_filter: bool = True):
    """
    Acoustic Mastering for Neural Speech:
    - If noise_filter is True:
      1. Cuts out-of-band vocoder phase noise & hash (>11.5 kHz) using a transparent 4th-order Butterworth filter.
      2. Peak-normalizes to -1.0 dBFS (0.89) to eliminate intersample clipping on headphones/DACs during loud shouting.
      3. Encodes to clean MP3 without lossy pre-echo.
    - If noise_filter is False:
      Saves the raw audio stream directly as returned by the neural model.
    """
    if not noise_filter:
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        return

    try:
        with io.BytesIO(audio_bytes) as bio:
            data, sr = sf.read(bio)
            
        if data.ndim > 1:
            data = np.mean(data, axis=1)

        # Gentle Butterworth lowpass filter at 11.5 kHz (cuts out-of-band vocoder rasp while preserving 100% of vocal presence)
        sos = signal.butter(4, 11500, btype='lowpass', fs=sr, output='sos')
        cleaned = signal.sosfiltfilt(sos, data)

        # Peak normalization with -1.0 dBFS headroom
        peak = np.max(np.abs(cleaned))
        if peak > 0:
            cleaned = cleaned * (0.89 / peak)

        sf.write(output_path, cleaned, sr, format='MP3')
    except Exception as e:
        print(f"Mastering note: {e}, writing raw audio stream.")
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

def format_for_fish_audio(text: str, noise_filter: bool = True) -> str:
    """
    Direct Native Fish Audio S2 / S2.1 Pipeline with Vocoder Noise Mitigation:
    - Strips actions in asterisks (*smirks*).
    - Removes quotes and duplicate punctuation (?! -> ?).
    - If noise_filter is True: translates screeching rage tags ([furious], [screaming]) -> [cold fury] / [venomous].
      This avoids pushing the neural vocoder into distorted screeching/hash while preserving David Vincent's deep, terrifying regal anger.
    - If noise_filter is False: preserves raw tags exactly as generated.
    - Preserves native cues ([laughing], [arrogant laughter], [calm], [whispering], [solemn], [sigh], [haughty]).
    """
    # 1. Remove roleplay actions while preserving emphasized dialogue words (*see* -> see)
    clean = strip_roleplay_actions_only(text)

    # 2. Convert any remaining parentheses emotion tags to Fish square brackets
    clean = re.sub(r"\(([a-zA-Z\s,]+)\)", r"[\1]", clean)

    # 3. Soften screeching rage tags to cold regal fury if filter enabled
    if noise_filter:
        def tune_rage(m):
            tag = m.group(1).lower()
            if any(w in tag for w in ["furi", "rage", "scream", "mad"]):
                return "[cold fury]"
            if "ang" in tag:
                return "[venomous]"
            return f"[{m.group(1)}]"
        clean = re.sub(r"\[([a-zA-Z\s,]+)\]", tune_rage, clean)

    # 4. Strip quotes
    clean = re.sub(r'["\'`]', '', clean)

    # 5. Normalize duplicate punctuation that causes vocoder clicks
    clean = re.sub(r"[?!]{2,}", "?", clean)
    clean = re.sub(r"!{2,}", "!", clean)
    clean = re.sub(r"\.{2,}", ", ", clean)

    # 6. Clean up redundant spaces
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

async def synthesize_fish_audio(
    text: str,
    output_path: str,
    api_key: str,
    model_id: Optional[str] = None,
    noise_filter: bool = True
) -> bool:
    directed_text = format_for_fish_audio(text, noise_filter=noise_filter)
    if not directed_text:
        directed_text = "Hmph."

    target_model = model_id or DEFAULT_FISH_MODEL_ID
    requested_format = "wav" if noise_filter else "mp3"

    try:
        async with AsyncFishAudio(api_key=api_key) as client:
            try:
                # Request lossless WAV if noise_filter is active, else raw MP3
                audio_bytes = await client.tts.convert(
                    text=directed_text,
                    reference_id=target_model,
                    model="s2.1-pro-free",
                    format=requested_format
                )
            except Exception as e:
                print(f"Fish Audio s2.1-pro-free fallback: {e}")
                audio_bytes = await client.tts.convert(
                    text=directed_text,
                    reference_id=target_model,
                    format=requested_format
                )
            
            clean_and_master_audio(audio_bytes, output_path, noise_filter=noise_filter)

        return os.path.exists(output_path) and os.path.getsize(output_path) > 500
    except Exception as e:
        print(f"Fish Audio synthesis error: {e}")
        return False

class VoicePipeline:
    def _stitch_audio_files(self, input_files: List[str], output_path: str, pause_sec: float = 0.06):
        """
        Concatenates audio files with a tight, natural human pause (~60ms).
        Prevents robotic dead air between sentence transitions.
        """
        all_data = []
        target_sr = None

        for f in input_files:
            if not os.path.exists(f) or os.path.getsize(f) == 0:
                continue
            data, sr = sf.read(f)
            if target_sr is None:
                target_sr = sr

            # Standardize mono
            if data.ndim > 1:
                data = np.mean(data, axis=1)

            all_data.append(data)
            # Ultra-short natural breath gap (60ms)
            if pause_sec > 0:
                silence = np.zeros(int(target_sr * pause_sec), dtype=data.dtype)
                all_data.append(silence)

        if all_data:
            # Remove trailing pause
            if pause_sec > 0:
                all_data = all_data[:-1]
            combined = np.concatenate(all_data)
            sf.write(output_path, combined, target_sr, format="MP3")

    async def _synthesize_single_segment(
        self,
        text: str,
        output_path: str,
        emotion: str = "haughty",
        engine: str = "rvc",
        fish_api_key: Optional[str] = None,
        fish_model_id: Optional[str] = None,
        export_format: str = "MP3"
    ) -> bool:
        # Route 1: Fish Audio
        effective_fish_key = fish_api_key or os.getenv("FISH_API_KEY")
        if engine == "fish_audio" and effective_fish_key and effective_fish_key.strip():
            target_model = fish_model_id or os.getenv("FISH_MODEL_ID") or DEFAULT_FISH_MODEL_ID
            success = await synthesize_fish_audio(text, output_path, api_key=effective_fish_key.strip(), model_id=target_model)
            if success:
                return True

        # Route 2: Local RTX 4050 RVC
        profile = EMOTION_PROFILES.get(emotion, EMOTION_PROFILES["haughty"])
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_base:
            base_wav = tmp_base.name

        try:
            await generate_base_speech(text, base_wav, profile)
            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(None, convert_with_rvc, base_wav, output_path, profile, export_format)
            if not success:
                await generate_base_speech(text, output_path, profile)
            return True
        finally:
            if os.path.exists(base_wav):
                try:
                    os.remove(base_wav)
                except:
                    pass

    async def synthesize(
        self,
        text: str,
        output_path: str,
        emotion: str = "haughty",
        engine: str = "rvc",
        fish_api_key: Optional[str] = None,
        fish_model_id: Optional[str] = None,
        noise_filter: bool = True
    ) -> str:
        # Route 1: Fish Audio Fast Cloud Generation (Single call for full natural paragraph)
        effective_fish_key = fish_api_key or os.getenv("FISH_API_KEY")
        if engine == "fish_audio" and effective_fish_key and effective_fish_key.strip():
            target_model = fish_model_id or os.getenv("FISH_MODEL_ID") or DEFAULT_FISH_MODEL_ID
            success = await synthesize_fish_audio(
                text,
                output_path,
                api_key=effective_fish_key.strip(),
                model_id=target_model,
                noise_filter=noise_filter
            )
            if success:
                return output_path
            print("Fish Audio cloud generation failed; falling back to Local RTX 4050 RVC.")

        # Route 2: ElevenLabs-style Multi-Emotion Segmentation for Local GPU
        segments = parse_emotional_segments(text)

        # Single segment fast-path
        if len(segments) <= 1:
            emo, seg_text = segments[0] if segments else (emotion, text)
            await self._synthesize_single_segment(
                seg_text, output_path, emotion=emo, engine=engine,
                fish_api_key=fish_api_key, fish_model_id=fish_model_id,
                export_format="MP3"
            )
            return output_path

        # Multi-segment pipeline
        temp_files = []
        try:
            for emo, seg_text in segments:
                if not seg_text.strip():
                    continue
                temp_seg = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
                temp_files.append(temp_seg)
                await self._synthesize_single_segment(
                    seg_text, temp_seg, emotion=emo, engine=engine,
                    fish_api_key=fish_api_key, fish_model_id=fish_model_id,
                    export_format="WAV"
                )

            # Stitch with ultra-tight, natural 60ms breath pause (no robotic dead air)
            self._stitch_audio_files(temp_files, output_path, pause_sec=0.06)
            return output_path
        finally:
            for tf in temp_files:
                if os.path.exists(tf):
                    try:
                        os.remove(tf)
                    except:
                        pass

voice_engine = VoicePipeline()
