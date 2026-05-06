"""
Script generation service.
Primary: Ollama local LLM (if running).
Fallback: Groq API free tier (needs GROQ_API_KEY in .env).
Last resort: smart template engine.
Supports Hinglish / Hindi-English mixed scripts.
"""
import os
import re
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

_HINGLISH_KEYWORDS = {
    "hinglish", "hindi", "indian", "hindi english", "hinglish language",
    "hindi mein", "hindi me", "hindi mai", "bolna", "bolo",
}


def _detect_hinglish(prompt: str) -> bool:
    p = prompt.lower()
    return any(k in p for k in _HINGLISH_KEYWORDS)


def _make_system_prompt(prompt: str, video_type: str, duration: int) -> str:
    words = int(duration * 2.3)
    is_hinglish = _detect_hinglish(prompt)

    if is_hinglish:
        lang_note = (
            "Write in Hinglish (Hindi-English mix): use simple English words but Hindi sentence structure. "
            "Example style: 'Aaj hum baat karenge HTTP aur HTTPS ke baare mein. "
            "Basically, HTTP matlab hypertext transfer protocol — ye data transfer karta hai without encryption...'"
        )
    else:
        lang_note = "Write in clear conversational English."

    return f"""You are a professional short-form video scriptwriter.
Write a {duration}-second spoken script (~{words} words) about: {prompt}
{lang_note}
Rules:
- Start with a strong hook (question or bold statement)
- Speak directly to viewer ("aap" in Hindi, "you" in English)
- No stage directions, no [brackets], no asterisks, no headers
- Natural, conversational tone as if speaking to a friend
- End with a call to action
Output ONLY the spoken words, nothing else."""


async def generate_script(prompt: str, video_type: str, duration: int) -> str:
    script = await _try_ollama(prompt, video_type, duration)
    if script:
        return script

    if GROQ_API_KEY:
        script = await _try_groq(prompt, video_type, duration)
        if script:
            return script

    return _smart_script(prompt, video_type, duration)


async def _try_ollama(prompt: str, video_type: str, duration: int) -> str:
    words = int(duration * 2.3)
    system = _make_system_prompt(prompt, video_type, duration)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": system,
                    "stream": False,
                    "options": {"temperature": 0.75, "num_predict": words + 60},
                },
            )
            if r.status_code == 200:
                text = r.json().get("response", "").strip()
                text = _clean(text)
                if len(text.split()) > 20:
                    return text
    except Exception:
        pass
    return ""


async def _try_groq(prompt: str, video_type: str, duration: int) -> str:
    words = int(duration * 2.3)
    is_hinglish = _detect_hinglish(prompt)
    lang_instruction = (
        "Write in Hinglish (Hindi-English mix) — casual Indian tone."
        if is_hinglish
        else "Write in clear conversational English."
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {
                            "role": "system",
                            "content": f"You write short video scripts. Output only spoken words, no stage directions. {lang_instruction}",
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Write a {duration}-second video script (~{words} words) about: {prompt}. "
                                f"Start with a hook, be conversational, end with call to action."
                            ),
                        },
                    ],
                    "max_tokens": words + 80,
                    "temperature": 0.7,
                },
            )
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"]["content"].strip()
                return _clean(text)
    except Exception:
        pass
    return ""


