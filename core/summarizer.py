import os
from typing import Optional

import requests

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
ENGLISH_OUTPUT_INSTRUCTION = (
    "Always respond in English, even if the transcript is in Hindi or Hinglish. "
    "Translate names, issues, decisions, and questions into natural English while preserving proper nouns."
)


def _chat(prompt: str, system_prompt: str) -> str:
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not set in environment / .env")

    response = requests.post(
        MISTRAL_CHAT_URL,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_title(transcript: str) -> str:
    prompt = (
        "Create a concise, professional meeting title from this transcript. "
        "Return only the title. "
        f"{ENGLISH_OUTPUT_INSTRUCTION}\n\n"
        f"Transcript:\n{transcript}"
    )
    return _chat(
        prompt,
        f"You generate short, clear meeting titles. {ENGLISH_OUTPUT_INSTRUCTION}",
    )


def summarize(transcript: str, context: Optional[str] = None) -> str:
    prompt = (
        "Summarize the following meeting transcript in clear bullet points. "
        "Focus on key topics, outcomes, and next steps. "
        f"{ENGLISH_OUTPUT_INSTRUCTION}"
    )
    if context:
        prompt += f"\n\nExtra context:\n{context}"
    prompt += f"\n\nTranscript:\n{transcript}"

    return _chat(
        prompt,
        f"You create practical, concise meeting summaries. {ENGLISH_OUTPUT_INSTRUCTION}",
    )
