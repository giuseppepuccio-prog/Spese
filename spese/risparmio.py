"""Analisi del risparmio: fotografia della situazione e obiettivi realistici.

Nessun consiglio generico: tutto viene calcolato dai movimenti reali.
"""
import re
from collections import defaultdict
from datetime import date
from statistics import median

# Spese che si ripetono ogni mese quasi uguali: sono il tuo "costo fisso".
CATEGORIE_FISSE = {
    "Casa e utenze", "Assicurazioni", "Abbonamenti digitali",
    "Commissioni bancarie", "Imposte e bolli", "Servizi professionali",
    "Mutuo Siena", "Mutuo Milano",
}
# Spese su cui puoi davvero incidere nel breve periodo
CATEGORIE_COMPRIMIBILI = {
    "Ristoranti e bar", "Shopping", "Tempo libero", "Pagamenti Satispay",
}


# voci contabili ricorrenti che non sono sottoscrizioni
NON_ABBONAMENTI = ("IMPOSTA DI BOLLO", "RIT.CED", "CED.SU", "ADDEBITO PENALE",
                   "CANONE MENSILE", "SCONTO CANONE", "PRELEVAMENTO",
                   "QUOTA ASSOCIATIVA", "BEN:", "BENEFICIARIO:", "PIANO BONIFICO")


def _trova_abbonamenti(transazioni: list[dict]) -> list[dict]:
    """Addebiti che si ripetono sempre della stessa cifra: le sottoscrizioni.

    Il criterio e' la regolarita', non la categoria: un abbonamento a un
    servizio di benessere non compare fra quelli "digitali", ed e' proprio
    il tipo che resta attivo per anni senza che ci si accorga.
    """
    spese = [t for t in transazioni if not t["escludi"] and t["importo"] < 0]
    if not spese:
        return []
    oggi = max(t["data"] for t in spese)

    gruppi: dict[str, list] = defaultdict(list)
    for t in spese:
        nome = re.sub(r"\s{2,}.*$", "", (t["merchant"] or t["descrizione"])).upper()
        nome = re.sub(r"[*#]?\s*\d{5,}.*$", "", nome).strip()
        if any(c in nome for c in NON_ABBONAMENTI):
            continue
        gruppi[nome[:34]].append(t)

    fuori = []
    for nome, elenco in gruppi.items():
        if len(elenco) < 3:
            continue
        importi = {round(-t["importo"], 2) for t in elenco}
        mesi = {t["data"][:7] for t in elenco}
        if len(importi) > 2 or len(mesi) < 3:
            continue

        date_ord = sorted(t["data"] for t in elenco)
        giorni = max(1, (date.fromisoformat(date_ord[-1])
                         - date.fromisoformat(date_ord[0])).days)
        totale = sum(-t["importo"] for t in elenco)
        fermo = (date.fromisoformat(oggi) - date.fromisoformat(date_ord[-1])).days
        fuori.append({
            "nome": nome.title(),
            "rata": round(min(importi), 2),
            "addebiti": len(elenco),
            "totale": round(totale, 2),
            "stima_annua": round(totale / giorni * 365, 2),
            "dal": date_ord[0],
            "ultimo": date_ord[-1],
            "giorni_fermo": fermo,
            "attivo": fermo <= 100,
            "categoria": elenco[0]["categoria"],
        })

    fuori.sort(key=lambda a: (not a["attivo"], -a["stima_annua"]))
    return fuori[:25]


