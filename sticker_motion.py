"""Shared sticker-motion helpers for the cutout renderers (round 1, 2026-11-07).

Round 1 changes (user spec, 2026-11-07; only motion and trigger timing):
- No more uniform idle bob on every object, no hop when another element
  appears. People, buildings and certificates stay still after entering.
  The airplane orbit is kept as the one exception.
- Entrances and yields use smootherstep easing (zero velocity and zero
  acceleration at both ends), not the old ease-out squared.
- Detail stickers fall with acceleration (not the old (1-p)^2 ease-out)
  and land with a single small upward bounce that never goes below the
  sand line and settles in ~0.35s.
- Detail trigger time is resolved per beat from an optional `motion`
  config: trigger_time > word timestamp > estimated by keyword position
  (marked "estimated") > mid-sentence default.
- Beat durations come from --beat-durs / the script's `beat_durs` field /
  the theoretical estimate, never from a hardcoded list for one film.

This module only builds ffmpeg overlay expressions and resolves config;
it does not render anything itself. Both renderers
(make_cutout_from_script.py and make_cutout_from_script_v13.py) import
it so the two entries produce identical motion.
"""

# ---------------------------------------------------------------- constants
FPS = 30
ENTER_DUR = 0.6      # entrance slide duration (s)
ENTER_DIST = 400     # entrance slide distance (px)
YIELD_DUR = 0.6      # main-sticker yield duration (s)
YIELD_LEAD = 0.1     # yield starts this many seconds before the detail enters
DROP_DUR = 0.5       # detail fall duration (s)
DROP_HEIGHT = 400    # detail drop start height above the sand line (px)
BOUNCE_AMP = 8       # single bounce height (px, upward)
BOUNCE_DUR = 0.35    # bounce settle time (s)


# ---------------------------------------------------------------- ffmpeg easing
def ff_clamp01(p_expr):
    """Clamp an ffmpeg progress expression to [0, 1]."""
    return "min(max(%s,0),1)" % p_expr


def ff_smoother(p_expr):
    """Smootherstep easing of a 0..1 progress expression.

    ease = 6p^5 - 15p^4 + 10p^3; velocity and acceleration are zero at
    p=0 and p=1, so a slide starts and stops without a jolt.
    """
    return ("(6*pow(%s,5)-15*pow(%s,4)+10*pow(%s,3))"
            % (p_expr, p_expr, p_expr))


def ff_progress(start, dur, t_expr="t"):
    """Clamped 0..1 progress of time within [start, start+dur]."""
    return ff_clamp01("(%s-(%.3f))/%.3f" % (t_expr, start, dur))


def ff_slide(from_expr, to_expr, start, dur, t_expr="t"):
    """ffmpeg expression sliding from `from` to `to` over [start, start+dur].

    Uses smootherstep, so the value is exactly `from` before `start` and
    exactly `to` after `start+dur`.
    """
    p = ff_progress(start, dur, t_expr)
    e = ff_smoother(p)
    return "(%s+((%s)-(%s))*%s)" % (from_expr, to_expr, from_expr, e)


def ff_enter_offset(direction, start=0.0, dur=ENTER_DUR, dist=ENTER_DIST):
    """Horizontal entrance offset for a main sticker.

    direction "left"  -> starts `dist` px left of its final x, slides in.
    direction "right" -> starts `dist` px right of its final x, slides in.
    Returns an expression that is 0 once the entrance is done.
    """
    if direction == "right":
        return ff_slide(str(dist), "0", start, dur)
    return ff_slide(str(-dist), "0", start, dur)


def ff_drop(trigger, fall_dur=DROP_DUR, height=DROP_HEIGHT, t_expr="t"):
    """Accelerating fall offset for a detail sticker.

    Returns the height above the sand line that is still to fall:
    height*(1-p^2) with p = clamped progress of (t-trigger)/fall_dur.
    At t<=trigger the offset is `height`; at t>=trigger+fall_dur it is 0
    (landed). Speed grows with p, i.e. the fall accelerates like a real
    drop, unlike the old (1-p)^2 ease-out that started fast and slowed.
    The caller subtracts this from the ground y.
    """
    p = ff_progress(trigger, fall_dur, t_expr)
    return "(%.1f*(1-pow(%s,2)))" % (height, p)


def ff_bounce(land, amp=BOUNCE_AMP, settle=BOUNCE_DUR, t_expr="t"):
    """Single upward bounce after landing, ffmpeg expression.

    Returns a y offset (negative = upward on screen) that is 0 at `land`,
    peaks at -amp halfway through, returns to 0 at land+settle and stays
    0 afterwards. It is never positive, so the sticker never goes below
    the sand line, and it is position-continuous with the drop at `land`
    (both are 0 there). No sine oscillation is added after settling.
    """
    p = ff_progress(land, settle, t_expr)
    return "(-%.1f*sin(PI*%s))" % (amp, p)


# ---------------------------------------------------------------- per-beat config
def beat_motion(beat):
    """Return the beat's `motion` dict (empty when the script has none)."""
    m = beat.get("motion") if isinstance(beat, dict) else None
    return m if isinstance(m, dict) else {}


