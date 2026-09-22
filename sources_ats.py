"""Directe careers-feeds van specifieke bedrijven.

Ondersteund: Recruitee, Greenhouse, Lever en Workday. Dit zijn stabiele,
publieke JSON-endpoints; geen anti-botproblemen zoals bij de grote borden.

Entries in config.yaml mogen een kale slug zijn ("bedrijfsnaam") of een dict
met nette naam: {slug: werkenbijdeafm, naam: AFM}. Slugs vinden en testen:
zie README.md.

Grote banken en fondsen (ABN, ING, Rabobank, APG) posten vrijwel alles ook
op LinkedIn en Indeed; deze module is vooral nuttig voor organisaties met een
eigen board die niet overal cross-posten.
"""
from datetime import datetime

import requests

from sources_tekst import plat

HEADERS = {"User-Agent": "Mozilla/5.0 (vacaturemonitor; persoonlijk gebruik)"}
TIMEOUT = 20


def _entry(e):
    if isinstance(e, str):
        return e, e
    return e["slug"], e.get("naam") or e["slug"]


def fetch_ats(cfg):
    a = cfg.get("ats") or {}
    jobs = []
    for e in a.get("recruitee") or []:
        jobs += _safe(_recruitee, *_entry(e))
    for e in a.get("greenhouse") or []:
        jobs += _safe(_greenhouse, *_entry(e))
    for e in a.get("lever") or []:
        jobs += _safe(_lever, *_entry(e))
    for wd in a.get("workday") or []:
        jobs += _safe(_workday, wd, wd.get("naam") or wd.get("tenant", "?"))
    return jobs


def _safe(fn, arg, naam):
    label = fn.__name__.lstrip("_")
    try:
        res = fn(arg, naam)
        print(f"[ats] {label} {naam}: {len(res)} vacatures")
        return res
    except Exception as e:
        print(f"[ats] {label} {naam} mislukt: {e}")
        return []


def _recruitee(slug, naam):
    r = requests.get(
        f"https://{slug}.recruitee.com/api/offers/", headers=HEADERS, timeout=TIMEOUT
    )
    r.raise_for_status()
    out = []
    for o in r.json().get("offers", []):
        out.append({
            "bron": "recruitee",
            "bedrijf": naam,
            "functie": o.get("title") or "",
            "locatie": o.get("city") or o.get("location") or "",
            "geplaatst": (o.get("created_at") or "")[:10],
            "salaris": "",
            "url": o.get("careers_url")
            or f"https://{slug}.recruitee.com/o/{o.get('slug', '')}",
            "beschrijving": plat(o.get("description")),
        })
    return out


def _greenhouse(slug, naam):
    r = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "bron": "greenhouse",
            "bedrijf": naam,
            "functie": j.get("title") or "",
            "locatie": (j.get("location") or {}).get("name", ""),
            "geplaatst": (j.get("updated_at") or "")[:10],
            "salaris": "",
            "url": j.get("absolute_url") or "",
            "beschrijving": plat(j.get("content")),
        })
    return out


def _lever(slug, naam):
    r = requests.get(
        f"https://api.lever.co/v0/postings/{slug}?mode=json",
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for j in r.json():
        cat = j.get("categories") or {}
        ts = j.get("createdAt")
        datum = datetime.fromtimestamp(ts / 1000).date().isoformat() if ts else ""
        out.append({
            "bron": "lever",
            "bedrijf": naam,
            "functie": j.get("text") or "",
            "locatie": cat.get("location") or "",
            "geplaatst": datum,
            "salaris": "",
            "url": j.get("hostedUrl") or "",
            "beschrijving": "",
        })
    return out


def _workday(wd, naam):
    """wd is een dict uit config.yaml: {tenant, host, site, naam en zoekterm optioneel}."""
    endpoint = f"https://{wd['host']}/wday/cxs/{wd['tenant']}/{wd['site']}/jobs"
    out, offset, limit = [], 0, 20
    while offset < 100:
        body = {
            "appliedFacets": {},
            "limit": limit,
            "offset": offset,
            "searchText": wd.get("zoekterm", ""),
        }
        r = requests.post(
            endpoint,
            json=body,
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        postings = r.json().get("jobPostings", [])
        for p in postings:
            path = p.get("externalPath", "")
            out.append({
                "bron": "workday",
                "bedrijf": naam,
                "functie": p.get("title") or "",
                "locatie": p.get("locationsText") or "",
                "geplaatst": p.get("postedOn") or "",
                "salaris": "",
                "url": f"https://{wd['host']}/{wd['site']}{path}",
                "beschrijving": "",
            })
        if len(postings) < limit:
            break
        offset += limit
    return out
