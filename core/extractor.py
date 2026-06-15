import os

import requests

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
ENGLISH_OUTPUT_INSTRUCTION = (
    "Always respond in English, even if the transcript is in Hindi or Hinglish. "
    "Translate extracted content into natural English while preserving proper nouns."
)


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 120) -> requests.Response:
    session = requests.Session()
    session.trust_env = False
    return session.post(url, headers=headers, json=payload, timeout=timeout)


def _chat(prompt: str, system_prompt: str) -> str:
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not set in environment / .env")

    response = _post_json(
        MISTRAL_CHAT_URL,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        payload={
            "model": MISTRAL_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        },
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def extract_action_items(transcript: str) -> str:
    prompt = (
        "Extract only explicit action items or requested next steps from this meeting transcript. "
        "Use bullet points. Include owner and deadline only if clearly stated. "
        "Do not include open questions, concerns, risks, or general discussion points. "
        f"{ENGLISH_OUTPUT_INSTRUCTION}\n\n"
        f"Transcript:\n{transcript}"
    )
    return _chat(prompt, f"You extract practical action items from meetings. {ENGLISH_OUTPUT_INSTRUCTION}")


def extract_key_decisions(transcript: str) -> str:
    prompt = (
        "Extract only the decisions that were actually made in this meeting transcript. "
        "Return concise bullet points. Do not include proposed actions, unresolved questions, "
        "or speculative statements. "
        f"{ENGLISH_OUTPUT_INSTRUCTION}\n\n"
        f"Transcript:\n{transcript}"
    )
    return _chat(prompt, f"You extract clear decisions from meetings. {ENGLISH_OUTPUT_INSTRUCTION}")


def extract_questions(transcript: str) -> str:
    prompt = (
        "Extract only unresolved open questions from this meeting transcript. "
        "Return bullet points phrased as real questions. "
        "Do not include action items, demands, recommendations, decisions, or generic follow-ups unless they are explicitly framed as unanswered questions. "
        f"{ENGLISH_OUTPUT_INSTRUCTION}\n\n"
        f"Transcript:\n{transcript}"
    )
    return _chat(prompt, f"You extract only unresolved questions from meetings. {ENGLISH_OUTPUT_INSTRUCTION}")


def extract_meeting_insights(transcript: str) -> dict[str, str]:
    prompt = (
        "Read the meeting transcript and return exactly three sections using this plain format:\n"
        "ACTION_ITEMS:\n"
        "- bullet points only for explicit action items or requested next steps\n\n"
        "KEY_DECISIONS:\n"
        "- bullet points only for decisions that were actually made\n\n"
        "OPEN_QUESTIONS:\n"
        "- bullet points only for unresolved questions\n\n"
        "Rules:\n"
        "- Keep everything in English\n"
        "- Do not add any extra heading or explanation outside these three sections\n"
        "- Do not mix action items, decisions, and questions with each other\n"
        "- If a section has nothing, write a single bullet: - None clearly stated\n\n"
        f"Transcript:\n{transcript}"
    )
    raw = _chat(
        prompt,
        "You extract structured meeting insights with clean section formatting. "
        f"{ENGLISH_OUTPUT_INSTRUCTION}",
    )

    sections = {
        "ACTION_ITEMS": "- None clearly stated",
        "KEY_DECISIONS": "- None clearly stated",
        "OPEN_QUESTIONS": "- None clearly stated",
    }

    current_section = None
    buffer: list[str] = []

    def flush_section() -> None:
        nonlocal buffer, current_section
        if current_section:
            text = "\n".join(line for line in buffer if line.strip()).strip()
            sections[current_section] = text or "- None clearly stated"
        buffer = []

    for line in raw.splitlines():
        stripped = line.strip()
        if stripped in sections:
            flush_section()
            current_section = stripped
            continue
        if current_section:
            buffer.append(line.rstrip())

    flush_section()

    return {
        "action_items": sections["ACTION_ITEMS"],
        "key_decisions": sections["KEY_DECISIONS"],
        "open_questions": sections["OPEN_QUESTIONS"],
    }
