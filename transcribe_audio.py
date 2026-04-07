# Transcribe Audio
# Copyright (c) 2026
#
# Flame 2026 | macOS
# Right-click a timeline segment → Logik → Transcribe Audio
#
# Outputs: SRT file, Flame timeline markers, and/or Flame captions track.
# Transcription runs locally via openai-whisper in a dedicated venv.
#
# One-time setup:
#   Flame Main Menu → Logik → Transcribe Audio → Setup Whisper Environment

# =========================================================================== #
# Imports
# =========================================================================== #

import json
import os
import subprocess
import sys
import tempfile

# Make PyFlame UI classes available from the installed logik_portal library.
sys.path.insert(0, '/opt/Autodesk/shared/python/logik_portal')
from pyflame_lib_logik_portal import (
    MessageType,
    Style,
    PyFlameDialogWindow,
    PyFlameLabel,
    PyFlameLineEdit,
    PyFlameMessageWindow,
    PyFlameProgressWindow,
    PyFlamePushButton,
    PyFlamePushButtonMenu,
)

from PySide6 import QtWidgets

# =========================================================================== #
# Constants
# =========================================================================== #

SCRIPT_NAME    = 'Transcribe Audio'
SCRIPT_VERSION = 'v1.0.0'

VENV_PATH      = os.path.expanduser('~/.transcribe_audio_venv')
VENV_PYTHON    = os.path.join(VENV_PATH, 'bin', 'python')
WORKER_SCRIPT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'worker.py')

WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large']

# Display name → ISO code (None = auto-detect)
LANGUAGE_OPTIONS = [
    'Auto Detect', 'English', 'Spanish', 'French', 'German',
    'Italian', 'Portuguese', 'Dutch', 'Russian',
    'Chinese', 'Japanese', 'Korean', 'Arabic',
]
LANGUAGE_CODES = {
    'Auto Detect': None,
    'English':     'en',
    'Spanish':     'es',
    'French':      'fr',
    'German':      'de',
    'Italian':     'it',
    'Portuguese':  'pt',
    'Dutch':       'nl',
    'Russian':     'ru',
    'Chinese':     'zh',
    'Japanese':    'ja',
    'Korean':      'ko',
    'Arabic':      'ar',
}

# =========================================================================== #
# Utility helpers
# =========================================================================== #

def venv_ready():
    return os.path.isfile(VENV_PYTHON)


def find_ffmpeg():
    for candidate in ('/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg'):
        if os.path.isfile(candidate):
            return candidate
    result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
    return result.stdout.strip() or None


def find_system_python():
    # Prefer versions with known-good PyTorch/Whisper support.
    # Python 3.14 is too new — torch wheels may not exist yet.
    preferred = [
        'python3.12', 'python3.11', 'python3.13', 'python3.10',
    ]
    search_dirs = ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin']
    for version in preferred:
        for directory in search_dirs:
            candidate = os.path.join(directory, version)
            if os.path.isfile(candidate):
                return candidate
    # Fall back to whatever python3 resolves to on PATH.
    result = subprocess.run(['which', 'python3'], capture_output=True, text=True)
    return result.stdout.strip() or None


def seconds_to_srt_time(seconds):
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def parse_frame_rate(fr):
    return float(str(fr).split()[0])


def timecode_to_seconds(tc, fps):
    """
    Convert a Flame timecode value (PyTime or string HH:MM:SS:FF) to seconds.
    Returns 0.0 if conversion fails.
    """
    try:
        s = str(tc).strip()
        parts = s.replace(';', ':').split(':')
        if len(parts) == 4:
            h, m, sec, f = (int(p) for p in parts)
            return h * 3600 + m * 60 + sec + f / fps
    except Exception:
        pass
    return 0.0


def segment_fps(segment):
    """Return the segment's frame rate as a float."""
    return parse_frame_rate(getattr(segment, 'source_frame_rate', '24'))


def segment_source_start_seconds(segment, fps):
    """Return the segment's source in-point in seconds (for ffmpeg -ss trimming)."""
    return timecode_to_seconds(getattr(segment, 'source_in', None), fps)


def segment_duration_seconds(segment, fps):
    """Return the segment's record duration in seconds (for ffmpeg -t trimming)."""
    tc = getattr(segment, 'record_duration', None)
    if tc is None:
        return None
    secs = timecode_to_seconds(tc, fps)
    return secs if secs > 0 else None


# =========================================================================== #
# Options window
# =========================================================================== #

