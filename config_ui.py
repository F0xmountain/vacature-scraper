"""Kleine lokale interface om config.yaml aan te passen zonder de YAML met de hand te bewerken.

Draaien vanuit de projectmap:
    ./.venv/bin/python -m streamlit run config_ui.py

Opent in je browser. Past alleen config.yaml aan; raakt de scraper niet.
Comments en structuur in config.yaml blijven behouden (ruamel.yaml).
"""
import pandas as pd
import streamlit as st

import scraper
from config_io import laad, schrijf_profiel

# Termen die als ervaringsniveau apart getoond worden; de rest van
# titel_uitsluiten blijft een vrije lijst.
SENIORITY = ["senior", "medior", "lead", "head of", "director", "manager"]


def lijst_editor(waarden, sleutel, kolom, hoogte):
    """Bewerkbare eenkoloms-lijst via st.data_editor.

    Toevoegen en verwijderen gaat met de knoppen van de tabel. Geeft altijd een
    platte lijst van opgeschoonde strings terug, zodat de opslaglogica ongewijzigd
    blijft werken.
    """
    df = pd.DataFrame({kolom: list(waarden)})
    bewerkt = st.data_editor(
        df,
        key=sleutel,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        height=hoogte,
        column_config={kolom: st.column_config.TextColumn(kolom, width="large")},
    )
    schoon = []
    for waarde in bewerkt[kolom].tolist():
        if pd.isna(waarde):
            continue
        tekst = str(waarde).strip()
        if tekst:
            schoon.append(tekst)
    return schoon


def bron_status(aan):
    """Kleine statusregel onder een bron-schakelaar."""
    if aan:
        return "● Actief, gaat mee in de run"
    return "○ Uit, wordt overgeslagen"


def toon_resultaat(rijen):
    """Toon gevonden vacatures als tabel met een klikbare link per rij."""
    if not rijen:
        st.info("Geen vacatures om te tonen.")
        return
    df = pd.DataFrame(
        [
            {
                "Functie": r.get("functie", ""),
                "Bedrijf": r.get("bedrijf", ""),
                "Locatie": r.get("locatie", ""),
                "Flags": r.get("flags", ""),
                "Link": r.get("url", ""),
            }
            for r in rijen
        ]
    )
    hoogte = min(len(df) * 36 + 40, 600)
    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        height=hoogte,
        column_config={
            "Functie": st.column_config.TextColumn("Functie", width="large"),
            "Bedrijf": st.column_config.TextColumn("Bedrijf", width="medium"),
            "Locatie": st.column_config.TextColumn("Locatie", width="medium"),
            "Flags": st.column_config.TextColumn("Flags", width="small"),
            "Link": st.column_config.LinkColumn("Link", display_text="openen", width="small"),
        },
    )


st.set_page_config(
    page_title="Vacature-scraper zoekprofiel",
    layout="wide",
    initial_sidebar_state="expanded",
)

cfg = laad()
boards = cfg.setdefault("boards", {})

with st.sidebar:
    st.title("Zoekprofiel")
    st.write(
        "Hier stel je in waar de scraper op zoekt: welke functies, waar, wat je "
        "uitsluit en welke bronnen meedraaien."
    )
    st.caption(
        "Wijzigingen gaan naar config.yaml. De comments in dat bestand blijven "
        "behouden. Draai na het opslaan altijd eerst een dry-run ter controle."
    )
    st.divider()
    st.caption("Zo draai je een dry-run in de terminal:")
    st.code("./.venv/bin/python scraper.py --dry-run", language="bash")

st.title("Zoekprofiel")
st.caption(
    "Stel je zoekprofiel samen, sla het op en zoek. Opslaan schrijft naar "
    "config.yaml en behoudt de comments."
)
st.divider()

kol_functie, kol_locatie = st.columns(2, gap="large")

with kol_functie:
    with st.container(border=True):
        st.subheader("Zoektermen")
        st.caption(
            "Waarop de borden (LinkedIn, Indeed) worden doorzocht. Toevoegen en "
            "verwijderen met de knoppen rechtsboven in de tabel."
        )
        zoektermen_lijst = lijst_editor(
            cfg.get("zoektermen") or [], "ed_zoektermen", "Zoekterm", 360,
        )

with kol_locatie:
    with st.container(border=True):
        st.subheader("Locaties")

        st.markdown("**Zoeklocaties borden**")
        st.caption(
            "WAAR de borden zoeken (LinkedIn, Indeed). Weinig items; elke locatie "
            "is een aparte zoekronde per zoekterm, dus meer locaties betekent meer "
            "requests. Kale steden mogen: 'Amsterdam' wordt bij het zoeken "
            "aangevuld tot 'Amsterdam, Netherlands'. Heb je zelf een komma getypt, "
            "dan blijft je invoer staan."
        )
        zoeklocaties_start = boards.get("locaties")
        if not zoeklocaties_start:
            enkel = boards.get("locatie")
            zoeklocaties_start = [enkel] if enkel else []
        boards_locaties_lijst = lijst_editor(
            zoeklocaties_start, "ed_boards_locaties", "Zoeklocatie", 160,
        )
        st.caption(
            "Let op: een zoeklocatie hoort ook bij de toegestane locaties hieronder "
            "te staan. Anders wordt zijn resultaat wel opgehaald, maar daarna "
            "weggefilterd."
        )

        st.markdown("**Toegestane locaties (filter)**")
        st.caption(
            "Het FILTER op alles wat is opgehaald, uit alle bronnen. Substring-match "
            "op de locatietekst; een lege locatie wordt niet gedropt maar geflagd."
        )
        locaties_lijst = lijst_editor(
            cfg.get("locaties_toegestaan") or [], "ed_locaties", "Toegestane locatie", 260,
        )

