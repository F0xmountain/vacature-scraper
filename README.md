# Vacature-scraper

Dagelijkse monitor voor junior analytische finance-rollen rond Amsterdam. Haalt vacatures op, past een voorfilter toe op basis van je rollenfilter (titel-uitsluitingen, locatie, twijfelflags), ontdubbelt over bronnen en toont per run alleen wat nieuw is, als xlsx met klikbare links.

## Bronnen

| Bron | Hoe | Betrouwbaarheid |
|---|---|---|
| LinkedIn, Indeed, Glassdoor, Google | python-jobspy (onderhouden open-source library, publieke gast-endpoints, geen login) | Goed; LinkedIn kan bij veel requests tijdelijk 429 geven, Glassdoor is de wisselvalligste |
| Recruitee, Greenhouse, Lever, Workday | Directe careers-API's van bedrijven die jij in config.yaml zet | Zeer stabiel; publieke JSON-feeds. Voorgevuld: AFM (Recruitee), Flow Traders en Optiver (Greenhouse) |
| Eigen careers-sites (werkenbij-module) | Servergerenderde overzichtspagina's, linkpatroon per site in config | Voorgevuld: DNB en Banken.nl (sectorbrede vacaturebank). Layoutwijziging kan de parser breken; fouten worden gemeld en de rest draait door |
| Magnet.me | Eigen module via de publieke overzichtspagina's (servergerenderd, geen login) | Goed; een layoutwijziging van de site kan de parser breken, fouten worden gemeld en de rest draait door. Hun e-mailalerts aanhouden als backup kan geen kwaad. |

Grote banken en fondsen posten vrijwel alles ook op LinkedIn en Indeed, dus die vang je al via de borden. De ATS-module is voor boutiques en handelshuizen die alleen op hun eigen careers-pagina posten.

## Dekking per doelwerkgever

Live geverifieerd op 14 juli 2026:

| Doelwerkgever | Route | Status |
|---|---|---|
| DNB | Eigen site (werkenbij-module) plus LinkedIn, Indeed en magnet.me | Draait op Radancy; de lijst komt als HTML-fragment in een JSON-veld, zie `json_veld` in de config |
| AFM | Recruitee-feed, slug werkenbijdeafm | Geverifieerd |
| Flow Traders, Optiver | Greenhouse-feeds, slugs flowtraders en optiverus | Geverifieerd; locatiefilter houdt alleen Amsterdam over uit hun wereldwijde boards |
| IMC | Waarschijnlijk Greenhouse | Uitgecommentarieerd in config; slug eerst zelf verifiëren |
| Banken.nl | Sectorbrede vacaturebank (banken incl. VLK, NIBC), werkenbij-module | Geverifieerd; locatie soms onbekend, dan krijgt de vacature een flag |
| ABN AMRO, ING, Rabobank | LinkedIn en Indeed; ze cross-posten alles | Via boards |
| APG | LinkedIn, Indeed en magnet.me; eigen site is JS-gerenderd | Via boards |
| NN, Aegon, Achmea, PGGM | Via boards; hoofdkantoren (Den Haag, Zeist) vallen buiten je reistijdpoort, het locatiefilter regelt dat | Via boards |
| a.s.r. | Via boards; Utrecht is je randgeval | Via boards |
| Corporates treasury (KLM, Heineken, Philips) | Via boards met de zoektermen treasury en financial analyst | Via boards |

Zelf een eigen site toevoegen aan de werkenbij-module: open de vacaturepagina, bekijk de paginabron (Cmd+Option+U), zoek hoe de vacaturelinks eruitzien en zet url plus linkpatroon (regex) in config.yaml. Staat de lijst niet in de paginabron, dan is de site JS-gerenderd en werkt deze route niet; check dan of het bedrijf op LinkedIn of magnet.me post.

## Installatie (eenmalig)

