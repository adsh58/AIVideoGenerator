import httpx
import re
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


async def generate_script(prompt: str, video_type: str, duration: int) -> str:
    """Generate a video script using Ollama local LLM."""
    type_guidelines = {
        "short": f"Write a very concise, punchy script for a {duration}-second short video.",
        "reel": f"Write an engaging, hook-first script for a {duration}-second Instagram/YouTube Reel.",
        "long": f"Write a structured, informative script for a {duration}-second video with clear intro, body, and outro.",
    }

    guideline = type_guidelines.get(video_type, type_guidelines["reel"])
    words_estimate = int(duration * 2.5)  # ~150 words/min speaking rate

    system_prompt = f"""You are a professional video script writer.
{guideline}
Target approximately {words_estimate} words — NO MORE.
Write naturally spoken dialogue only. No stage directions, no scene descriptions, no [brackets].
Start immediately with the hook. Be conversational and engaging."""

    user_message = f"Write a video script about: {prompt}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"{system_prompt}\n\n{user_message}",
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": words_estimate + 50},
                },
            )
            if response.status_code == 200:
                data = response.json()
                script = data.get("response", "").strip()
                script = _clean_script(script)
                return script if script else _fallback_script(prompt, duration)
    except Exception:
        pass

    return _fallback_script(prompt, duration)


def _clean_script(text: str) -> str:
    """Remove stage directions, brackets, and non-spoken content."""
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\*.*?\*', '', text)
    text = re.sub(r'#.*?\n', '\n', text)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return ' '.join(lines)


def _fallback_script(prompt: str, duration: int) -> str:
    """Simple fallback if Ollama is not running."""
    words = int(duration * 2.5)
    return (
        f"Today, I want to talk about {prompt}. "
        "This is something that truly matters, and I believe understanding it "
        "can make a real difference in your life. "
        "Let me break this down in a way that's simple and actionable. "
        "The key insight here is that when we approach this topic with an open mind, "
        "we start to see possibilities that were always there but perhaps overlooked. "
        "So whether you're just starting out or looking to go deeper, "
        "I hope this gives you something valuable to take away. "
        "Thanks for watching, and I'll see you in the next one."
    )[:words * 5]
