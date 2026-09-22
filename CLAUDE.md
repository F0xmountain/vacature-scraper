# CLAUDE.md

Werkregels voor deze repository. Deze staan hier omdat ze makkelijk per ongeluk
worden overtreden bij het "verbeteren" van de tool.

## Omgeving

**De venv draait Python 3.11 of 3.12.** Niet nieuwer. python-jobspy pint
`numpy==1.26.3`, en daar bestaat geen wheel voor Python 3.14. Op 3.14 breekt de
installatie dus. Draai Python altijd via het expliciete pad, bijvoorbeeld
`./.venv/bin/python check.py`, niet via `source .venv/bin/activate`.

## Werkregels die niet geschonden mogen worden

**scraper.py wordt nooit zonder `--dry-run` gedraaid.** Een echte run schrijft
xlsx weg en verbruikt nieuwheid in `state.json`. Alleen draaien met `--dry-run`,
tenzij de gebruiker expliciet om een echte run vraagt.

**Een normale run verbruikt nieuwheid.** `state.json` onthoudt wat al gezien is.
Bij het afstellen van filters altijd `--dry-run` gebruiken. Wie tijdens het
sleutelen echte runs draait, mist vacatures in de eerstvolgende echte run.

**De poort blijft handwerk.** Bouw geen automatische scoring die vacatures
afwijst op basis van de rollenfilter van de gebruiker. Hybride dagen, salaris en
de vraag of de analytische kern echt is, staan zelden betrouwbaar in een listing.
De tool versmalt de trechter; de gebruiker beoordeelt. Over-filteren is in het
verleden een concreet probleem geweest.

**Twijfelgevallen droppen niet, die krijgen een flag.** `flag_termen` markeert
alleen. Een compliance-touchpoint diskwalificeert niet, een compliance-kern wel,
en dat verschil is niet machinaal vast te stellen.

**Titeluitsluitingen zijn bot en werken op woordgrens.** `manager` dropt "Risk
Manager" maar niet "Risk Management Analyst". `medior` staat er nu in; dat is een
bewuste keuze van de gebruiker die hij zelf kan terugdraaien.

**Geen em-dashes** in code, commentaar, documentatie of berichten. Puntkomma's,
komma's of een nieuwe zin. Staande voorkeur van de gebruiker.

**Geen login of scraping achter authenticatie.** Alle bronnen draaien op
publieke, uitgelogde endpoints. Dat houdt de eigen accounts van de gebruiker
buiten schot en dat moet zo blijven.
