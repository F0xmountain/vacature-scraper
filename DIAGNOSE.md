# Diagnose live zelftest

Run: `./.venv/bin/python check.py`, precies een keer uitgevoerd op 2026-07-24
om 22:02. Exit 0. Er is niets weggeschreven. LinkedIn gaf geen 429.

## Status per bron

| Bron | Status | Resultaat |
|---|---|---|
| Python 3.11.15 | OK | Voldoet aan 3.11/3.12 eis |
| Pakketten (jobspy, pandas, openpyxl, PyYAML, requests, bs4) | OK | Allemaal aanwezig |
| Borden: LinkedIn, Indeed, Glassdoor | OK (met kanttekening) | 10 vacatures in 4s. Zie Glassdoor hieronder |
| Magnet.me | OK | 20 vacatures in 4s. Voorbeeld: Trust & Safety Analyst, Booking.com, amsterdam |
| Careers-feed Recruitee AFM | OK | 14 vacatures |
| Careers-feed Greenhouse Flow Traders | OK | 38 vacatures |
| Careers-feed Greenhouse Optiver | OK | 190 vacatures |
| DNB (werkenbij-module) | OK | 2 vacatures. Voorbeeld: Functioneel Beheerder, DNB, amsterdam |
| Banken.nl (werkenbij-module) | OK | 44 vacatures. Voorbeeld: Technisch ApplicatiebeheerderNWB Bank, Nwb Bank, geen locatie |

Filterresultaat over de hele set: opgehaald 318, na ontdubbelen 313, gedropt op
titel 111, gedropt op locatie 103, blijft over 99.

## Bronnen die niet volledig OK zijn

Geen enkele bron-groep gaf LEEG of FOUT, dus `check.py` heeft geen enkele pagina
in `debug/` bewaard; die map bestaat niet. Er is dus geen bewaarde pagina om te
analyseren en op dit moment niets aan een parser te repareren.

Er is wel een sub-bron met een probleem:

### Glassdoor (binnen de borden-groep): 400, location not parsed

Logregels bij de run:

```
ERROR - JobSpy:Glassdoor - Glassdoor response status code 400
ERROR - JobSpy:Glassdoor - Glassdoor: location not parsed
```

Wat er waarschijnlijk mis is: dit is geen parser van dit project maar gedrag
binnen python-jobspy. Glassdoor kon de meegegeven locatie niet omzetten naar zijn
interne location-id en gaf daarom een 400 terug. Dit is precies de wisselvalligheid
die in HANDOFF sectie 7 en README staat vermeld (Glassdoor is de wisselvalligste
van de drie borden). De borden-groep blijft OK omdat LinkedIn en Indeed samen 10
vacatures leverden; Glassdoor droeg deze run niets bij. Omdat de groep niet leeg
was, is er geen debug-pagina bewaard.

Dit valt buiten de opdracht om parsers van dit project te repareren; het zit in de
library. Mogelijke richtingen voor later (niet nu uitgevoerd): de locatiestring
voor Glassdoor anders formatteren, of Glassdoor als bron minder zwaar wegen.

**Opgelost op 2026-07-24:** Glassdoor is uit de borden gehaald in config.yaml
(`sites: [linkedin, indeed]`). Glassdoor is dus niet langer actief. Zie de sectie
"Wijzigingen in config.yaml" hieronder.

## Conclusie

Alle bronnen van het project zelf leveren data en het filter werkt. De enige
zichtbare storing is Glassdoor via python-jobspy (400), wat een bekende en zachte
degradatie is. Geen parser van dit project hoeft op basis van deze run gerepareerd
te worden.

## Wijzigingen in config.yaml (2026-07-24)

Na de zelftest zijn drie wijzigingen doorgevoerd in config.yaml.

1. **Glassdoor uit de borden.** `sites` is `[linkedin, indeed]` geworden.
   Reden: Glassdoor gaf een 400 "location not parsed" op elke zoekterm, een
   bekende jobspy-bug met komma-locaties, en de NL-dekking overlapt met Indeed.

