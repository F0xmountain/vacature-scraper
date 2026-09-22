"""Ontdubbelen over bronnen en bijhouden wat al eerder gezien is.

state.json is het geheugen van de scraper. Weggooien betekent dat alles
bij de volgende run opnieuw als 'nieuw' wordt gemeld.
"""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

STATE_PATH = Path(__file__).with_name("state.json")


def _norm(s: str) -> str:
    return re.sub(r"\W+", "", (s or "").lower())


def job_key(job) -> str:
    stad = (job.get("locatie") or "").split(",")[0]
    raw = "|".join([_norm(job.get("bedrijf")), _norm(job.get("functie")), _norm(stad)])
    return hashlib.md5(raw.encode()).hexdigest()


def dedupe(jobs):
    """Zelfde bedrijf, functie en stad over meerdere borden: bronnen samenvoegen."""
    merged = {}
    for j in jobs:
        k = job_key(j)
        if k in merged:
            bronnen = set(filter(None, (merged[k].get("bron") or "").split(", ")))
            bronnen |= set(filter(None, (j.get("bron") or "").split(", ")))
            merged[k]["bron"] = ", ".join(sorted(bronnen))
        else:
            merged[k] = j
    return list(merged.values())


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def split_new(jobs, state):
    vandaag = date.today().isoformat()
    nieuw = []
    for j in jobs:
        k = job_key(j)
        if k not in state:
            state[k] = vandaag
            j["eerste_keer_gezien"] = vandaag
            nieuw.append(j)
    return nieuw


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")
