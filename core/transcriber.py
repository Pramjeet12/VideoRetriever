import os
from subprocess import CalledProcessError, run

import numpy as np
import requests
import whisper
import whisper.audio
from pydub import AudioSegment

from utils.audio_processor import ensure_ffmpeg_tools, get_ffmpeg_dir

# Sarvam's sync STT-translate API rejects audio longer than 30s.
# We slice each chunk into 25s pieces before sending.
SARVAM_PIECE_SECONDS = 25

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text-translate"
SARVAM_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v2.5")

_model = None
_whisper_ffmpeg_patched = False


def ensure_ffmpeg_on_path() -> str:
    ffmpeg_dir = get_ffmpeg_dir()
    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    normalized_parts = {os.path.normcase(part) for part in path_parts}
    if os.path.normcase(ffmpeg_dir) not in normalized_parts:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path
    return ffmpeg_dir


def patch_whisper_ffmpeg() -> None:
    global _whisper_ffmpeg_patched

    if _whisper_ffmpeg_patched:
        return

    ensure_ffmpeg_on_path()
    ffmpeg_exe, _ = ensure_ffmpeg_tools()

    def load_audio_fixed(file: str, sr: int = whisper.audio.SAMPLE_RATE):
        cmd = [
            ffmpeg_exe,
            "-nostdin",
            "-threads",
            "0",
            "-i",
            file,
            "-f",
            "s16le",
            "-ac",
            "1",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sr),
            "-",
        ]
        try:
            out = run(cmd, capture_output=True, check=True).stdout
        except CalledProcessError as e:
            raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e
        return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0

    whisper.audio.load_audio = load_audio_fixed
    _whisper_ffmpeg_patched = True


def load_model():
    global _model

    if _model is None:
        ensure_ffmpeg_on_path()
        patch_whisper_ffmpeg()
        print(f"Loading Whisper model: {WHISPER_MODEL} ...")
        _model = whisper.load_model(WHISPER_MODEL)
        print("Whisper model loaded.")
    return _model


def transcribe_chunk_whisper(chunk_path: str) -> str:
    ensure_ffmpeg_on_path()
    patch_whisper_ffmpeg()
    model = load_model()
    result = model.transcribe(chunk_path, task="transcribe")
    return result["text"]


def _send_to_sarvam(piece_path: str) -> str:
    """Send one <=30s WAV file to Sarvam and return the English transcript."""
    headers = {"api-subscription-key": SARVAM_API_KEY}

    with open(piece_path, "rb") as f:
        files = {"file": (os.path.basename(piece_path), f, "audio/wav")}
        data = {"model": SARVAM_MODEL, "with_diarization": "false"}
        response = requests.post(
            SARVAM_STT_TRANSLATE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )

    if not response.ok:
        print(f"\nSarvam returned {response.status_code}")
        print(f"Response body: {response.text}\n")
        response.raise_for_status()

    return response.json().get("transcript", "")


def transcribe_chunk_sarvam(chunk_path: str) -> str:
    """
    Sarvam sync API only accepts <=30s audio. We split this chunk into
    25-second pieces, send each separately, and join the transcripts.
    """
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set in environment / .env")

    audio = AudioSegment.from_wav(chunk_path)
    piece_ms = SARVAM_PIECE_SECONDS * 1000

    full_text = ""
    total_pieces = (len(audio) + piece_ms - 1) // piece_ms

    for i, start in enumerate(range(0, len(audio), piece_ms)):
        piece = audio[start:start + piece_ms]
        piece_path = f"{chunk_path}_sv_{i}.wav"
        piece.export(piece_path, format="wav")

        try:
            print(f"  -> Sarvam piece {i + 1}/{total_pieces} ...")
            full_text += _send_to_sarvam(piece_path) + " "
        finally:
            if os.path.exists(piece_path):
                os.remove(piece_path)

    return full_text.strip()


def transcribe_chunk(chunk_path: str, language: str = "english") -> str:
    """
    Route one chunk to Whisper or Sarvam depending on language choice.
    - english -> Whisper (local model)
    - hindi / hinglish -> Sarvam (translates to English while transcribing)
    """
    if language.lower() in {"hindi", "hinglish"}:
        print("Using Sarvam for Hindi/Hinglish transcription.")
        return transcribe_chunk_sarvam(chunk_path)
    print("Using Whisper for English transcription.")
    return transcribe_chunk_whisper(chunk_path)


def transcribe_all(chunks: list, language: str = "english") -> str:
    full_transcript = ""
    engine = "Sarvam AI" if language.lower() in {"hindi", "hinglish"} else "Whisper"
    print(f"Using {engine} for transcription.")

    for i, chunk in enumerate(chunks):
        print(f"Transcribing chunk {i + 1}/{len(chunks)}...")
        text = transcribe_chunk(chunk, language=language)
        full_transcript += text + " "

    print("Transcription complete.")
    return full_transcript.strip()
