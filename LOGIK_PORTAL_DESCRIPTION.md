# Transcribe Audio

Transcribe any audio or video segment on the Flame timeline directly to SRT subtitles,
sequence markers, and/or a Flame captions track — powered entirely by OpenAI Whisper
running locally on your machine. No internet connection required after setup.
No API keys. No subscription. Your media never leaves your workstation.

## What it does

Right-click any segment in the timeline and choose:

    Logik → Transcribe Audio → Transcribe Selected Segment

A dialog opens where you choose:

- **Whisper model** — tiny / base / small / medium / large (larger = slower but more accurate)
- **Language** — auto-detect or specify (English, Spanish, French, German, Italian,
  Portuguese, Dutch, Russian, Chinese, Japanese, Korean, Arabic)
- **Output options:**
  - **SRT File** — written alongside the source media, ready for delivery or import anywhere
  - **Timeline Markers** — one marker per caption line, placed at the correct timecode
    on the sequence, with the transcript text as the marker comment
  - **Captions Track** — imports the SRT directly as a Flame subtitle track

## Requirements

- Flame 2026 on macOS
- Homebrew (`brew install ffmpeg` and `brew install python@3.12`)
- ~2 GB disk space for the Whisper environment (one-time download)

## Setup

Run once from the Flame main menu:

    Logik → Transcribe Audio → Setup Whisper Environment

This creates a self-contained Python virtual environment at `~/.transcribe_audio_venv`
and installs Whisper + PyTorch. Flame will be unresponsive for several minutes while
packages download. After that it's instant.

## Notes

- Transcription speed depends on your hardware and model size.
  On Apple Silicon, PyTorch uses the CPU by default with this build.
  The `base` model typically transcribes a 1-minute clip in under 30 seconds.
- The Whisper environment is per-user (`~/.transcribe_audio_venv`).
  Each workstation user needs to run Setup once.
- The SRT file is written to the same folder as the source media by default.
  You can change the path in the dialog.