def _smart_script(prompt: str, video_type: str, duration: int) -> str:
    topic = prompt.strip().rstrip(".")
    words_needed = int(duration * 2.3)
    is_hinglish = _detect_hinglish(topic)

    # Strip language instructions from topic for cleaner display
    clean_topic = re.sub(
        r'\s*\b(in hinglish language|in hindi english|hinglish language|in hinglish|in hindi|hindi me|hindi mein)\b',
        '', topic, flags=re.IGNORECASE
    )
    clean_topic = re.sub(r'\s*\blanguage\b\s*$', '', clean_topic, flags=re.IGNORECASE)
    clean_topic = clean_topic.strip().rstrip(",. ").strip()
    if not clean_topic:
        clean_topic = topic

    if is_hinglish:
        hooks = [
            f"Yaar, {clean_topic} ke baare mein ek baat batata hoon jo bahut log miss kar dete hain.",
            f"Aaj hum baat karenge {clean_topic} ke baare mein — aur main guarantee karta hoon ye helpful hoga.",
            f"Ek simple question — kya aap {clean_topic} ke baare mein sach jaanna chahte ho?",
            f"Dekho, {clean_topic} itna bhi complicated nahi hai jitna log samajhte hain.",
        ]
        bodies = [
            (
                f"Basically, {clean_topic} ek aisi cheez hai jo aapki life mein daily use hoti hai. "
                f"Pehli baat — iska concept bilkul simple hai. "
                f"Aap directly apne browser mein ya apne kaam mein dekh sakte ho. "
                f"Jab aap isko properly samajh lete ho, toh baaki sab automatically clear ho jaata hai. "
                f"Isliye step by step socho aur ek ek cheez ko practically try karo."
            ),
            (
                f"Toh {clean_topic} ka main concept ye hai: ye real world mein kaise kaam karta hai. "
                f"Bahut saare log sirf theory padhte hain, lekin practical side pe dhyan nahi dete. "
                f"Aur wahi sabse important part hai. "
                f"Jab aap hands-on try karte ho, tab concepts mind mein permanently set ho jaate hain. "
                f"So dosto, sirf padhna nahi — actually implement karo."
            ),
        ]
        ctas = [
            "Agar ye helpful laga toh like karo aur follow karo aur comment mein batao aur kya jaanna chahte ho.",
            "Aage bhi aisi videos ke liye follow karo. Apna feedback zaroor do comments mein.",
        ]
    else:
        hooks = [
            f"Let me tell you something about {clean_topic} that most people completely get wrong.",
            f"If you want to truly understand {clean_topic}, you need to hear this first.",
            f"Here is the truth about {clean_topic} that nobody talks about.",
            f"I spent a long time figuring out {clean_topic} — here is exactly what I learned.",
        ]
        bodies = [
            (
                f"When it comes to {clean_topic}, the most important thing to understand is that it is not as complicated as it seems. "
                f"Most people overthink it. The real key is understanding the core concept and applying it consistently. "
                f"Once you grasp the fundamentals, everything else falls into place naturally. "
                f"Start small, be consistent, and focus on real-world application over theory."
            ),
            (
                f"The thing about {clean_topic} is that it affects your work every single day, whether you realize it or not. "
                f"Once you start paying attention to the details, you will see improvements faster than you ever expected. "
                f"The key is to focus on progress over perfection, and to practice what you learn immediately."
            ),
        ]
        ctas = [
            "If this was helpful, follow me for more. Drop a comment telling me what you want to learn next.",
            "Save this video and try it out. Follow for more practical content every week.",
        ]

    import hashlib
    seed = int(hashlib.md5(clean_topic.encode()).hexdigest(), 16)
    hook = hooks[seed % len(hooks)]
    body = bodies[(seed // 3) % len(bodies)]
    cta = ctas[(seed // 7) % len(ctas)]

    script = f"{hook} {body} {cta}"

    words = script.split()
    if len(words) > words_needed:
        script = " ".join(words[:words_needed])
    elif len(words) < words_needed - 15:
        if is_hinglish:
            extra = f" Yaad rakho, {clean_topic} ek journey hai. Ek ek step uthao aur trust karo process ko."
        else:
            extra = f" Remember, mastering {clean_topic} is a journey. Take it one step at a time and trust the process."
        script += extra

    return script


def _clean(text: str) -> str:
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\*+.*?\*+', '', text)
    text = re.sub(r'^(Script:|Narrator:|Host:|Speaker:)\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n+', ' ', text)
    return text.strip()
