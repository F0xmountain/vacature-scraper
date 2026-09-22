"""
Logo-proxy voor de webinterface.

Doel: logo's tonen zonder dat de browser ooit een externe dienst aanroept.
De server haalt een logo eenmalig op, valideert het en legt het op schijf.
Daarna komt alles van 127.0.0.1.

Aansluiten in webui/server.py:

    from webui import logos          # of: import logos, afhankelijk van je imports

    # in do_GET, voor de bestaande statische-bestandsroute:
    if pad.startswith("/logo"):
        logos.serveer(self, query.get("bedrijf", [""])[0])
        return

Raakt de scraperkern niet aan. Alleen interfacecode.
"""

import hashlib
import ipaddress
import os
import re
import socket
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logocache")
MAX_BYTES = 200 * 1024          # een favicon of logo is nooit groter
TIMEOUT = 4                     # seconden; de pagina mag hier niet op wachten
TIMEOUT_EIGEN = 2               # korter voor het domein zelf; een dood domein mag niet ophouden
MISS_TTL = 14 * 24 * 3600       # een mislukking twee weken onthouden
TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}
# image/svg+xml staat er bewust NIET bij: svg is een document dat script kan
# bevatten. Alleen rasterformaten.

# Handmatige lijst gaat voor. Uitbreiden is goedkoop en altijd veiliger dan gokken.
DOMEIN = {
    "optiver": "optiver.com",
    "imc": "imc.com",
    "imc trading": "imc.com",
    "flow traders": "flowtraders.com",
    "afm": "afm.nl",
    "autoriteit financiele markten": "afm.nl",
    "dnb": "dnb.nl",
    "de nederlandsche bank": "dnb.nl",
    "abn amro": "abnamro.com",
    "ing": "ing.com",
    "ing bank": "ing.com",
    "rabobank": "rabobank.nl",
    "apg": "apg.nl",
    "nn group": "nn-group.com",
    "nationale nederlanden": "nn.nl",
    "aegon": "aegon.com",
    "achmea": "achmea.nl",
    "robeco": "robeco.com",
    "van lanschot kempen": "vanlanschotkempen.com",
    "pggm": "pggm.nl",
    "mn": "mn.nl",
    "bng bank": "bngbank.nl",
    "nibc": "nibc.com",
    "triodos bank": "triodos.nl",
    "de volksbank": "devolksbank.nl",
    "bridgefund": "bridgefund.nl",
    "mufg": "mufg.jp",
    "santander": "santander.nl",
    "greenchoice": "greenchoice.nl",
    "euronext": "euronext.com",
    "adyen": "adyen.com",
    "mollie": "mollie.com",
    "kpmg": "kpmg.nl",
    "deloitte": "deloitte.nl",
    "pwc": "pwc.nl",
    "cboe": "cboe.com",
    "zanders": "zanders.eu",
    "ayvens": "ayvens.com",
    "brunel": "brunel.nl",
    "cimsolutions": "cimsolutions.nl",
    "samsung benelux": "samsung.com",
    "handelsbanken": "handelsbanken.nl",
    "accenture": "accenture.com",
    "alvarez & marsal": "alvarezandmarsal.com",
    "mckinsey": "mckinsey.com",
    "capgemini": "capgemini.com",
    "grant thornton": "grantthornton.nl",
    "kpn": "kpn.com",
    "tony's chocolonely": "tonyschocolonely.com",
    "netflix": "netflix.com",
    "picnic": "picnic.app",
    "hema": "hema.nl",
    "atradius": "atradius.com",
    "politie": "politie.nl",
    "magnet.me": "magnet.me",
    "nn": "nn-group.com",
    "alvarez marsal": "alvarezandmarsal.com",
    "tony s chocolonely": "tonyschocolonely.com",
    "deutsche": "db.com"
}

# Namen waar de gok het verkeerde logo oplevert; die gokken we nooit, ook niet via
# .nl. Zet hier een genormaliseerde bedrijfsnaam neer. Staat de naam ook in DOMEIN,
# dan gaat DOMEIN voor.
UITSLUITEN = {
    "jobster",           # gok pakt een onverwante Amerikaanse vacaturesite
    "gemeente utrecht",  # gok pakt een vreemd HD-merk
}

