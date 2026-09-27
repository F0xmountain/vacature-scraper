"""Matchdossier: de geselecteerde vacatures plus een opdracht in een bestand.

Bedoeld om samen met je cv aan Claude te geven, zodat die rangschikt waar jij
op zou moeten reageren. De xlsx is er om te sorteren en te filteren, dit
bestand is er om te laten lezen: de volledige functietekst gaat mee, en de
opdracht staat erboven zodat je alleen nog je cv hoeft aan te hechten.

Twee dingen maken dit meer dan een dump.

Een tekstbudget. Het venster van drie dagen is zeven miljoen tekens, en dat is
ruim een miljoen tokens; geen enkel gesprek neemt dat op. Het budget verdeelt de
ruimte over de geselecteerde vacatures, dus hoe scherper je filtert hoe meer
tekst er per vacature overblijft. Bij de scherpe trechter (rond de tachtig
vacatures) is dat ruim drieduizend tekens per stuk, genoeg voor de hele kern.

Slim afkappen. Moet er geknipt worden, dan gaat het eisenblok mee en niet alleen
de introductie. Gemeten op 27-09-2026 over 1210 teksten: 51 procent heeft een
vindbare eisenkop, de mediaan staat op 52 procent van de tekst, en in 454
gevallen valt die voorbij de eerste veertig procent. Plat afkappen op de kop
gooit dus precies het stuk weg waar het om gaat.

Dit is de enige schrijfroute naar output/matchdossier.md. De webinterface
gebruikt bouw() en stuurt het resultaat als download; die raakt de schijf niet.
"""
import argparse
import re
from datetime import datetime
from pathlib import Path

import vaardigheden


# Tekens, niet tokens: een teken is ruwweg een kwart token, dus dit is grofweg
# tachtigduizend tokens aan vacaturetekst. Dat laat in een gesprek van
# tweehonderdduizend ruimte over voor je cv, de opdracht en het antwoord.
BUDGET = 320_000
# Onder de ondergrens is een tekst niet meer te beoordelen; dan liever minder
# vacatures in het dossier. De bovengrens telt alleen als je een handvol
# vacatures selecteert, want dan is het budget de beperking niet. Zesduizend
# tekens laat 76 procent van de teksten in het venster van 26-09-2026 helemaal
# heel; daarboven staan doorgaans arbeidsvoorwaarden en de eeo-alinea, en wat
# er wel telt haalt het slimme afkappen er toch al uit.
PER_MIN = 800
PER_MAX = 6000

# Koppen die een eisenblok aankondigen. Bewust ruim en tweetalig.
#
# Het venster van 40 tekens ervoor en 15 erna doet het werk: een kop is kort.
# Met het ruimere venster dat hier eerst stond (70 en 45) sloeg de regex ook aan
# op gewone zinnen, en dan begint het tweede stuk van de tekst midden in een
# alinea in plaats van bij de eisen. Gemeten op 27-09-2026 was 7 procent van de
# treffers een regel langer dan 60 tekens, oftewel een zin; met dit venster zijn
# dat er 2 van de 612, en de dekking zakt maar van 56 naar 51 procent.
# Elk alternatief hierin haalt los gemeten 83 tot 100 procent kopachtige regels.
_EISENKOP = re.compile(
    r"^.{0,40}?\b("
    r"wat (wij |we |jij )?(vragen|zoeken|meebrengt|meeneemt)|wat breng je mee|"
    r"wat neem je mee|jouw profiel|jouw achtergrond|wie ben jij|dit ben jij|"
    r"functie-?eisen|jij hebt|je hebt|wij vragen|"
    r"your profile|about you|who you are|requirements|qualifications|"
    r"what you.{0,3}ll bring|what we.{0,3}re looking for|skills and experience|"
    r"your (background|experience|skills)|we are looking for"
    r")\b.{0,15}$",
    re.I | re.M,
)

_KNIPMARKERING = "\n\n[... tussenstuk weggelaten ...]\n\n"

