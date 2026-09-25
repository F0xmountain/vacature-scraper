"""Gevraagde vaardigheden uit de vacaturetekst halen, als tags bij de vacature.

Waarom dit er is: aan een titel zie je niet of de analytische kern echt is. Een
"Financial Analyst" die SQL en Python noemt is iets anders dan een die alleen
Excel noemt, en dat verschil staat wel in de omschrijving maar niet in de
listing. Deze module haalt dat naar boven zodat het in de lijst zichtbaar wordt.

Net als flag_termen markeert dit alleen. Er wordt niets gedropt en niets
gerangschikt; het blijft jouw beoordeling. Dat is bewust, want een vermelding is
geen eis: "wij werken met Python" in een bedrijfsprofiel telt hier net zo zwaar
als "je beheerst Python". Dat verschil is niet betrouwbaar machinaal vast te
stellen en het zou onterecht vertrouwen geven als de tool deed alsof van wel.

Hoofdlettergevoelig waar dat moet. Afkortingen als SAS, RA en RC leveren
hopeloos veel valse treffers op wanneer je ze kleineletterig matcht: 'sas' zit in
van alles, 'ra' helemaal. Die patronen draaien daarom op de originele tekst.
Losse letters (R als taal) zitten er bewust niet in; die zijn niet betrouwbaar
van hun omgeving te scheiden en leverden in een proef vooral ruis op.
"""
import re
from functools import lru_cache

# (label, groep, patroon, hoofdlettergevoelig)
VAARDIGHEDEN = [
    # Gereedschap: het duidelijkste signaal of er echt met data gewerkt wordt.
    ("Excel",            "tools",  r"\bexcel\b", False),
    ("SQL",              "tools",  r"\bSQL\b", True),
    ("Python",           "tools",  r"\bpython\b", False),
    ("Power BI",         "tools",  r"power\s?bi\b", False),
    ("Tableau",          "tools",  r"\btableau\b", False),
    ("VBA",              "tools",  r"\bVBA\b", True),
    ("SAS",              "tools",  r"\bSAS\b", True),
    ("Alteryx",          "tools",  r"\balteryx\b", False),
    ("SAP",              "tools",  r"\bSAP\b", True),
    ("Bloomberg",        "tools",  r"\bbloomberg\b", False),
    ("AFAS",             "tools",  r"\bAFAS\b", True),
    ("Exact",            "tools",  r"\bexact online\b", False),

    # Methoden en onderwerpen.
    ("financial modelling", "methode", r"financial model|financi[eë]le model", False),
    ("forecasting",      "methode", r"\bforecast", False),
    ("rapportage",       "methode", r"\brapportage|\breporting\b", False),
    ("dashboards",       "methode", r"\bdashboard", False),
    ("datavisualisatie", "methode", r"datavisualisatie|data visualisation|data visualization", False),
    ("IFRS",             "methode", r"\bIFRS\b", True),
    ("Basel",            "methode", r"\bbasel\s?(i{1,3}|iv|\d)\b", False),
    ("Solvency",         "methode", r"\bsolvency\b|solvabiliteit", False),
    ("Agile of Scrum",   "methode", r"\bagile\b|\bscrum\b", False),
    ("stakeholdermanagement", "methode", r"stakeholder", False),

    # Certificeringen: zeldzaam, maar zwaarwegend als ze er staan.
    ("CFA",              "diploma", r"\bCFA\b", True),
    ("FRM",              "diploma", r"\bFRM\b", True),
    ("RA of RC",         "diploma", r"\b(RA|RC)\b|registeraccountant|register controller", True),
    ("CAIA",             "diploma", r"\bCAIA\b", True),

    # Taal: bepaalt vaak of je überhaupt in aanmerking komt.
    ("Nederlands",       "taal",   r"\bnederlands\b|\bdutch\b", False),
    ("Engels",           "taal",   r"\bengels\b|\benglish\b", False),
]

GROEPEN = {
    "tools": "Gereedschap",
    "methode": "Methode",
    "diploma": "Diploma",
    "taal": "Taal",
}

_GECOMPILEERD = [
    (label, groep, re.compile(patroon, 0 if gevoelig else re.IGNORECASE))
    for label, groep, patroon, gevoelig in VAARDIGHEDEN
]

# Alleen deze groepen tellen mee als signaal voor 'analytische kern'. Taal en
# stakeholdermanagement zeggen daar niets over en horen er dus buiten.
_KERN = {"SQL", "Python", "Power BI", "Tableau", "VBA", "SAS", "Alteryx",
         "financial modelling", "forecasting", "dashboards", "datavisualisatie"}


# Dezelfde omschrijvingen komen bij elke pagina-lading opnieuw langs. Zonder
# cache is dat bij vijftienhonderd vacatures bijna twee seconden per verzoek,
# telkens voor exact hetzelfde antwoord. De tekst zelf is de sleutel; die
# verandert niet meer zodra hij is opgehaald.
@lru_cache(maxsize=4096)
def _zoek(tekst):
    return tuple(label for label, _, patroon in _GECOMPILEERD if patroon.search(tekst))


def uit_tekst(tekst):
    """Lijst van gevonden vaardigheden, in de volgorde van VAARDIGHEDEN."""
    if not tekst:
        return []
    return list(_zoek(tekst))


def groep_van(label):
    for l, groep, _, _ in VAARDIGHEDEN:
        if l == label:
            return groep
    return "methode"


def kernsignalen(gevonden):
    """Hoeveel van de gevonden vaardigheden wijzen op echt analytisch werk.

    Nadrukkelijk een telling en geen oordeel: Excel telt hier niet mee omdat
    vrijwel elke kantoorvacature het noemt, en taal evenmin. Twee of meer is in
    de praktijk een aanwijzing dat er data-werk in zit, maar de listing kan
    liegen en de poort blijft handwerk.
    """
    return sum(1 for v in gevonden if v in _KERN)
