"""Lokale webserver voor de strakke HTML-interface (alternatief voor config_ui.py).

Draaien vanuit de projectmap:
    ./.venv/bin/python webui/server.py

Opent op http://127.0.0.1:8500. Serveert de HTML-pagina en biedt endpoints voor:
het profiel lezen, het profiel opslaan (comment-behoudend via config_io) en de
scraper draaien (dry-run of echte run). De zoek- en filterketen komt volledig uit
scraper.py; hier staat geen kopie van die logica. Alleen presentatie en een dunne
API-laag.
"""
import json
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

# De projectmap op het pad zetten zodat scraper en config_io importeerbaar zijn,
# ongeacht vanuit welke map de server wordt gestart.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config_io
import output
import scraper
import store  # alleen lezen: job_key levert de dedupe-sleutel voor de beoordeling

# webui/logos.py serveert bedrijfslogo's op /logo. Ontbreekt de module nog, dan
# blijft /logo uitgeschakeld en start de rest van de server gewoon door.
try:
    import logos
except ModuleNotFoundError:
    logos = None
    print("[webui] let op: webui/logos.py niet gevonden; /logo is uitgeschakeld")

# webui/oordeel.py is de enige schrijfroute naar beoordeling.json.
import oordeel

# webui/rooster.py is de enige schrijfroute naar launchd (de dagelijkse run).
import rooster

# webui/functies.py deelt titels in functiefamilies in, puur voor het filter.
import functies

# webui/vaardigheden.py haalt genoemde vaardigheden uit de omschrijving. Markeert
# alleen, net als flag_termen; er wordt niets mee gedropt of gerangschikt.
import vaardigheden

STATIC = Path(__file__).resolve().parent / "static"
HOST, POORT = "127.0.0.1", 8500

# Runs draaien in een achtergrondthread; de browser pollt de status. Zo blijft er
# geen verbinding minutenlang open (wat een BrokenPipe gaf als de browser die
# sloot) en kan er niet per ongeluk dubbel worden gedraaid.
_run_lock = threading.Lock()
_run_state = {"status": "idle", "resultaat": None, "fout": None}

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}

# Content-Security-Policy voor de HTML-pagina. Alleen de eigen origin, plus data:
# voor kleine afbeeldingen en inline styles die de pagina gebruikt.
_CSP = (
    "default-src 'self'; img-src 'self' data:; script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'"
)


def _schoon_lijst(waarden):
    """Lijst van strings opschonen: trim en lege eruit, zoals de editor deed."""
    schoon = []
    for w in waarden or []:
        tekst = str(w).strip()
        if tekst:
            schoon.append(tekst)
    return schoon


def _lees_profiel():
    """Huidig profiel uit config.yaml als platte dict voor de interface."""
    cfg = scraper.laad_config()
    boards = cfg.get("boards") or {}
    zoeklocaties = boards.get("locaties")
    if not zoeklocaties:
        enkel = boards.get("locatie")
        zoeklocaties = [enkel] if enkel else []
    return {
        "zoektermen": list(cfg.get("zoektermen") or []),
        "boards_locaties": list(zoeklocaties),
        "locaties_toegestaan": list(cfg.get("locaties_toegestaan") or []),
        "titel_uitsluiten": list(cfg.get("titel_uitsluiten") or []),
        "flag_termen": list(cfg.get("flag_termen") or []),
        "boards_actief": bool(boards.get("actief", True)),
        "boards_sites": list(boards.get("sites") or ["linkedin", "indeed"]),
        "resultaten_per_term": int(boards.get("resultaten_per_term", 25)),
        "max_uren_oud": int(boards.get("max_uren_oud", 72)),
        "ats_actief": bool((cfg.get("ats") or {}).get("actief", True)),
        "magnetme_actief": bool((cfg.get("magnetme") or {}).get("actief", True)),
        "werkenbij_actief": bool((cfg.get("werkenbij") or {}).get("actief", True)),
    }