class TranscribeOptionsWindow:
    """
    Modal dialog that collects transcription options from the user.
    After .show(), read .cancelled to check whether the user confirmed.
    """

    def __init__(self, default_srt_path='', default_start_frame=1):
        self.cancelled      = True
        self.model          = 'base'
        self.language       = None
        self.do_srt         = True
        self.do_markers     = True
        self.do_captions    = False
        self.srt_path       = default_srt_path
        self.start_frame    = default_start_frame
        self._build(default_srt_path, default_start_frame)

    # ---------------------------------------------------------------------- #

    def _build(self, default_srt_path, default_start_frame):

        def confirm():
            self.model       = self.model_menu.text()
            lang_display     = self.language_menu.text()
            self.language    = LANGUAGE_CODES.get(lang_display)
            self.do_srt      = self.srt_btn.isChecked()
            self.do_markers  = self.markers_btn.isChecked()
            self.do_captions = self.captions_btn.isChecked()
            self.srt_path    = self.srt_path_entry.text()
            try:
                self.start_frame = int(self.start_frame_entry.text())
            except ValueError:
                self.start_frame = 1
            if not self.do_srt and not self.do_markers and not self.do_captions:
                PyFlameMessageWindow(
                    message='Select at least one output type.',
                    type=MessageType.ERROR,
                )
                return
            self.cancelled = False
            self.window.accept()

        def cancel():
            self.cancelled = True
            self.window.reject()

        def browse_srt():
            chosen = QtWidgets.QFileDialog.getExistingDirectory(
                self.window,
                'Select SRT Output Folder',
                self.srt_path_entry.text() or os.path.expanduser('~'),
            )
            if chosen:
                current_name = os.path.basename(self.srt_path_entry.text()) or 'transcript.srt'
                self.srt_path_entry.setText(os.path.join(chosen, current_name))

        def toggle_srt_path():
            enabled = self.srt_btn.isChecked()
            self.srt_path_entry.setEnabled(enabled)
            self.browse_btn.setEnabled(enabled)

        # ------------------------------------------------------------------ #

        self.window = PyFlameDialogWindow(
            title=f'{SCRIPT_NAME}  <small>{SCRIPT_VERSION}',
            return_pressed=confirm,
            grid_layout_columns=6,
            grid_layout_rows=10,
            grid_layout_column_width=120,
            grid_layout_row_height=30,
            grid_layout_adjust_column_widths={5: 100},
        )

        # ── Transcription settings ─────────────────────────────────────────

        settings_label = PyFlameLabel(text='Transcription Settings', style=Style.UNDERLINE)

        model_label    = PyFlameLabel(text='Whisper Model')
        self.model_menu = PyFlamePushButtonMenu(
            text='base',
            menu_options=WHISPER_MODELS,
        )

        language_label     = PyFlameLabel(text='Language')
        self.language_menu = PyFlamePushButtonMenu(
            text='Auto Detect',
            menu_options=LANGUAGE_OPTIONS,
        )

        # ── Output options ─────────────────────────────────────────────────

        output_label = PyFlameLabel(text='Output Options', style=Style.UNDERLINE)

        self.srt_btn = PyFlamePushButton(
            text='SRT File',
            button_checked=True,
            connect=toggle_srt_path,
        )
        self.markers_btn = PyFlamePushButton(
            text='Timeline Markers',
            button_checked=True,
        )
        self.captions_btn = PyFlamePushButton(
            text='Captions Track',
            button_checked=False,
        )

        # ── SRT output path ────────────────────────────────────────────────

        srt_path_label      = PyFlameLabel(text='SRT Output Path')
        self.srt_path_entry = PyFlameLineEdit(text=default_srt_path)
        self.browse_btn     = PyFlamePushButton(text='Browse', connect=browse_srt)

        # ── Marker start frame ─────────────────────────────────────────────

        start_frame_label      = PyFlameLabel(text='Marker Start Frame')
        self.start_frame_entry = PyFlameLineEdit(text=str(default_start_frame))

        # ── Action buttons ─────────────────────────────────────────────────

        cancel_btn    = PyFlamePushButton(text='Cancel',    connect=cancel)
        transcribe_btn = PyFlamePushButton(text='Transcribe', connect=confirm)

        # ── Layout ────────────────────────────────────────────────────────
        #
        #  col:  0                1           2             3          4          5
        #  row 0: [── Transcription Settings ───────────────────────────────────]
        #  row 1: [Model lbl] [model menu ──────] [Lang lbl] [lang menu ─────────]
        #  row 2: (spacer)
        #  row 3: [── Output Options ───────────────────────────────────────────]
        #  row 4: [SRT btn ──────────] [Markers btn ─────────] [Captions btn ───]
        #  row 5: (spacer)
        #  row 6: [SRT path lbl] [path entry ────────────────────────] [Browse]
        #  row 7: [Marker Start Frame lbl] [entry]
        #  row 8: (spacer)
        #  row 9:                                              [Cancel] [Transcribe]

        gl = self.window.grid_layout
        gl.addWidget(settings_label,          0, 0, 1, 6)
        gl.addWidget(model_label,             1, 0)
        gl.addWidget(self.model_menu,         1, 1, 1, 2)
        gl.addWidget(language_label,          1, 3)
        gl.addWidget(self.language_menu,      1, 4, 1, 2)
        gl.addWidget(output_label,            3, 0, 1, 6)
        gl.addWidget(self.srt_btn,            4, 0, 1, 2)
        gl.addWidget(self.markers_btn,        4, 2, 1, 2)
        gl.addWidget(self.captions_btn,       4, 4, 1, 2)
        gl.addWidget(srt_path_label,          6, 0)
        gl.addWidget(self.srt_path_entry,     6, 1, 1, 4)
        gl.addWidget(self.browse_btn,         6, 5)
        gl.addWidget(start_frame_label,       7, 0)
        gl.addWidget(self.start_frame_entry,  7, 1)
        gl.addWidget(cancel_btn,              9, 4)
        gl.addWidget(transcribe_btn,          9, 5)

        self.window.exec()


