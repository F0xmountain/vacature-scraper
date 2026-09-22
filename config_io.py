"""Gedeelde, comment-behoudende lees- en schrijflogica voor config.yaml.

Zowel de Streamlit-interface (config_ui.py) als de HTML-webserver
(webui/server.py) gebruiken deze functies. Zo bestaat er maar een schrijfroute
naar config.yaml en blijven de comments in het bestand behouden (ruamel.yaml).
"""
from pathlib import Path

from ruamel.yaml import YAML

CONFIG = Path(__file__).with_name("config.yaml")

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)


def laad():
    with open(CONFIG) as f:
        return yaml.load(f)


def zet_lijst(parent, key, waarden):
    """Vervang een lijst maar behoud de comments in config.yaml.

    Ongewijzigde lijsten worden niet aangeraakt. Bij een gewijzigde lijst
    worden inline comments per waarde herkoppeld en de sectie-comment die
    na de lijst hoort mee naar de nieuwe laatste regel verplaatst.
    """
    bestaand = parent.get(key)
    if isinstance(bestaand, str) or bestaand is None or not hasattr(bestaand, "__setitem__"):
        parent[key] = waarden
        return
    if list(bestaand) == list(waarden):
        return
    ca = getattr(bestaand, "ca", None)
    oud_laatste = len(bestaand) - 1
    staart = ca.items.get(oud_laatste) if ca else None
    per_waarde = {
        bestaand[i]: ca.items[i]
        for i in range(len(bestaand))
        if ca and i in ca.items and i != oud_laatste
    }
    bestaand[:] = waarden
    for j, w in enumerate(waarden):
        if w in per_waarde:
            bestaand.ca.items[j] = per_waarde[w]
    if staart is not None and waarden:
        bestaand.ca.items[len(waarden) - 1] = staart


def bewaar(cfg):
    with open(CONFIG, "w") as f:
        yaml.dump(cfg, f)


def schrijf_profiel(cfg, profiel):
    """Schrijf een profiel-dict naar config.yaml via zet_lijst en bewaar.

    Dit is de ene schrijfroute die zowel config_ui.py als de webserver gebruiken.
    De velden en de volgorde zijn gelijk aan de oude opslaglogica in config_ui.py,
    zodat de comments in config.yaml behouden blijven.
    """
    boards = cfg.setdefault("boards", {})
    zet_lijst(cfg, "zoektermen", profiel["zoektermen"])
    zet_lijst(cfg, "titel_uitsluiten", profiel["titel_uitsluiten"])
    zet_lijst(cfg, "locaties_toegestaan", profiel["locaties_toegestaan"])
    zet_lijst(cfg, "flag_termen", profiel["flag_termen"])
    boards["actief"] = profiel["boards_actief"]
    zet_lijst(boards, "sites", profiel["boards_sites"])
    zet_lijst(boards, "locaties", profiel["boards_locaties"])
    boards["resultaten_per_term"] = int(profiel["resultaten_per_term"])
    boards["max_uren_oud"] = int(profiel["max_uren_oud"])
    cfg.setdefault("ats", {})["actief"] = profiel["ats_actief"]
    cfg.setdefault("magnetme", {})["actief"] = profiel["magnetme_actief"]
    cfg.setdefault("werkenbij", {})["actief"] = profiel["werkenbij_actief"]
    bewaar(cfg)