st.write("")

kol_uitsluiten, kol_flags = st.columns(2, gap="large")

with kol_uitsluiten:
    with st.container(border=True):
        st.subheader("Titel-uitsluitingen")
        st.caption("Harde drop op woordgrens. Deze titels halen de poort nooit.")

        st.markdown("**Ervaringsniveau**")
        huidige_excl = [t.lower() for t in cfg.get("titel_uitsluiten") or []]
        uitgesloten_niveaus = st.multiselect(
            "Uit te sluiten niveaus",
            options=SENIORITY,
            default=[t for t in SENIORITY if t in huidige_excl],
            label_visibility="collapsed",
        )
        st.caption("Aangevinkt betekent: dit niveau wordt uitgesloten.")

        st.markdown("**Overige uitsluitingen**")
        overige_excl = [t for t in (cfg.get("titel_uitsluiten") or []) if t.lower() not in SENIORITY]
        overige_lijst = lijst_editor(
            overige_excl, "ed_overige", "Term", 300,
        )

with kol_flags:
    with st.container(border=True):
        st.subheader("Flags")
        st.caption(
            "Markeren, niet droppen. De vacature blijft staan met een flag, zodat "
            "je zelf beoordeelt."
        )
        flags_lijst = lijst_editor(
            cfg.get("flag_termen") or [], "ed_flags", "Flag-term", 340,
        )

st.write("")

with st.container(border=True):
    st.subheader("Bronnen")
    st.caption("Zet per kanaal aan of het meedraait in de run.")

    kol_borden, kol_bordinstellingen = st.columns([1, 2], gap="large")
    with kol_borden:
        br_aan = st.toggle(
            "Borden (LinkedIn, Indeed)", value=bool(boards.get("actief", True))
        )
        st.caption(bron_status(br_aan))
    with kol_bordinstellingen:
        sites = st.multiselect(
            "Actieve borden",
            options=["linkedin", "indeed", "glassdoor"],
            default=list(boards.get("sites") or ["linkedin", "indeed"]),
            disabled=not br_aan,
        )
        kol_per_term, kol_uren = st.columns(2)
        with kol_per_term:
            per_term = st.number_input(
                "Resultaten per zoekterm", min_value=5, max_value=100,
                value=int(boards.get("resultaten_per_term", 25)), step=5,
                disabled=not br_aan,
            )
        with kol_uren:
            uren = st.number_input(
                "Maximale ouderdom (uren)", min_value=24, max_value=336,
                value=int(boards.get("max_uren_oud", 72)), step=24,
                disabled=not br_aan,
            )

    st.divider()

    kol_ats, kol_magnet, kol_werkenbij = st.columns(3, gap="large")
    with kol_ats:
        ats_aan = st.toggle(
            "ATS-feeds", value=bool((cfg.get("ats") or {}).get("actief", True))
        )
        st.caption("AFM, Flow Traders, Optiver, IMC")
        st.caption(bron_status(ats_aan))
    with kol_magnet:
        mag_aan = st.toggle(
            "Magnet.me", value=bool((cfg.get("magnetme") or {}).get("actief", True))
        )
        st.caption("Publieke overzichtspagina's")
        st.caption(bron_status(mag_aan))
    with kol_werkenbij:
        wb_aan = st.toggle(
            "Werkenbij", value=bool((cfg.get("werkenbij") or {}).get("actief", True))
        )
        st.caption("DNB, Banken.nl")
        st.caption(bron_status(wb_aan))

st.write("")
st.divider()

st.subheader("Opslaan")
st.caption("Schrijf je wijzigingen naar config.yaml; de comments blijven behouden.")
if st.button("Opslaan in config.yaml", type="primary"):
    schrijf_profiel(cfg, {
        "zoektermen": zoektermen_lijst,
        "titel_uitsluiten": uitgesloten_niveaus + overige_lijst,
        "locaties_toegestaan": locaties_lijst,
        "flag_termen": flags_lijst,
        "boards_actief": br_aan,
        "boards_sites": sites,
        "boards_locaties": boards_locaties_lijst,
        "resultaten_per_term": int(per_term),
        "max_uren_oud": int(uren),
        "ats_actief": ats_aan,
        "magnetme_actief": mag_aan,
        "werkenbij_actief": wb_aan,
    })
    st.success("Opgeslagen. Draai nu een dry-run in de terminal ter controle.")
    st.code('./.venv/bin/python scraper.py --dry-run', language="bash")

st.write("")
st.divider()

