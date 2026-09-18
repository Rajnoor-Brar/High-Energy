"""How things look and how numbers read (06 §1).

Nothing here renders; it decides what a number should say. The reason it is its own module is that the
live dashboard and the plain lines must agree — a run that says `1.18 k ev/s` on screen and
`1183.4 ev/s` in the log is two different reports of one run.

The formatting rules come from the mock-ups in 06 §1–2: counts in engineering steps (`1.00 M`), rates
with the same steps and a unit (`1.18 k ev/s`), durations as `9m12s` rather than `0:09:12`, and σ as a
value with a *relative* error, because a reader compares ±0.3 % across points far more easily than
±55 pb.
"""

from __future__ import annotations

import math
from datetime import datetime

#: Everything here is UTF-8 by default, because every terminal worth the name is. But a batch job, a
#: cron entry or a CI runner can still have LANG unset, where stdout encodes as ASCII and a single "σ"
#: raises UnicodeEncodeError — a progress bar must never be the reason a run's log dies. `autodetect`
#: asks the stream what it can encode, and the tables below degrade to ASCII when the answer is "not
#: much".
ASCII = False

FALLBACK = {
    "✔": "ok", "▶": ">", "·": "-", "✖": "x", "◐": "~", "↷": "^",
    "█": "#", "░": ".", "σ": "sigma", "±": "+-", "×": "x", "≈": "~", "—": "-", "─": "-",
}


def set_ascii(enabled: bool) -> None:
    global ASCII
    ASCII = bool(enabled)


def autodetect(stream=None) -> bool:
    """Turn on the ASCII fallback when `stream` cannot encode what this module writes."""
    import sys

    stream = stream if stream is not None else sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        "".join(FALLBACK).encode(encoding)
    except (UnicodeEncodeError, LookupError):
        set_ascii(True)
    else:
        set_ascii(False)
    return ASCII


def t(text: str) -> str:
    """A literal, transliterated when the output cannot hold it."""
    if not ASCII:
        return text
    for fancy, plain in FALLBACK.items():
        text = text.replace(fancy, plain)
    return text

#: Point states, as 06 §1's point list draws them.
GLYPH = {
    "queued": "·",
    "running": "▶",
    "done": "✔",
    "failed": "✖",
    "stopped": "◐",
    "skipped": "↷",
}

COLOUR = {
    "queued": "dim",
    "running": "cyan",
    "done": "green",
    "failed": "red",
    "stopped": "yellow",
    "skipped": "blue",
}

LEVEL_COLOUR = {"info": "dim", "warn": "yellow", "error": "red"}
LEVEL_LETTER = {"info": "I", "warn": "W", "error": "E"}

STEPS = ((1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"))


def glyph(state: str) -> str:
    return t(GLYPH.get(state, "·"))


def count(value: float | int | None) -> str:
    """`642113` → `642 113`; `1000000` → `1.00 M`. Below a thousand, the number itself."""
    if value is None:
        return t("—")
    value = float(value)
    for scale, suffix in STEPS:
        if abs(value) >= scale:
            return f"{value / scale:.2f} {suffix}"
    if abs(value) >= 1000:                                   # pragma: no cover - covered by STEPS
        return f"{value:,.0f}".replace(",", " ")
    return f"{value:.0f}"


def rate(value: float | None, unit: str = "ev/s") -> str:
    if not value:
        return t("—")
    for scale, suffix in STEPS:
        if abs(value) >= scale:
            return f"{value / scale:.2f} {suffix} {unit}"
    return f"{value:.0f} {unit}"


def grouped(value: float | int | None) -> str:
    """`642113` → `642 113`. Used where a bar shows exact counts rather than a rounded one."""
    if value is None:
        return t("—")
    return f"{int(value):,}".replace(",", " ")


def duration(seconds: float | None) -> str:
    """`552` → `9m12s`; `37 * 60` → `37m00s`; `None` → `—`. Hours appear only when there are any."""
    if seconds is None or seconds < 0 or math.isnan(seconds) or math.isinf(seconds):
        return t("—")
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def clock(timestamp: float | None) -> str:
    if not timestamp:
        return "  :  :  "
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def sigma(value: float | None, error: float | None = None, *, running: bool = False) -> str:
    """`1.832e+04 pb ± 0.3 %`. A relative error is what a reader actually compares across points."""
    if value is None or value == 0:
        return t("—")
    text = f"{value:.4g} pb" if abs(value) < 1e4 else f"{value:.3e} pb"
    if error:
        text += t(f" ± {abs(error) / abs(value) * 100:.1f} %")
    return t("σ(running) " if running else "σ = ") + text


def percent(done: float | None, total: float | None) -> str:
    if not total:
        return t("—")
    return f"{(done or 0) / total * 100:.0f} %"


def bar(done: float | None, total: float | None, width: int = 20, *,
        full: str = "█", empty: str = "░") -> str:
    """A plain-text bar, for the tests and for plain mode. The dashboard uses rich's own."""
    full, empty = t(full), t(empty)
    if not total:
        return empty * width
    filled = max(0, min(width, int(round((done or 0) / total * width))))
    return full * filled + empty * (width - filled)


def eta(done: float | None, total: float | None, rate_per_second: float | None) -> float | None:
    """Seconds remaining, or None when it cannot be known.

    The idea (and the caution) come from `Monitor/Methods.hh`: extrapolate from the observed rate, and
    say nothing rather than something wrong when there is no rate or no total yet.
    """
    if not total or not rate_per_second or rate_per_second <= 0:
        return None
    remaining = total - (done or 0)
    return remaining / rate_per_second if remaining > 0 else 0.0


def progress_interval(total: float | None, rate_per_second: float | None, *,
                      ceiling: float = 30.0, floor: float = 1.0, steps: int = 20) -> float:
    """How often a progress line is worth printing, **computed after the totals are known**.

    This is the legacy defect the step names: `Monitor` fixed its interval before it knew how long the
    run would be, so a two-minute run printed once and an eight-hour run printed thousands of times.
    With a total and a rate, the interval is "about `steps` lines over the whole run", clamped so that
    it never spams and never goes quiet for more than `ceiling`.
    """
    if not total or not rate_per_second or rate_per_second <= 0:
        return ceiling
    expected = total / rate_per_second
    return max(floor, min(ceiling, expected / max(1, steps)))
