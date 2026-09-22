"""Smoke test zonder netwerk: python test_lokaal.py

Voert nepvacatures door de hele pipeline (ontdubbelen, filteren, state, xlsx)
en ruimt zichzelf op. Handig om te checken of de installatie werkt.
"""
import shutil
from pathlib import Path

import yaml

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

    print(f"Alle checks OK. Testbestand: {pad.name}")

    shutil.rmtree(HIER / "output_test", ignore_errors=True)
    (HIER / "state_test.json").unlink(missing_ok=True)
    print("Testbestanden opgeruimd. Installatie werkt.")


if __name__ == "__main__":
    main()