# Opmaak die uit de bron meekomt en hier in de weg zit.
#
# De hekjes moeten weg omdat dit bestand zelf markdown is: het dossier zet elke
# vacature onder een kop met drie hekjes, en een functietekst die zelf
# "### Description" bevat maakt dan een kop op hetzelfde niveau. Dan is niet meer
# te zien waar de ene vacature ophoudt en de volgende begint. Alleen hekjes met
# een spatie erachter; "#Jobster" is een hashtag en geen kop, en die komt in dit
# venster 131 keer voor tegen 123 echte koppen.
#
# De ontsnappingen komen van bronnen die markdown doorsturen ("25\-Sep\-2026",
# "Dolce \& Gabbana"). Ze zeggen niets en lezen slecht. Sterretjes blijven juist
# staan: dit bestand wordt als markdown gelezen, dus daar dragen ze nadruk.
_BRONKOP = re.compile(r"^#{1,6}[ \t]+", re.M)
_ONTSNAPT = re.compile(r"\\([^\w\s])")

# Onder deze ruimte levert knippen in twee stukken twee snippers op in plaats van
# een leesbare kop plus een leesbaar eisenblok; dan liever gewoon vooraan
# beginnen. Bewust los van PER_MIN: die is de ondergrens voor een hele tekst, en
# als je daar op uitkomt (honderden vacatures in een dossier) is het eisenblok
# juist het enige wat nog waarde heeft.
_SPLITS_MINIMUM = 300

# Dezelfde selectie als de knop "Scherpe trechter" in de webinterface: de vier
# families waar de zoekopdracht om draait, plus twee of meer datasignalen. Staat
# hier zodat --scherp precies hetzelfde doet als die knop; twee dingen die zo
# heten en iets anders selecteren is een val.
KERNROLLEN = ("analist", "controller", "finance", "risk")


def scherp(jobs):
    """De scherpe trechter: kernrollen met twee of meer datasignalen."""
    import functies

    uit = []
    for j in jobs:
        if functies.familie(j.get("functie") or "") not in KERNROLLEN:
            continue
        if vaardigheden.kernsignalen(vaardigheden.uit_tekst(j.get("beschrijving"))) < 2:
            continue
        uit.append(j)
    return uit


def _plat(tekst):
    """Witruimte en meegekomen opmaak opruimen, alinea's houden.

    De bronnen leveren regelafstand die alle kanten op gaat: LinkedIn plakt
    losse regels aan elkaar, een ats-feed geeft drie lege regels tussen elke
    kop. Meerdere lege regels worden er een, en spaties binnen een regel
    worden er een, maar de regelovergangen blijven staan. Die dragen de
    structuur van een vacaturetekst, en die structuur is juist wat een lezer
    de eisen laat vinden.
    """
    tekst = _ONTSNAPT.sub(r"\1", _BRONKOP.sub("", tekst or ""))
    regels = [" ".join(r.split()) for r in tekst.splitlines()]
    uit = []
    for r in regels:
        if not r and (not uit or not uit[-1]):
            continue
        uit.append(r)
    return "\n".join(uit).strip()


def _knip_zacht(tekst, limiet):
    """Afkappen op de laatste regel- of zinsgrens die nog binnen de limiet valt.

    De laatste grens, niet de eerste die toevallig voorbij de helft ligt. Dat
    was hier eerst anders: een regelovergang op 51 procent van de ruimte won
    het van een zinseinde op 98 procent, en dan viel de halve toegemeten ruimte
    weg. Gemeten op 27-09-2026 bij 800 tekens per vacature: 239 van de 1198
    afgekapte teksten vulden minder dan tachtig procent van hun ruimte, de
    slechtste 43 procent.

    Een zinseinde houdt zijn punt; een regelovergang niet, die is de grens zelf.
    Een spatie is de laatste uitweg, want dat knipt midden in een zin.
    """
    if len(tekst) <= limiet:
        return tekst
    knip = tekst[:limiet]
    regel, zin = knip.rfind("\n"), knip.rfind(". ")
    if max(regel, zin) > limiet // 2:
        einde = regel if regel > zin else zin + 1
        return knip[:einde].rstrip()
    spatie = knip.rfind(" ")
    return knip[:spatie].rstrip() if spatie > limiet // 2 else knip.rstrip()