2. **IMC toegevoegd aan de greenhouse-lijst, na verificatie.** De opgegeven
   controle was `curl -s "https://boards-api.greenhouse.io/v1/boards/imc/jobs" | grep -c '"title"'`,
   die 1 teruggaf. Dat is misleidend: de feed is een enkele regel JSON, dus
   `grep -c` telt regels, niet voorkomens. Het echte aantal is geteld met
   `grep -o '"title"' | wc -l` en met de `meta.total` uit de JSON: beide geven
   **153 vacatures**. De feed levert geldige JSON met een HTTP 200 en locaties
   als "Amsterdam, Netherlands; Mumbai, India". 153 valt ruim in de tientallen,
   dus de regel `- {slug: imc, naam: IMC}` is uitgecommentarieerd weggehaald en
   nu actief. Het locatiefilter houdt straks alleen de Amsterdamse rollen over.

3. **Drie titeluitsluitingen toegevoegd** aan `titel_uitsluiten`: `inventory`,
   `trust & safety`, `supply chain`. `underwriter` is bewust NIET toegevoegd,
   zodat verzekeringsrollen blijven doorkomen.

Niet aangeraakt: filters.py, state.json, en verder niets aan zoektermen,
locaties of bronnen buiten het bovenstaande. scraper.py is niet gedraaid; de
gebruiker draait zelf een dry-run ter controle.

## Wijzigingen op 2026-07-25

Vier functionele wijzigingen plus een opschoning, zonder de filterlogica of de
schrijfroute van config_ui.py aan te raken.

1. **Zoeken op meerdere locaties op de borden.** In config.yaml is onder `boards`
   het enkele veld `locatie` vervangen door een lijst `locaties` met
   "Amsterdam, Netherlands" en "Rotterdam, Netherlands". In sources_boards.py
   loopt de borden-zoekopdracht nu per zoekterm over elke locatie, als aparte
   ronde per term per locatie. Ontbreekt `locaties`, dan valt de code terug op het
   oude `locatie`-veld, zodat bestaande configs blijven werken. Ontdubbelen over
   locaties gebeurt verderop in store.py; hier is geen dedupe toegevoegd. Let op:
   dit vermenigvuldigt het aantal requests met het aantal locaties en vergroot dus
   de kans op een LinkedIn-429. Dat staat als comment in beide bestanden.

2. **Backoff op de borden.** De scrape_jobs-aanroep zit nu in `_scrape_ronde`, die
   bij een 429 of tijdelijke fout wacht en hooguit twee keer opnieuw probeert met
   oplopende wachttijd (5s, dan 10s). Lukt het daarna nog niet, dan wordt die
   zoekterm plus locatie overgeslagen (melden en door), net als voorheen. De
   bestaande pauze van 3s tussen calls is behouden en er is geen parallellisme
   toegevoegd. Dit is een vangnet, geen vrijbrief om harder te vragen.

3. **Twee locatielijsten zichtbaar in de interface.** config_ui.py toont nu
   `boards.locaties` (WAAR de borden zoeken, weinig items) als aparte bewerkbare
   lijst via de bestaande `zet_lijst`, duidelijk gescheiden van
   `locaties_toegestaan` (het FILTER op alles wat is opgehaald, veel items). Bij de
   zoeklocaties staat een hint dat een zoeklocatie ook in de toegestane locaties
   hoort te staan, anders wordt zijn resultaat wel opgehaald maar daarna
   weggefilterd.

4. **Requirements gesplitst.** requirements.txt houdt alleen wat de scraper zelf
   nodig heeft. De interface-only pakketten staan nu in requirements-ui.txt
   (streamlit, ruamel.yaml). README legt uit hoe je elk installeert.

Opschoning: de zoekterm "financieel analist" (een testterm) is uit config.yaml
verwijderd, en `boards.max_uren_oud` staat terug op 72.