with st.container(border=True):
    st.subheader("Zoeken")
    st.caption(
        "Draait dezelfde zoek- en filterketen als de terminal, op de opgeslagen "
        "config.yaml. Sla je wijzigingen dus eerst op. Een run duurt een paar minuten."
    )

    st.session_state.setdefault("zoek_bezig", False)
    st.session_state.setdefault("zoek_actie", None)
    st.session_state.setdefault("laatste_run", None)
    st.session_state.setdefault("echt_teller", 0)
    bezig = st.session_state.zoek_bezig

    kol_dry, kol_echt = st.columns(2, gap="large")
    with kol_dry:
        with st.container(border=True):
            st.markdown("**Zoek en toon**")
            st.caption(
                "Dry-run: haalt op en filtert, schrijft niets weg en raakt "
                "state.json niet aan. Zo vaak als je wilt."
            )
            st.write("")
            start_dry = st.button(
                "Zoek en toon", width="stretch", type="primary",
                disabled=bezig, key="btn_dry",
            )
    with kol_echt:
        with st.container(border=True):
            st.markdown("**Vastleggen (echte run)**")
            st.caption(
                "Schrijft de xlsx en werkt state.json bij. Verbruikt nieuwheid: wat "
                "nu wordt vastgelegd, meldt de tool later niet meer als nieuw. Doe "
                "dit bewust, meestal een keer per dag."
            )
            bevestig = st.checkbox(
                "Ja, vastleggen en nieuwheid verbruiken",
                key=f"bevestig_echt_{st.session_state.echt_teller}",
                disabled=bezig,
            )
            start_echt = st.button(
                "Vastleggen (echte run)", width="stretch",
                disabled=bezig or not bevestig, key="btn_echt",
            )

    if bezig:
        st.info("Bezig met een run. Even geduld, dit duurt een paar minuten.")

    # Fase 1: een klik zet de actie klaar en blokkeert beide knoppen via een rerun,
    # zodat er niet dubbel kan worden aangeroepen terwijl de run loopt.
    if start_dry and not bezig:
        st.session_state.zoek_bezig = True
        st.session_state.zoek_actie = "dry"
        st.rerun()
    if start_echt and not bezig:
        st.session_state.zoek_bezig = True
        st.session_state.zoek_actie = "echt"
        st.rerun()

    # Fase 2: voer de klaargezette actie uit terwijl de knoppen geblokkeerd staan.
    # We hergebruiken de functies uit scraper.py; geen kopie van die logica hier.
    if st.session_state.zoek_bezig and st.session_state.zoek_actie:
        actie = st.session_state.zoek_actie
        try:
            run_cfg = scraper.laad_config()
            if actie == "dry":
                with st.spinner("Bezig met zoeken (dry-run). Dit duurt een paar minuten..."):
                    kept, stats, opgehaald = scraper.verzamel_dedupe_filter(run_cfg)
                st.session_state.laatste_run = {
                    "soort": "dry", "rijen": kept, "stats": stats,
                    "opgehaald": opgehaald, "over": len(kept),
                }
            else:
                with st.spinner("Bezig met vastleggen (echte run). Dit duurt een paar minuten..."):
                    kept, stats, opgehaald = scraper.verzamel_dedupe_filter(run_cfg)
                    nieuw, pad = scraper.leg_vast(kept, run_cfg)
                st.session_state.laatste_run = {
                    "soort": "echt", "rijen": nieuw, "stats": stats,
                    "opgehaald": opgehaald, "over": len(kept),
                    "pad": str(pad) if pad else None,
                }
                st.session_state.echt_teller += 1
        except Exception as e:
            st.session_state.laatste_run = {"soort": "fout", "fout": str(e)}
        finally:
            st.session_state.zoek_bezig = False
            st.session_state.zoek_actie = None
        st.rerun()

    laatste = st.session_state.laatste_run
    if laatste:
        st.divider()
        if laatste["soort"] == "fout":
            st.error(f"De run is mislukt: {laatste['fout']}")
        elif laatste["soort"] == "dry":
            s = laatste["stats"]
            st.markdown("**Resultaat: dry-run.** Er is niets weggeschreven.")
            st.caption(
                f"Opgehaald {laatste['opgehaald']}, na ontdubbelen {s['totaal']}, "
                f"gedropt op titel {s['titel']}, gedropt op locatie {s['locatie']}, "
                f"over {laatste['over']}. Hieronder de volledige lijst die door het "
                "filter komt."
            )
            toon_resultaat(laatste["rijen"])
        else:
            st.markdown("**Resultaat: echte run.** Weggeschreven en onthouden.")
            if laatste.get("pad"):
                st.caption(
                    f"Over na filter {laatste['over']}, waarvan {len(laatste['rijen'])} "
                    f"nieuw. Weggeschreven naar {laatste['pad']}. Hieronder alleen de "
                    "nieuw vastgelegde vacatures."
                )
            else:
                st.caption(
                    f"Over na filter {laatste['over']}, maar niets nieuws sinds de "
                    "vorige run. state.json is bijgewerkt."
                )
            toon_resultaat(laatste["rijen"])
