"""Begrenzte Wiederholungen für kostenpflichtige KI-Lesungen einer Quelle.

Früher galt: schlägt die KI-Lesung einer Wochenkarte einmal fehl, wird erst am
nächsten Tag wieder probiert. Dadurch blieb ein Menü nach einer einzigen
Störung den ganzen Tag veraltet. Jetzt darf dieselbe Quellversion am selben
Tag mehrmals gelesen werden – aber mit Pause dazwischen und fester Obergrenze,
damit ein dauerhaft unlesbares Dokument keine Kosten im Stundentakt erzeugt.

Eine geänderte Quelle (anderer Hash), eine neue Woche oder eine neue
Prüfversion ergibt eine neue Identität und damit ein frisches Kontingent.
"""
from __future__ import annotations

from datetime import datetime

MAX_PER_DAY = 2
MIN_GAP_MINUTES = 60


def identity(week_start, version, digest):
    return f"{week_start}|{version}|{digest}"


def _parse(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def state(record, ident, now):
    """Zählerstand für genau diese Quellversion am heutigen Tag."""
    stored = (record or {}).get("attempts") or {}
    if stored.get("identity") == ident and stored.get("day") == now.date().isoformat():
        return {"count": int(stored.get("count") or 0), "last_at": stored.get("last_at")}
    return {"count": 0, "last_at": None}


def allowed(record, ident, now, *, max_per_day=MAX_PER_DAY, min_gap_minutes=MIN_GAP_MINUTES):
    """(erlaubt, Begründung). `now` muss eine Zeitzone tragen."""
    current = state(record, ident, now)
    if current["count"] >= max_per_day:
        return False, (f"heute bereits {current['count']}-mal mit KI geprüft; "
                       "neuer Versuch erst bei geänderter Quelle oder morgen")
    last = _parse(current["last_at"])
    if last is not None and last.tzinfo is not None:
        waited = (now - last).total_seconds() / 60
        if 0 <= waited < min_gap_minutes:
            return False, (f"letzter KI-Versuch vor {int(waited)} Minuten; "
                           f"nächster Versuch frühestens nach {min_gap_minutes} Minuten")
    return True, ""


def register(record, ident, now):
    """Vor dem bezahlten Aufruf vermerken, damit auch Abbrüche mitzählen."""
    current = state(record, ident, now)
    record["attempts"] = {"identity": ident, "day": now.date().isoformat(),
                          "count": current["count"] + 1,
                          "last_at": now.isoformat(timespec="seconds")}
    return record["attempts"]
