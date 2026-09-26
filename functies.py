"""Vacaturetitels indelen in functiefamilies, voor het filter in de interface.

Trefwoorden en geen taalmodel. Dat is hier de juiste maat: het draait lokaal bij
elke keer dat de lijst binnenkomt, het is na te lezen en aan te passen, en het
faalt zichtbaar. Grotere projecten die dit met regex doen halen rond de 85 procent
op titels; een taalmodel erbij halen zou hier een vrachtwagen voor een boodschap
zijn.

Belangrijk: de volgorde is de logica. De eerste familie die raakt wint, dus de
specifieke staan boven de algemene. "Credit Risk Analyst" hoort bij analist en
niet bij risk, want voor deze zoekopdracht is het analistenwerk het kenmerk en
risk het onderwerp. "Compliance Officer" heeft geen analistenterm en valt dus wel
in risk.

Dit deelt alleen in. Het dropt niets en het rangschikt niets. Wat er door de poort
komt bepaalt filters.py, en of de rol deugt beoordeel jij.
"""
import re

# (sleutel, label, patroon). Volgorde telt: de eerste die raakt wint.
FAMILIES = [
    ("analist", "Analist", r"\banalyst|analist|analytics|quant|onderzoeker|researcher\b"),
    ("controller", "Controller", r"\bcontroll(er|ing)\b"),
    ("finance", "Finance overig", (
        r"\bfinanc|treasury|accounting|boekhoud|reporting|rapportage|fp&a|"
        r"corporate finance|valuation|waardering|transaction services|"
        r"vermogensbeheer|portfolio|belegging|invest|credit|krediet|lending|"
        r"actuar|audit|accountant|trader|trading|dealer|hypothe|verzeker|"
        r"pensioen|fiscal|tax|bonds|equity\b"
    )),
    ("risk", "Risk en compliance", (
        r"\brisk|risico|compliance|kyc|cdd|due diligence|aml|"
        r"financial crime|fraud|toezicht|transaction monitoring|sanctions|"
        r"sancties|integriteit|onderzoek financi\b"
    )),
    ("advies", "Advies en consultancy", (
        r"\bconsultant|consultancy|adviseur|advisor|advies|"
        r"interim|transformation|strateg\b"
    )),
    ("data", "Data en IT", (
        r"\bdata scien|data engineer|engineer|developer|software|"
        r"programmeur|it |ict|cyber|security|cloud|devops|"
        r"applicatie|systeem|architect\b"
    )),
    ("commercieel", "Commercieel", (
        r"\bsales|account manager|accountmanager|business development|"
        r"commercieel|relatiebeheer|klantadviseur|acquisitie|marketing|"
        r"marketeer|communicatie|content|customer relations|klantcontact\b"
    )),
    ("operations", "Operations en support", (
        r"\boperations|operationeel|support|administrat|backoffice|"
        r"back office|medewerker|assistent|secretar|planner|coordinator|"
        r"coordinat|inkoop|inkoper|procurement|logistiek|servicedesk\b"
    )),
    ("hr", "HR en recruitment", (
        r"\brecruit|talent|hr |human resources|people|"
        r"personeel|arbeids\b"
    )),
    ("project", "Project en product", (
        r"\bproject|product owner|product manager|scrum|agile|"
        r"programma|implementatie|change\b"
    )),
    ("management", "Management", (
        r"\bmanager|director|hoofd|head of|lead|teamleider|"
        r"sectiehoofd|partner\b"
    )),
]

OVERIG = ("overig", "Overig")

_GECOMPILEERD = [
    (sleutel, label, re.compile(patroon, re.IGNORECASE))
    for sleutel, label, patroon in FAMILIES
]

# sleutel -> label, inclusief de restcategorie. Voor de interface.
LABELS = {s: l for s, l, _ in FAMILIES}
LABELS[OVERIG[0]] = OVERIG[1]


def familie(titel):
    """De sleutel van de eerste familie die raakt, anders 'overig'."""
    tekst = (titel or "").lower()
    for sleutel, _, patroon in _GECOMPILEERD:
        if patroon.search(tekst):
            return sleutel
    return OVERIG[0]


def label(sleutel):
    return LABELS.get(sleutel, OVERIG[1])