DOMEIN_OK = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9-]{1,63})+$")


# ---------------------------------------------------------------- naam -> domein

def normaliseer(naam):
    n = unicodedata.normalize("NFD", (naam or "").lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    n = re.sub(r"\b(b\.?v\.?|n\.?v\.?|holding|group|nederland|netherlands|amsterdam)\b", " ", n)
    n = re.sub(r"[^a-z0-9. ]", " ", n)
    # Gooi tokens weg die geen letter of cijfer bevatten; een losse punt die na het
    # strippen van "n.v." overblijft mag de woordtelling niet verpesten.
    return " ".join(t for t in n.split() if re.search(r"[a-z0-9]", t))


# DOMEIN-sleutels genormaliseerd inlezen, zodat een sleutel als "nn group" (waar
# normaliseer "group" uit haalt) niet dood is. --misses waarschuwt voor sleutels
# die hierbij veranderen, zodat de bronvorm opgeschoond kan worden.
_DOMEIN = {normaliseer(k): v for k, v in DOMEIN.items()}


def _domein_uit_lijst(n):
    """Domein van de langste DOMEIN-sleutel die op woordgrens een prefix van n is.

    Zo matcht "cboe" op "cboe global markets", maar "ing" niet op
    "ingenieursbureau". Geeft None als geen sleutel past.
    """
    beste_sleutel = None
    beste_domein = None
    for sleutel, domein in _DOMEIN.items():
        if n == sleutel or n.startswith(sleutel + " "):
            if beste_sleutel is None or len(sleutel) > len(beste_sleutel):
                beste_sleutel, beste_domein = sleutel, domein
    return beste_domein


# Staarten die alleen bij het gokken hinderen; bewust niet in normaliseer, want
# de DOMEIN-lijst kent sleutels als "bng bank" en "imc trading".
_STAARTEN = re.compile(r"\b(investment banking|corporate|bank|nederland|nl)\b")


def _strip_staarten(n):
    return re.sub(r"\s+", " ", _STAARTEN.sub(" ", n)).strip()


def domeinen_voor(bedrijf):
    """Geordende lijst kandidaat-domeinen, of een lege lijst.

    De handmatige DOMEIN-lijst gaat voor, op de langste sleutel die op woordgrens
    een prefix van de genormaliseerde naam is. Staat de naam in UITSLUITEN, dan
    gokken we niet. Is de genormaliseerde naam zelf al een domein, dan die. Anders
    gokken we, eerst .com en dan .nl. Een fout logo is erger dan geen logo, dus bij
    een lange of dubbelzinnige naam geven we niets.
    """
    n = normaliseer(bedrijf)
    handmatig = _domein_uit_lijst(n)
    if handmatig:
        return [handmatig]
    if n in UITSLUITEN:
        return []
    if "." in n and " " not in n:
        kandidaten = [n]
    else:
        g = _strip_staarten(n)
        woorden = [w for w in g.split(" ") if w]
        if 1 <= len(woorden) <= 2 and 3 <= len(g) <= 18:
            basis = "".join(woorden)
            kandidaten = [basis + ".com", basis + ".nl"]
        else:
            kandidaten = []
    # Weiger IP-achtige kandidaten: het laatste label van een echt domein is nooit
    # alleen cijfers.
    return [d for d in kandidaten if not d.rsplit(".", 1)[-1].isdigit()]


# ---------------------------------------------------------------- netwerkcheck

def _publiek(host):
    """True als elk IP achter deze hostnaam publiek routeerbaar is.

    Blokkeert 127.0.0.1, 10.x, 192.168.x, 169.254.169.254 en de rest van de
    interne ruimte. De bedrijfsnaam komt uit gescrapete pagina's en is dus
    onvertrouwde invoer; zonder deze check kan die de server iets binnen je
    eigen netwerk laten opvragen.
    """
    try:
        info = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    if not info:
        return False
    for rec in info:
        ip = ipaddress.ip_address(rec[4][0])
        if not ip.is_global or ip.is_multicast:
            return False
    return True


class _Redirect(urllib.request.HTTPRedirectHandler):
    """Herkeurt elke redirect; anders kan een 302 alsnog naar 127.0.0.1 wijzen."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme != "https" or not _publiek(u.hostname or ""):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_Redirect)
_opener.addheaders = [("User-Agent", "vacature-scraper/1.0 (lokaal)")]


# ---------------------------------------------------------------- ophalen

# Twee favicon-diensten. DuckDuckGo geeft een echte 404 bij een onbekend domein.
# Google geeft dan geen 404 maar een generiek wereldbol-icoon; dat herkennen we
# aan zijn hash zodat we het niet als logo bewaren.
_DDG = "https://icons.duckduckgo.com/ip3/%s.ico"
_GOOGLE = "https://www.google.com/s2/favicons?domain=%s&sz=64"

# Domein dat gegarandeerd niet bestaat (.invalid is daarvoor gereserveerd), om
# eenmalig het wereldbol-icoon van Google op te halen.
_NEP_DOMEIN = "geen-logo-bekend.invalid"
_GLOBE_HASH = None
_GLOBE_GEPROBEERD = False


def _haal_url(url, timeout=TIMEOUT):
    """Haal een raster-icoon op van een url; (bytes, extensie) of (None, None).

    Controles: alleen https, publiek routeerbaar IP van de host, redirects herkeurd
    via _opener, alleen rasterformaten, maxgrootte.
    """
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or not _publiek(p.hostname or ""):
        return None, None
    try:
        with _opener.open(url, timeout=timeout) as r:
            ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ct not in TYPES:
                return None, None
            data = r.read(MAX_BYTES + 1)
    except (urllib.error.URLError, socket.timeout, OSError, ValueError):
        return None, None
    if not data or len(data) > MAX_BYTES:
        return None, None
    return data, TYPES[ct]


def _globe_hash():
    """sha256 van het generieke wereldbol-icoon van Google, eenmalig per proces
    opgehaald en onthouden. Zo verwerpen we die terugval zonder een hash hard in de
    code te zetten. None als het ophalen niet lukte."""
    global _GLOBE_HASH, _GLOBE_GEPROBEERD
    if not _GLOBE_GEPROBEERD:
        _GLOBE_GEPROBEERD = True
        data, _ = _haal_url(_GOOGLE % _NEP_DOMEIN)
        if data:
            _GLOBE_HASH = hashlib.sha256(data).hexdigest()
    return _GLOBE_HASH


def _haal(domein):
    """Geeft (bytes, extensie) of (None, None).

    Keten: eerst DuckDuckGo, dan Google (het wereldbol-icoon verwerpen we via de
    hash uit _globe_hash), dan het domein zelf.
    """
    if not DOMEIN_OK.match(domein) or len(domein) > 100:
        return None, None

    data, ext = _haal_url(_DDG % domein)
    if data:
        return data, ext

    data, ext = _haal_url(_GOOGLE % domein)
    if data:
        globe = _globe_hash()
        if globe and hashlib.sha256(data).hexdigest() == globe:
            return None, None
        return data, ext

    # Derde schakel: het domein zelf. Dit is de enige host die uit een gescrapete
    # naam is afgeleid, dus controleer hier expliciet dat hij publiek routeerbaar is
    # voordat we iets opvragen. De redirect-handler in _opener herkeurt bovendien
    # elke doorverwijzing. Korte timeout: een dood domein mag de pagina niet ophouden.
    if _publiek(domein):
        data, ext = _haal_url("https://%s/favicon.ico" % domein, timeout=TIMEOUT_EIGEN)
        if data:
            return data, ext

    return None, None


# ---------------------------------------------------------------- cache

def _sleutel(domein):
    # hash, geen bedrijfsnaam: een naam als "../../config.yaml" kan zo geen
    # pad worden en rare tekens kunnen het bestandssysteem niet raken
    return hashlib.sha256(domein.encode("utf-8")).hexdigest()[:20]


def _zoek_cache(sleutel):
    for ext in (".png", ".ico", ".jpg", ".webp", ".gif"):
        p = os.path.join(CACHE, sleutel + ext)
        if os.path.exists(p):
            return p
    return None


def _mis_vers(sleutel):
    p = os.path.join(CACHE, sleutel + ".mis")
    return os.path.exists(p) and time.time() - os.path.getmtime(p) < MISS_TTL


def _schrijf_mis(sleutel, domein):
    # Onthoud de mislukking met het geprobeerde domein, zodat --misses laat zien
    # welke domeinen je aan DOMEIN kunt toevoegen.
    with open(os.path.join(CACHE, sleutel + ".mis"), "w", encoding="utf-8") as f:
        f.write(domein)


def logo_pad(bedrijf):
    """Pad naar een gecacht logobestand, of None. Haalt op wanneer nodig.

    Probeert de kandidaat-domeinen op volgorde (bij een gok eerst .com, dan .nl).
    Wat lukt komt in de cache onder zijn eigen domein, dus een volgende keer wordt
    er niet opnieuw gegokt.
    """
    kandidaten = domeinen_voor(bedrijf)
    if not kandidaten:
        return None
    os.makedirs(CACHE, exist_ok=True)

    for domein in kandidaten:
        pad = _zoek_cache(_sleutel(domein))
        if pad:
            return pad

    for domein in kandidaten:
        sleutel = _sleutel(domein)
        if _mis_vers(sleutel):
            continue
        data, ext = _haal(domein)
        if data:
            pad = os.path.join(CACHE, sleutel + ext)
            tijdelijk = pad + ".tmp"
            with open(tijdelijk, "wb") as f:
                f.write(data)
            os.replace(tijdelijk, pad)
            return pad
        _schrijf_mis(sleutel, domein)
    return None


# ---------------------------------------------------------------- handler

_EXT_CT = {".png": "image/png", ".ico": "image/x-icon", ".jpg": "image/jpeg",
           ".webp": "image/webp", ".gif": "image/gif"}


def serveer(handler, bedrijf):
    """Schrijft het logo naar de response, of een 404 zodat de front-end
    terugvalt op de monogramtegel."""
    pad = logo_pad(bedrijf) if bedrijf else None
    if not pad:
        handler.send_response(404)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    with open(pad, "rb") as f:
        data = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", _EXT_CT.get(os.path.splitext(pad)[1], "image/png"))
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "public, max-age=604800")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(data)


def _print_misses():
    """Print de domeinen uit de .mis-bestanden, zodat je DOMEIN kunt bijvullen."""
    if not os.path.isdir(CACHE):
        return
    domeinen = set()
    for naam in os.listdir(CACHE):
        if not naam.endswith(".mis"):
            continue
        try:
            with open(os.path.join(CACHE, naam), encoding="utf-8") as f:
                d = f.read().strip()
        except OSError:
            continue
        if d:
            domeinen.add(d)
    for d in sorted(domeinen):
        print(d)


def _waarschuw_sleutels():
    """Waarschuw voor DOMEIN-sleutels die na normalisatie veranderen. Die werken
    wel (ze worden genormaliseerd ingelezen), maar de bronvorm is misleidend, dus
    schrijf ze liever meteen genormaliseerd. Zo valt een dode sleutel als
    'nn group' op."""
    veranderd = sorted((k, normaliseer(k)) for k in DOMEIN if normaliseer(k) != k)
    if veranderd:
        print("Let op, deze DOMEIN-sleutels veranderen na normalisatie:")
        for k, n in veranderd:
            print("  %r -> %r" % (k, n))


if __name__ == "__main__":
    if "--misses" in sys.argv:
        # python webui/logos.py --misses  mislukte domeinen plus dode sleutels
        _print_misses()
        _waarschuw_sleutels()
    else:
        # handmatige test: python webui/logos.py
        for naam in ["Optiver", "ABN AMRO Bank N.V.", "Flow Traders", "Jobster",
                     "Gemeente Utrecht", "127.0.0.1"]:
            print("%-20s %-28s %s" % (naam, domeinen_voor(naam), logo_pad(naam)))
