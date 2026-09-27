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

**Afgeschermde bestanden.** `.claude/settings.json` zet `scraper.py`, `output.py`,
`store.py`, `config_io.py` en `state.json` op de deny-lijst, voor zowel Bash als
Edit. Ga daar niet omheen door van gereedschap te wisselen; dat is eerder gebeurd
en het is precies wat die regels moeten voorkomen. Moet er iets in, lever dan de
code aan en laat de gebruiker plakken.

## Hoe het draait

**Twee runs per dag via launchd**, om 08:00 en 20:00, ingesteld in
`~/Library/LaunchAgents/com.basvossenberg.vacature-scraper.plist`. De bronversie
en de uitleg staan in `launchd/`. Bewust launchd en geen cron: cron slaat een
gemiste run op een slapende laptop over, launchd haalt hem in. De opdracht draait
via `caffeinate`, omdat launchd de Mac wel wekt om te starten maar niet wakker
houdt tijdens de run.

**Het rooster is vanuit de webinterface te bedienen** (Zoekprofiel, onderaan).
`webui/rooster.py` is de enige schrijfroute naar launchd en vervangt alleen het
`StartCalendarInterval`-blok, zodat de comments in de plist blijven staan.

**`max_uren_oud` hoort marge te houden op het rooster.** Twee runs twaalf uur uit
elkaar met zestien uur terugkijken geeft vier uur speling, want een run op een
slapende laptop start zelden op tijd. Eenmalig dieper: `scraper.py --uren 72`.

## Gemeten valkuilen, niet opnieuw in trappen

**Zet `linkedin_beschrijving` niet aan.** Dan haalt jobspy per zoekterm de
omschrijving van elk resultaat serieel op, voor het filteren. Gemeten op
20-09-2026: ruim zeven minuten per ronde, bijna zeven uur per run. De
omschrijvingen komen via `sources_detail.py`, parallel en pas na de poort.

**LinkedIn-detailpagina's hebben een eigen tempo nodig.** Zes tegelijk zonder
pauze gaf op 21-09-2026 279 keer een 429, waardoor de helft van de flags wegviel.
`sources_detail.py` houdt per host een tempo aan; voor linkedin.com twee tegelijk
met 1,2 seconde ertussen.

**Jobspy mist de plaatsingsdatum bij verse vacatures.** LinkedIn geeft die in de
zoekresultaten de klasse `job-search-card__listdate--new`, en jobspy zoekt alleen
op `job-search-card__listdate`. Bij een korte terugkijktijd is alles vers en
verdwijnt de datum bijna overal. `sources_detail.py` haalt hem daarom uit de
detailpagina, die toch al wordt opgehaald.

**Filteren op de omschrijving werkt niet.** Gemeten op 26-09-2026: sectorwoorden
komen vaker terloops voor in relevante vacatures dan als kenmerk in ruis. "zorg"
stond in 162 ruisvacatures maar ook in 489 relevante, "retail" in 26 tegen 62.
Uitsluiten gaat op titel en werkgever, niet op tekst.

**Kies grafiek- en bronkleuren niet op het oog.** Het eerste bronpalet was zo
gekozen en faalde gemeten: LinkedIn en Indeed, de twee bronnen die altijd naast
elkaar in de vangststrip staan, lagen op een verschil van 6,6 terwijl 15 de
ondergrens is voor normaal zicht, en vijf van de negen kleuren zaten onder de
chromavloer en lazen dus als grijs. Het palet in `webui/static/app.js` is nu
gevalideerd (slechtste buurpaar 9,1 bij kleurenblindheid, 19,6 normaal). Acht is
het maximum: een negende en tiende kleur erbij verzinnen faalt opnieuw, dus Lever
en Workday staan bewust neutraal. Meet voor je hier iets aan verandert.

**Een dossier van het hele venster past niet in een gesprek.** Het venster van
drie dagen telt miljoenen tekens; op 27-09-2026 kwam het hele venster uit op een
dossier van 320.000 tokens, en dat past nergens in. `dossier.py` verdeelt
daarom een tekenbudget over de selectie, met een ondergrens van 800 tekens per
vacature; wordt die ondergrens bereikt, dan staat er een waarschuwing in het
bestand in plaats van dat er stil vacatures wegvallen. Moet er ingekort worden,
dan gaat het eisenblok mee: 51 procent van de teksten heeft een vindbare eisenkop
en de mediaan staat op 52 procent van de tekst, dus plat afkappen op de kop
verwijdert juist de eisen. Het venster waarin die kop gezocht wordt is krap
(40 tekens ervoor, 15 erna) omdat een kop kort is; ruimer maken laat de regex
aanslaan op gewone zinnen en dan knipt hij midden in een alinea.

**Bouw geen insluitlijst op titels.** Zo'n lijst faalt stil: functietitels zijn
niet gestandaardiseerd en je ziet niet wat je weggooit. Dat botst met de regel dat
overfilteren het probleem is. Zeven in de interface, waar niets verdwijnt.

## Indeling van de modules

De kern staat in de projectmap: `scraper.py`, `filters.py`, `store.py`,
`output.py`, de `sources_*` en de gedeelde classificatiemodules `functies.py` en
`vaardigheden.py`. Alles wat alleen de interface aangaat staat in `webui/`.

Elke module die naar een bestand schrijft is de enige schrijfroute daarheen:
`config_io.py` naar config.yaml, `store.py` naar state.json, `webui/oordeel.py`
naar beoordeling.json, `webui/rooster.py` naar launchd, `dossier.py` naar
output/matchdossier.md. Bouw er geen tweede.

`dossier.py` maakt het matchdossier voor Claude en bepaalt zelf de opmaak, de
opdracht en het tekenbudget. De webinterface roept `bouw()` aan en stuurt het
resultaat als download; die bouwt geen eigen versie van de tekst en filtert niet
opnieuw, maar stuurt de sleutels van wat de gebruiker ziet.
