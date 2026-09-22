"""Grote vacatureborden (LinkedIn, Indeed, Glassdoor, Google) via python-jobspy.

jobspy gebruikt de publieke gast-endpoints van deze sites; er wordt nergens
ingelogd, dus je eigen accounts lopen geen risico. LinkedIn kan bij veel
requests tijdelijk blokkeren (429); dan minder zoektermen of een dag wachten.
"""
import time


def _clean(value) -> str:
    s = "" if value is None else str(value)
    return "" if s.lower() in ("nat", "none", "nan") else s


def _num(value):
    try:
        f = float(value)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _salaris(row) -> str:
    lo, hi = _num(row.get("min_amount")), _num(row.get("max_amount"))
    if lo is None and hi is None:
        return ""
    cur = _clean(row.get("currency")) or "EUR"
    interval = _clean(row.get("interval"))
    if lo is not None and hi is not None:
        kern = f"{lo:,.0f} tot {hi:,.0f} {cur}"
    else:
        kern = f"{(lo if lo is not None else hi):,.0f} {cur}"
    return f"{kern} ({interval})" if interval else kern


def _normaliseer_locatie(loc: str) -> str:
    """Kale stad naar het volledige zoekformaat 'Stad, Netherlands'.

    De borden verwachten een land erbij. Heeft de gebruiker al een komma getypt
    (bijvoorbeeld 'Rotterdam, South Holland'), dan laten we de invoer staan. Dit
    gebeurt alleen bij het meegeven aan de zoekopdracht; config.yaml blijft zoals
    ingevoerd.
    """
    loc = (loc or "").strip()
    if not loc or "," in loc:
        return loc
    return f"{loc}, Netherlands"


# Backoff voor de borden. Laag houden: dit is een vangnet bij een 429 of een
# tijdelijke fout, geen vrijbrief om harder te vragen. De bestaande pauze tussen
# calls blijft staan en er wordt niets parallel gedaan.
_MAX_POGINGEN = 3        # eerste poging plus hooguit twee retries
_BACKOFF_BASIS_SEC = 5   # oplopende wachttijd: 5s na de eerste fout, 10s na de tweede


def _is_rate_limit(err) -> bool:
    tekst = str(err).lower()
    return "429" in tekst or "too many requests" in tekst or "rate limit" in tekst


def _scrape_ronde(scrape_jobs, sites, term, loc, b):
    """Een borden-ronde (een zoekterm op een locatie) met backoff.

    Probeert hooguit _MAX_POGINGEN keer met oplopende wachttijd bij een 429 of
    tijdelijke fout. Lukt het daarna nog niet, dan wordt de ronde overgeslagen
    (melden en door), net als voorheen. Geeft de DataFrame terug, of None als de
    ronde is opgegeven.
    """
    for poging in range(1, _MAX_POGINGEN + 1):
        try:
            return scrape_jobs(
                site_name=sites,
                search_term=term,
                google_search_term=f"{term} vacature {loc}",
                location=loc,
                results_wanted=int(b.get("resultaten_per_term", 25)),
                hours_old=int(b.get("max_uren_oud", 72)),
                country_indeed=b.get("land_indeed", "netherlands"),
                linkedin_fetch_description=bool(b.get("linkedin_beschrijving", False)),
                description_format="markdown",
                verbose=1,
            )
        except Exception as e:
            if poging == _MAX_POGINGEN:
                print(f"[boards] '{term}' in {loc} mislukt na {poging} pogingen: {e}")
                return None
            wacht = _BACKOFF_BASIS_SEC * poging
            reden = "429 of rate limit" if _is_rate_limit(e) else "tijdelijke fout"
            print(f"[boards] '{term}' in {loc} {reden}, opnieuw over {wacht}s")
            time.sleep(wacht)


def fetch_boards(cfg):
    from jobspy import scrape_jobs

    b = cfg.get("boards") or {}
    sites = b.get("sites") or ["linkedin", "indeed", "glassdoor"]
    terms = cfg.get("zoektermen") or []
    # Zoeklocaties: nieuwe lijst 'locaties', met terugval op het oude enkele veld
    # 'locatie' zodat bestaande configs blijven werken.
    locaties = b.get("locaties") or [b.get("locatie", "Amsterdam, Netherlands")]
    detail = bool(cfg.get("detail_beschrijving"))
    jobs = []

    # Elke zoekterm wordt per locatie apart bevraagd. Dit vermenigvuldigt het
    # aantal requests met het aantal locaties en vergroot dus de kans op een
    # LinkedIn-429; de backoff in _scrape_ronde vangt dat op, maar houd de lijst
    # met zoektermen en locaties klein. Ontdubbelen over locaties gebeurt later in
    # store.py, dus hier geen dedupe.
    for i, term in enumerate(terms, 1):
        for loc in locaties:
            zoekloc = _normaliseer_locatie(loc)
            print(f"[boards] {i}/{len(terms)}: '{term}' in {zoekloc} via {', '.join(sites)}")
            df = _scrape_ronde(scrape_jobs, sites, term, zoekloc, b)
            if df is None:
                continue

            for _, r in df.iterrows():
                job = {
                    "bron": _clean(r.get("site")),
                    "bedrijf": _clean(r.get("company")),
                    "functie": _clean(r.get("title")),
                    "locatie": _clean(r.get("location")),
                    "geplaatst": _clean(r.get("date_posted")),
                    "salaris": _salaris(r),
                    "url": _clean(r.get("job_url")),
                    "beschrijving": _clean(r.get("description")),
                }
                # Zonder omschrijving en met een LinkedIn-vacaturepagina: laat
                # sources_detail hem later ophalen. Dat gebeurt parallel en pas na
                # de poort, dus alleen voor wat overblijft. Jobspy's eigen
                # linkedin_beschrijving doet hetzelfde serieel en vooraf, voor elk
                # resultaat; dat is bij tientallen zoektermen uren werk.
                if detail and not job["beschrijving"] and "linkedin.com/jobs/view" in job["url"]:
                    job["_detail"] = True
                jobs.append(job)
            time.sleep(3)

    return jobs
