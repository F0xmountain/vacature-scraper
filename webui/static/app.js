"use strict";

/* ============================================================
   ADAPTER. Het enige blok dat met de server praat. Vacatures komen
   uit een run: POST /api/run start hem, GET /api/run/status levert
   het resultaat via polling. Er is geen los vacatures-endpoint.
   ============================================================ */

// Een serverrij naar de vorm die de weergave gebruikt. flags is een string van
// de server; hier splitsen we die op komma's naar losse vlaggen.
function naVacature(r) {
  return {
    sleutel: r.sleutel || "",
    familie: r.familie || "overig",
    vaardigheden: r.vaardigheden || [],
    kern: r.kern || 0,
    familieLabel: r.familie_label || "Overig",
    bron: r.bron || "",
    bedrijf: r.bedrijf || "",
    functie: r.functie || "",
    locatie: r.locatie || "",
    geplaatst: r.geplaatst || "",
    salaris: r.salaris || "",
    url: r.url || "",
    beschrijving: r.beschrijving || "",
    vlaggen: (r.flags || "").split(",").map((s) => s.trim()).filter(Boolean),
  };
}

// Laadbalk plus meelopende tijdteller tijdens een run. De server kent geen
// voortgang, dus de balk is onbepaald (heen en weer) en de teller telt op.
let bezigTimer = null;
let bezigStart = 0;
let bezigLabel = "";

function tijd(ms) {
  const s = Math.floor(ms / 1000);
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}

function startLaadbalk(label) {
  bezigLabel = label;
  bezigStart = Date.now();
  $("laadbalk").hidden = false;
  const tik = () => {
    $("stip").className = "stip bezig";
    $("statustekst").textContent = `${bezigLabel}, ${tijd(Date.now() - bezigStart)}`;
  };
  tik();
  clearInterval(bezigTimer);
  bezigTimer = setInterval(tik, 1000);
}

function stopLaadbalk() {
  clearInterval(bezigTimer);
  bezigTimer = null;
  $("laadbalk").hidden = true;
}

async function startRun(onthoud) {
  const modus = onthoud ? "echt" : "dry";
  startLaadbalk(onthoud ? "vastleggen loopt" : "dry-run loopt");
  zetKnoppen(true);
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modus }),
    });
    const data = await res.json();
    if (res.status === 409) {
      // Er loopt al een run (bijvoorbeeld in een ander tabblad): die volgen we.
      pollRun();
      return;
    }
    if (!res.ok || data.fout) {
      stopLaadbalk();
      zetStatus("klaar", "run mislukt: " + (data.fout || res.status));
      zetKnoppen(false);
      return;
    }
    pollRun();
  } catch (e) {
    stopLaadbalk();
    zetStatus("klaar", "run mislukt: " + e);
    zetKnoppen(false);
  }
}

async function pollRun() {
  try {
    const res = await fetch("/api/run/status");
    const st = await res.json();
    if (st.status === "bezig") {
      setTimeout(pollRun, 2500);
      return;
    }
    stopLaadbalk();
    zetKnoppen(false);
    if (st.status === "klaar" && st.resultaat) {
      const r = st.resultaat;
      const soort = r.soort === "echt" ? "vastgelegd" : "dry-run";
      zetStatus("klaar", `${soort}: ${r.rijen.length} in beeld, ${r.over} na filter`);
      vul(r.rijen.map(naVacature));
    } else if (st.status === "fout") {
      zetStatus("klaar", "run mislukt: " + (st.fout || "onbekend"));
    }
  } catch (e) {
    // Tijdelijke pollingfout: blijf proberen, de run loopt door op de server.
    setTimeout(pollRun, 2500);
  }
}

function zetKnoppen(bezig) {
  $("btnToon").disabled = bezig;
  $("btnOnthoud").disabled = bezig;
}

async function laadBijStart() {
  // Loopt er een run? Volg die. Anders: toon de nieuwste van twee bronnen, het
  // resultaat in het geheugen van deze server en de run die op schijf staat.
  // Vergelijken op tijd, want anders bleef een dry-run van 's middags staan
  // nadat de automatische run van 20:00 allang klaar was.
  try {
    const st = await (await fetch("/api/run/status")).json();
    if (st.status === "bezig") {
      startLaadbalk("run loopt");
      zetKnoppen(true);
      pollRun();
      return;
    }
    const geheugen = (st.status === "klaar" && st.resultaat) ? st.resultaat : null;
    const schijf = await haalBewaardeRun();

    if (geheugen && (!schijf || (geheugen.moment || "") >= (schijf.moment || ""))) {
      zetStatus("klaar", `vorige run: ${geheugen.rijen.length} in beeld`);
      vul(geheugen.rijen.map(naVacature));
    } else {
      toonBewaardeRun(schijf);
    }
  } catch (e) {
    zetStatus("klaar", "server niet bereikbaar");
    vul([]);
  }
}

// Datum en tijd van een bewaarde run, kort en leesbaar ("22 sep 08:47").
function momentTekst(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short" }) +
    " " + d.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
}

async function haalBewaardeRun() {
  try {
    const r = await (await fetch("/api/laatste")).json();
    return (r.leeg || r.fout || !r.rijen) ? null : r;
  } catch (e) {
    return null;
  }
}

function toonBewaardeRun(r) {
  if (!r) {
    zetStatus("klaar", "nog geen run; klik Zoek en toon");
    vul([]);
    return;
  }
  const wanneer = momentTekst(r.moment);
  if (!r.rijen.length) {
    zetStatus("klaar", `run van ${wanneer}: geen nieuwe vacatures`);
    vul([]);
    return;
  }
  const venster = r.runs > 1 ? `, ${r.runs} runs` : "";
  zetStatus("klaar", `run van ${wanneer}: ${r.rijen.length} nieuw${venster}`);
  vul(r.rijen.map(naVacature));
}

// Knop in de werkbalk: haal de laatst weggeschreven run op, ook als er nog een
// ouder resultaat in het geheugen van deze server zit.
async function laadBewaardeRun() {
  zetStatus("klaar", "laatste run ophalen...");
  toonBewaardeRun(await haalBewaardeRun());
}

