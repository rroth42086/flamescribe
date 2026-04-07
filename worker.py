#!/usr/bin/env python3
"""
Transcribe Audio - Whisper Worker
==================================
Runs inside the dedicated venv (~/.transcribe_audio_venv).
Called as a subprocess by transcribe_audio.py.
Accepts audio file path + options via CLI args.
Outputs a single JSON object to stdout.

Usage:
    python worker.py --audio /tmp/audio.wav --model base [--language en]
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description='Whisper transcription worker')
    parser.add_argument('--audio',    required=True,  help='Path to audio file')
    parser.add_argument('--model',    default='base',  help='Whisper model size: tiny/base/small/medium/large')
    parser.add_argument('--language', default=None,    help='ISO language code (e.g. "en"), or omit for auto-detect')
    args = parser.parse_args()

    try:
        import whisper
    except ImportError as exc:
        _fail(f'openai-whisper is not installed in this environment: {exc}')

    try:
        model = whisper.load_model(args.model)
    except Exception as exc:
        _fail(f'Failed to load Whisper model "{args.model}": {exc}')

    transcribe_opts = {}
    if args.language and args.language.lower() not in ('none', 'auto'):
        transcribe_opts['language'] = args.language

    try:
        result = model.transcribe(args.audio, **transcribe_opts)
    except Exception as exc:
        _fail(f'Transcription failed: {exc}')

    output = {
        'language': result.get('language', 'unknown'),
        'text':     result['text'].strip(),
        'segments': [
            {
                'id':    seg['id'],
                'start': seg['start'],   # seconds (float)
                'end':   seg['end'],     # seconds (float)
                'text':  seg['text'].strip(),
            }
            for seg in result['segments']
        ],
    }

    print(json.dumps(output))


def _fail(message: str):
    """Write an error JSON to stdout and exit non-zero."""
    print(json.dumps({'error': message}))
    sys.exit(1)


if __name__ == '__main__':
    main()
