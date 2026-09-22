"""Bediening van de dagelijkse launchd-run. Enige schrijfroute naar launchd.

Net als oordeel.py voor beoordeling.json is dit de enige plek die de agent aan-
of uitzet en het tijdstip wijzigt. De server roept alleen deze functies aan.

De agent draait scraper.py zonder --dry-run: een echte run, die de xlsx wegschrijft
en nieuwheid in state.json verbruikt. Uitzetten is daarom stil gevaarlijk; er
gebeurt dan wekenlang niets zonder dat iets dat meldt. De interface toont om die
reden een statusregel, niet alleen een schakelaar.

Twee begrippen die launchd uit elkaar houdt, en die hier allebei meetellen:

  geladen        de agent zit in de huidige sessie en zal afgaan. Verdwijnt bij
                 bootout, maar komt bij de volgende keer inloggen gewoon terug,
                 want de plist staat nog in ~/Library/LaunchAgents.
  uitgeschakeld  een vlag die een herstart wel overleeft (launchctl disable).

Alleen allebei goed betekent dat er morgen echt iets draait. Vandaar dat 'aan'
hier betekent: geladen en niet uitgeschakeld.
"""
import os
import re
import subprocess
from pathlib import Path

LABEL = "com.basvossenberg.vacature-scraper"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
# De bronversie in het project; die houden we gelijk aan de geinstalleerde kopie,
# zodat het project blijft vertellen wat er werkelijk draait.
BRON_PLIST = Path(__file__).resolve().parent.parent / "launchd" / f"{LABEL}.plist"

# Alleen het StartCalendarInterval-blok wordt vervangen, de rest van het bestand
# blijft byte voor byte staan. Bewust geen plistlib: die herschrijft alles en gooit
# de comments weg, inclusief de uitleg waarom dit launchd is en geen cron, en
# waarom er caffeinate omheen zit. config_io.py doet hetzelfde voor config.yaml.
#
# Lezen kan beide vormen aan: een enkele <dict> (zoals de plist begon) en een
# <array> van dicts (meerdere tijdstippen). Schrijven doet altijd de array-vorm,
# ook bij een tijdstip, zodat er maar een vorm is om te onderhouden.
_BLOK_RE = re.compile(
    r"(<key>StartCalendarInterval</key>\s*)(<dict>.*?</dict>|<array>.*?</array>)",
    re.DOTALL,
)
_PAAR_RE = re.compile(
    r"<key>Hour</key>\s*<integer>(\d+)</integer>\s*"
    r"<key>Minute</key>\s*<integer>(\d+)</integer>",
    re.DOTALL,
)


def _blok(tijden):
    """De array-vorm opbouwen, met de inspringing die de rest van de plist volgt."""
    regels = ["<array>"]
    for uur, minuut in tijden:
        regels += [
            "        <dict>",
            "            <key>Hour</key>",
            f"            <integer>{uur}</integer>",
            "            <key>Minute</key>",
            f"            <integer>{minuut}</integer>",
            "        </dict>",
        ]
    regels.append("    </array>")
    return "\n".join(regels)


def _domein():
    return f"gui/{os.getuid()}"


def _launchctl(*args):
    """launchctl aanroepen. Geeft (exitcode, uitvoer) terug, gooit niets."""
    r = subprocess.run(
        ["launchctl", *args], capture_output=True, text=True, timeout=20
    )
    return r.returncode, (r.stdout + r.stderr).strip()


def _lees_tijden(tekst):
    """Alle ingestelde tijdstippen als [[uur, minuut], ...], oplopend gesorteerd."""
    m = _BLOK_RE.search(tekst)
    if not m:
        return []
    paren = [[int(u), int(mi)] for u, mi in _PAAR_RE.findall(m.group(2))]
    return sorted(paren)