/* ============================================================
   LOGO'S
   De tegel toont het logo via de server-route /logo?bedrijf=...
   Lukt dat niet (geen logo gevonden, of de module staat uit), dan
   valt hij terug op een monogram met de initialen.
   ============================================================ */

function normaliseer(naam) {
  return (naam || "")
    .toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/\b(b\.?v\.?|n\.?v\.?|holding|group|nederland|netherlands|amsterdam)\b/g, "")
    .replace(/[^a-z0-9. ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const TINTEN = ["#0B4F5C", "#2E5E8C", "#4B54A8", "#2F7A5A", "#8C5A2E", "#7A2E6B"];
function tintVoor(naam) {
  let h = 0;
  for (let i = 0; i < naam.length; i++) h = (h * 31 + naam.charCodeAt(i)) >>> 0;
  return TINTEN[h % TINTEN.length];
}
function initialen(naam) {
  const w = normaliseer(naam).split(" ").filter(Boolean);
  if (!w.length) return "?";
  if (w.length === 1) return w[0].slice(0, 2).toUpperCase();
  return (w[0][0] + w[1][0]).toUpperCase();
}

function maakTegel(bedrijf, bronkleur) {
  const tegel = document.createElement("div");
  tegel.className = "tegel";
  tegel.style.setProperty("--bronkleur", bronkleur);

  const monogram = () => {
    tegel.innerHTML = "";
    const s = document.createElement("span");
    s.className = "mono";
    s.textContent = initialen(bedrijf);
    s.style.color = tintVoor(bedrijf);
    tegel.appendChild(s);
  };

  if (!bedrijf) {
    monogram();
    return tegel;
  }

  const img = new Image();
  img.alt = "";
  img.loading = "lazy";
  img.onerror = monogram;
  img.src = "/logo?bedrijf=" + encodeURIComponent(bedrijf);
  tegel.appendChild(img);
  monogramAlsPlaceholder(tegel, bedrijf, img);
  return tegel;
}

function monogramAlsPlaceholder(tegel, bedrijf, img) {
  // toon alvast de initialen zodat er niets springt terwijl het logo laadt
  const s = document.createElement("span");
  s.className = "mono";
  s.textContent = initialen(bedrijf);
  s.style.color = tintVoor(bedrijf);
  s.style.position = "absolute";
  tegel.insertBefore(s, img);
  img.addEventListener("load", () => s.remove());
  img.addEventListener("error", () => { /* monogram blijft staan */ });
}

/* ============================================================
   BRONNEN EN WEERGAVE
   ============================================================ */

const BRON = {
  linkedin: { label: "LinkedIn", kleur: "#2E5E8C" },
  indeed: { label: "Indeed", kleur: "#4B54A8" },
  greenhouse: { label: "Greenhouse", kleur: "#2F7A5A" },
  recruitee: { label: "Recruitee", kleur: "#8C5A2E" },
  lever: { label: "Lever", kleur: "#3E7C8C" },
  workday: { label: "Workday", kleur: "#6B7A2E" },
  magnetme: { label: "Magnet.me", kleur: "#7A2E6B" },
  "banken.nl": { label: "Banken.nl", kleur: "#8C3A4A" },
  werkenbijdnb: { label: "DNB", kleur: "#0B4F5C" },
};

// Samengestelde bronwaarden ("linkedin, magnetme" na dedupe) tonen we onder het
// eerste deel voor de komma; de volledige waarde komt als vol in de tooltip.
function bronInfo(b) {
  const vol = b || "";
  const eerste = vol.split(",")[0].trim();
  const basis = BRON[eerste] || { label: eerste || "onbekend", kleur: "#5F6975" };
  return { label: basis.label, kleur: basis.kleur, vol };
}

let alles = [];
let actief = null;
// sleutel -> "ja" | "nee". De dedupe-sleutel komt per rij van de server mee.
let oordelen = {};
// De werkbalk is de enige plek waar filters staan; de dropdowns zijn de bron van
// waarheid. Leeg betekent telkens: niet filteren op dit veld.
const filters = {
  familie: "",
  bron: "",
  locatie: "",
  vaardigheid: "",
  oordeel: "alles",
  vlag: "",        // "" | "met" | "zonder"
  sorteer: "nieuw", // "nieuw" | "oud" | "bron"
};

const $ = (id) => document.getElementById(id);

function zetStatus(soort, tekst) {
  $("stip").className = "stip " + soort;
  $("statustekst").textContent = tekst;
}

function zichtbaar() {
  const q = $("zoek").value.trim().toLowerCase();
  const rijen = alles.filter((v) => {
    if (filters.bron && v.bron !== filters.bron) return false;
    if (filters.familie && v.familie !== filters.familie) return false;
    if (filters.locatie && plaatsSleutel(v.locatie) !== filters.locatie) return false;
    if (filters.vaardigheid === "_kern") {
      if ((v.kern || 0) < 2) return false;            // twee of meer signalen
    } else if (filters.vaardigheid && !(v.vaardigheden || []).includes(filters.vaardigheid)) {
      return false;
    }
    const vlaggen = (v.vlaggen || []).length;
    if (filters.vlag === "met" && !vlaggen) return false;
    if (filters.vlag === "zonder" && vlaggen) return false;
    const o = oordelen[v.sleutel] || "";
    if (filters.oordeel === "onbeoordeeld" && o) return false;
    if (filters.oordeel === "ja" && o !== "ja") return false;
    if (filters.oordeel === "nee" && o !== "nee") return false;
    if (q && !`${v.functie} ${v.bedrijf} ${v.locatie}`.toLowerCase().includes(q)) return false;
    return true;
  });
  return sorteerLijst(rijen);
}

// geplaatst komt per bron in een andere vorm binnen: de borden, Recruitee,
// Greenhouse en Lever leveren een ISO-datum, Workday levert losse tekst
// ("Posted 3 Days Ago"), en magnet.me en de werkenbij-sites leveren niets.
// Hier wordt daar een getal van gemaakt om op te sorteren. Wat de rij toont
// blijft staan zoals de bron het zegt; dit raakt alleen de volgorde.
// null betekent: deze bron geeft geen datum, niet dat de vacature oud is.
function sorteerTijd(v) {
  const ruw = String(v.geplaatst || "").trim();
  if (!ruw) return null;
  const iso = Date.parse(ruw);
  if (!isNaN(iso)) return iso;
  const tekst = ruw.toLowerCase();
  if (/\b(today|vandaag)\b/.test(tekst)) return Date.now();
  if (/\b(yesterday|gisteren)\b/.test(tekst)) return Date.now() - 864e5;
  const dagen = tekst.match(/(\d+)\+?\s*(day|dag)/);
  if (dagen) return Date.now() - Number(dagen[1]) * 864e5;
  const maanden = tekst.match(/(\d+)\+?\s*(month|maand)/);
  if (maanden) return Date.now() - Number(maanden[1]) * 30 * 864e5;
  return null;
}

// Vacatures zonder datum zakken naar onderen, in beide richtingen. Ze droppen
// niet: geen datum is onbekend, niet oud, en dat oordeel is aan de gebruiker.
// Binnen gelijke datums blijft de oorspronkelijke volgorde staan.
function sorteerLijst(rijen) {
  if (filters.sorteer === "bron") return rijen;
  const richting = filters.sorteer === "oud" ? 1 : -1;
  return rijen
    .map((v, i) => ({ v, i, t: sorteerTijd(v) }))
    .sort((a, b) => {
      if (a.t === null && b.t === null) return a.i - b.i;
      if (a.t === null) return 1;
      if (b.t === null) return -1;
      if (a.t !== b.t) return (a.t - b.t) * richting;
      return a.i - b.i;
    })
    .map((x) => x.v);
}

function tekenVangst() {
  const per = {};
  alles.forEach((v) => (per[v.bron] = (per[v.bron] || 0) + 1));

  const balken = $("balken");
  balken.innerHTML = "";
  const totaal = alles.length || 1;
  Object.entries(per).sort((a, b) => b[1] - a[1]).forEach(([bron, n]) => {
    const info = bronInfo(bron);
    const pct = (n / totaal) * 100;
    const b = document.createElement("button");
    b.className = "segment";
    b.style.flex = String(n);
    b.style.background = info.kleur;
    b.setAttribute("aria-pressed", String(!filters.bron || filters.bron === bron));
    b.title = `${info.vol}: ${n}`;
    const s = document.createElement("span");
    if (pct > 8) s.textContent = `${info.label} ${n}`;
    else if (pct >= 3) s.textContent = String(n);
    // onder de 3 procent: geen tekst in het segment, alleen de tooltip
    b.appendChild(s);
    b.onclick = () => {
      // Klikken op de strip zet de brondropdown; nog eens klikken zet hem terug
      // op alle bronnen. Een bediening, twee ingangen, geen tweede filterstaat.
      filters.bron = filters.bron === bron ? "" : bron;
      $("filterBron").value = filters.bron;
      teken();
    };
    balken.appendChild(b);
  });

  $("legenda").innerHTML = Object.entries(per).sort((a, b) => b[1] - a[1])
    .map(([bron, n]) => `<span><i style="background:${bronInfo(bron).kleur}"></i>${esc(bronInfo(bron).label)} ${n}</span>`)
    .join("");

  $("totaal").textContent = alles.length;
  $("reset").hidden = !filters.bron;
}


/* ============================================================
   KEUZELIJSTEN. De opties komen uit de geladen vacatures, niet uit een
   vaste lijst: zo staan er nooit keuzes in die niets opleveren, en
   verschijnen nieuwe bronnen of functiefamilies vanzelf. De aantallen
   staan erbij zodat je ziet wat een keuze je gaat kosten.
   ============================================================ */

function vulKeuze(id, paren, alleLabel) {
  const el = $(id);
  const huidig = el.value;
  el.innerHTML = "";
  const alles_ = document.createElement("option");
  alles_.value = "";
  alles_.textContent = alleLabel;
  el.appendChild(alles_);
  paren.forEach(([waarde, label, aantal]) => {
    const o = document.createElement("option");
    o.value = waarde;
    o.textContent = `${label} (${aantal})`;
    el.appendChild(o);
  });
  // Stond er een keuze die nu niet meer bestaat, val dan terug op alles.
  el.value = Array.from(el.options).some((o) => o.value === huidig) ? huidig : "";
}

function tel(sleutelVan, labelVan) {
  const per = new Map();
  alles.forEach((v) => {
    const k = sleutelVan(v);
    if (!k) return;
    const r = per.get(k) || { label: labelVan(v), n: 0 };
    r.n += 1;
    per.set(k, r);
  });
  return Array.from(per, ([k, r]) => [k, r.label, r.n]).sort((a, b) => b[2] - a[2]);
}

function vulKeuzelijsten() {
  vulKeuze("filterFamilie", tel((v) => v.familie, (v) => v.familieLabel), "alle functies");
  vulKeuze("filterBron", tel((v) => v.bron, (v) => bronInfo(v.bron).label), "alle bronnen");
  vulKeuze("filterLocatie", tel((v) => plaatsSleutel(v.locatie), (v) => plaatsLabel(v.locatie)), "alle locaties");

  // Vaardigheden: een vacature kan er meerdere hebben, dus niet via tel().
  const perV = new Map();
  alles.forEach((v) => (v.vaardigheden || []).forEach((n) => perV.set(n, (perV.get(n) || 0) + 1)));
  const metKern = alles.filter((v) => (v.kern || 0) >= 2).length;
  const opties = Array.from(perV, ([n, aantal]) => [n, n, aantal]).sort((a, b) => b[2] - a[2]);
  if (metKern) opties.unshift(["_kern", "twee of meer datasignalen", metKern]);
  vulKeuze("filterVaardigheid", opties, "alle vaardigheden");
  filters.vaardigheid = $("filterVaardigheid").value;
  // De filterstaat volgt de dropdowns, voor het geval een keuze is weggevallen.
  filters.familie = $("filterFamilie").value;
  filters.bron = $("filterBron").value;
  filters.locatie = $("filterLocatie").value;
}

// De wis-knop verschijnt alleen als er echt iets te wissen valt.
function markeerFilters() {
  const actiefFilter = !!(filters.familie || filters.bron || filters.locatie ||
    filters.vaardigheid || filters.vlag || filters.oordeel !== "alles" ||
    $("zoek").value.trim());
  $("btnWisFilters").hidden = !actiefFilter;
}

function maakRij(v, i) {
  const info = bronInfo(v.bron);
  const rij = document.createElement("button");
  rij.className = "rij";
  rij.type = "button";
  rij.setAttribute("role", "option");
  rij.setAttribute("aria-selected", String(actief === v));
  rij.dataset.index = i;

  rij.appendChild(maakTegel(v.bedrijf, info.kleur));

  const midden = document.createElement("div");
  midden.style.minWidth = "0";
  midden.innerHTML = `
    <h3>${esc(v.functie)}</h3>
    <div><span class="bedrijf">${esc(v.bedrijf)}</span> <span class="plaats">${esc(kortePlaats(v.locatie))}</span></div>
    <div class="meta">
      <span class="tag bron" style="background:${info.kleur}">${esc(info.label)}</span>
      ${v.salaris ? `<span class="tag salaris">${esc(v.salaris)}</span>` : ""}
      ${(v.kern || 0) >= 2 ? `<span class="tag kern" title="${esc((v.vaardigheden || []).join(", "))}">${v.kern} datasignalen</span>` : ""}
      ${(v.vlaggen || []).map((f) => `<span class="tag vlag">${esc(f)}</span>`).join("")}
    </div>`;
  rij.appendChild(midden);

  const rechts = document.createElement("div");
  rechts.className = "rechts";
  const o = oordelen[v.sleutel] || "";
  rechts.innerHTML = `<span>${v.geplaatst ? esc(datum(v.geplaatst)) : "geen datum"}</span>` +
    (o === "ja" ? `<span class="merk-ja">shortlist</span>` : "");
  rij.appendChild(rechts);

  // ja krijgt een duidelijke markering (groene rand plus label), nee wordt gedimd.
  if (o === "ja") rij.classList.add("is-ja");
  else if (o === "nee") rij.classList.add("is-nee");

  rij.onclick = () => { actief = v; teken(); tekenDetail(); };
  return rij;
}

function teken() {
  const lijst = $("lijst");
  const rijen = zichtbaar();
  lijst.innerHTML = "";
  if (!rijen.length) {
    lijst.innerHTML = `<div class="leeg"><span class="eyebrow">Niets in beeld</span>
      Geen vacature past bij deze filters, of er is nog geen run gedraaid. Klik Zoek en toon, of maak het zoekveld leeg.</div>`;
  } else {
    rijen.forEach((v, i) => lijst.appendChild(maakRij(v, i)));
  }
  $("telling").textContent = `${rijen.length} van ${alles.length} getoond`;
  markeerFilters();
  if (weergave === "analyse") tekenAnalyse();
  tekenVangst();
}


/* ============================================================
   ANALYSE. Rekent op de vacatures die nu zichtbaar zijn, dus de
   filters werken door: zet je de functie op Analist, dan gaat de
   vaardighedengrafiek daarover.

   Alle grafieken zijn magnitudevergelijkingen met een reeks, dus een
   staaf per categorie in een kleur. Donkerder-is-groter zou de lengte
   dubbel coderen en het enige vrije kanaal verbranden aan iets dat de
   staaf al laat zien. Kleur draagt hier dus bewust geen informatie;
   het label doet dat.
   ============================================================ */

let weergave = "lijst";

function kpiTegel(waarde, label, toelichting) {
  return `<div class="kpi" ${toelichting ? `title="${esc(toelichting)}"` : ""}>
    <b>${waarde}</b><span>${esc(label)}</span></div>`;
}

// paren: [sleutel, label, aantal]. klik zet optioneel een filter.
function staafGrafiek(titel, paren, opties = {}) {
  if (!paren.length) return "";
  const top = Math.max(...paren.map((p) => p[2]));
  const rijen = paren.slice(0, opties.limiet || 12).map(([sleutel, label, n]) => {
    const pct = (n / top) * 100;
    return `<button class="staaf-rij" data-filter="${esc(opties.filter || "")}" data-waarde="${esc(sleutel)}"
              title="${esc(label)}: ${n}">
      <span class="staaf-label">${esc(label)}</span>
      <span class="staaf-baan"><span class="staaf" style="width:${pct}%"></span></span>
      <span class="staaf-waarde">${n}</span>
    </button>`;
  }).join("");
  const rest = paren.length > (opties.limiet || 12)
    ? `<p class="staaf-rest">en nog ${paren.length - (opties.limiet || 12)} andere</p>` : "";
  return `<section class="grafiek"><span class="eyebrow">${esc(titel)}</span>
    <div class="staven">${rijen}</div>${rest}</section>`;
}

function tekenAnalyse() {
  const rijen = zichtbaar();
  const n = rijen.length;
  if (!n) {
    $("kpis").innerHTML = "";
    $("grafieken").innerHTML = `<div class="leeg"><span class="eyebrow">Niets te analyseren</span>
      Geen vacature past bij deze filters.</div>`;
    $("analyseVoet").textContent = "";
    return;
  }

  const kern2 = rijen.filter((v) => (v.kern || 0) >= 2).length;
  const onbeoordeeld = rijen.filter((v) => !oordelen[v.sleutel]).length;
  const metTekst = rijen.filter((v) => v.beschrijving).length;
  $("kpis").innerHTML =
    kpiTegel(n, "in beeld") +
    kpiTegel(kern2, "met 2+ datasignalen", "Vacatures die twee of meer termen noemen die op echt data-werk wijzen") +
    kpiTegel(onbeoordeeld, "nog te beoordelen") +
    kpiTegel(new Set(rijen.map((v) => v.bedrijf).filter(Boolean)).size, "werkgevers");

  // Vaardigheden: meerdere per vacature, dus apart tellen.
  const perV = new Map();
  rijen.forEach((v) => (v.vaardigheden || []).forEach((k) => perV.set(k, (perV.get(k) || 0) + 1)));
  const vaardig = Array.from(perV, ([k, a]) => [k, k, a]).sort((a, b) => b[2] - a[2]);

  const telOp = (sleutelVan, labelVan) => {
    const m = new Map();
    rijen.forEach((v) => {
      const k = sleutelVan(v);
      if (!k) return;
      const r = m.get(k) || { label: labelVan(v), n: 0 };
      r.n += 1; m.set(k, r);
    });
    return Array.from(m, ([k, r]) => [k, r.label, r.n]).sort((a, b) => b[2] - a[2]);
  };

  $("grafieken").innerHTML =
    staafGrafiek("Functiefamilie", telOp((v) => v.familie, (v) => v.familieLabel), { filter: "familie" }) +
    staafGrafiek("Gevraagde vaardigheden", vaardig, { filter: "vaardigheid", limiet: 14 }) +
    staafGrafiek("Werkgevers die het meest werven", telOp((v) => v.bedrijf, (v) => v.bedrijf), { limiet: 12 }) +
    staafGrafiek("Locatie", telOp((v) => plaatsSleutel(v.locatie) || "_onbekend", (v) => plaatsLabel(v.locatie) || "locatie onbekend"), { filter: "locatie" }) +
    staafGrafiek("Bron", telOp((v) => v.bron, (v) => bronInfo(v.bron).label), { filter: "bron" });

  // Klikken op een staaf zet het bijbehorende filter.
  $("grafieken").querySelectorAll(".staaf-rij").forEach((b) => {
    const sleutel = b.dataset.filter;
    if (!sleutel) { b.classList.add("niet-klikbaar"); return; }
    b.onclick = () => {
      filters[sleutel] = filters[sleutel] === b.dataset.waarde ? "" : b.dataset.waarde;
      const veld = { familie: "filterFamilie", bron: "filterBron", locatie: "filterLocatie",
                     vaardigheid: "filterVaardigheid" }[sleutel];
      if (veld) $(veld).value = filters[sleutel];
      teken();
    };
  });

  $("analyseVoet").textContent =
    `Gerekend over ${n} vacatures, waarvan ${metTekst} met omschrijving. ` +
    `Vaardigheden komen uit de omschrijving: een vermelding is geen eis, dus lees het als een aanwijzing en niet als een cijfer.`;
}

function kiesWeergave(w) {
  weergave = w;
  $("weergaveLijst").hidden = w !== "lijst";
  $("weergaveAnalyse").hidden = w !== "analyse";
  document.querySelectorAll(".weergavekeuze .segknop").forEach((b) => {
    const aan = b.dataset.w === w;
    b.classList.toggle("aan", aan);
    b.setAttribute("aria-pressed", String(aan));
  });
  teken();
}

function tekenDetail() {
  const d = $("detail");
  if (!actief) {
    d.innerHTML = `<div class="leeg"><span class="eyebrow">Detail</span>
      Kies een vacature om de omschrijving hier te lezen.</div>`;
    return;
  }
  const v = actief, info = bronInfo(v.bron);
  d.innerHTML = "";

  const kop = document.createElement("div");
  kop.className = "kop";
  kop.appendChild(maakTegel(v.bedrijf, info.kleur));
  const tekst = document.createElement("div");
  tekst.innerHTML = `<h2>${esc(v.functie)}</h2>
    <div class="onder">${esc(v.bedrijf)} &middot; ${esc(v.locatie)}</div>`;
  kop.appendChild(tekst);
  d.appendChild(kop);

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.innerHTML = `
    <span class="tag bron" style="background:${info.kleur}">${esc(info.label)}</span>
    ${v.geplaatst ? `<span class="tag">${esc(datum(v.geplaatst))}</span>` : `<span class="tag">bron geeft geen datum</span>`}
    ${v.salaris ? `<span class="tag salaris">${esc(v.salaris)}</span>` : ""}
    ${(v.vlaggen || []).map((f) => `<span class="tag vlag">${esc(f)}</span>`).join("")}`;
  d.appendChild(meta);

  // Ja/nee met de muis; spiegelt de pijltjestoetsen en springt daarna door.
  const huidig = oordelen[v.sleutel] || "";
  const oord = document.createElement("div");
  oord.className = "oordeel-acties";
  oord.innerHTML =
    `<button class="knop oordeel-ja${huidig === "ja" ? " aan" : ""}" id="oJa">Ja, shortlist</button>
     <button class="knop oordeel-nee${huidig === "nee" ? " aan" : ""}" id="oNee">Nee</button>` +
    (huidig ? `<button class="knop-wis" id="oWis">maak onbeoordeeld</button>` : "");
  d.appendChild(oord);
  oord.querySelector("#oJa").onclick = () => beoordeel(v, "ja");
  oord.querySelector("#oNee").onclick = () => beoordeel(v, "nee");
  if (huidig) oord.querySelector("#oWis").onclick = () => beoordeel(v, "onbeoordeeld");

  const acties = document.createElement("div");
  acties.className = "acties";
  const veiligeUrl = /^https?:\/\//i.test(v.url) ? v.url : "";
  acties.innerHTML = `<a class="knop primair" href="${esc(veiligeUrl)}" target="_blank" rel="noopener">Open vacature</a>
    <button class="knop" id="kopieer">Kopieer link</button>`;
  d.appendChild(acties);
  acties.querySelector("#kopieer").onclick = (e) => {
    navigator.clipboard.writeText(veiligeUrl);
    e.target.textContent = "Gekopieerd";
    setTimeout(() => { e.target.textContent = "Kopieer link"; }, 1600);
  };

  // Gevraagde vaardigheden uit de omschrijving. Bewust boven de tekst: het is
  // het snelste antwoord op "heeft deze rol een echte analytische kern". Geen
  // oordeel; een vermelding in een bedrijfsprofiel telt hier net zo zwaar als
  // een harde eis, en dat verschil is niet machinaal vast te stellen.
  if ((v.vaardigheden || []).length) {
    const vk = document.createElement("div");
    vk.className = "vaardigheden";
    const kop = (v.kern || 0) >= 2
      ? `Genoemde vaardigheden &middot; <b>${v.kern} datasignalen</b>`
      : "Genoemde vaardigheden";
    vk.innerHTML = `<span class="eyebrow">${kop}</span><div class="v-tags">` +
      v.vaardigheden.map((n) => `<span class="tag v">${esc(n)}</span>`).join("") +
      `</div>`;
    d.appendChild(vk);
  }

  const b = document.createElement("div");
  b.className = "beschrijving";
  b.textContent = v.beschrijving ||
    `${info.label || "De bron"} levert geen omschrijving in de lijstweergave. Open de vacature voor de volledige tekst.`;
  d.appendChild(b);
}

function vul(data) {
  alles = data;
  actief = null;
  // Werkstand: staan er al oordelen op de geladen set, start dan op 'onbeoordeeld',
  // want dat is wat er nog te doen valt. Anders gewoon alles tonen.
  filters.oordeel = alles.some((v) => oordelen[v.sleutel]) ? "onbeoordeeld" : "alles";
  $("filterOordeel").value = filters.oordeel;
  vulKeuzelijsten();
  teken();
  tekenDetail();
}

/* hulpjes */
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function kortePlaats(l) { return String(l || "").split(",")[0].trim(); }
// Groeperen en filteren op plaats moet hoofdletterongevoelig: de borden leveren
// "Amsterdam, NH" en de werkenbij-bronnen een kale "amsterdam". Zonder dit staan
// dezelfde stad twee keer in de lijst en mist het filter de helft.
function plaatsSleutel(l) { return kortePlaats(l).toLowerCase(); }
function plaatsLabel(l) {
  const p = kortePlaats(l);
  return p ? p.charAt(0).toUpperCase() + p.slice(1) : "";
}
function datum(d) {
  const dt = new Date(d);
  if (isNaN(dt)) return d;
  const opties = { day: "numeric", month: "short" };
  // Jaartal erbij zodra de vacature niet uit het lopende jaar komt; bij sorteren
  // op recentheid is "18 sep" anders niet van vorig jaar te onderscheiden.
  if (dt.getFullYear() !== new Date().getFullYear()) opties.year = "numeric";
  return dt.toLocaleDateString("nl-NL", opties);
}

/* ============================================================
   OORDEEL. Handmatige ja/nee-beoordeling. De sleutel is de dedupe-sleutel
   die per rij van de server meekomt, zodat een oordeel over runs heen blijft
   kloppen. De enige schrijfroute is POST /api/oordeel; de tool wijst niets af.
   ============================================================ */

async function laadOordelen() {
  try {
    const res = await fetch("/api/oordelen");
    const kaart = await res.json();
    oordelen = {};
    Object.entries(kaart || {}).forEach(([sleutel, waarde]) => {
      // De server bewaart {oordeel, tijd}; de weergave heeft alleen het oordeel nodig.
      const o = waarde && waarde.oordeel ? waarde.oordeel : waarde;
      if (o === "ja" || o === "nee") oordelen[sleutel] = o;
    });
  } catch (e) {
    // Zonder oordelen werkt de rest gewoon; alles staat dan op onbeoordeeld.
    oordelen = {};
  }
}

async function stuurOordeel(sleutel, keuze) {
  try {
    const res = await fetch("/api/oordeel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sleutel, oordeel: keuze }),
    });
    if (!res.ok) throw new Error("status " + res.status);
  } catch (e) {
    // Localhost; een mislukking is zeldzaam. De lokale staat blijft staan zodat
    // het doorlopen niet stokt; alleen een korte melding in de statusregel.
    zetStatus("klaar", "oordeel niet opgeslagen: " + e);
  }
}

// Beoordeel v en spring daarna door naar de volgende onbeoordeelde vacature.
// Wissen ("onbeoordeeld") is een correctie en blijft staan.
function beoordeel(v, keuze) {
  if (!v) return;
  const oudZicht = zichtbaar();
  const i = oudZicht.indexOf(v);

  if (keuze === "onbeoordeeld") delete oordelen[v.sleutel];
  else oordelen[v.sleutel] = keuze;
  stuurOordeel(v.sleutel, keuze);

  if (keuze !== "onbeoordeeld") {
    actief = volgendeOnbeoordeeld(oudZicht, i);
  }
  teken();
  tekenDetail();
  document.querySelector('.rij[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}

// De volgende nog niet beoordeelde vacature, vanaf net na de huidige positie en
// rondwrappend. Is er geen onbeoordeelde meer in beeld, dan valt hij terug op wat
// er na de huidige positie nog staat, of op niets als de lijst leeg raakt.
function volgendeOnbeoordeeld(oudZicht, i) {
  const n = oudZicht.length;
  if (!n) return null;
  const start = i < 0 ? 0 : i;
  for (let d = 1; d <= n; d++) {
    const kandidaat = oudZicht[(start + d) % n];
    if (!oordelen[kandidaat.sleutel]) return kandidaat;
  }
  const nu = zichtbaar();
  if (!nu.length) return null;
  return nu[Math.min(start, nu.length - 1)];
}

// De ja-lijst als csv, in de browser opgebouwd uit wat al geladen is.
function exporteerJa() {
  const kolommen = ["functie", "bedrijf", "locatie", "bron", "geplaatst", "url"];
  const rijen = alles.filter((v) => oordelen[v.sleutel] === "ja");
  const regels = [kolommen.join(",")].concat(
    rijen.map((v) => kolommen.map((k) => csvVeld(v[k])).join(","))
  );
  const blob = new Blob([regels.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "shortlist-ja.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function csvVeld(waarde) {
  const s = String(waarde ?? "");
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

// Alle oordelen (ja en nee) van de geladen vacatures terug op onbeoordeeld. Met
// bevestiging, want het is niet terug te draaien. Persisteert in een verzoek via
// de enige schrijfroute (oordeel.py); de lokale staat gaat meteen mee.
async function wisAlleOordelen() {
  const sleutels = alles.filter((v) => oordelen[v.sleutel]).map((v) => v.sleutel);
  if (!sleutels.length) {
    zetStatus("klaar", "geen oordelen om te wissen");
    return;
  }
  if (!confirm(`Alle ${sleutels.length} oordelen wissen? Dit zet ja en nee terug op onbeoordeeld.`)) {
    return;
  }
  sleutels.forEach((s) => delete oordelen[s]);
  try {
    const res = await fetch("/api/oordelen/wis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sleutels }),
    });
    if (!res.ok) throw new Error("status " + res.status);
  } catch (e) {
    zetStatus("klaar", "wissen niet opgeslagen: " + e);
  }
  // Zonder oordelen is 'onbeoordeeld' hetzelfde als 'alles'; zet 'm op alles zodat
  // een ja- of nee-filter niet op een lege lijst blijft staan.
  filters.oordeel = "alles";
  $("filterOordeel").value = "alles";
  teken();
  tekenDetail();
}

/* ============================================================
   ZOEKPROFIEL-PANEEL
   Bewerkt config.yaml via GET/POST /api/profiel. De server schrijft
   comment-behoudend via config_io; hier staat geen tweede schrijfroute.
   ============================================================ */

const LIJSTEN = [
  "zoektermen",
  "boards_locaties",
  "locaties_toegestaan",
  "titel_uitsluiten",
  "flag_termen",
];

function lijstRij(waarde) {
  const rij = document.createElement("div");
  rij.className = "lijst-rij";
  const input = document.createElement("input");
  input.type = "text";
  input.value = waarde || "";
  const weg = document.createElement("button");
  weg.type = "button";
  weg.className = "verwijder";
  weg.textContent = "×";
  weg.title = "Verwijderen";
  weg.addEventListener("click", () => rij.remove());
  rij.append(input, weg);
  return rij;
}

function vulLijst(sleutel, items) {
  const houder = $("lijst-" + sleutel);
  houder.innerHTML = "";
  (items || []).forEach((w) => houder.append(lijstRij(w)));
}

function leesLijst(sleutel) {
  return Array.from($("lijst-" + sleutel).querySelectorAll("input"))
    .map((i) => i.value.trim())
    .filter((v) => v.length > 0);
}

function zetOpslaanStatus(tekst, soort) {
  const el = $("opslaan-status");
  el.textContent = tekst;
  el.className = "status" + (soort ? " " + soort : "");
}

async function laadProfiel() {
  try {
    const res = await fetch("/api/profiel");
    const p = await res.json();
    if (p.fout) {
      zetOpslaanStatus("Laden mislukt: " + p.fout, "fout");
      return;
    }
    LIJSTEN.forEach((s) => vulLijst(s, p[s]));
    $("bron-boards_actief").checked = p.boards_actief;
    $("bron-ats_actief").checked = p.ats_actief;
    $("bron-magnetme_actief").checked = p.magnetme_actief;
    $("bron-werkenbij_actief").checked = p.werkenbij_actief;
    const sites = p.boards_sites || [];
    ["linkedin", "indeed", "glassdoor"].forEach((s) => {
      $("site-" + s).checked = sites.includes(s);
    });
    $("resultaten_per_term").value = p.resultaten_per_term;
    $("max_uren_oud").value = p.max_uren_oud;
  } catch (e) {
    zetOpslaanStatus("Laden mislukt: " + e, "fout");
  }
}

function leesProfiel() {
  const sites = ["linkedin", "indeed", "glassdoor"].filter((s) => $("site-" + s).checked);
  const profiel = {
    boards_actief: $("bron-boards_actief").checked,
    ats_actief: $("bron-ats_actief").checked,
    magnetme_actief: $("bron-magnetme_actief").checked,
    werkenbij_actief: $("bron-werkenbij_actief").checked,
    boards_sites: sites,
    resultaten_per_term: Number($("resultaten_per_term").value) || 25,
    max_uren_oud: Number($("max_uren_oud").value) || 72,
  };
  LIJSTEN.forEach((s) => (profiel[s] = leesLijst(s)));
  return profiel;
}

async function opslaan() {
  zetOpslaanStatus("Bezig met opslaan...", "");
  try {
    const res = await fetch("/api/profiel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(leesProfiel()),
    });
    const data = await res.json();
    if (!res.ok || data.fout) {
      zetOpslaanStatus("Opslaan mislukt: " + (data.fout || res.status), "fout");
    } else {
      zetOpslaanStatus("Opgeslagen in config.yaml.", "ok");
    }
  } catch (e) {
    zetOpslaanStatus("Opslaan mislukt: " + e, "fout");
  }
}

/* ============================================================
   DAGELIJKSE RUN (launchd). Bediening via GET/POST /api/rooster.
   De server schrijft via rooster.py; hier staat geen tweede route.
   Uitzetten is stil gevaarlijk (er gebeurt dan wekenlang niets zonder
   melding), dus de statusregel zegt altijd voluit wat de stand is.
   ============================================================ */

function tijdRij(uur, minuut) {
  const rij = document.createElement("span");
  rij.className = "tijd-rij";
  const u = document.createElement("input");
  u.type = "number"; u.min = 0; u.max = 23; u.step = 1;
  u.value = String(uur).padStart(2, "0"); u.setAttribute("aria-label", "uur");
  const m = document.createElement("input");
  m.type = "number"; m.min = 0; m.max = 59; m.step = 5;
  m.value = String(minuut).padStart(2, "0"); m.setAttribute("aria-label", "minuut");
  const weg = document.createElement("button");
  weg.type = "button"; weg.className = "verwijder"; weg.textContent = "\u00d7";
  weg.title = "Dit tijdstip verwijderen";
  // Het laatste tijdstip mag niet weg; zonder rooster draait er nooit meer iets
  // en dat zou je pas weken later merken.
  weg.addEventListener("click", () => {
    if ($("rooster-tijden").querySelectorAll(".tijd-rij").length > 1) rij.remove();
  });
  rij.append(u, document.createTextNode(":"), m, weg);
  return rij;
}

function leesTijden() {
  return Array.from($("rooster-tijden").querySelectorAll(".tijd-rij")).map((rij) => {
    const [u, m] = rij.querySelectorAll("input");
    return [Number(u.value) || 0, Number(m.value) || 0];
  });
}

function toonRooster(r) {
  const veld = $("rooster-veld");
  const houder = $("rooster-tijden");
  if (!r || r.fout || !r.beschikbaar) {
    veld.classList.add("uit");
    $("rooster-status").textContent =
      "Geen LaunchAgent geinstalleerd; er draait niets automatisch.";
    ["rooster-aan", "btn-rooster", "btn-tijd-erbij"].forEach((id) => ($(id).disabled = true));
    return;
  }
  $("rooster-aan").checked = !!r.aan;
  const tijden = (r.tijden && r.tijden.length) ? r.tijden : [[8, 0]];
  houder.innerHTML = "";
  tijden.forEach(([u, m]) => houder.append(tijdRij(u, m)));

  const lijst = tijden
    .map(([u, m]) => String(u).padStart(2, "0") + ":" + String(m).padStart(2, "0"))
    .join(" en ");
  $("rooster-status").textContent = r.aan
    ? `Staat aan; draait om ${lijst}.`
    : "Staat uit; er draait niets automatisch.";
  $("rooster-status").className = "status" + (r.aan ? " ok" : "");
}

async function laadRooster() {
  try {
    toonRooster(await (await fetch("/api/rooster")).json());
  } catch (e) {
    toonRooster(null);
  }
}

async function stuurRooster(body, bezigTekst) {
  $("rooster-status").textContent = bezigTekst;
  $("rooster-status").className = "status";
  try {
    const res = await fetch("/api/rooster", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const r = await res.json();
    if (!res.ok || r.fout) {
      $("rooster-status").textContent = "Mislukt: " + (r.fout || res.status);
      $("rooster-status").className = "status fout";
      // Terug naar de echte stand, zodat het vinkje niet liegt.
      laadRooster();
      return;
    }
    toonRooster(r);
  } catch (e) {
    $("rooster-status").textContent = "Mislukt: " + e;
    $("rooster-status").className = "status fout";
    laadRooster();
  }
}

function toggleProfiel() {
  $("profiel").classList.toggle("open");
}

/* bediening */
$("zoek").addEventListener("input", teken);
$("reset").onclick = () => { filters.bron = ""; $("filterBron").value = ""; teken(); };
[["filterFamilie", "familie"], ["filterBron", "bron"], ["filterLocatie", "locatie"],
 ["filterVaardigheid", "vaardigheid"], ["filterOordeel", "oordeel"],
 ["filterVlag", "vlag"], ["sorteer", "sorteer"]]
  .forEach(([id, sleutel]) => {
    $(id).addEventListener("change", (e) => {
      filters[sleutel] = e.target.value;
      teken();
      tekenDetail();
    });
  });
$("btnWisFilters").onclick = () => {
  Object.assign(filters, { familie: "", bron: "", locatie: "", vaardigheid: "", oordeel: "alles", vlag: "" });
  $("zoek").value = "";
  ["filterFamilie", "filterBron", "filterLocatie", "filterVaardigheid", "filterVlag"]
    .forEach((id) => ($(id).value = ""));
  $("filterOordeel").value = "alles";
  teken();
};
$("btnLaatste").onclick = laadBewaardeRun;
$("btnExport").onclick = exporteerJa;
$("btnWisAlle").onclick = wisAlleOordelen;
$("btnToon").onclick = () => startRun(false);
$("btnOnthoud").onclick = () => {
  // Een echte run verbruikt nieuwheid en dat is onomkeerbaar: eerst bevestigen.
  const akkoord = confirm(
    "Zoek en onthoud draait een echte run: de resultaten worden weggeschreven en " +
    "nieuwheid wordt verbruikt. Wat nu wordt vastgelegd, meldt de tool later niet " +
    "meer als nieuw. Dat is onomkeerbaar. Doorgaan?"
  );
  if (akkoord) startRun(true);
};
document.querySelectorAll(".weergavekeuze .segknop").forEach((b) => {
  b.onclick = () => kiesWeergave(b.dataset.w);
});
$("btnProfiel").onclick = toggleProfiel;
$("btn-opslaan").onclick = opslaan;
$("rooster-aan").onchange = (e) => {
  // Uitzetten bevestigen: er gebeurt daarna niets meer, en juist dat merk je niet.
  if (!e.target.checked &&
      !confirm("Dagelijkse run uitzetten? Er draait dan niets meer automatisch, " +
               "en daar krijg je geen melding van.")) {
    e.target.checked = true;
    return;
  }
  stuurRooster({ aan: e.target.checked }, "bezig...");
};
$("btn-rooster").onclick = () => stuurRooster({ tijden: leesTijden() }, "rooster opslaan...");
$("btn-tijd-erbij").onclick = () => $("rooster-tijden").append(tijdRij(20, 0));
document.querySelectorAll(".add").forEach((knop) => {
  knop.addEventListener("click", () => {
    const houder = $(knop.dataset.doel);
    const rij = lijstRij("");
    houder.append(rij);
    rij.querySelector("input").focus();
  });
});

// Escape sluit het profielpaneel, ook vanuit een invoerveld.
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("profiel").classList.contains("open")) {
    $("profiel").classList.remove("open");
  }
});

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input")) return;

  // Pijl rechts is ja, pijl links is nee; daarna springt de selectie automatisch
  // door naar de volgende onbeoordeelde vacature. Dat doorlopen is het hele punt.
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    if (!actief) return;
    beoordeel(actief, e.key === "ArrowRight" ? "ja" : "nee");
    e.preventDefault();
    return;
  }

  // j en k (en pijl omhoog/omlaag) navigeren zonder te oordelen.
  if (e.key === "j" || e.key === "k" || e.key === "ArrowDown" || e.key === "ArrowUp") {
    const rijen = zichtbaar();
    if (!rijen.length) return;
    const i = rijen.indexOf(actief);
    const stap = (e.key === "j" || e.key === "ArrowDown") ? 1 : -1;
    actief = rijen[Math.min(rijen.length - 1, Math.max(0, (i === -1 ? 0 : i + stap)))];
    teken(); tekenDetail();
    document.querySelector('.rij[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
    e.preventDefault();
  }
});

laadProfiel();
laadRooster();
// Oordelen eerst laden zodat de rijen meteen goed gemarkeerd staan en het filter
// op de juiste werkstand start; daarna pas de vacatures ophalen.
laadOordelen().then(laadBijStart);
