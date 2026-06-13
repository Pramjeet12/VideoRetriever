import os

import requests

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
ENGLISH_OUTPUT_INSTRUCTION = (
    "Always respond in English, even if the transcript is in Hindi or Hinglish. "
    "Translate extracted content into natural English while preserving proper nouns."
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
