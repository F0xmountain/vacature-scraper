"""Filterlogica: harde uitsluitingen op titel, locatiecheck en flags.

De tool automatiseert alleen wat betrouwbaar uit een listing te halen valt.
Hybride werken, salaris en de vraag of de analytische kern echt is, staan
zelden in de listing; die poortbeoordeling blijft handwerk.

De filtering valt in twee fasen uiteen. split_drop doet de harde drops op titel en
locatie; die hebben de omschrijving niet nodig. wijs_flags kent daarna de flags toe
en matcht flag_termen ook op de omschrijving, dus die fase draait pas nadat de
omschrijvingen zijn opgehaald. Zo hoeven omschrijvingen alleen te worden opgehaald
voor de vacatures die de poort al zijn gepasseerd, zonder dat een flag verloren
gaat. apply_filters voert beide fasen na elkaar uit voor code die de omschrijving al
binnen heeft (tests, check.py).
"""
import re


def _pattern(term: str) -> re.Pattern:
    # Woordgrens zodat 'manager' niet matcht op 'management'
    return re.compile(r"\b" + re.escape(term.lower()) + r"\b")


def _compile(terms):
    return [(t, _pattern(t)) for t in terms or []]


def _stad(locatie: str) -> str:
    """Normaliseer een toegestane locatie tot het eerste, betekenisvolle deel.

    Splitst op komma en gebruikt alleen het eerste stuk (de stad of het
    steekwoord), kleine letters. Zo matcht "Rotterdam, Netherlands" via substring
    op een board-locatie als "Rotterdam, South Holland, Netherlands", en blijven
    korte items als "amsterdam" en "utrecht" gewoon werken; zonder komma is het
    eerste deel de hele string.
    """
    return locatie.split(",")[0].strip().lower()


def _allowed(cfg):
    return [s for s in (_stad(c) for c in cfg.get("locaties_toegestaan") or []) if s]


def split_drop(jobs, cfg):
    """Drop-fase: harde titel-uitsluiting en locatiecheck. Geeft (kept, stats).

    Gebruikt de omschrijving niet, zodat deze fase voor het ophalen van de
    omschrijvingen kan draaien. Een lege locatie wordt niet gedropt (die krijgt in
    wijs_flags de flag 'locatie onbekend'); de flags komen daar, niet hier.
    """
    excl = _compile(cfg.get("titel_uitsluiten"))
    allowed = _allowed(cfg)

    kept = []
    stats = {"totaal": len(jobs), "titel": 0, "locatie": 0}

    for job in jobs:
        titel = (job.get("functie") or "").lower()
        if any(p.search(titel) for _, p in excl):
            stats["titel"] += 1
            continue

        loc = (job.get("locatie") or "").lower()
        if allowed and loc and not any(a in loc for a in allowed):
            stats["locatie"] += 1
            continue

        kept.append(job)

    return kept, stats


def wijs_flags(jobs, cfg):
    """Flag-fase: ken flags toe op titel plus omschrijving. Geeft de jobs terug.

    Draait na het ophalen van de omschrijvingen, zodat flag_termen ook de
    omschrijving zien. Een lege locatie (met een ingestelde locatielijst) krijgt de
    flag 'locatie onbekend', als eerste flag, net als voorheen.
    """
    flag_pats = _compile(cfg.get("flag_termen"))
    allowed = _allowed(cfg)

    for job in jobs:
        job_flags = []
        loc = (job.get("locatie") or "").lower()
        if allowed and not loc:
            job_flags.append("locatie onbekend")

        tekst = (job.get("functie") or "").lower() + " " + (job.get("beschrijving") or "").lower()
        job_flags += [t for t, p in flag_pats if p.search(tekst)]
        job["flags"] = ", ".join(dict.fromkeys(job_flags))

    return jobs


def apply_filters(jobs, cfg):
    """Beide fasen na elkaar; voor code die de omschrijving al binnen heeft.

    Gedraagt zich exact als voorheen: eerst de harde drops, dan de flags.
    """
    kept, stats = split_drop(jobs, cfg)
    wijs_flags(kept, cfg)
    return kept, stats
