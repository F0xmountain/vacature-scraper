"""Vacature-scraper voor Bas Vossenberg.

    python scraper.py              normale run, schrijft xlsx en onthoudt wat gezien is
    python scraper.py --dry-run    toont resultaat in beeld, schrijft niets weg
    python scraper.py --bron ats   draait één bron (boards, ats, magnetme, werkenbij)

Configuratie: config.yaml. Zelftest: python check.py. Uitleg: README.md.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from filters import split_drop, wijs_flags
from output import bewaar_run, export
from sources_detail import vul_beschrijvingen
from store import dedupe, job_key, load_state, save_state, split_new


def verzamel(cfg, bron=None):
    """Haal de listings van elke actieve bron op, de bronnen parallel.

    De vier bronnen zijn onafhankelijk en vooral I/O-bepaald (netwerk), dus ze
    draaien tegelijk in threads in plaats van na elkaar; de trage borden overlappen
    zo met de rest. De resultaten worden in vaste bronvolgorde samengevoegd (boards,
    ats, magnetme, werkenbij), zodat het ontdubbelen daarna dezelfde voorrang houdt
    als voorheen. Omschrijvingen van detailpagina's worden hier niet opgehaald; dat
    gebeurt pas na het filteren, alleen voor wat de poort haalt (zie
    verzamel_dedupe_filter).
    """
    taken = []
    if bron in (None, "boards") and (cfg.get("boards") or {}).get("actief"):
        from sources_boards import fetch_boards
        taken.append(fetch_boards)
    if bron in (None, "ats") and (cfg.get("ats") or {}).get("actief"):
        from sources_ats import fetch_ats
        taken.append(fetch_ats)
    if bron in (None, "magnetme") and (cfg.get("magnetme") or {}).get("actief"):
        from sources_magnetme import fetch_magnetme
        taken.append(fetch_magnetme)
    if bron in (None, "werkenbij") and (cfg.get("werkenbij") or {}).get("actief"):
        from sources_html import fetch_werkenbij
        taken.append(fetch_werkenbij)

    if not taken:
        return []

    jobs = []
    with ThreadPoolExecutor(max_workers=len(taken)) as ex:
        futures = [ex.submit(fn, cfg) for fn in taken]
        # In indien-volgorde uitlezen: parallel gedraaid, maar vaste volgorde zodat
        # het ontdubbelen deterministisch blijft (boards wint van magnetme, enz.).
        for fut in futures:
            jobs += fut.result()
    return jobs


def toon(jobs, limiet=25):
    print(f"\n{'FUNCTIE':<44} {'BEDRIJF':<22} {'LOCATIE':<16} FLAGS")
    for j in jobs[:limiet]:
        print(
            f"{j['functie'][:43]:<44} {j['bedrijf'][:21]:<22} "
            f"{(j['locatie'] or '')[:15]:<16} {j.get('flags', '')}"
        )
    if len(jobs) > limiet:
        print(f"... en nog {len(jobs) - limiet}")


def laad_config():
    """Lees config.yaml als platte dict, net als de terminal-run doet."""
    return yaml.safe_load(
        Path(__file__).with_name("config.yaml").read_text(encoding="utf-8")
    )


def verzamel_dedupe_filter(cfg, bron=None, alleen_nieuw=False):
    """Haal op, ontdubbel en filter. Geeft (kept, stats, opgehaald) terug.

    Dit is exact de keten van de dry-run; er wordt niets weggeschreven en
    state.json wordt niet aangeraakt. De UI hergebruikt deze functie zodat er
    geen tweede kopie van de zoek- en filterlogica ontstaat.

    Volgorde: listings ophalen (bronnen parallel), ontdubbelen, de harde drops op
    titel en locatie, dan pas de omschrijvingen ophalen voor wat overblijft (bronnen
    met een eigen detailpagina, parallel), en tot slot de flags toekennen. Zo worden
    er geen omschrijvingen opgehaald voor weggefilterde vacatures, terwijl flags die
    op de omschrijving matchen behouden blijven.

    alleen_nieuw beperkt het ophalen van omschrijvingen tot vacatures die nog niet
    in state.json staan. Voor een echte run is dat genoeg, want alleen nieuwe
    vacatures worden geexporteerd. Dat maakt een tweede run op een dag goedkoop:
    die kent bijna alles al en doet dus bijna geen detailrequests. Zonder deze
    beperking haalt elke run de omschrijving op van alles wat door de poort komt,
    ook van wat hij gisteren al zag. De dry-run laat hem uit, want die toont de
    volledige lijst en heeft de tekst overal voor nodig.
    """
    jobs = verzamel(cfg, bron)
    opgehaald = len(jobs)
    jobs = dedupe(jobs)
    kept, stats = split_drop(jobs, cfg)

    if alleen_nieuw:
        # Alleen lezen; split_new in leg_vast doet later het echte bijwerken.
        state = load_state()
        for job in kept:
            if job_key(job) in state:
                job.pop("_detail", None)

    vul_beschrijvingen(kept)
    wijs_flags(kept, cfg)
    return kept, stats, opgehaald


def leg_vast(kept, cfg):
    """Echte run: bepaal nieuwe vacatures, werk state.json bij en schrijf de xlsx.

    Zelfde logica en volgorde als de echte run hieronder in main(): load_state,
    split_new, save_state, dan export. Geeft (nieuw, pad) terug; pad is None als
    er niets nieuws was.
    """
    state = load_state()
    nieuw = split_new(kept, state)
    save_state(state)
    pad = export(nieuw, cfg) if nieuw else None
    # De omschrijvingen apart bewaren; de xlsx heeft die kolom niet en zonder dit
    # gooit de run de tekst weg die hij net heeft opgehaald. De webinterface leest
    # dit bestand bij het opstarten, zodat de oogst van 08:30 er meteen staat.
    bewaar_run(nieuw, cfg, pad)
    return nieuw, pad


def main():
    p = argparse.ArgumentParser(description="Vacature-scraper")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="toon het resultaat zonder state.json of output te schrijven",
    )
    p.add_argument(
        "--bron",
        choices=["boards", "ats", "magnetme", "werkenbij"],
        help="draai maar één bron",
    )
    p.add_argument(
        "--uren",
        type=int,
        help=(
            "overschrijf max_uren_oud voor deze run. Het vaste rooster kijkt kort "
            "terug; hiermee doe je eenmalig een diepe inhaalslag, bijvoorbeeld "
            "--uren 72 na een paar dagen weg"
        ),
    )
    args = p.parse_args()

    cfg = laad_config()
    if args.uren:
        cfg.setdefault("boards", {})["max_uren_oud"] = args.uren
        print(f"Terugkijktijd voor deze run: {args.uren} uur")

    # Bij een echte run alleen voor nieuwe vacatures de omschrijving ophalen.
    kept, stats, opgehaald = verzamel_dedupe_filter(
        cfg, args.bron, alleen_nieuw=not args.dry_run
    )
    print(f"\nOpgehaald: {opgehaald} vacatures")
    print(
        f"Na ontdubbelen: {stats['totaal']} | gedropt op titel: {stats['titel']}"
        f" | gedropt op locatie: {stats['locatie']} | over: {len(kept)}"
    )

    if args.dry_run:
        print("\nDRY RUN: er wordt niets weggeschreven en niets onthouden.")
        if kept:
            toon(kept)
        return

    nieuw, pad = leg_vast(kept, cfg)
    if not nieuw:
        print("Geen nieuwe vacatures sinds de vorige run.")
        return
    print(f"{len(nieuw)} nieuwe vacatures weggeschreven naar: {pad}")


if __name__ == "__main__":
    main()
