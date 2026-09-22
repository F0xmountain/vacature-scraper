# Automatisch draaien (macOS launchd)

De scraper draait twee keer per dag vanzelf via een LaunchAgent. De werkende
plist staat in `~/Library/LaunchAgents/` en wordt hier gespiegeld, maar het
gespiegelde bestand staat in `.gitignore`: het bevat absolute paden naar één
specifieke machine.

Hieronder staat hoe je hem zelf maakt.

## Waarom launchd en niet cron

De README noemt `crontab -e` als optie, maar op een laptop is dat de verkeerde
keuze. Slaapt de machine op het geplande moment, dan slaat cron die run gewoon
over en haalt niets in. launchd voert een gemiste run alsnog uit zodra de machine
wakker wordt, en vouwt meerdere gemiste momenten samen tot één run. Dat is hier
belangrijk, want elke run verbruikt nieuwheid: wat eenmaal is vastgelegd, meldt
de tool daarna niet meer als nieuw.

## Waarom caffeinate ervoor

launchd kan een gemiste run inhalen, maar houdt de Mac niet wakker *terwijl* die
run loopt. Zonder `caffeinate` startte een run op een onderhoudswekker, viel de
Mac een paar seconden later weer in slaap, en had het proces na twee uur
wachttijd 36 seconden CPU verbruikt en een derde van het werk gedaan.

`-i` houdt idle sleep tegen, `-s` system sleep (die laatste werkt alleen op
netstroom). Met een dichte klep op accu slaapt een Mac hoe dan ook; daar helpt
dit niet tegen.

## De plist maken

Maak `~/Library/LaunchAgents/com.JOUWNAAM.vacature-scraper.plist` met de inhoud
hieronder. Vervang `/PAD/NAAR/vacature-scraper` door je eigen projectmap en
`com.JOUWNAAM` door een label dat je zelf kiest. Let op: het label moet gelijk
zijn aan de bestandsnaam, en aan `LABEL` in `webui/rooster.py`, anders kan de
webinterface het rooster niet bedienen.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.JOUWNAAM.vacature-scraper</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-i</string>
        <string>-s</string>
        <string>/PAD/NAAR/vacature-scraper/.venv/bin/python</string>
        <string>/PAD/NAAR/vacature-scraper/scraper.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/PAD/NAAR/vacature-scraper</string>

    <!-- Twee runs per dag. De webinterface bewerkt precies dit blok. -->
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>8</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>20</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>

    <!-- false, zodat installeren of inloggen niet meteen een echte run start
         en dus ook geen nieuwheid verbruikt. -->
    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>/PAD/NAAR/vacature-scraper/logs/run.log</string>
    <key>StandardErrorPath</key>
    <string>/PAD/NAAR/vacature-scraper/logs/run.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

Maak daarna de logmap aan, want launchd doet dat niet zelf en de job start niet
als hij ontbreekt:

```
mkdir -p logs
plutil -lint ~/Library/LaunchAgents/com.JOUWNAAM.vacature-scraper.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.JOUWNAAM.vacature-scraper.plist
```

## Aan- en uitzetten

```
launchctl disable gui/$(id -u)/com.JOUWNAAM.vacature-scraper
launchctl bootout  gui/$(id -u)/com.JOUWNAAM.vacature-scraper

launchctl enable    gui/$(id -u)/com.JOUWNAAM.vacature-scraper
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.JOUWNAAM.vacature-scraper.plist
```

`bootout` alleen is niet genoeg: de plist staat nog in `~/Library/LaunchAgents`,
dus bij de volgende keer inloggen is de agent er weer. `disable` zet de vlag die
een herstart overleeft. Hetzelfde geldt omgekeerd: `enable` doet niets tot je ook
`bootstrap` draait.

Eenvoudiger is het via de webinterface: **Zoekprofiel**, onderaan bij
**Automatische run**. Daar zet je hem aan of uit en beheer je de tijdstippen.
Die route schrijft via `webui/rooster.py`, dat alleen het
`StartCalendarInterval`-blok vervangt en de rest van het bestand ongemoeid laat.