def _schrijf_profiel(data):
    """Profiel wegschrijven via de comment-behoudende route uit config_io."""
    profiel = {
        "zoektermen": _schoon_lijst(data.get("zoektermen")),
        "titel_uitsluiten": _schoon_lijst(data.get("titel_uitsluiten")),
        "locaties_toegestaan": _schoon_lijst(data.get("locaties_toegestaan")),
        "flag_termen": _schoon_lijst(data.get("flag_termen")),
        "boards_actief": bool(data.get("boards_actief", True)),
        "boards_sites": _schoon_lijst(data.get("boards_sites")),
        "boards_locaties": _schoon_lijst(data.get("boards_locaties")),
        "resultaten_per_term": int(data.get("resultaten_per_term", 25)),
        "max_uren_oud": int(data.get("max_uren_oud", 72)),
        "ats_actief": bool(data.get("ats_actief", True)),
        "magnetme_actief": bool(data.get("magnetme_actief", True)),
        "werkenbij_actief": bool(data.get("werkenbij_actief", True)),
    }
    cfg = config_io.laad()
    config_io.schrijf_profiel(cfg, profiel)


_BESCHRIJVING_LIMIET = 10000  # ruim; op localhost is de payload geen punt, dit pakt alleen uitschieters


def _kort_beschrijving(tekst):
    """Kap een lange beschrijving netjes af, met een ellips erachter.

    Knipt op de laatste zinsgrens binnen de limiet; is die er niet, dan op de
    laatste spatie voor de limiet; anders hard op de limiet. Zo valt de knip niet
    midden in een woord. Een korte beschrijving blijft ongewijzigd. Dit gebeurt
    puur bij het doorgeven; de scraper en de bron worden niet aangeraakt.
    """
    tekst = tekst or ""
    if len(tekst) <= _BESCHRIJVING_LIMIET:
        return tekst
    knip = tekst[:_BESCHRIJVING_LIMIET]
    grens = max(knip.rfind(". "), knip.rfind("! "), knip.rfind("? "))
    if grens != -1:
        knip = knip[:grens + 1]
    else:
        spatie = knip.rfind(" ")
        if spatie != -1:
            knip = knip[:spatie]
    return knip.rstrip() + " ..."


def _rijen(jobs):
    """Alleen de velden die de interface toont, in vaste volgorde.

    geplaatst wordt meegegeven zoals de bron hem levert; de opmaak tot een
    leesbare datum gebeurt in de browser. Niet elke bron levert een datum.
    bron, salaris en beschrijving worden doorgelaten zoals de scraper ze al
    levert; beschrijving wordt met _kort_beschrijving afgekapt zodat de payload
    bij honderden rijen niet te groot wordt. Hier geen nieuwe logica.

    sleutel is de dedupe-sleutel uit store.job_key: dezelfde vacature krijgt over
    runs heen dezelfde sleutel, zodat de handmatige beoordeling blijft kloppen.
    """
    return [
        {
            "sleutel": store.job_key(j),
            # Alleen voor het filter in de interface; dit dropt of rangschikt niets.
            "familie": functies.familie(j.get("functie", "")),
            "familie_label": functies.label(functies.familie(j.get("functie", ""))),
            "functie": j.get("functie", ""),
            "bedrijf": j.get("bedrijf", ""),
            "locatie": j.get("locatie", ""),
            "geplaatst": j.get("geplaatst", ""),
            "flags": j.get("flags", ""),
            "url": j.get("url", ""),
            "bron": j.get("bron", ""),
            "salaris": j.get("salaris", ""),
            "beschrijving": _kort_beschrijving(j.get("beschrijving")),
            # Op de volledige tekst, niet op de afgekapte versie: anders zouden
            # vaardigheden die achterin staan stilletjes wegvallen.
            **_vaardigheden(j.get("beschrijving")),
        }
        for j in jobs
    ]


def _vaardigheden(tekst):
    gevonden = vaardigheden.uit_tekst(tekst)
    return {
        "vaardigheden": gevonden,
        # Telling, geen oordeel: hoeveel van de gevonden termen wijzen op echt
        # data-werk. Excel en taal tellen niet mee, die zeggen te weinig.
        "kern": vaardigheden.kernsignalen(gevonden),
    }


