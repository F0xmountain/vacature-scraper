"""Smoke test zonder netwerk: python test_lokaal.py

Voert nepvacatures door de hele pipeline (ontdubbelen, filteren, state, xlsx)
en ruimt zichzelf op. Handig om te checken of de installatie werkt.
"""
import shutil
from pathlib import Path

import store
from filters import apply_filters
from output import export
from store import dedupe, load_state, save_state, split_new

HIER = Path(__file__).parent

FAKE = [
    {"bron": "linkedin", "bedrijf": "Testbank", "functie": "Credit Risk Analyst",
     "locatie": "Amsterdam, Noord-Holland", "geplaatst": "2026-07-13", "salaris": "",
     "url": "https://example.com/1", "beschrijving": "kredietanalyse en rapportage"},
    {"bron": "indeed", "bedrijf": "Testbank", "functie": "Credit Risk Analyst",
     "locatie": "Amsterdam", "geplaatst": "2026-07-13", "salaris": "",
     "url": "https://example.com/1b", "beschrijving": ""},
    {"bron": "linkedin", "bedrijf": "Testbank", "functie": "Senior Risk Analyst",
     "locatie": "Amsterdam", "geplaatst": "2026-07-12", "salaris": "",
     "url": "https://example.com/2", "beschrijving": ""},
    {"bron": "indeed", "bedrijf": "Verkooporg", "functie": "Sales Analyst",
     "locatie": "Amsterdam", "geplaatst": "2026-07-12", "salaris": "",
     "url": "https://example.com/3", "beschrijving": ""},
    {"bron": "glassdoor", "bedrijf": "Zuidbank", "functie": "Portfolio Analyst",
     "locatie": "Rotterdam", "geplaatst": "2026-07-12", "salaris": "",
     "url": "https://example.com/4", "beschrijving": ""},
    {"bron": "recruitee", "bedrijf": "Boutique", "functie": "Reporting Analist",
     "locatie": "Amsterdam", "geplaatst": "2026-07-11", "salaris": "",
     "url": "https://example.com/5", "beschrijving": "compliance touchpoint en kyc"},
]


# Eigen profiel voor de test, los van config.yaml. Dat laatste is het
# persoonlijke zoekprofiel van de gebruiker: het staat in .gitignore, het bestaat
# dus niet in een verse kloon, en het verandert met elke afstelling. Een test die
# daarop leunt faalt zodra iemand een term aanpast, en dat is geen defect in de
# code. De verwachtingen hieronder horen bij dit vaste profiel.
TEST_CFG = {
    "titel_uitsluiten": ["senior", "sales"],
    "locaties_toegestaan": ["amsterdam", "rotterdam", "remote"],
    "flag_termen": ["compliance", "kyc"],
}