def resolve_enter(beat):
    """Main-sticker entrance direction for this beat: "left" or "right"."""
    d = str(beat_motion(beat).get("enter", "left")).lower()
    return "right" if d in ("right", "r") else "left"


def _word_start(word_times, beat_idx, trigger_word, sent, dur):
    """Find the trigger word's start time (seconds within the beat).

    Returns (time, source) with source "word_time" or None when the word
    is not in the timestamp data.
    word_times maps beat index (str or int) -> [{"word":..,"start":..}].
    Times are relative to the beat's start.
    """
    if not word_times or not trigger_word:
        return None, None
    entries = word_times.get(str(beat_idx), word_times.get(beat_idx))
    if not entries:
        return None, None
    for e in entries:
        w = str(e.get("word", ""))
        if not w:
            continue
        if trigger_word in w or w in trigger_word:
            try:
                return float(e["start"]), "word_time"
            except (KeyError, TypeError, ValueError):
                return None, None
    return None, None


def resolve_trigger(beat, beat_idx, dur, word_times=None):
    """Detail trigger time (seconds within the beat) and its source.

    Priority (user spec):
    1. motion.trigger_time (seconds within the beat, clamped to [0, dur]).
    2. motion.trigger_word matched to a real word timestamp.
    3. motion.trigger_word without timestamps: estimate by the word's
       position in the sentence; source is "estimated" (this is NOT
       real voice alignment and must be labelled as such).
    4. No motion config: mid-sentence, source "default".
    The returned time is when the detail STARTS entering.
    """
    m = beat_motion(beat)
    tt = m.get("trigger_time")
    if tt is not None:
        try:
            return max(0.0, min(float(tt), dur)), "trigger_time"
        except (TypeError, ValueError):
            pass
    word = m.get("trigger_word")
    if word:
        t, src = _word_start(word_times, beat_idx, str(word),
                             beat.get("text", ""), dur)
        if t is not None:
            return max(0.0, min(t, dur)), src
        sent = beat.get("text", "") or ""
        pos = sent.find(str(word))
        if pos >= 0 and len(sent) > 0:
            return dur * (pos / len(sent)), "estimated"
    return dur / 2.0, "default"


# ---------------------------------------------------------------- beat durations
def _load_durs_file(path):
    import json
    data = json.loads(open(path, encoding="utf-8").read())
    if isinstance(data, dict):
        data = data.get("beat_durs", data.get("durs", []))
    return [float(x) for x in data]


def resolve_beat_durs(script, beat_durs_arg, dur_of, script_path=None):
    """Per-beat durations (seconds) and where they came from.

    Priority:
    1. --beat-durs: a JSON file path (list, or {"beat_durs": [...]}) or a
       comma-separated list of seconds.
    2. A "<script stem>_beat_durs.json" sidecar next to the script file.
    3. The script JSON's own top-level `beat_durs` field.
    4. The theoretical estimate dur_of(sentence) per beat.
    Returns (durs, source). Raises ValueError when a supplied list has
    the wrong length.
    """
    from pathlib import Path
    n = len(script["beats"])
    if beat_durs_arg:
        arg = str(beat_durs_arg)
        try:
            durs = _load_durs_file(arg)
            src = "beat-durs file %s" % arg
        except (OSError, ValueError, KeyError):
            durs = [float(x) for x in arg.split(",") if x.strip()]
            src = "beat-durs list"
        if len(durs) != n:
            raise ValueError(
                "beat_durs has %d entries but the script has %d beats"
                % (len(durs), n))
        return durs, src
    if script_path:
        sidecar = Path(script_path).with_name(
            Path(script_path).stem + "_beat_durs.json")
        if sidecar.exists():
            durs = _load_durs_file(str(sidecar))
            if len(durs) != n:
                raise ValueError(
                    "beat_durs sidecar has %d entries but the script has "
                    "%d beats" % (len(durs), n))
            return durs, "sidecar %s" % sidecar.name
    if script.get("beat_durs"):
        durs = [float(x) for x in script["beat_durs"]]
        if len(durs) != n:
            raise ValueError(
                "script beat_durs has %d entries but the script has %d beats"
                % (len(durs), n))
        return durs, "script beat_durs"
    return [dur_of(b["text"]) for b in script["beats"]], "theoretical"


def frame_bounds(durs, fps=FPS):
    """Frame-exact beat boundaries from per-beat durations.

    Quantises the CUMULATIVE boundaries to whole frames (instead of
    rounding each beat's duration) so the error does not accumulate.
    Returns (bounds_seconds, bounds_frames, frames_per_beat).
    """
    bounds = [0.0]
    for d in durs:
        bounds.append(bounds[-1] + d)
    bounds_f = [round(b * fps) for b in bounds]
    frames = [bounds_f[i + 1] - bounds_f[i] for i in range(len(durs))]
    return bounds, bounds_f, frames


def load_word_times(word_times_arg, script=None):
    """Load word timestamps from a file or from the script's `word_times`.

    Returns a dict beat-index -> [{"word":..,"start":..,"end":..}] with
    times relative to the beat's start, or None when there is none.
    """
    import json
    if word_times_arg:
        return json.loads(open(word_times_arg, encoding="utf-8").read())
    if script and script.get("word_times"):
        return script["word_times"]
    return None
