# Development Notes: Transcribe Audio
## A guide for the Logik community on building Python hooks with undocumented APIs

---

## The problem this hook solves

Autodesk does not publish a complete Python API reference for Flame. Method names,
argument types, and object structures must be discovered through live inspection.
This document describes exactly how we did that — every technique is reproducible
for any hook you build.

---

## 1. Isolating heavy Python dependencies from Flame

Flame bundles its own Python interpreter. You cannot install packages like PyTorch
or Whisper into it reliably — the path varies, pip may not be present, and a Flame
update can wipe your additions.

**The pattern that works: a dedicated virtual environment.**

```
~/.transcribe_audio_venv/   ← lives in the user's home folder
    bin/python              ← the Python that runs Whisper
    lib/...                 ← PyTorch, openai-whisper, and dependencies
```

The Flame hook (which runs inside Flame's Python) calls the venv Python as a
subprocess. Results come back as JSON over stdout. The two environments never
touch each other.

```python
result = subprocess.run(
    [VENV_PYTHON, WORKER_SCRIPT, '--audio', audio_path, '--model', model],
    capture_output=True,
    text=True,
    env=env,
)
data = json.loads(result.stdout)
```

**Why prefer Python 3.12 for the venv:**
Using `find_system_python()`, the hook searches for `python3.12`, then `3.11`,
then `3.13`, before falling back to generic `python3`. As of 2026, Python 3.14 is
too new — PyTorch wheels don't exist for it yet. Pinning to a known-good version
avoids silent install failures.

---

## 2. Homebrew's PATH is not Flame's PATH

Flame launches with a minimal environment — `/usr/bin`, `/bin`, not Homebrew.
Whisper calls `ffmpeg` internally when it loads audio. Even though we found ffmpeg
at `/opt/homebrew/bin/ffmpeg` from the hook, the venv subprocess couldn't find it.

**Fix:** inject the ffmpeg directory into the subprocess environment explicitly.

```python
env = os.environ.copy()
ffmpeg_bin = find_ffmpeg()
if ffmpeg_bin:
    env['PATH'] = os.path.dirname(ffmpeg_bin) + os.pathsep + env.get('PATH', '')
result = subprocess.run(cmd, capture_output=True, text=True, env=env)
```

This pattern applies to any subprocess you launch from a Flame hook that needs
Homebrew tools. Always pass `env=` explicitly rather than relying on inheritance.

---

## 3. Non-zero exit codes don't always mean failure

On Python 3.14, PyTorch emits cleanup warnings on interpreter shutdown that cause
a non-zero exit code even when transcription completed successfully. Checking only
`returncode` would discard valid results.

**Pattern: parse stdout first, treat exit code as secondary.**

```python
data = None
if result.stdout.strip():
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pass

if result.returncode != 0 and (data is None or 'error' in data):
    raise RuntimeError(f'Worker failed:\n{result.stderr[-1500:]}')
```

If the JSON is valid and has no `error` key, use it regardless of exit code.

---

## 4. Probing undocumented Boost.Python APIs

Flame's Python API is implemented as C++ Boost.Python bindings. `inspect.signature`
doesn't work on them. The right approach is to call them with wrong arguments
deliberately — the error messages include the full C++ signature.

**Example probe script:**

```python
def try_call(label, fn, *args):
    try:
        r = fn(*args)
        print(label, '-> OK:', type(r).__name__, repr(r))
    except Exception as e:
        print(label, '-> ERROR:', e)

try_call('create_marker()',    seq.create_marker)
try_call('create_marker(0)',   seq.create_marker, 0)
try_call('import_subtitles_file("")', seq.import_subtitles_file, '')
```

From `create_marker()` failing, we learned:

```
C++ signature: create_marker(PyClip*, _object* location)
```

`location` accepts an integer frame number. `create_marker(0)` confirmed it.

From `import_subtitles_file("")` failing with "Unsupported File Type" (not an
argument error), we learned the signature is correct — it just needs a real file.

From `create_subtitle()` succeeding with no args and returning `PySubtitleTrack`,
we learned it creates an empty subtitle track. We then inspected that object too.

**The general method:**
1. Call with no args → see the signature in the error
2. Call with correct arg count but wrong types → see type expectations
3. Call with correct args → confirm it works and check the return type
4. Inspect the returned object with `dir()` and repeat

---

## 5. Finding the correct sequence object

Early versions of the hook walked `segment.parent.parent` to get the sequence.
This failed because `segment.parent` is a `PyTrack` and `PyTrack.parent` can be
a group inside the sequence, not the sequence itself.

**The reliable way to get the current sequence in a timeline hook:**

```python
import flame
seq = flame.timeline.clip   # always the clip open in the timeline editor
```

`flame.timeline` also exposes `current_segment` and `current_marker` for hooks
that need context about what's under the playhead.

---

## 6. PyTime is None in Flame 2026

`segment.record_start` returns `None` in Flame 2026. We spent significant time
building a multi-strategy `PyTime` converter before discovering this through
direct inspection:

```python
seg = flame.timeline.current_segment
print('record_start:', repr(seg.record_start))   # → None NoneType
print('start_frame:', repr(seg.start_frame))     # → 1001 int
```

`segment.start_frame` is the absolute frame position in the sequence as a plain
Python integer. Use it directly.

`record_duration`, `source_in`, and `source_out` do hold PyTime values, but they
print as timecode strings (`"00:00:50:03"`). Parse them with:

```python
def timecode_to_seconds(tc, fps):
    parts = str(tc).strip().replace(';', ':').split(':')
    if len(parts) == 4:
        h, m, sec, f = (int(p) for p in parts)
        return h * 3600 + m * 60 + sec + f / fps
    return 0.0
```

---

## 7. Discovering the subtitles API

The `dir()` output on a `PySequence` revealed:

```
['create_subtitle', 'import_subtitles_file', 'subtitles', ...]
```

Probing `create_subtitle()` with no args returned a `PySubtitleTrack`. Probing
`import_subtitles_file("")` gave us the full C++ signature including optional
`file_type`, `align_first_event_to_clip_start`, and `convert_from_frame_rate`
parameters.

Since we already generate an SRT file, the implementation became a one-liner:

```python
seq.import_subtitles_file(srt_path)
```

The lesson: before building complex output logic, check whether Flame already has
an import method that accepts a standard file format. It often does.

---

## The inspection toolkit

Save this as a reusable starting point for any new hook:

```python
import flame

# Get the current sequence and segment
seq = flame.timeline.clip
seg = flame.timeline.current_segment

# List all non-dunder attributes with their values
for a in dir(seg):
    if a.startswith('__'):
        continue
    try:
        v = getattr(seg, a)
        if not callable(v):
            print(f'{a}: {repr(v)}')
    except Exception as e:
        print(f'{a}: ERROR {e}')

# Probe a method's signature by calling it with wrong args
def try_call(label, fn, *args):
    try:
        print(label, '-> OK:', type(fn(*args)).__name__)
    except Exception as e:
        print(label, '-> ERROR:', e)

try_call('create_marker()',  seq.create_marker)
try_call('create_marker(0)', seq.create_marker, 0)
```

Run this from the Flame Python console (via ShotGrid's tk-multi-pythonconsole or
the built-in Python editor) using:

```python
exec(open('/path/to/your/inspect_script.py').read())
```

---

## File structure

```
/opt/Autodesk/shared/python/transcribe_audio/
    transcribe_audio.py     Flame hook — runs inside Flame's Python
    worker.py               Whisper runner — runs inside the venv
```

`worker.py` has zero Flame dependencies. It can be tested standalone:

```bash
~/.transcribe_audio_venv/bin/python worker.py --audio /tmp/test.wav --model base
```

Keeping the heavy logic in the worker and the Flame logic in the hook makes both
easier to debug and maintain independently.