def main():
    cfg = dict(TEST_CFG)
    cfg["output_map"] = "output_test"
    store.STATE_PATH = HIER / "state_test.json"

    jobs = dedupe(list(FAKE))
    assert len(jobs) == 5, f"ontdubbelen faalt: {len(jobs)}"
    dubbel = next(j for j in jobs if j["functie"] == "Credit Risk Analyst")
    assert dubbel["bron"] == "indeed, linkedin", f"bronmerge faalt: {dubbel['bron']}"

    kept, stats = apply_filters(jobs, cfg)
    titels = {j["functie"] for j in kept}
    assert "Senior Risk Analyst" not in titels, "senior niet gedropt"
    assert "Sales Analyst" not in titels, "sales niet gedropt"
    assert "Portfolio Analyst" in titels, "Rotterdam staat toegestaan, moet blijven"
    assert len(kept) == 3, f"verwacht 3 over, kreeg {len(kept)}"
    reporting = next(j for j in kept if j["functie"] == "Reporting Analist")
    assert "compliance" in reporting["flags"] and "kyc" in reporting["flags"], "flags falen"

    # Locatiefilter robuust tegen invoerformaat: "Rotterdam, Netherlands" in de
    # toegestane lijst moet matchen op een board-locatie in het uitgebreide
    # formaat "Rotterdam, South Holland, Netherlands".
    rott_cfg = {"locaties_toegestaan": ["Rotterdam, Netherlands"]}
    rott_kept, _ = apply_filters(
        [{"functie": "Portfolio Analyst",
          "locatie": "Rotterdam, South Holland, Netherlands", "beschrijving": ""}],
        rott_cfg,
    )
    assert len(rott_kept) == 1, "Rotterdam-formaat matcht niet op board-locatie"
    onbekend_kept, _ = apply_filters(
        [{"functie": "Portfolio Analyst", "locatie": "Berlin, Germany", "beschrijving": ""}],
        rott_cfg,
    )
    assert len(onbekend_kept) == 0, "stad buiten de lijst wordt niet gedropt"

    state = load_state()
    nieuw = split_new(kept, state)
    save_state(state)
    assert len(nieuw) == 3, "state faalt (eerste run)"
    assert len(split_new(kept, load_state())) == 0, "state faalt (tweede run)"

    pad = export(nieuw, cfg)
    assert pad.exists() and pad.stat().st_size > 0, "xlsx niet geschreven"

    # Magnet.me parser op HTML in de structuur van de echte overzichtspagina
    from sources_magnetme import _parse_listing
    html = """
    <ol>
      <li>
        <img alt="Logo Testbank" src="x"/>
        <p>Testbank</p><p>Financieel &amp; Banken</p>
        <a href="/nl-NL/vacature/123456/credit-analyst">Credit Analyst</a>
        <ul><li>Amsterdam</li><li>0 - 2 jaar ervaring</li>
        <li>€ 3.500 - € 4.400 per maand</li></ul>
      </li>
      <li>
        <img alt="Logo Zuidfonds" src="x"/>
        <a href="https://magnet.me/nl-NL/vacature/654321/portfolio-analyst">Portfolio Analyst</a>
      </li>
    </ol>
    """
    rows = _parse_listing(html, "amsterdam")
    assert len(rows) == 2, f"magnetme parser: verwacht 2, kreeg {len(rows)}"
    assert rows[0]["bedrijf"] == "Testbank", "magnetme bedrijf faalt"
    assert rows[0]["salaris"].startswith("€"), "magnetme salaris faalt"
    assert rows[0]["url"].startswith("https://magnet.me/nl-NL/vacature/123456"), "magnetme url faalt"
    assert rows[1]["locatie"] == "amsterdam", "magnetme locatie faalt"

    # Generieke werkenbij-parser: DNB-lijststructuur
    from sources_html import _parse as parse_wb
    dnb_html = """
    <ul>
      <li><a href="/vacatures/kredietanalist-e1234">Kredietanalist</a>
          <span>Master</span><span>€ 3.840 - € 5.250 bruto p.m.</span></li>
      <li><a href="/vacatures/stagiair-kunst-e5678">Stagiair Kunst</a></li>
      <li><a href="/vacatures">Alle vacatures</a></li>
    </ul>
    """
    dnb_site = {"naam": "DNB", "bron": "werkenbijdnb",
                "url": "https://www.werkenbijdnb.nl/vacatures",
                "patroon": r"/vacatures/[a-z0-9-]+-e\d+", "stad": "amsterdam"}
    rows = parse_wb(dnb_html, dnb_site)
    assert len(rows) == 2, f"werkenbij dnb: verwacht 2, kreeg {len(rows)}"
    assert rows[0]["salaris"].startswith("€ 3.840"), "werkenbij salaris faalt"
    assert rows[0]["url"].endswith("/vacatures/kredietanalist-e1234"), "werkenbij url faalt"
    assert rows[0]["locatie"] == "amsterdam", "werkenbij stad faalt"

    # Generieke werkenbij-parser: Banken.nl-tabelstructuur met bedrijf uit de link
    banken_html = """
    <table><tr>
      <td><a href="https://www.banken.nl/vacatures/46880/de-nederlandsche-bank/junior-toezichthouder">Junior toezichthouder</a></td>
      <td><a href="https://www.banken.nl/vacatures/46880/de-nederlandsche-bank/junior-toezichthouder">Toezicht</a></td>
      <td><a href="https://www.banken.nl/vacatures/46880/de-nederlandsche-bank/junior-toezichthouder">Amsterdam</a></td>
    </tr></table>
    """
    banken_site = {"naam": "Banken.nl", "bron": "banken.nl",
                   "url": "https://www.banken.nl/vacatures",
                   "patroon": r"/vacatures/\d+/",
                   "bedrijf_regex": r"/vacatures/\d+/([a-z0-9-]+)/"}
    rows = parse_wb(banken_html, banken_site)
    assert len(rows) == 1, f"werkenbij banken.nl: verwacht 1, kreeg {len(rows)}"
    assert rows[0]["bedrijf"] == "De Nederlandsche Bank", "bedrijf_regex faalt"
    assert rows[0]["functie"] == "Junior toezichthouder", "banken.nl titel faalt"

    test_bedrijf_uitsluiten()
    test_functies()
    test_vaardigheden()
    test_runvenster(cfg)
    test_linkedin_datum()
    test_rooster_tijden()
    test_werkenbij_opties()

    print(f"Alle checks OK. Testbestand: {pad.name}")


