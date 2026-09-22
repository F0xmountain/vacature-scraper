"""Handmatige ja/nee-beoordeling van gevonden vacatures.

Dit is de enige schrijfroute naar beoordeling.json in de projectroot; bouw geen
tweede. De sleutel is de dedupe-sleutel uit store.job_key, zodat een oordeel over
runs heen blijft kloppen: dezelfde vacature krijgt altijd dezelfde sleutel. Dit is
expliciet handwerk, geen scoring; de tool wijst niets af, de gebruiker beoordeelt.

Vorm van beoordeling.json:
    { "<sleutel>": { "oordeel": "ja" | "nee", "tijd": "<iso-tijdstempel>" }, ... }
"""
import json
from datetime import datetime
from pathlib import Path

# In de projectroot, naast state.json. webui/oordeel.py -> parent is webui, en
# parent.parent is de projectmap.
PAD = Path(__file__).resolve().parent.parent / "beoordeling.json"

GELDIG = ("ja", "nee")


def laad():
    """De hele oordeelmap teruggeven; een lege map als er nog niets is.

    Een kapot of half geschreven bestand mag de interface niet laten vallen; in
    dat geval komt er een lege map terug en overschrijft de eerste schrijfactie
    het bestand weer netjes.
    """
    if PAD.exists():
        try:
            return json.loads(PAD.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def zet(sleutel, oordeel):
    """Een oordeel opslaan of wissen; geeft de bijgewerkte map terug.

    "onbeoordeeld" verwijdert de sleutel weer. "ja" en "nee" schrijven een oordeel
    met tijdstempel. Elke andere waarde is een fout. Dit is de enige plek die naar
    beoordeling.json schrijft.
    """
    sleutel = (sleutel or "").strip()
    if not sleutel:
        raise ValueError("lege sleutel")
    kaart = laad()
    if oordeel == "onbeoordeeld":
        kaart.pop(sleutel, None)
    elif oordeel in GELDIG:
        kaart[sleutel] = {
            "oordeel": oordeel,
            "tijd": datetime.now().isoformat(timespec="seconds"),
        }
    else:
        raise ValueError(f"ongeldig oordeel: {oordeel!r}")
    PAD.write_text(json.dumps(kaart, indent=1, ensure_ascii=False), encoding="utf-8")
    return kaart


def wis(sleutels):
    """Verwijder de oordelen voor de gegeven sleutels in een keer; geeft de
    bijgewerkte map terug.

    Voor de 'alles wissen'-knop: in een schrijfactie in plaats van per sleutel.
    Sleutels die er niet in staan worden overgeslagen; is er niets te wissen, dan
    blijft het bestand ongemoeid. Blijft de enige schrijfroute naar beoordeling.json.
    """
    kaart = laad()
    weg = [s for s in (sleutels or []) if s in kaart]
    if not weg:
        return kaart
    for s in weg:
        kaart.pop(s, None)
    PAD.write_text(json.dumps(kaart, indent=1, ensure_ascii=False), encoding="utf-8")
    return kaart