Vereist Python 3.11 of 3.12; niet 3.14, want python-jobspy pint numpy 1.26.3 en
daar bestaat geen wheel voor 3.14. Vanuit de projectmap:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
python3 test_lokaal.py
python3 check.py
```

In een nieuwe terminal activeer je de venv opnieuw met `source .venv/bin/activate`.

`requirements.txt` bevat alleen wat de scraper zelf nodig heeft. De losse
configuratie-interface (`config_ui.py`) heeft extra pakketten nodig; die staan in
`requirements-ui.txt`. Wil je die interface gebruiken, installeer dan beide en
start hem daarna:

```
pip install -r requirements.txt -r requirements-ui.txt
python3 -m streamlit run config_ui.py
```

`test_lokaal.py` test de logica offline in een seconde. `check.py` doet de echte
test: die roept elke bron één keer live aan en rapporteert per bron of er data
binnenkomt, met een voorbeeldregel. Er wordt niets weggeschreven, dus je kunt
hem zo vaak draaien als je wilt.

## Werkt het echt?

Wat vooraf is getest en wat niet, zodat je weet waar je op moet letten:

| Onderdeel | Status |
|---|---|
| Filteren, ontdubbelen, geheugen, xlsx-export | Offline getest via `test_lokaal.py`; werkt |
| Link- en URL-patronen per site | Afgeleid uit de echte pagina's, gecontroleerd op 14 juli 2026 |
| Live requests naar de sites | Niet vooraf getest; dat kan alleen op jouw machine, daarvoor is `check.py` |
| Bedrijfsnaam en salaris per vacaturekaart | Best effort. Lukt het niet, dan blijft het veld leeg en gaat de vacature gewoon mee met titel en link |

Kort gezegd: de kans op stilletjes verkeerde data is klein, want elke bron faalt
zichtbaar en apart. De kans dat een bron een keer niets teruggeeft is reëel, en
dat zie je meteen in de uitvoer.

Geeft een bron nul resultaten, dan bewaart `check.py` de opgehaalde pagina in
`debug/`. Daarmee is te zien of de site zijn layout heeft gewijzigd.

## Dagelijks gebruik en je zoekprofiel

`config.yaml` is je profiel: zoektermen, uitsluitingen op titel, toegestane
locaties en twijfelflags. Aanpassen en het effect zien zonder gevolgen:

```
python3 scraper.py --dry-run      toont wat er doorheen komt, schrijft niets weg
python3 scraper.py --bron ats     draait één bron, handig bij het afstellen
python3 scraper.py --uren 72      kijkt eenmalig verder terug, na een paar dagen weg
python3 scraper.py                de echte run
```

Werkwijze bij het afstellen: pas een zoekterm of uitsluiting aan, draai
`--dry-run`, kijk of de lijst beter wordt. Pas als je tevreden bent, draai je de
echte run. Dat is belangrijk, want een normale run onthoudt wat hij gezien heeft;
alles wat daar eenmaal in staat, meldt hij daarna niet meer als nieuw.

## De Streamlit-interface (config_ui.py)

Naast het bewerken van je zoekprofiel kun je vanuit de interface ook zoeken. Er
zijn twee knoppen, bewust gescheiden:

- **Zoek en toon** doet een dry-run: dezelfde zoek- en filterketen als
  `scraper.py --dry-run`. Schrijft niets weg en raakt state.json niet aan, dus zo
  vaak als je wilt. Je ziet de volledige lijst die door het filter komt.
- **Vastleggen (echte run)** doet een echte run: schrijft de xlsx en werkt
  state.json bij, net als `scraper.py` zonder `--dry-run`. Dit verbruikt
  nieuwheid, dus de knop vraagt eerst een bevestiging. Je ziet daarna alleen wat
  er nieuw is weggeschreven.

Beide knoppen blokkeren zichzelf terwijl een run loopt (een run duurt een paar
minuten) en tonen de gevonden banen als tabel met een klikbare link. De interface
draait op de opgeslagen config.yaml, dus sla je wijzigingen eerst op.

Zoeklocaties mag je als kale steden invoeren. "Amsterdam" wordt bij het zoeken
aangevuld tot "Amsterdam, Netherlands"; heb je zelf een komma getypt, dan blijft
je invoer staan. In config.yaml worden de locaties bewaard zoals je ze invoert; de
aanvulling gebeurt alleen op het moment van zoeken.

## De webinterface (webui)

Een strakke HTML-interface op een kleine lokale Python-server, als alternatief
voor de Streamlit-versie hierboven. Geen webframework: hij draait op de standaard
http-server van Python en gebruikt onder de motorkap exact dezelfde zoek- en
filterketen als de terminal.

Starten vanuit de projectmap:

```
./.venv/bin/python webui/server.py
```

Of `./start-webui.sh`, dat hetzelfde doet maar losgekoppeld start, wacht tot de
server luistert, en de browser opent. Geen tweede server als er al een draait.
Open anders zelf http://127.0.0.1:8500; de server luistert alleen op loopback.

Wat de interface kan:

- **Profiel bewerken en opslaan**, comment-behoudend naar `config.yaml`
- **Zoek en toon** doet een dry-run: schrijft niets weg, raakt `state.json` niet
  aan, dus zo vaak als je wilt
- **Vastleggen** doet een echte run, met bevestiging, want dat verbruikt nieuwheid
- **Laatste run** toont de oogst van de automatische run, inclusief functietekst,
  zonder opnieuw op te halen. Er wordt een venster van de laatste zes runs
  bewaard, zodat een batch die je nog niet hebt bekeken niet verdwijnt
- **Beoordelen met ja/nee**, met pijltjestoetsen en automatisch doorspringen naar
  de volgende onbeoordeelde; het oordeel overleeft runs via de dedupe-sleutel
- **Sorteren** op meest recent geplaatst, met vacatures zonder datum onderaan
  (geen datum is onbekend, niet oud)
- **Filteren** op bron, op vlag en op oordeel, plus een csv-export van je ja-lijst
- **Automatische run bedienen**: aan of uit, en de tijdstippen beheren. Schrijft
  via `webui/rooster.py` naar launchd en vervangt alleen het
  `StartCalendarInterval`-blok in de plist, zodat de comments blijven staan

## Draaien

Vanuit een terminal in deze map, met de venv geactiveerd:

```
source .venv/bin/activate
python3 scraper.py
```

Output verschijnt in de map `output`:
- `nieuw_JJJJ-MM-DD_UUMM.xlsx`: alleen vacatures die je nog niet eerder zag
- `alle_vacatures.csv`: cumulatief logboek van alles wat ooit door het filter kwam
- `state.json` (hoofdmap): het geheugen. Weggooien betekent dat alles opnieuw als nieuw wordt gemeld.

## Automatisch draaien (macOS launchd)

Standaard twee runs per dag, om 08:00 en 20:00, via een LaunchAgent. Opzetten
staat in [launchd/README.md](launchd/README.md); bedienen kan daarna zonder
terminal via de webinterface.

Bewust launchd en niet cron. Slaapt je laptop op het geplande moment, dan slaat
cron die run over en haalt niets in, terwijl launchd hem alsnog uitvoert zodra de
machine wakker wordt. Dat telt hier zwaar, want elke run verbruikt nieuwheid.

De opdracht draait bovendien via `caffeinate`, omdat launchd de Mac wel wakker
maakt om te starten maar niet wakker houdt tijdens de run. Zonder die wikkel viel
de machine na een paar seconden terug in slaap en had een run na twee uur pas een
derde van het werk gedaan.

## Config aanpassen (config.yaml)

- `zoektermen`: waarop de borden doorzocht worden. Meer termen betekent meer requests; tien is een goede balans.
- `boards.locaties`: WAAR de borden zoeken (LinkedIn, Indeed). Elke zoekterm wordt per locatie apart bevraagd, dus meer locaties betekent evenredig meer requests en meer kans op een LinkedIn-429. Voorgevuld: Amsterdam en Rotterdam. Een zoeklocatie hoort ook in `locaties_toegestaan` te staan, anders wordt zijn resultaat wel opgehaald maar daarna weggefilterd. Ontbreekt dit veld, dan valt de scraper terug op het oude enkele veld `locatie`. Kale steden mogen: "Amsterdam" wordt bij het zoeken aangevuld tot "Amsterdam, Netherlands", tenzij je zelf al een komma typt.
- `titel_uitsluiten`: harde drops op woordgrens. `manager` dropt "Risk Manager" maar niet "Risk Management Analyst".
- `flag_termen`: droppen niet, markeren wel. Compliance-touchpoints horen hier, een compliance-kern beoordeel je zelf in de listing.
- `locaties_toegestaan`: het FILTER op alles wat is opgehaald, uit alle bronnen. Substring-match op de locatietekst; onbekende locatie wordt bewaard met flag. Dit staat los van `boards.locaties`: dat veld bepaalt WAAR de borden zoeken, dit bepaalt WAT er na het ophalen doorheen komt. Een zoeklocatie die hier niet in staat, levert dus niets op.
- `max_uren_oud`: stem af op je rooster. Twee runs per dag met twaalf uur
  ertussen vraagt om zo'n 16 uur terugkijken: die vier uur marge vangt op dat een
  run zelden precies op tijd start. Eenmalig dieper: `scraper.py --uren 72`.
- `magnetme.paden`: overzichtspagina's in het formaat `banen/{stad}/{functie}`. Standaard de categorieën analyst en finance in Amsterdam. Steden die magnet.me kent en binnen jouw reistijd vallen: amstelveen, hoofddorp, schiphol, haarlem, diemen, utrecht. Magnet.me toont geen geplaatst-datum op deze pagina's; nieuwheid wordt via state.json bepaald.

## ATS-slugs vinden

Open de careers-pagina van het bedrijf en kijk naar de URL of de netwerk-tab (Cmd+Option+I). Test daarna de feed-URL in je browser; zie je JSON, dan klopt de slug.

- **Recruitee**: careers-URL is vaak `bedrijf.recruitee.com`. Test: `https://SLUG.recruitee.com/api/offers/`
- **Greenhouse**: vaak `boards.greenhouse.io/SLUG` of `job-boards.greenhouse.io/SLUG`. Test: `https://boards-api.greenhouse.io/v1/boards/SLUG/jobs`
- **Lever**: `jobs.lever.co/SLUG`. Test: `https://api.lever.co/v0/postings/SLUG?mode=json`
- **Workday**: careers-URL heeft de vorm `https://TENANT.wd3.myworkdayjobs.com/SITE`. In config:

