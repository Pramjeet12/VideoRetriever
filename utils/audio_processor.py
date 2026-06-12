import glob
import os
import re
import shutil
import subprocess
import uuid
import yt_dlp
from pydub import AudioSegment

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _tool_healthy(exe_path: str) -> bool:
    try:
        result = subprocess.run(
            [exe_path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def get_ffmpeg_dir() -> str:
    candidates: list[str] = []

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if ffmpeg_path and ffprobe_path:
        ffmpeg_dir = os.path.dirname(ffmpeg_path)
        ffprobe_dir = os.path.dirname(ffprobe_path)
        if os.path.normcase(ffmpeg_dir) == os.path.normcase(ffprobe_dir):
            candidates.append(ffmpeg_dir)

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        candidates.append(os.path.join(conda_prefix, "Library", "bin"))

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.extend(
            glob.glob(
                os.path.join(
                    local_app_data,
                    "Microsoft",
                    "WinGet",
                    "Packages",
                    "*",
                    "*",
                    "bin",
                )
            )
        )

    for candidate in candidates:
        ffmpeg_exe = os.path.join(candidate, "ffmpeg.exe")
        ffprobe_exe = os.path.join(candidate, "ffprobe.exe")
        if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
            if _tool_healthy(ffmpeg_exe) and _tool_healthy(ffprobe_exe):
                return candidate

    raise RuntimeError("Healthy ffmpeg/ffprobe not found.")


def ensure_ffmpeg_tools() -> tuple[str, str]:
    ffmpeg_dir = get_ffmpeg_dir()
    ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    ffprobe_exe = os.path.join(ffmpeg_dir, "ffprobe.exe")
    return ffmpeg_exe, ffprobe_exe


def clean_title_stem(raw_stem: str) -> str:
    clean_title = re.sub(r"^[0-9a-fA-F]{8}_", "", raw_stem)
    clean_title = re.sub(r"[<>:\"/\\\\|?*]", " ", clean_title)
    clean_title = clean_title.replace("_", " ")
    clean_title = re.sub(r"\s+", " ", clean_title).strip().rstrip(".")
    return clean_title


def download_youtube_audio(url: str) -> str:
    output_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex[:8]}_%(title)s.%(ext)s")
    ffmpeg_dir = get_ffmpeg_dir()
    ydl_opts = {
        "format": "140/139/251/250/249/bestaudio/best",
        "outtmpl": output_path,
        "ffmpeg_location": ffmpeg_dir,
        "proxy": "",
        "windowsfilenames": True,
        "trim_file_name": 180,
        "nopart": True,
        "overwrites": True,
        "fixup": "never",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_file = ydl.prepare_filename(info)

    title_stem = os.path.splitext(os.path.basename(downloaded_file))[0]
    clean_title = clean_title_stem(title_stem)
    clean_downloaded_file = os.path.join(
        DOWNLOAD_DIR,
        f"{clean_title}{os.path.splitext(downloaded_file)[1]}",
    )
    if os.path.normcase(downloaded_file) != os.path.normcase(clean_downloaded_file):
        try:
            if not os.path.exists(clean_downloaded_file):
                os.replace(downloaded_file, clean_downloaded_file)
            else:
                os.remove(downloaded_file)
        except OSError:
            clean_downloaded_file = downloaded_file

    return clean_downloaded_file


def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to 16kHz mono WAV."""
    ffmpeg_exe, _ = ensure_ffmpeg_tools()
    title_stem = os.path.splitext(os.path.basename(input_path))[0]
    clean_title = clean_title_stem(title_stem)
    output_path = os.path.join(DOWNLOAD_DIR, f"{clean_title}_converted.wav")
    subprocess.run(
        [ffmpeg_exe, "-y", "-i", input_path, "-ac", "1", "-ar", "16000", output_path],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return output_path


def chunk_audio(wav_path: str, chunk_minutes: int = 10) -> list[str]:
    audio = AudioSegment.from_wav(wav_path)
    chunk_ms = chunk_minutes * 60 * 1000
    chunks: list[str] = []

    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start:start + chunk_ms]
        chunk_path = f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path, format="wav")
        chunks.append(chunk_path)

    return chunks


def process_input(source: str, chunk_minutes: int = 10) -> list[str]:
    if source.startswith(("http://", "https://")):
        print("Detected YouTube URL. Downloading audio...")
        downloaded_path = download_youtube_audio(source)
        print("Converting downloaded audio to WAV...")
        wav_path = convert_to_wav(downloaded_path)
    else:
        if not os.path.exists(source):
            raise FileNotFoundError(f"Input file not found: {source}")
        print("Detected local file. Converting to WAV...")
        wav_path = convert_to_wav(source)

    print("Chunking audio...")
    chunks = chunk_audio(wav_path, chunk_minutes=chunk_minutes)
    print(f"Audio ready - {len(chunks)} chunk(s) created.")
    return chunks