def kort(tekst, limiet):
    """De tekst binnen de limiet brengen, met het eisenblok erin.

    Past de tekst, dan verandert er niets. Anders gaat veertig procent van de
    ruimte naar de kop van de tekst (daar staat waar de rol over gaat) en de
    rest naar het stuk dat begint bij de eisenkop. Is er geen eisenkop te
    vinden, dan wordt er gewoon aan het eind geknipt; dat is beter dan gokken.
    """
    tekst = _plat(tekst)
    if len(tekst) <= limiet:
        return tekst

    kop = _EISENKOP.search(tekst)
    ruimte = limiet - len(_KNIPMARKERING)
    # Valt het eisenblok binnen wat we toch al zouden meenemen, dan is knippen
    # in twee stukken alleen maar verwarrend.
    if not kop or ruimte < _SPLITS_MINIMUM or kop.start() <= int(ruimte * 0.4):
        return _knip_zacht(tekst, limiet).rstrip() + " [...]"

    begin, rest = tekst[: kop.start()], tekst[kop.start():]
    voor = _knip_zacht(begin, int(ruimte * 0.4))
    eisen = _knip_zacht(rest, ruimte - len(voor))
    # Is het eisenblok korter dan zijn deel, dan gaat wat overblijft terug naar
    # de kop. Zonder deze stap bleef die ruimte gewoon leeg: de kop werd op
    # veertig procent afgekapt terwijl er nog plek was.
    if len(voor) + len(eisen) < ruimte and len(voor) < len(begin):
        voor = _knip_zacht(begin, ruimte - len(eisen))
    # Alleen een knipmarkering als er echt iets tussenuit valt.
    tussen = _KNIPMARKERING if len(voor) < len(begin) else "\n"
    afsluiting = " [...]" if len(eisen) < len(rest) else ""
    return voor + tussen + eisen + afsluiting


