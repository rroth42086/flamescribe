# flamescribe

Local AI transcription for Autodesk Flame. Right-click any timeline segment and
transcribe its audio to an SRT file, sequence markers, and/or a Flame captions
track — powered by OpenAI Whisper running entirely on your workstation.

No internet connection required after setup. No API keys. No subscription.
Your media never leaves your machine.

---

## What it does

**Right-click any timeline segment → Logik → Transcribe Audio → Transcribe Selected Segment**

A dialog lets you choose:

| Option | Description |
|--------|-------------|
| Whisper Model | `tiny` `base` `small` `medium` `large` — larger is slower but more accurate |
| Language | Auto-detect or specify (13 languages supported) |
| SRT File | Written alongside the source media |
| Timeline Markers | One marker per caption line at the correct timecode |
| Captions Track | Imported directly as a Flame subtitle track |

---

## Requirements

- Autodesk Flame 2026, macOS
- [Homebrew](https://brew.sh)
- ffmpeg: `brew install ffmpeg`
- Python 3.12: `brew install python@3.12`
- ~2 GB disk space for the Whisper environment (one-time download)
- [Logik Portal](https://logik-portal.com) installed (provides the PyFlame UI library)

---

## Installation

Copy the `transcribe_audio` folder to your Flame Python hooks directory:

```bash
cp -r transcribe_audio /opt/Autodesk/shared/python/
```

Then in Flame, rescan hooks:

**Flame Main Menu → Python → Rescan Python Hooks**

---

## Setup (one-time per user)

**Flame Main Menu → Logik → Transcribe Audio → Setup Whisper Environment**

This creates a self-contained Python virtual environment at `~/.transcribe_audio_venv`
and installs Whisper + PyTorch. Flame will be unresponsive for a few minutes while
packages download (~2 GB). After that it's ready permanently.

Each workstation user needs to run this once.

---

## File structure

```
transcribe_audio/
    transcribe_audio.py     Flame hook — runs inside Flame's Python
    worker.py               Whisper runner — runs inside the dedicated venv
    README.md               This file
    LOGIK_PORTAL_DESCRIPTION.md   Portal listing copy
    DEVELOPMENT_NOTES.md    How this was built — techniques for the community
```

---

## For developers: how this was built

See [`DEVELOPMENT_NOTES.md`](DEVELOPMENT_NOTES.md) for a detailed walkthrough of
every technique used — including how to probe undocumented Boost.Python C++ APIs,
isolate heavy dependencies from Flame's bundled Python, deal with Homebrew's PATH
disappearing in subprocesses, and navigate Flame 2026's timeline object model.

Useful reading for anyone building Flame hooks that go beyond the basics.

---

## Acknowledgements

- [OpenAI Whisper](https://github.com/openai/whisper)
- [Logik Portal](https://logik-portal.com) — PyFlame UI library and community
- Developed with the Logik community in mind