def status():
    """Huidige stand: beschikbaar, aan, en de ingestelde tijdstippen."""
    if not PLIST.exists():
        return {"beschikbaar": False, "reden": "geen LaunchAgent geinstalleerd"}

    tijden = _lees_tijden(PLIST.read_text(encoding="utf-8"))

    geladen = _launchctl("print", f"{_domein()}/{LABEL}")[0] == 0

    # Staat het label niet in print-disabled, dan is het niet expliciet
    # uitgeschakeld en geldt de standaard: ingeschakeld.
    _, uit = _launchctl("print-disabled", _domein())
    uitgeschakeld = any(
        LABEL in regel and "disabled" in regel for regel in uit.splitlines()
    )

    return {
        "beschikbaar": True,
        "aan": geladen and not uitgeschakeld,
        "geladen": geladen,
        "uitgeschakeld": uitgeschakeld,
        "tijden": tijden,
    }


def zet_aan(aan):
    """Agent aan- of uitzetten, blijvend over een herstart heen.

    enable/disable zet de vlag die een herstart overleeft; bootstrap/bootout laat
    het meteen ingaan. Alleen het een zonder het ander geeft de verwarrende stand
    waarin het nu uit lijkt maar morgen weer aan staat, of andersom.
    """
    if not PLIST.exists():
        raise RuntimeError("geen LaunchAgent geinstalleerd")

    doel = f"{_domein()}/{LABEL}"
    if aan:
        _launchctl("enable", doel)
        code, uit = _launchctl("bootstrap", _domein(), str(PLIST))
        # Al geladen is geen fout; dan is de gewenste eindstand al bereikt.
        if code != 0 and "already" not in uit.lower():
            raise RuntimeError(f"bootstrap mislukt: {uit}")
    else:
        _launchctl("disable", doel)
        _launchctl("bootout", doel)  # niet geladen is geen fout
    return status()


def zet_tijden(tijden):
    """Tijdstippen wijzigen in de plist en de agent opnieuw inlezen.

    tijden is een lijst van (uur, minuut). Alleen het StartCalendarInterval-blok
    gaat om; de comments eromheen blijven staan. Het resultaat wordt door plutil
    gehaald voordat het geinstalleerd wordt, zodat een kapotte plist nooit de
    draaiende kopie vervangt.
    """
    schoon = []
    for uur, minuut in tijden or []:
        uur, minuut = int(uur), int(minuut)
        if not (0 <= uur <= 23 and 0 <= minuut <= 59):
            raise ValueError("uur moet 0 tot 23 zijn en minuut 0 tot 59")
        if [uur, minuut] not in schoon:
            schoon.append([uur, minuut])
    if not schoon:
        raise ValueError("er moet minstens een tijdstip zijn")
    schoon.sort()

    if not PLIST.exists():
        raise RuntimeError("geen LaunchAgent geinstalleerd")

    tekst = PLIST.read_text(encoding="utf-8")
    nieuw_blok = _blok(schoon)
    nieuw, n = _BLOK_RE.subn(lambda m: m.group(1) + nieuw_blok, tekst)
    if n != 1:
        raise RuntimeError("StartCalendarInterval niet gevonden in de plist")

    tijdelijk = PLIST.with_suffix(".plist.nieuw")
    tijdelijk.write_text(nieuw, encoding="utf-8")
    controle = subprocess.run(
        ["plutil", "-lint", str(tijdelijk)], capture_output=True, text=True
    )
    if controle.returncode != 0:
        tijdelijk.unlink(missing_ok=True)
        raise RuntimeError(f"plist zou ongeldig worden: {controle.stdout.strip()}")

    tijdelijk.replace(PLIST)
    # Bronversie in het project meenemen, zodat die niet gaat afwijken.
    if BRON_PLIST.exists():
        BRON_PLIST.write_text(nieuw, encoding="utf-8")

    # Opnieuw inlezen, anders blijft launchd het oude rooster aanhouden. Alleen
    # als hij aan staat; een uitgezette agent laten we uit.
    if status().get("aan"):
        _launchctl("bootout", f"{_domein()}/{LABEL}")
        code, uit = _launchctl("bootstrap", _domein(), str(PLIST))
        if code != 0 and "already" not in uit.lower():
            raise RuntimeError(f"opnieuw laden mislukt: {uit}")
    return status()