# =========================================================================== #
# Main transcription class
# =========================================================================== #

class TranscribeAudio:

    def __init__(self, selection):
        self.segment = selection[0]

    # ---------------------------------------------------------------------- #

    def run(self):
        import flame

        if not venv_ready():
            PyFlameMessageWindow(
                message=(
                    'Whisper environment not found.\n\n'
                    'Run:  Flame Main Menu → Logik → Transcribe Audio → Setup Whisper Environment'
                ),
                type=MessageType.ERROR,
            )
            return

        if not find_ffmpeg():
            PyFlameMessageWindow(
                message='ffmpeg not found.\n\nInstall it with:  brew install ffmpeg',
                type=MessageType.ERROR,
            )
            return

        file_path = self._get_file_path()
        if not file_path:
            PyFlameMessageWindow(
                message='Could not determine source media path for this segment.',
                type=MessageType.ERROR,
            )
            return

        clip_name     = str(self.segment.name)
        srt_dir       = str(Path(file_path).parent)
        default_srt   = os.path.join(srt_dir, f'{clip_name}.srt')

        opts = TranscribeOptionsWindow(
            default_srt_path=default_srt,
            default_start_frame=int(self.segment.start_frame),
        )
        if opts.cancelled:
            return

        # Frame rate — read directly from the segment (confirmed working in Flame 2026).
        try:
            fps = segment_fps(self.segment)
        except Exception:
            fps = 24.0

        with tempfile.TemporaryDirectory(prefix='transcribe_audio_') as tmp:
            # ── 1. Extract audio ───────────────────────────────────────────
            progress = PyFlameProgressWindow(
                num_to_do=3,
                title='Transcribing...',
                text='Step 1 of 3: Extracting audio with ffmpeg',
            )
            progress.show()
            QtWidgets.QApplication.instance().processEvents()

            try:
                audio_path = self._extract_audio(file_path, tmp, fps)
            except RuntimeError as exc:
                progress.close()
                PyFlameMessageWindow(message=str(exc), type=MessageType.ERROR)
                return

            # ── 2. Run Whisper ─────────────────────────────────────────────
            progress.set_progress_value(1)
            progress.set_text(
                f'Step 2 of 3: Transcribing with Whisper ({opts.model})\n'
                'This may take a minute...'
            )
            QtWidgets.QApplication.instance().processEvents()

            try:
                data = self._run_whisper(audio_path, opts.model, opts.language)
            except RuntimeError as exc:
                progress.close()
                PyFlameMessageWindow(message=str(exc), type=MessageType.ERROR)
                return

            segments = data['segments']

            # ── 3. Write outputs ───────────────────────────────────────────
            progress.set_progress_value(2)
            progress.set_text('Step 3 of 3: Writing outputs')
            QtWidgets.QApplication.instance().processEvents()

            results = []

            if opts.do_srt:
                try:
                    self._write_srt(segments, opts.srt_path)
                    results.append(f'SRT file:  {opts.srt_path}')
                except Exception as exc:
                    results.append(f'SRT FAILED: {exc}')

            if opts.do_markers:
                try:
                    count = self._create_markers(segments, fps, opts.start_frame)
                    results.append(f'Markers:   {count} created on timeline')
                except Exception as exc:
                    results.append(f'Markers FAILED: {exc}')

            if opts.do_captions:
                try:
                    # import_subtitles_file needs an SRT on disk.
                    # Use the one we just wrote, or write a temp copy.
                    caption_srt = opts.srt_path if (opts.do_srt and os.path.isfile(opts.srt_path)) else None
                    if caption_srt is None:
                        caption_srt = os.path.join(tmp, 'captions_temp.srt')
                        self._write_srt(segments, caption_srt)
                    count = self._create_captions(caption_srt, len(segments))
                    results.append(f'Captions:  {count} subtitle events imported')
                except Exception as exc:
                    results.append(f'Captions FAILED: {exc}')

            progress.set_progress_value(3)
            progress.enable_done_button(True)
            progress.close()

        summary = '\n'.join(results) if results else 'No outputs selected.'
        PyFlameMessageWindow(
            message=f'Transcription complete.\nDetected language: {data.get("language", "unknown")}\n\n{summary}',
            type=MessageType.OPERATION_COMPLETE,
        )

    # ---------------------------------------------------------------------- #
    # Private methods
    # ---------------------------------------------------------------------- #

    def _get_file_path(self):
        """Return the source media path for the segment, or None if not found."""
        path = str(getattr(self.segment, 'file_path', '') or '')
        return path if os.path.isfile(path) else None

    # ---------------------------------------------------------------------- #

    def _extract_audio(self, file_path: str, tmp_dir: str, fps: float) -> str:
        """
        Use ffmpeg to extract and downmix audio to a 16kHz mono WAV.
        Trims to the segment's source in/out points so Whisper timestamps
        align with the segment's position in the timeline.
        """
        ffmpeg  = find_ffmpeg()
        out_wav = os.path.join(tmp_dir, 'audio.wav')

        source_start_s    = segment_source_start_seconds(self.segment, fps)
        duration_s        = segment_duration_seconds(self.segment, fps)

        cmd = [ffmpeg, '-y']
        if source_start_s > 0:
            cmd += ['-ss', str(source_start_s)]
        cmd += ['-i', file_path]
        if duration_s:
            cmd += ['-t', str(duration_s)]
        cmd += [
            '-vn',                    # drop video
            '-acodec', 'pcm_s16le',   # 16-bit PCM
            '-ar',     '16000',       # 16 kHz — Whisper's native sample rate
            '-ac',     '1',           # mono
            out_wav,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'ffmpeg failed:\n{result.stderr[-800:]}')
        return out_wav

    # ---------------------------------------------------------------------- #

    def _run_whisper(self, audio_path, model, language):
        """Invoke worker.py inside the venv and return the parsed JSON result."""
        cmd = [VENV_PYTHON, WORKER_SCRIPT, '--audio', audio_path, '--model', model]
        if language:
            cmd += ['--language', language]

        # Whisper calls ffmpeg internally to decode audio. The worker subprocess
        # may not inherit Homebrew's PATH when launched from inside Flame, so
        # inject the ffmpeg directory explicitly.
        env = os.environ.copy()
        ffmpeg_bin = find_ffmpeg()
        if ffmpeg_bin:
            env['PATH'] = os.path.dirname(ffmpeg_bin) + os.pathsep + env.get('PATH', '')

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        # Try to parse stdout regardless of exit code.
        # Python 3.14 + torch can emit non-fatal cleanup errors on exit that
        # produce a non-zero return code even when transcription succeeded.
        data = None
        if result.stdout.strip():
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass

        if result.returncode != 0 and (data is None or 'error' in data):
            stderr_display = result.stderr[-1500:] if result.stderr else '(no stderr)'
            stdout_display = result.stdout[:400]   if result.stdout else '(no stdout)'
            raise RuntimeError(
                f'Whisper worker exited with code {result.returncode}.\n\n'
                f'stderr (last 1500 chars):\n{stderr_display}\n\n'
                f'stdout:\n{stdout_display}'
            )

        if data is None:
            raise RuntimeError('Worker produced no output.')

        if 'error' in data:
            raise RuntimeError(data['error'])

        return data

    # ---------------------------------------------------------------------- #

    def _write_srt(self, segments: list, output_path: str):
        """Write segments to a standard SRT subtitle file."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = seconds_to_srt_time(seg['start'])
            end   = seconds_to_srt_time(seg['end'])
            lines.append(f'{i}\n{start} --> {end}\n{seg["text"]}\n')

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    # ---------------------------------------------------------------------- #

    def _create_markers(self, segments, fps, start_frame):
        """
        Create sequence-level markers on the open timeline clip.
        start_frame is supplied by the user via the dialog (defaults to
        segment.start_frame but can be overridden if Flame reports it wrong).
        """
        import flame

        seq       = flame.timeline.clip
        rec_start = start_frame
        created   = 0

        for seg in segments:
            frame          = rec_start + int(seg['start'] * fps)
            marker         = seq.create_marker(frame)
            marker.comment = seg['text']
            created += 1

        return created

    # ---------------------------------------------------------------------- #

    def _create_captions(self, srt_path, segment_count):
        """
        Import an SRT file as a Flame subtitle track using the confirmed API:
            PySequence.import_subtitles_file(file_name, file_type=None, ...)
        """
        import flame

        seq = flame.timeline.clip
        seq.import_subtitles_file(srt_path)
        return segment_count


# =========================================================================== #
# One-time environment setup
# =========================================================================== #

def setup_environment(selection=None):
    """
    Create the venv and install openai-whisper + PyTorch.
    Triggered from the Flame main menu.
    Flame will be unresponsive during the pip install (~2-5 min on first run).
    """
    if venv_ready():
        proceed = PyFlameMessageWindow(
            message=(
                'Whisper environment already exists.\n\n'
                'Reinstall? This will replace the existing venv.'
            ),
            type=MessageType.CONFIRM,
        )
        if not proceed:
            return
        import shutil
        shutil.rmtree(VENV_PATH, ignore_errors=True)

    python3 = find_system_python()
    if not python3:
        PyFlameMessageWindow(
            message='Python 3 not found on this system.\n\nInstall it with:  brew install python3',
            type=MessageType.ERROR,
        )
        return

    if not find_ffmpeg():
        PyFlameMessageWindow(
            message=(
                'ffmpeg not found — it is required for audio extraction.\n\n'
                'Install it with:  brew install ffmpeg\n\n'
                'Continuing with Whisper setup...'
            ),
            type=MessageType.WARNING,
        )

    proceed = PyFlameMessageWindow(
        message=(
            f'Ready to set up the Whisper environment at:\n{VENV_PATH}\n\n'
            'This installs Whisper + PyTorch (~2 GB download).\n'
            'Flame will be unresponsive for several minutes.\n\n'
            'Proceed?'
        ),
        type=MessageType.CONFIRM,
    )
    if not proceed:
        return

    pip = os.path.join(VENV_PATH, 'bin', 'pip')

    try:
        subprocess.run(
            [python3, '-m', 'venv', VENV_PATH],
            check=True, capture_output=True,
        )
        subprocess.run(
            [pip, 'install', '--upgrade', 'pip'],
            check=True, capture_output=True,
        )
        subprocess.run(
            [pip, 'install', 'openai-whisper'],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode(errors='replace')[-600:] if exc.stderr else str(exc)
        PyFlameMessageWindow(
            message=f'Setup failed:\n\n{err}',
            type=MessageType.ERROR,
        )
        return

    PyFlameMessageWindow(
        message='Whisper environment set up successfully.\n\nTranscribe Audio is ready to use.',
        type=MessageType.OPERATION_COMPLETE,
    )


# =========================================================================== #
# Flame hook entry points
# =========================================================================== #

def scope_segment(selection):
    import flame
    return any(isinstance(item, flame.PySegment) for item in selection)


def transcribe_selected(selection):
    script = TranscribeAudio(selection)
    script.run()


def get_timeline_custom_ui_actions():
    return [
        {
            'name':    'Logik',
            'hierarchy': [],
            'actions': [],
        },
        {
            'name':      'Transcribe Audio',
            'hierarchy': ['Logik'],
            'order':     1,
            'actions': [
                {
                    'name':           'Transcribe Selected Segment',
                    'order':          0,
                    'isVisible':      scope_segment,
                    'execute':        transcribe_selected,
                    'minimumVersion': '2026',
                },
            ],
        },
    ]


def get_main_menu_custom_ui_actions():
    return [
        {
            'name':    'Logik',
            'hierarchy': [],
            'actions': [],
        },
        {
            'name':      'Transcribe Audio',
            'hierarchy': ['Logik'],
            'order':     1,
            'actions': [
                {
                    'name':           'Setup Whisper Environment',
                    'execute':        setup_environment,
                    'minimumVersion': '2026',
                },
            ],
        },
    ]