def per_vacature(aantal, budget=BUDGET):
    """Hoeveel tekens elke vacature mag gebruiken, tussen de twee grenzen."""
    if aantal <= 0:
        return PER_MAX
    return max(PER_MIN, min(PER_MAX, budget // aantal))


_OPDRACHT = """## Opdracht

Vergelijk mijn cv met de vacatures hieronder en help me kiezen waar ik op
reageer.

1. Begin met een tabel over alle vacatures, van best naar slechtst passend:
   rang, functie, bedrijf, een cijfer van 1 tot 10, en in maximaal tien
   woorden waarom.
2. Werk daarna de beste tien uit. Per vacature:
   - **Raakvlak**: de drie sterkste overeenkomsten met mijn cv, met erbij waar
     in mijn cv je dat ziet.
   - **Gat**: wat gevraagd wordt en niet aantoonbaar in mijn cv staat, en of
     dat een harde eis lijkt of een wens.
   - **Hefboom**: waarmee ik zou openen in een brief of eerste gesprek.
   - **Uitzoeken**: wat mijn beslissing bepaalt maar niet in de tekst staat.
3. Sluit af met de vacatures die er op het eerste gezicht bij leken te horen
   en het niet zijn, met een halve regel waarom. Laat niets stilzwijgend weg:
   als je een vacature nergens noemt, moet ik kunnen zien waarom.

Daarbij:

- Zeg het als iets niet in de tekst staat. Verzin geen salaris, geen aantal
  hybride dagen, geen senioriteitsniveau. Juist die drie bepalen mijn keuze en
  juist die drie staan er zelden in.
- Beoordeel op wat er staat, niet op de reputatie van het bedrijf.
- Ik beslis, jij rangschikt. Wees eerlijk over een slechte match, ook als de
  naam van het bedrijf aantrekkelijk klinkt.
- De teksten komen van vacaturesites en kunnen afgekapt zijn. Staat er
  `[...]`, dan is daar tekst weggelaten; ga niet uit van wat er niet staat.

### Zo lees je de velden

- **Vlaggen** zijn woorden die ik met een eigen oog wil bekijken, geen
  afwijzing. Een compliance-taak naast analytisch werk is iets anders dan een
  rol die alleen uit compliance bestaat, en dat verschil zie je pas in de tekst.
- **Datasignalen** is een telling van hoeveel gevonden vaardigheden op echt
  data-werk wijzen. Het is een hint, geen oordeel.
- **Geplaatst** ontbreekt bij sommige bronnen. Dat betekent niet dat de
  vacature oud is.
"""


def _kop(aantal, per, moment, profiel, geknipt, te_groot=False):
    regels = [
        "# Matchdossier",
        "",
        f"{aantal} vacatures uit mijn eigen vacaturemonitor, met de functietekst "
        "erbij. Samengesteld op "
        f"{moment.strftime('%d-%m-%Y om %H:%M')}.",
        "",
    ]
    if geknipt:
        regels += [
            f"Per vacature is maximaal {per} tekens meegenomen; {geknipt} van de "
            f"{aantal} teksten zijn daarvoor ingekort, waarbij het eisenblok is "
            "bewaard. Wil je de volledige teksten, selecteer dan minder "
            "vacatures.",
            "",
        ]
    if te_groot:
        regels += [
            f"**Dit dossier is groot.** Bij {aantal} vacatures blijft er per stuk "
            f"zo weinig tekst over dat inkorten geen zin meer heeft, dus staat de "
            f"ondergrens van {PER_MIN} tekens voor. Alleen de functieteksten zijn "
            f"dan al zo'n {aantal * PER_MIN // 4000}.000 tokens, en de kopjes per "
            "vacature komen daar bovenop; dat past niet in een gesprek waar ook nog "
            "een antwoord bij moet. Filter scherper en maak een nieuw dossier.",
            "",
        ]
    if profiel:
        regels += ["## Waar ik naar zoek", "", profiel, ""]
    regels += [_OPDRACHT]
    return "\n".join(regels)


def _profieltekst(cfg):
    """Een paar regels over het zoekprofiel, uit config.yaml.

    Genoeg om te weten waar de lijst vandaan komt, zonder de hele configuratie
    over te nemen. Wat jij zoekt staat in je cv en in je eigen woorden; dit is
    alleen het net waarmee gevist is.
    """
    if not cfg:
        return ""
    boards = cfg.get("boards") or {}
    # zoektermen staat op het hoogste niveau, max_uren_oud onder boards.
    termen = [str(t) for t in (cfg.get("zoektermen") or []) if str(t).strip()]
    plaatsen = [str(p) for p in (cfg.get("locaties_toegestaan") or []) if str(p).strip()]
    uren = boards.get("max_uren_oud")
    regels = []
    if termen:
        regels.append(f"- Gezocht op: {', '.join(termen)}")
    if plaatsen:
        regels.append(f"- Alleen deze plaatsen: {', '.join(plaatsen)}")
    if uren:
        regels.append(f"- Alleen vacatures van de laatste {uren} uur per run")
    return "\n".join(regels)


def _vacature(nummer, job, limiet):
    tekst = kort(job.get("beschrijving"), limiet)
    gevonden = vaardigheden.uit_tekst(job.get("beschrijving"))
    vlaggen = str(job.get("flags") or "").strip()

    regels = [
        f"### {nummer}. {job.get('functie') or 'zonder titel'}",
        "",
        f"- Bedrijf: {job.get('bedrijf') or 'onbekend'}",
        f"- Locatie: {job.get('locatie') or 'niet vermeld'}",
        f"- Geplaatst: {job.get('geplaatst') or 'niet vermeld'}"
        f" | Bron: {job.get('bron') or 'onbekend'}"
        f" | Salaris: {job.get('salaris') or 'niet vermeld'}",
    ]
    if gevonden:
        regels.append(
            f"- Vaardigheden in de tekst: {', '.join(gevonden)}"
            f" (datasignalen: {vaardigheden.kernsignalen(gevonden)})"
        )
    if vlaggen:
        regels.append(f"- Vlaggen: {vlaggen}")
    if job.get("url"):
        regels.append(f"- {job['url']}")
    regels += ["", tekst or "_geen functietekst opgehaald_", ""]
    return "\n".join(regels)


def bouw(jobs, cfg=None, cv=None, budget=BUDGET):
    """Het hele dossier als een string, plus wat cijfers erover.

    Geeft (tekst, meta). meta heeft aantal, per_vacature, geknipt en tekens,
    zodat de aanroeper kan melden wat er gebeurd is zonder het bestand te
    hoeven natellen.
    """
    jobs = list(jobs or [])
    per = per_vacature(len(jobs), budget)
    geknipt = sum(1 for j in jobs if len(_plat(j.get("beschrijving"))) > per)

    delen = [
        _kop(len(jobs), per, datetime.now(), _profieltekst(cfg), geknipt,
             te_groot=len(jobs) * per > budget),
        "## Mijn cv",
        "",
        (cv.strip() if cv and cv.strip() else
         "_Mijn cv zit als bijlage bij dit bericht._"),
        "",
        f"## Vacatures ({len(jobs)})",
        "",
    ]
    delen += [_vacature(i, j, per) for i, j in enumerate(jobs, 1)]
    if not jobs:
        delen.append("_Geen vacatures geselecteerd._\n")
    tekst = "\n".join(delen)
    return tekst, {
        "aantal": len(jobs),
        "per_vacature": per,
        "geknipt": geknipt,
        "tekens": len(tekst),
        # Waar: de ondergrens per vacature won van het budget. Dan is er niets
        # meer te verdelen en moet de gebruiker scherper filteren.
        "te_groot": len(jobs) * per > budget,
    }


def bestandsnaam(moment=None):
    return f"matchdossier_{(moment or datetime.now()).strftime('%Y-%m-%d_%H%M')}.md"


def schrijf(tekst, cfg=None, naam="matchdossier.md"):
    """Wegschrijven naar de outputmap. Enige schrijfroute naar dit bestand."""
    outdir = Path(__file__).with_name((cfg or {}).get("output_map") or "output")
    outdir.mkdir(exist_ok=True)
    pad = outdir / naam
    pad.write_text(tekst, encoding="utf-8")
    return pad


def _lees_cv(pad):
    if not pad:
        return None
    p = Path(pad)
    if not p.exists():
        raise SystemExit(f"cv niet gevonden: {p}")
    if p.suffix.lower() not in (".txt", ".md", ".markdown"):
        raise SystemExit(
            f"cv moet .txt of .md zijn, dit is {p.suffix}. Een pdf kun je beter "
            "los aan Claude meegeven; dan hoeft er hier geen pdf-lezer bij."
        )
    return p.read_text(encoding="utf-8")


# Naast de map van dit bestand ook de cv's die je hier los neerzet. Beide staan
# in .gitignore, want een cv hoort niet in een publieke repository.
_CV_STANDAARD = ("cv.md", "cv.txt")


def cv_naast_het_project():
    for naam in _CV_STANDAARD:
        p = Path(__file__).with_name(naam)
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def _getal(n):
    return f"{n:,}".replace(",", ".")


def main():
    import scraper
    import output

    p = argparse.ArgumentParser(
        description="Maak een matchdossier van de bewaarde vacatures."
    )
    p.add_argument("--max", type=int, default=0,
                   help="alleen de eerste N uit het venster, nieuwste run eerst (0 is alles)")
    p.add_argument("--scherp", action="store_true",
                   help="de scherpe trechter: kernrollen met twee of meer datasignalen")
    p.add_argument("--budget", type=int, default=BUDGET,
                   help=f"tekenbudget voor alle functieteksten samen (standaard {BUDGET})")
    p.add_argument("--cv", default=None, help="pad naar je cv als .txt of .md")
    p.add_argument("--uit", default="matchdossier.md", help="bestandsnaam in de outputmap")
    args = p.parse_args()

    cfg = scraper.laad_config()
    data = output.lees_laatste_run(cfg)
    if not data or not data.get("jobs"):
        raise SystemExit(
            "Nog geen bewaarde runs in output/laatste_run.json. Draai eerst de "
            "scraper, of gebruik de knop in de webinterface."
        )

    jobs = data["jobs"]
    if args.scherp:
        jobs = scherp(jobs)
    if args.max > 0:
        jobs = jobs[: args.max]

    cv = _lees_cv(args.cv) if args.cv else cv_naast_het_project()
    tekst, meta = bouw(jobs, cfg, cv, args.budget)
    pad = schrijf(tekst, cfg, args.uit)

    print(f"{meta['aantal']} vacatures in {pad}")
    print(f"  {_getal(meta['tekens'])} tekens, ruwweg {_getal(meta['tekens'] // 4)} tokens")
    print(f"  per vacature maximaal {meta['per_vacature']} tekens, {meta['geknipt']} ingekort")
    if meta["te_groot"]:
        print("  LET OP: te veel vacatures voor een gesprek. Filter scherper.")
    if cv:
        print("  cv staat in het dossier")
    else:
        print("  geen cv gevonden; hecht hem los aan het bericht, of zet cv.md in de projectmap")


if __name__ == "__main__":
    main()