```yaml
workday:
  - {tenant: TENANT, host: TENANT.wd3.myworkdayjobs.com, site: SITE, zoekterm: analyst}
```

## Beperkingen, eerlijk

- **De poort blijft handwerk.** Hybride dagen, salaris en de vraag of de analytische kern echt is, staan zelden betrouwbaar in de listing. De tool versmalt de trechter; jij beoordeelt.
- **LinkedIn rate-limits, met backoff.** Na te veel requests volgt tijdelijk een 429. De borden hebben nu een lichte backoff: bij een 429 of tijdelijke fout wacht de scraper en probeert hooguit twee keer opnieuw met oplopende wachttijd, daarna slaat hij die zoekterm plus locatie over en gaat door. Dat is een vangnet, geen vrijbrief; meer zoektermen of zoeklocaties betekent nog steeds meer requests. Oplossing bij aanhoudende 429: minder zoektermen, minder zoeklocaties, `resultaten_per_term` verlagen, of een run overslaan. Eén run per dag is ruim voldoende.
- **ToS-grijze zone.** De borden verbieden scrapen formeel in hun voorwaarden. Dit gebruik (publieke listings, persoonlijk, geen login, lage frequentie) is gangbaar en raakt je eigen accounts niet, maar weet dat het geen officiële API is en dus kan breken.
- **Flags op functietekst** werken alleen voor bronnen die de omschrijving
  leveren. Titel-uitsluitingen werken altijd. Laat `linkedin_beschrijving` uit:
  die liet jobspy de tekst serieel ophalen voor elk resultaat en voor het
  filteren, goed voor bijna zeven uur per run. De omschrijvingen komen nu via
  `sources_detail.py`, parallel en pas na de poort, met een eigen tempo per host
  omdat LinkedIn anders na een paar honderd pagina's 429's gaat geven.
- **Eén bron kapot betekent niet run kapot.** Elke bron en elke zoekterm is apart afgevangen; fouten worden gemeld en de rest draait door. Draai `check.py` om te zien welke bron het is.