def test_bedrijf_uitsluiten():
    """Uitsluiten op werkgever, op woordgrens net als bij titels."""
    cfg = {"locaties_toegestaan": ["amsterdam"], "bedrijf_uitsluiten": ["marriott"]}
    jobs = [{"functie": "Analist", "bedrijf": "Marriott International", "locatie": "Amsterdam"},
            {"functie": "Analist", "bedrijf": "Rabobank", "locatie": "Amsterdam"},
            {"functie": "Analist", "bedrijf": "", "locatie": "Amsterdam"}]
    kept, stats = apply_filters([dict(j) for j in jobs], cfg)
    assert len(kept) == 2, f"bedrijf_uitsluiten: verwacht 2 over, kreeg {len(kept)}"
    assert stats["bedrijf"] == 1, "bedrijf-drop wordt niet geteld"
    assert all("marriott" not in (j["bedrijf"] or "").lower() for j in kept)
    # Een ontbrekend veld mag niets veranderen; oudere configs moeten blijven werken.
    kaal, st = apply_filters([dict(j) for j in jobs], {"locaties_toegestaan": ["amsterdam"]})
    assert len(kaal) == 3 and st["bedrijf"] == 0, "ontbrekend veld verandert gedrag"


def test_functies():
    """Indeling in families; de volgorde bepaalt de uitkomst."""
    import functies
    verwacht = {
        "Credit Risk Analyst": "analist",      # analist wint van risk
        "Compliance Officer": "risk",          # geen analistenterm, dus wel risk
        "Business Controller": "controller",
        "Data Engineer": "data",
        "Wax Specialist": "overig",
    }
    for titel, fam in verwacht.items():
        echt = functies.familie(titel)
        assert echt == fam, f"functies: {titel!r} -> {echt}, verwacht {fam}"
    assert functies.label("analist") == "Analist"
    assert functies.familie("") == "overig", "lege titel moet overig geven"


def test_vaardigheden():
    """Vaardigheden uit tekst, en de telling van datasignalen."""
    import vaardigheden as V
    tekst = "Je werkt met Excel, SQL en Python aan forecasting. Nederlands vereist."
    gevonden = V.uit_tekst(tekst)
    for v in ("Excel", "SQL", "Python", "forecasting", "Nederlands"):
        assert v in gevonden, f"vaardigheden: {v} niet gevonden"
    # Excel en taal tellen niet mee als datasignaal; SQL, Python en forecasting wel.
    assert V.kernsignalen(gevonden) == 3, f"kernsignalen: {V.kernsignalen(gevonden)}"
    assert V.uit_tekst("") == [], "lege tekst moet een lege lijst geven"
    # Hoofdlettergevoelig, anders matcht 'sas' en 'ra' overal op.
    assert "SAS" in V.uit_tekst("ervaring met SAS en Python")
    assert "SAS" not in V.uit_tekst("hij was bezig met de kassa")


