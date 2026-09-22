"""Gedeelde helpers om opgehaalde HTML naar leesbare platte tekst te maken.

De detailkolom in de webinterface rendert via textContent, dus de bronnen leveren
platte tekst, geen HTML. Twee ingangen: plat() voor een stuk omschrijving-HTML
(Greenhouse content, Recruitee description) en uit_pagina() voor een volledige
detailpagina.
"""
import re
from html import unescape

from bs4 import BeautifulSoup


def _schoon(tekst):
    regels = [r.strip() for r in (tekst or "").splitlines()]
    regels = [r for r in regels if r]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(regels)).strip()


def plat(html):
    """HTML met alleen de omschrijving naar platte tekst.

    Greenhouse levert de content ge-escaped (&lt;p&gt;...), dus eerst unescapen en
    dan de tags eruit. Recruitee levert gewone HTML; unescapen is daar onschadelijk.
    """
    if not html:
        return ""
    soup = BeautifulSoup(unescape(html), "html.parser")
    return _schoon(soup.get_text("\n"))


def uit_pagina(html, selector=None):
    """Platte tekst uit een volledige detailpagina.

    Ruis (script, style, nav, header, footer, form, aside) eruit, en dan liefst de
    main of article, anders de body. Best effort: zonder site-specifieke selectors
    kan er wat randtekst meekomen, maar de omschrijving zit erin.

    Met selector wordt eerst dat element geprobeerd. Nodig voor sites die hun
    omschrijving in een bekend blok zetten en er verder een pagina vol navigatie
    en gerelateerde vacatures omheen bouwen; LinkedIn is daar het voorbeeld van.
    Levert de selector niets op, dan valt hij terug op de gewone route.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    if selector:
        kern = soup.select_one(selector)
        if kern is not None:
            tekst = _schoon(kern.get_text("\n"))
            if tekst:
                return tekst
    for weg in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside"]):
        weg.decompose()
    kern = soup.find("main") or soup.find("article") or soup.body or soup
    return _schoon(kern.get_text("\n"))
