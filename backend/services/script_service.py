"""
Script generation service.
Primary: Ollama local LLM (if running).
Fallback: Groq API free tier (needs GROQ_API_KEY in .env).
Last resort: smart template engine.
"""
import os
import re
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


async def generate_script(prompt: str, video_type: str, duration: int) -> str:
    # Try Ollama first
    script = await _try_ollama(prompt, video_type, duration)
    if script:
        return script

    # Try Groq free API (user sets GROQ_API_KEY in .env — free at console.groq.com)
    if GROQ_API_KEY:
        script = await _try_groq(prompt, video_type, duration)
        if script:
            return script

    # Smart fallback
    return _smart_script(prompt, video_type, duration)


async def _try_ollama(prompt: str, video_type: str, duration: int) -> str:
    words = int(duration * 2.3)
    system = f"""You are a professional short-form video scriptwriter.
Write a {duration}-second spoken script (~{words} words) about: {prompt}
Rules:
- Start with a strong hook (question or bold statement)
- Speak directly to viewer, use "you"
- No stage directions, no [brackets], no asterisks
- Natural conversational tone
- End with a call to action
Output ONLY the spoken words."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": system, "stream": False,
                      "options": {"temperature": 0.75, "num_predict": words + 60}},
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
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "You write short video scripts. Output only spoken words, no stage directions."},
                        {"role": "user", "content": f"Write a {duration}-second video script (~{words} words) about: {prompt}. Start with a hook, be conversational, end with call to action."}
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
    """
    Generates a real, specific, engaging script using the user's prompt.
    Far better than a generic fallback — uses the prompt words directly.
    """
    topic = prompt.strip().rstrip(".")
    words_needed = int(duration * 2.3)

    # Build a structured script around the actual topic
    hook_templates = [
        f"Let me tell you something about {topic} that most people completely get wrong.",
        f"If you want to understand {topic}, you need to hear this first.",
        f"Here is the truth about {topic} that nobody is talking about.",
        f"I spent a long time figuring out {topic}, and here is what I learned.",
        f"Stop what you are doing — because what I am about to share about {topic} will change how you think.",
    ]

    body_templates = [
        f"When it comes to {topic}, the most important thing to understand is that it is not as complicated as it seems. "
        f"Most people overthink it. The real secret is consistency and taking small steps every single day. "
        f"You do not need to be perfect. You just need to start and keep going no matter what.",

        f"The thing about {topic} is that it affects every area of your life, whether you realize it or not. "
        f"Once you start paying attention to it, you will notice changes faster than you ever expected. "
        f"The key is to focus on progress, not perfection, and celebrate every small win along the way.",

        f"A lot of people struggle with {topic} because they are missing just one or two key things. "
        f"And once you figure those out, everything else starts to fall into place. "
        f"It really is that simple — and I want to break it down for you in a way that is easy to apply starting today.",
    ]

    cta_templates = [
        "If this was helpful, follow me for more. And drop a comment telling me what you want to learn next.",
        "Try this for just seven days and watch what happens. Follow for more videos like this.",
        "Save this video so you can come back to it. And follow me — I post practical tips every week.",
    ]

    import hashlib
    seed = int(hashlib.md5(topic.encode()).hexdigest(), 16)

    hook = hook_templates[seed % len(hook_templates)]
    body = body_templates[(seed // 3) % len(body_templates)]
    cta = cta_templates[(seed // 7) % len(cta_templates)]

    script = f"{hook} {body} {cta}"

    # Trim or extend to roughly match duration
    words = script.split()
    if len(words) > words_needed:
        script = " ".join(words[:words_needed])
    elif len(words) < words_needed - 10:
        extra = (
            f" Remember, learning about {topic} is a journey, not a destination. "
            f"Take it one step at a time and trust the process."
        )
        script += extra

    return script


def _clean(text: str) -> str:
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\*+.*?\*+', '', text)
    text = re.sub(r'^(Script:|Narrator:|Host:)\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n+', ' ', text)
    return text.strip()