def _nu():
    """Tijdstempel in hetzelfde formaat als output.bewaar_run gebruikt.

    Nodig om een resultaat in het geheugen te kunnen vergelijken met de run die
    op schijf staat: de interface toont de nieuwste van de twee. Zonder dit bleef
    een dry-run van 's middags staan nadat de run van 20:00 allang klaar was.
    """
    return datetime.now().isoformat(timespec="seconds")


def _run(modus):
    """Dry-run of echte run via scraper.py; geeft een JSON-klaar resultaat."""
    cfg = scraper.laad_config()
    # Bij een echte run hoeven alleen nieuwe vacatures een omschrijving; alleen die
    # worden geexporteerd. De dry-run toont de volledige lijst en heeft de tekst
    # overal voor nodig, dus daar blijft het ophalen ongemoeid.
    kept, stats, opgehaald = scraper.verzamel_dedupe_filter(
        cfg, alleen_nieuw=(modus == "echt")
    )
    if modus == "echt":
        nieuw, pad = scraper.leg_vast(kept, cfg)
        return {
            "soort": "echt",
            "moment": _nu(),
            "opgehaald": opgehaald,
            "stats": stats,
            "over": len(kept),
            "pad": str(pad) if pad else None,
            "rijen": _rijen(nieuw),
        }
    return {
        "soort": "dry",
        "moment": _nu(),
        "opgehaald": opgehaald,
        "stats": stats,
        "over": len(kept),
        "rijen": _rijen(kept),
    }


def _start_run(modus):
    """Start een run in een achtergrondthread. Geeft False als er al een loopt."""
    global _run_state
    with _run_lock:
        if _run_state["status"] == "bezig":
            return False
        _run_state = {"status": "bezig", "resultaat": None, "fout": None}
    threading.Thread(target=_werk, args=(modus,), daemon=True).start()
    return True


def _werk(modus):
    """Achtergrondwerk: draait de scraper en bewaart het resultaat in _run_state."""
    global _run_state
    try:
        resultaat = _run(modus)
        nieuw = {"status": "klaar", "resultaat": resultaat, "fout": None}
    except Exception as e:
        nieuw = {"status": "fout", "resultaat": None, "fout": str(e)}
    with _run_lock:
        _run_state = nieuw


def _status():
    with _run_lock:
        return dict(_run_state)