### Opgelost op 2026-07-25: locatiefilter robuust tegen invoerformaat

De eerder beschreven caveat (Rotterdam wordt opgehaald maar mogelijk
weggefilterd) is verholpen in filters.py. Het filter normaliseert nu elke
toegestane locatie voordat het de substring-match doet: het splitst op komma en
gebruikt alleen het eerste, betekenisvolle deel (de stad of het steekwoord), in
kleine letters. Dat gebeurt in een klein hulpje `_stad`.

Concreet wordt "Rotterdam, Netherlands" tot de stad "rotterdam", en die matcht
wel op een board-locatie als "Rotterdam, South Holland, Netherlands". Korte items
als "amsterdam" en "utrecht" blijven onveranderd werken, want zonder komma is het
eerste deel de hele string. Zo werkt elke stad ongeacht het invoerformaat:
"Rotterdam", "rotterdam" en "Rotterdam, Netherlands" leveren allemaal dezelfde
match op.

Verder is er niets aan de filterlogica veranderd: geen nieuwe drops, geen scoring,
en de lege-locatie-flag en de titeluitsluitingen zijn ongemoeid. Dit gaat puur
over hoe een toegestane locatie tegen een board-locatie wordt gematcht.

test_lokaal.py is meegetrokken met dit gedrag. De oude assert die aannam dat de
neplocatie "Rotterdam" werd gedropt, gaat er nu van uit dat die terecht blijft
(Rotterdam staat immers in de toegestane lijst), waardoor het aantal doorgelaten
vacatures van 2 naar 3 gaat. Daarnaast is er een testgeval bijgekomen dat
expliciet controleert dat "Rotterdam, Netherlands" matcht op
"Rotterdam, South Holland, Netherlands", plus een negatief geval dat een stad
buiten de lijst (Berlin) nog steeds afvalt. De test is groen.

## Interface-uitbreiding op 2026-07-26

Twee toevoegingen aan de Streamlit-interface, plus een lichte refactor van
scraper.py zodat de UI de bestaande run-logica hergebruikt.

1. **Locatie-normalisatie bij de zoeklocaties.** Kale steden in `boards.locaties`
   worden op het moment van zoeken aangevuld tot het volledige formaat
   "Stad, Netherlands". Heeft de gebruiker zelf al een komma getypt, dan blijft de
   invoer staan. Dit gebeurt in `_normaliseer_locatie` in sources_boards.py, precies
   waar de locatie aan de zoekopdracht wordt meegegeven; config.yaml blijft dus
   leesbaar en bewaart de locaties zoals ingevoerd. Dit geldt voor zowel de
   terminal-run als de UI-run, want beide gaan door fetch_boards. Zoektermen
   (functienamen) worden niet genormaliseerd; daar is geen vast formaat voor.

2. **Twee zoekknoppen in de interface.** scraper.py is minimaal opgesplitst in
   `laad_config`, `verzamel_dedupe_filter` (de dry-keten) en `leg_vast` (de echte
   run: load_state, split_new, save_state, export, in die volgorde). main() roept
   deze aan en houdt exact hetzelfde terminalgedrag en dezelfde uitvoer. De UI
   hergebruikt deze functies, zodat er geen tweede kopie van de zoek- en
   filterlogica bestaat.
   - "Zoek en toon" draait een dry-run: schrijft niets weg en raakt state.json
     niet aan. Toont de volledige lijst die door het filter komt.
   - "Vastleggen (echte run)" draait een echte run: schrijft de xlsx en werkt
     state.json bij. De knop heeft een aanvinkbevestiging omdat hij nieuwheid
     verbruikt, en toont daarna alleen wat nieuw is weggeschreven.
   - Beide knoppen blokkeren zichzelf tijdens een run (twee-fasen via
     st.session_state plus een spinner) zodat er niet dubbel wordt aangeroepen.
   - De resultaten verschijnen als tabel met functie, bedrijf, locatie, flags en
     een klikbare link naar de vacature.

