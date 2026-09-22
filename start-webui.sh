#!/bin/zsh
# Start de webinterface en open hem in de browser.
#
# Dit is de logica achter "Vacature Scraper.app"; die app roept alleen dit
# script aan. Los draaien kan ook: ./start-webui.sh
#
# De app opnieuw bouwen na een wijziging hier is niet nodig, want hij roept dit
# script aan op pad. Is de app zelf kwijt, bouw hem dan terug met:
#
#     osacompile -o "Vacature Scraper.app" \
#       -e "do shell script \"$(pwd)/start-webui.sh\""
#
# Draait er al een server op de poort, dan wordt er geen tweede gestart (dat zou
# een "address already in use" geven); dan opent alleen de browser. Zo is
# dubbelklikken altijd veilig.

# Projectmap afleiden uit de locatie van dit script, zodat het werkt waar je het
# ook neerzet. De .app die dit aanroept gebruikt wel een absoluut pad, want die
# wordt door osacompile met dat pad gebouwd.
PROJECT="$(cd "$(dirname "$0")" && pwd)"
POORT=8500
URL="http://127.0.0.1:${POORT}/"

cd "$PROJECT" || exit 1

if ! lsof -nP -iTCP:${POORT} -sTCP:LISTEN >/dev/null 2>&1; then
  mkdir -p logs
  # Losgekoppeld starten zodat de server blijft draaien nadat dit script klaar
  # is. stdin/stdout/stderr gaan naar het logbestand; blijft er een handle open
  # staan, dan blijft de aanroepende app hangen.
  nohup "$PROJECT/.venv/bin/python" "$PROJECT/webui/server.py" \
    </dev/null >>"$PROJECT/logs/webui.log" 2>&1 &
  disown

  # Wachten tot hij echt luistert, anders opent de browser op een dode poort.
  # Ruim tien seconden; daarna toch openen zodat je de fout in beeld krijgt.
  for i in {1..40}; do
    if curl -s -o /dev/null --max-time 1 "$URL"; then
      break
    fi
    sleep 0.25
  done
fi

open "$URL"