def analizza(transazioni: list[dict], statistiche: dict) -> dict:
    mensili = statistiche["mensili"]
    # solo i mesi in cui lo stipendio risulta accreditato: gli altri hanno
    # le spese ma non le entrate, e mostrerebbero un deficit inesistente
    completi = [m for m in mensili if m.get("completo")]
    if not completi:
        return {"disponibile": False,
                "messaggio": "Servono estratti conto Fineco con lo stipendio "
                             "per calcolare la capacità di risparmio."}

    entrate = [m["entrate"] for m in completi]
    spese = [m["spese"] for m in completi]
    # Media per il bilancio: la mediana scarterebbe la tredicesima dalle
    # entrate lasciando pero' le spese di dicembre, e mostrerebbe un rosso
    # che nei dodici mesi non esiste. La mediana resta come "mese tipico".
    entrata_media = sum(entrate) / len(entrate)
    spesa_media = sum(spese) / len(spese)
    entrata_tipica = median(entrate)
    spesa_tipica = median(spese)

    # --- costi fissi contro costi variabili ------------------------------
    per_cat_mese = defaultdict(lambda: defaultdict(float))
    mesi_validi = {m["mese"] for m in completi}
    for t in transazioni:
        if t["escludi"] or t["importo"] >= 0:
            continue
        if t["macro"] in ("Entrate", "Risparmio"):
            continue
        if t["data"][:7] in mesi_validi:
            per_cat_mese[t["categoria"]][t["data"][:7]] += -t["importo"]

    n = len(mesi_validi)
    fisse = sum(sum(v.values()) for k, v in per_cat_mese.items()
                if k in CATEGORIE_FISSE) / n
    comprimibili = sum(sum(v.values()) for k, v in per_cat_mese.items()
                       if k in CATEGORIE_COMPRIMIBILI) / n

    accantonato = statistiche.get("accantonato_medio", 0)
    margine = entrata_media - spesa_media

    # --- il risparmio VERO e' entrate meno spese --------------------------
    # Spostare denaro su un altro conto non e' risparmio se intanto il saldo
    # complessivo scende: contarlo come tale darebbe una falsa sicurezza.
    tasso_attuale = (margine / entrata_media * 100) if entrata_media else 0
    in_deficit = margine < 0

    avvisi = []
    if in_deficit:
        avvisi.append(
            "Nei mesi analizzati le spese superano le entrate di "
            f"{abs(margine):,.0f} euro al mese: il saldo complessivo cala. "
            "Prima di fissare un obiettivo conviene capire se dipende dalle "
            "spese o da entrate che non compaiono negli estratti caricati."
            .replace(",", "."))
    mancanti = statistiche.get("mesi_incompleti") or []
    if mancanti:
        periodo = statistiche.get("periodo_confrontabile") or {}
        senza_carte = [m for m in mancanti
                       if not (periodo.get("da", "") <= m <= periodo.get("a", "z"))]
        senza_stipendio = [m for m in mancanti if m not in senza_carte]

        if senza_stipendio:
            avvisi.append(
                f"{len(senza_stipendio)} mesi sono esclusi perché manca "
                "l'estratto Fineco con lo stipendio: "
                f"{', '.join(senza_stipendio[:6])}"
                f"{'…' if len(senza_stipendio) > 6 else ''}.")
        if senza_carte:
            avvisi.append(
                f"Altri {len(senza_carte)} mesi sono esclusi perché non tutte "
                "le carte li coprono: mostrerebbero le entrate senza tutte le "
                "spese, e farebbero sembrare il risparmio più alto di quello "
                f"reale. Il periodo confrontabile va da {periodo.get('da', '?')} "
                f"a {periodo.get('a', '?')}.")

    obiettivi = [
        {"nome": "Prudente", "quota": 0.10,
         "descrizione": "Il 10% delle entrate: la soglia minima consigliata."},
        {"nome": "Equilibrato", "quota": 0.15,
         "descrizione": "Il 15%: costruisce un fondo di emergenza in tempi ragionevoli."},
        {"nome": "Ambizioso", "quota": 0.20,
         "descrizione": "Il 20%: richiede di ridurre le spese comprimibili."},
    ]
    for o in obiettivi:
        o["importo_mensile"] = round(entrata_media * o["quota"], 2)
        o["annuo"] = round(entrata_media * o["quota"] * 12, 2)
        o["raggiungibile"] = o["importo_mensile"] <= margine
        # quanto va tagliato dalle spese per arrivarci davvero
        o["sforzo"] = round(max(0.0, o["importo_mensile"] - margine), 2)

    # --- fondo di emergenza: 3-6 mesi di spese ---------------------------
    fondo_min, fondo_max = spesa_tipica * 3, spesa_tipica * 6

    # --- dove si può intervenire davvero ---------------------------------
    leve = []
    for cat in CATEGORIE_COMPRIMIBILI:
        if cat not in per_cat_mese:
            continue
        media = sum(per_cat_mese[cat].values()) / n
        if media < 30:
            continue
        leve.append({
            "categoria": cat,
            "media_mensile": round(media, 2),
            "risparmio_20": round(media * 0.20, 2),
            "risparmio_annuo_20": round(media * 0.20 * 12, 2),
        })
    leve.sort(key=lambda x: -x["media_mensile"])

    abbonamenti = _trova_abbonamenti(transazioni)

    return {
        "disponibile": True,
        "mesi_analizzati": n,
        "entrata_tipica": round(entrata_media, 2),
        "spesa_tipica": round(spesa_media, 2),
        "entrata_mese_tipico": round(entrata_tipica, 2),
        "spesa_mese_tipico": round(spesa_tipica, 2),
        "margine_teorico": round(margine, 2),
        "gia_accantonato_mese": round(accantonato, 2),
        "tasso_risparmio_attuale": round(tasso_attuale, 1),
        "in_deficit": in_deficit,
        "avvisi": avvisi,
        "spese_fisse_mese": round(fisse, 2),
        "spese_comprimibili_mese": round(comprimibili, 2),
        "fondo_emergenza_min": round(fondo_min, 2),
        "fondo_emergenza_max": round(fondo_max, 2),
        "obiettivi": obiettivi,
        "leve": leve,
        "abbonamenti": abbonamenti,
    }
