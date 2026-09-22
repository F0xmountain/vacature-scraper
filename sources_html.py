"""Generieke connector voor eigen careers-sites (werkenbij-pagina's).

Werkt voor sites die hun vacaturelijst servergerenderd aanbieden. Per site in
config.yaml: naam, url van de overzichtspagina, een regex-patroon voor de
vacaturelinks, en optioneel een vaste stad of een bedrijf_regex die de
werkgeversnaam uit de link haalt (handig voor sector-aggregators zoals
Banken.nl).

Sites met een JavaScript-gerenderde vacaturelijst (veel grote corporates,
waaronder APG) werken hier niet; die vang je via LinkedIn en Indeed, waar ze
toch alles cross-posten.
"""
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}
TIMEOUT = 20

SALARIS_RE = re.compile(
    r"€\s?[\d.,]+(?:\s*(?:-|tot)\s*€\s?[\d.,]+)?(?:\s*bruto)?"
    r"(?:\s*(?:per\s*maand|per\s*jaar|p\.?\s?/?\s?m\.?|p\.?\s?/?\s?j\.?))?",
    re.IGNORECASE,
)


def _salaris(tekst):
    """Alleen bedragen met een range of periode; losse eurobedragen overslaan."""
    m = SALARIS_RE.search(tekst)
    if not m:
        return ""
    s = m.group(0).strip()
    laag = s.lower()
    signalen = ("-", "tot", "maand", "jaar", "p.m", "p.j", "p/m", "p/j", "p m", "p j")
    return s if any(k in laag for k in signalen) else ""


def fetch_werkenbij(cfg):
    w = cfg.get("werkenbij") or {}
    detail = bool(cfg.get("detail_beschrijving"))
    jobs = []
    for site in w.get("sites") or []:
        try:
            rows = _fetch_site(site)
            # Detailpagina's niet hier ophalen: dat gebeurt na het filteren en
            # parallel (sources_detail), alleen voor wat de poort haalt. Hier alleen
            # de vlag zetten voor vacatures met een eigen detailpagina.
            if detail:
                for job in rows:
                    job["_detail"] = True
            print(f"[werkenbij] {site.get('naam', '?')}: {len(rows)} vacatures")
            jobs += rows
        except Exception as e:
            print(f"[werkenbij] {site.get('naam', '?')} mislukt: {e}")
        time.sleep(2)
    return jobs


def _fetch_site(site):
    r = requests.get(site["url"], headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return _parse(_html_uit(r, site), site)


def _html_uit(respons, site):
    """De HTML uit het antwoord halen.

    Normaal is dat gewoon de body. Sommige careers-sites (DNB draait op Radancy)
    serveren de vacaturelijst als HTML-fragment binnen een JSON-veld; zet dan
    json_veld in config.yaml, bijvoorbeeld json_veld: results. Zonder die sleutel
    verandert er niets aan het bestaande pad.
    """
    veld = site.get("json_veld")
    if not veld:
        return respons.text
    return (respons.json() or {}).get(veld, "") or ""


def _parse(html, site):
    soup = BeautifulSoup(html, "html.parser")
    patroon = re.compile(site["patroon"])
    bedrijf_re = re.compile(site["bedrijf_regex"]) if site.get("bedrijf_regex") else None

    out, gezien = [], set()
    for a in soup.find_all("a", href=patroon):
        # Scheidingsteken meegeven: zonder spatie plakt BeautifulSoup geneste
        # elementen aan elkaar ("Senior AssociateArtifer"). Dat brak de
        # titeluitsluitingen op woordgrens, want "Interim ManagerGalan" bevat geen
        # los woord 'manager'. De dedupe-sleutel verandert er niet van; job_key
        # haalt niet-woordtekens toch weg.
        #
        # Wikkelt de link de hele kaart (DNB), dan sleept de tekst opleiding,
        # uren en salaris mee de titel in. Dat is niet alleen lelijk: een woord
        # uit de kaarttekst kan dan een titel-uitsluiting laten afgaan en de
        # vacature onterecht droppen. Met titel_selector wijs je het element aan
        # dat de echte titel bevat, bijvoorbeeld titel_selector: h2.
        kies = site.get("titel_selector")
        titel_el = a.select_one(kies) if kies else None
        titel = (titel_el or a).get_text(" ", strip=True)
        if not titel:
            continue
        href = urljoin(site["url"], a["href"])
        if href in gezien:
            continue
        gezien.add(href)

        bedrijf = site.get("naam", "")
        if bedrijf_re:
            m = bedrijf_re.search(href)
            if m:
                bedrijf = m.group(1).replace("-", " ").title()

        kaart = (
            a.find_parent("li")
            or a.find_parent("tr")
            or a.find_parent("article")
            or a.parent
        )
        salaris = _salaris(kaart.get_text(" ", strip=True)) if kaart is not None else ""

        out.append({
            "bron": site.get("bron") or (site.get("naam", "werkenbij")).lower().replace(" ", ""),
            "bedrijf": bedrijf,
            "functie": titel,
            "locatie": site.get("stad", ""),
            "geplaatst": "",
            "salaris": salaris,
            "url": href,
            "beschrijving": "",
        })
    return out