def test_runvenster(cfg):
    """bewaar_run en lees_laatste_run: het venster mag niets kwijtraken."""
    from output import BEWAAR_RUNS, bewaar_run, lees_laatste_run
    pad = HIER / "output_test" / "laatste_run.json"
    pad.unlink(missing_ok=True)

    def job(n):
        return {"bron": "linkedin", "bedrijf": f"B{n}", "functie": f"F{n}",
                "locatie": "Amsterdam", "geplaatst": "2026-09-26", "salaris": "",
                "flags": "", "url": f"https://example.com/{n}",
                "beschrijving": f"tekst {n}", "eerste_keer_gezien": "2026-09-26",
                "_detail": True}

    bewaar_run([job(1), job(2)], cfg)
    bewaar_run([job(2), job(3)], cfg)          # overlap op url
    d = lees_laatste_run(cfg)
    assert d["runs"] == 2, f"venster telt {d['runs']} runs"
    assert d["aantal"] == 3, f"ontdubbelen op url faalt: {d['aantal']}"
    # Nieuwste run eerst, binnen een run de oorspronkelijke volgorde. F2 zat in
    # beide runs en telt mee vanaf zijn nieuwste voorkomen, dus voor F1.
    assert [j["functie"] for j in d["jobs"]] == ["F2", "F3", "F1"], \
        f"volgorde klopt niet: {[j['functie'] for j in d['jobs']]}"
    assert d["jobs"][0]["beschrijving"], "omschrijving gaat verloren"
    assert "_detail" not in d["jobs"][0], "interne vlag lekt het bestand in"

    bewaar_run([], cfg)                        # lege run wist het venster niet
    assert lees_laatste_run(cfg)["aantal"] == 3, "lege run wist eerdere vangst"

    for i in range(BEWAAR_RUNS + 2):
        bewaar_run([job(100 + i)], cfg)
    assert lees_laatste_run(cfg)["runs"] == BEWAAR_RUNS, "venster kapt niet af"


def test_linkedin_datum():
    """Plaatsingsdatum uit de detailpagina; jobspy mist die bij verse vacatures."""
    from datetime import date, timedelta
    from sources_detail import _linkedin_datum
    vandaag = date.today()
    for tekst, dagen in [("11 hours ago", 0), ("1 day ago", 1),
                         ("2 days ago", 2), ("1 week ago", 7)]:
        html = f'<span class="posted-time-ago__text">{tekst}</span>'
        verwacht = (vandaag - timedelta(days=dagen)).isoformat()
        assert _linkedin_datum(html) == verwacht, f"datum uit {tekst!r} faalt"
    assert _linkedin_datum("<span>geen datum hier</span>") == ""
    assert _linkedin_datum("") == ""


def test_rooster_tijden():
    """Roosterblok lezen en opbouwen, beide vormen."""
    import sys
    sys.path.insert(0, str(HIER / "webui"))
    import rooster
    enkel = ("<key>StartCalendarInterval</key><dict>"
             "<key>Hour</key><integer>8</integer>"
             "<key>Minute</key><integer>30</integer></dict>")
    assert rooster._lees_tijden(enkel) == [[8, 30]], "enkele dict wordt niet gelezen"
    meervoud = "<key>StartCalendarInterval</key>" + rooster._blok([[20, 0], [8, 0]])
    assert rooster._lees_tijden(meervoud) == [[8, 0], [20, 0]], "array wordt niet gesorteerd gelezen"
    assert rooster._lees_tijden("<key>Iets anders</key>") == []


def test_werkenbij_opties():
    """json_veld en titel_selector: nodig voor Radancy-sites zoals DNB."""
    import json as _json
    from sources_html import _html_uit, _parse

    class NepRespons:
        text = '{"results": "<a href=\'/nl/banen/x/y/1/2\'><h2>Analist</h2>extra tekst</a>"}'
        def json(self):
            return _json.loads(self.text)

    site = {"naam": "DNB", "bron": "werkenbijdnb", "url": "https://example.invalid/x",
            "json_veld": "results", "patroon": r"/nl/banen/", "titel_selector": "h2",
            "stad": "amsterdam"}
    rows = _parse(_html_uit(NepRespons(), site), site)
    assert len(rows) == 1, f"json_veld: verwacht 1 rij, kreeg {len(rows)}"
    assert rows[0]["functie"] == "Analist", f"titel_selector faalt: {rows[0]['functie']!r}"
    # Zonder json_veld blijft het pad ongewijzigd: gewone HTML uit de body.
    zonder = {k: v for k, v in site.items() if k != "json_veld"}
    assert _html_uit(NepRespons(), zonder) == NepRespons.text


if __name__ == "__main__":
    try:
        main()
    finally:
        # Ook opruimen als een assert faalt, anders blijft er rommel staan die de
        # volgende run vertroebelt.
        shutil.rmtree(HIER / "output_test", ignore_errors=True)
        (HIER / "state_test.json").unlink(missing_ok=True)
        print("Testbestanden opgeruimd.")