Niet aangeraakt: filters.py, store.py en de manier waarop state.json wordt
bijgewerkt (leg_vast gebruikt exact dezelfde store-aanroepen in dezelfde volgorde
als de oude main). In config_ui.py zijn laad, zet_lijst, bewaar en de schrijfroute
naar config.yaml ongemoeid. Geen scoring of ranking, geen wijziging aan de
filterlogica, geen verbrede zoektermen of locaties.

Noot bij verificatie: test_lokaal.py is groen. Een py_compile en de
Streamlit-AppTest-smoketest kon ik niet draaien omdat de permissie-instellingen nu
alleen `check.py` en `test_lokaal.py` via de venv-Python toestaan; de taalserver
(Pylance) meldt geen fouten in scraper.py, sources_boards.py en config_ui.py.

## HTML-webinterface op 2026-07-26

Naast de Streamlit-interface is er nu een strakkere HTML-interface met een kleine
lokale Python-server. config_ui.py blijft als werkende terugval bestaan.

- **Gedeelde schrijfroute (config_io.py).** De comment-behoudende functies `laad`,
  `zet_lijst` en `bewaar` zijn verplaatst naar een nieuw `config_io.py`, plus een
  gedeelde `schrijf_profiel` die de velden in vaste volgorde wegschrijft. Zowel
  config_ui.py als de webserver gebruiken deze ene route, zodat de comments in
  config.yaml behouden blijven en er geen tweede schrijflogica bestaat. config_ui.py
  is aangepast om uit config_io te importeren en `schrijf_profiel` te gebruiken;
  het gedrag en de comment-behoud zijn gelijk gebleven.

- **Server (webui/server.py).** Draait op de standaard `http.server` uit de
  standaardbibliotheek, geen webframework, dus geen extra dependency. Endpoints:
  `GET /api/profiel` (huidig profiel), `POST /api/profiel` (opslaan via config_io)
  en `POST /api/run` met `{"modus": "dry"|"echt"}`. De run hergebruikt
  `scraper.verzamel_dedupe_filter` en `scraper.leg_vast`; er staat geen kopie van
  de zoek- of filterlogica in de webui. Een threading-lock voorkomt dat er twee
  runs tegelijk lopen.

- **Interface (webui/static).** Eigen HTML, CSS en JavaScript, geen frameworks.
  Rustig ontwerp met hetzelfde gedempte blauwe accent. Bewerkbare lijsten voor
  zoektermen, zoeklocaties, toegestane locaties, titel-uitsluitingen en flags,
  plus bron-schakelaars en bord-instellingen. Twee gescheiden zoekknoppen: "Zoek
  en toon" (dry-run) en "Vastleggen" (echte run, met bevestigingsvinkje). Beide
  blokkeren zichzelf en tonen een bezig-indicatie tijdens de run. Resultaten in
  een nette tabel met functie, bedrijf, locatie, flags en een klikbare link;
  duidelijk onderscheid tussen de dry-lijst en de nieuw weggeschreven lijst.
  Starten: `./.venv/bin/python webui/server.py`, dan http://127.0.0.1:8500.

- **Locatie-normalisatie.** Ongewijzigd: kale steden worden pas bij het zoeken tot
  "Stad, Netherlands" aangevuld, in sources_boards.py. De webui slaat locaties op
  zoals ingevoerd.

Niet aangeraakt in gedrag: scraper.py, filters.py, store.py, sources_boards.py,
output.py en config.yaml. `git status` bevestigt dat alleen config_ui.py is
gewijzigd en dat config_io.py en webui/ nieuw zijn; de scraper- en filterbestanden
staan niet in de diff. De terminal-run (`python scraper.py --dry-run`) is dus
onveranderd.