class Handler(BaseHTTPRequestHandler):
    server_version = "VacatureWebUI/1.0"

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # browser sloot de verbinding; niets aan de hand

    def _bestand(self, naam):
        pad = (STATIC / naam).resolve()
        # Alleen bestanden binnen de static-map serveren.
        if STATIC not in pad.parents or not pad.is_file():
            self._json({"fout": "niet gevonden"}, 404)
            return
        data = pad.read_bytes()
        try:
            self.send_response(200)
            self.send_header("Content-Type", _MIME.get(pad.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            # Niet cachen. Dit draait lokaal, de bestanden zijn klein, en zonder
            # deze header blijft de browser na een wijziging de oude pagina tonen.
            # Dat kostte eerder onnodig zoekwerk ("ik zie de nieuwe knoppen niet").
            self.send_header("Cache-Control", "no-store, must-revalidate")
            if pad.suffix == ".html":
                self.send_header("Content-Security-Policy", _CSP)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        ontleed = urlsplit(self.path)
        pad = ontleed.path
        if pad == "/logo":
            bedrijf = parse_qs(ontleed.query).get("bedrijf", [""])[0]
            if logos is None:
                self._json({"fout": "logos-module niet beschikbaar"}, 404)
            else:
                logos.serveer(self, bedrijf)
            return
        if self.path in ("/", "/index.html"):
            self._bestand("index.html")
        elif self.path in ("/style.css", "/app.js", "/logo.svg"):
            self._bestand(self.path.lstrip("/"))
        elif self.path == "/api/profiel":
            try:
                self._json(_lees_profiel())
            except Exception as e:
                self._json({"fout": str(e)}, 500)
        elif self.path == "/api/run/status":
            self._json(_status())
        elif self.path == "/api/oordelen":
            try:
                self._json(oordeel.laad())
            except Exception as e:
                self._json({"fout": str(e)}, 500)
        elif self.path == "/api/laatste":
            # De laatst weggeschreven echte run, inclusief omschrijving. Hiermee
            # toont de interface bij het opstarten de oogst van de run van 08:30,
            # zonder alles opnieuw op te halen.
            try:
                data = output.lees_laatste_run(scraper.laad_config())
                if not data:
                    self._json({"leeg": True})
                else:
                    self._json({
                        "soort": "bewaard",
                        "moment": data.get("moment"),
                        "runs": data.get("runs", 1),
                        "over": data.get("aantal", 0),
                        "rijen": _rijen(data.get("jobs") or []),
                    })
            except Exception as e:
                self._json({"fout": str(e)}, 500)
        elif self.path == "/api/rooster":
            try:
                self._json(rooster.status())
            except Exception as e:
                self._json({"fout": str(e)}, 500)
        else:
            self._json({"fout": "niet gevonden"}, 404)

    def do_POST(self):
        lengte = int(self.headers.get("Content-Length") or 0)
        ruw = self.rfile.read(lengte) if lengte else b"{}"
        try:
            data = json.loads(ruw or b"{}")
        except json.JSONDecodeError:
            self._json({"fout": "ongeldige JSON"}, 400)
            return

        if self.path == "/api/profiel":
            try:
                _schrijf_profiel(data)
                self._json({"ok": True})
            except Exception as e:
                self._json({"fout": str(e)}, 500)
            return

        if self.path == "/api/run":
            modus = data.get("modus")
            if modus not in ("dry", "echt"):
                self._json({"fout": "onbekende modus"}, 400)
                return
            # Start de run in de achtergrond en keer meteen terug; de browser
            # pollt /api/run/status. Zo blijft de verbinding niet minutenlang open.
            if _start_run(modus):
                self._json({"status": "bezig"})
            else:
                self._json({"fout": "Er loopt al een run.", "status": "bezig"}, 409)
            return

        if self.path == "/api/oordeel":
            # sleutel is de dedupe-sleutel; oordeel is "ja", "nee" of "onbeoordeeld"
            # (die laatste wist het oordeel weer). oordeel.py is de enige schrijfroute.
            try:
                oordeel.zet(data.get("sleutel"), data.get("oordeel"))
                self._json({"ok": True})
            except ValueError as e:
                self._json({"fout": str(e)}, 400)
            except Exception as e:
                self._json({"fout": str(e)}, 500)
            return

        if self.path == "/api/rooster":
            # Dagelijkse run bedienen. 'aan' zet hem aan of uit; 'tijden' is een
            # lijst van [uur, minuut] en vervangt het hele rooster. Beide mogen in
            # een verzoek. rooster.py is de enige schrijfroute naar launchd; hier
            # staat geen launchctl-aanroep.
            try:
                if "tijden" in data:
                    rooster.zet_tijden(data["tijden"])
                if "aan" in data:
                    rooster.zet_aan(bool(data["aan"]))
                self._json(rooster.status())
            except ValueError as e:
                self._json({"fout": str(e)}, 400)
            except Exception as e:
                self._json({"fout": str(e)}, 500)
            return

        if self.path == "/api/oordelen/wis":
            # Meerdere oordelen in een keer wissen (de 'alles wissen'-knop). Gaat via
            # dezelfde schrijfroute in oordeel.py.
            sleutels = data.get("sleutels")
            if not isinstance(sleutels, list):
                self._json({"fout": "sleutels ontbreekt of is geen lijst"}, 400)
                return
            try:
                oordeel.wis(sleutels)
                self._json({"ok": True})
            except Exception as e:
                self._json({"fout": str(e)}, 500)
            return

        self._json({"fout": "niet gevonden"}, 404)

    def log_message(self, fmt, *args):
        # Beknopte log naar stdout in plaats van de standaard stderr-ruis.
        print(f"[webui] {self.command} {self.path}")


def main():
    server = ThreadingHTTPServer((HOST, POORT), Handler)
    print(f"Webinterface op http://{HOST}:{POORT}  (Ctrl+C om te stoppen)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGestopt.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
