"""Thin wrappers over the Sarvam SDK (LLM, STT, TTS)."""
import json
import re

from sarvamai import SarvamAI

from config import DATA_DIR, LLM_CHAT_MODEL, LLM_TASK_FALLBACK, LLM_TASK_MODEL, SARVAM_API_KEY, STT_MODEL, TTS_MODEL, TTS_SPEAKER

_client = None
TTS_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}


def client():
    global _client
    if _client is None:
        if not SARVAM_API_KEY:
            raise RuntimeError("SARVAM_API_KEY is not set (.env)")
        _client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    return _client


def chat(messages, model=LLM_CHAT_MODEL, max_tokens=400, temperature=0.4, tools=None):
    """tools: pass when the history contains tool calls/results (the API requires it); no new tool calls are made."""
    kw = {"tools": tools, "tool_choice": "none"} if tools else {}
    r = client().chat.completions(model=model, messages=messages, max_tokens=max_tokens, temperature=temperature, **kw)
    raw = r.choices[0].message.content or ""
    text = re.sub(r"<think>.*?(</think>|$)", "", raw, flags=re.S).strip()
    if not text:   # diagnose intermittent empty completions (seen as "technical dikkat" fallbacks)
        print(f"[sarvam.chat] empty reply: finish={r.choices[0].finish_reason} raw_len={len(raw)} "
              f"reasoning_len={len(r.choices[0].message.reasoning_content or '')}", flush=True)
    return text


def chat_tools(messages, tools, model=LLM_CHAT_MODEL, max_tokens=400, temperature=0.4):
    """One LLM call that may return tool calls. Returns (text, tool_calls) where tool_calls = [(id, name, args_dict)]."""
    r = client().chat.completions(model=model, messages=messages, tools=tools, tool_choice="auto",
                                  max_tokens=max_tokens, temperature=temperature)
    m = r.choices[0].message
    calls = []
    for tc in m.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append((tc.id, tc.function.name, args))
    text = re.sub(r"<think>.*?(</think>|$)", "", m.content or "", flags=re.S).strip()
    return text, calls


def chat_json(messages, required=("summary",)):
    """JSON-mode call on the fast model; falls back to the reasoning model if the output is unusable."""
    for model, kw in ((LLM_TASK_MODEL, {"max_tokens": 1500}),
                      (LLM_TASK_FALLBACK, {"max_tokens": 4000, "reasoning_effort": "low"})):
        try:
            r = client().chat.completions(model=model, messages=messages, temperature=0.1,
                                          response_format={"type": "json_object"}, **kw)
            m = re.search(r"\{.*\}", r.choices[0].message.content or "", re.S)
            data = json.loads(m.group(0)) if m else {}
            if all(data.get(k) for k in required):
                return data
        except Exception as e:
            print(f"chat_json {model} failed:", e)
    return {}


def stt(audio_bytes, filename="audio.webm", codec=None):
    kw = {"file": (filename, audio_bytes), "model": STT_MODEL, "mode": "transcribe", "language_code": "unknown"}
    if codec:
        kw["input_audio_codec"] = codec
    r = client().speech_to_text.transcribe(**kw)
    return r.transcript or "", r.language_code or "unknown"


VOICE_FILE = DATA_DIR / "voice.json"


def current_voice():
    """The bot's voice: data/voice.json (set from the /voices page) or config defaults."""
    try:
        v = json.loads(VOICE_FILE.read_text())
        return v["model"], v["speaker"]
    except Exception:
        return TTS_MODEL, TTS_SPEAKER


def set_voice(model, speaker):
    VOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    VOICE_FILE.write_text(json.dumps({"model": model, "speaker": speaker}))


def tts(text, language_code="hi-IN", speaker=None):
    """Returns base64 WAV in the voice chosen on the /voices page."""
    lang = language_code if language_code in TTS_LANGS else "en-IN"
    if re.search(r"[ऀ-ॿ]", text):     # Devanagari present -> Hindi voice
        lang = "hi-IN"
    model, default_speaker = current_voice()
    r = client().text_to_speech.convert(text=text[:2400], language_code=lang, model=model, speaker=speaker or default_speaker)
    return r.audios[0]