Noot bij verificatie: test_lokaal.py is groen. De taalserver (Pylance) meldt geen
fouten in config_io.py, config_ui.py en webui/server.py. De webserver zelf kon ik
niet starten door de permissie-instellingen (alleen `check.py` en `test_lokaal.py`
via de venv-Python); dat is een handmatige smoketest voor de gebruiker.

### Fix na eerste live test: run naar de achtergrond (2026-07-26)

Bij de eerste echte start van de webserver bleek de eerste opzet te fragiel. De
scraper draaide goed (data kwam binnen: IMC 150, Banken.nl 40, enzovoort), maar
`POST /api/run` hield de HTTP-verbinding minutenlang open tot de run klaar was. De
browser sloot die verbinding intussen, waardoor het antwoord een
`BrokenPipeError` gaf en er zelfs een tweede volledige run startte. Bij een echte
run zou dat nieuwheid verbruiken zonder dat de gebruiker een resultaat ziet.

Opgelost door de run asynchroon te maken, alleen in webui (scraper.py niet
aangeraakt):

- `POST /api/run` start de run nu in een achtergrondthread en keert meteen terug
  met `{"status": "bezig"}`. Een tweede run terwijl er een loopt geeft 409.
- Nieuw `GET /api/run/status` geeft `bezig`, `klaar` (met resultaat) of `fout`.
  Het resultaat wordt server-side bewaard, dus een verbroken verbinding of een
  reload verliest het niet meer.
- De browser (app.js) start de run, toont de bezig-indicatie en pollt elke paar
  seconden de status tot hij klaar is. Bij het laden checkt de pagina of er al een
  run loopt en pikt die op.
- De response-writes vangen nu `BrokenPipeError` en `ConnectionResetError` af, dus
  een weggeklikte browser geeft geen tracebacks meer.

test_lokaal.py blijft groen; Pylance meldt geen fouten in webui/server.py en
webui/static/app.js.

## Plaatsingsdatum in de resultatentabel (2026-07-27)

De webinterface toont nu een kolom Geplaatst, tussen Locatie en Flags.

- `webui/server.py` (`_rijen`) geeft het bestaande `geplaatst`-veld mee aan de
  rijen die naar de pagina gaan. Verder niets aan de run of het onderscheid
  dry-run versus echte run.
- `webui/static/app.js` formatteert de datum tot dd-mm-jjjj als hij te parsen valt
  (ISO-datum uit de borden, of anders een parseerbare datumstring) en laat de cel
  leeg als er geen datum is of hij niet te parsen valt. Boven de tabel staat een
  toelichting, en op de kolomkop een tooltip, dat een lege datum betekent dat de
  bron er geen levert (vooral ATS, Magnet.me en de werkenbij-sites), niet dat de
  vacature vandaag is geplaatst. Alleen de borden (LinkedIn, Indeed) leveren een
  betrouwbare datum.
- `webui/static/style.css` geeft de datumkolom een vaste, compacte breedte zonder
  afbreken, zodat functie en bedrijf niet worden afgeknepen.

output.py is niet aangeraakt: de xlsx-export had de kolom `geplaatst` (kop
"Geplaatst") al. Niet aangeraakt in gedrag: scraper.py, filters.py, store.py,
sources_boards.py, config.yaml en config_io.py. test_lokaal.py is groen en Pylance
meldt geen fouten in de gewijzigde bestanden.

## Bekende zwakke plekken

**Logodekking.** De logo's in de webinterface lopen via drie diensten, in deze
volgorde: DuckDuckGo, Google, en als laatste het eigen favicon van het domein
(`https://{domein}/favicon.ico`). Sommige bedrijven hebben bij geen van de drie
een bruikbaar icoon; deloitte.nl en mufg.jp zijn daar voorbeelden van. Die houden
hun monogramtegel. Dat is een grens van de bronnen, geen bug. Levert de gok voor
een bepaalde naam een verkeerd logo op, dan is `UITSLUITEN` in webui/logos.py de
plek om die naam uit te sluiten.
