"""Unisce Amex e Fineco, deduplica, categorizza e prepara i dati per il sito."""
import json
import os
from collections import defaultdict

from . import categorie, modello, parser_amex, parser_fineco, portali


def _carica_override(percorso: str) -> dict:
    """Correzioni fatte da te dall'app: hanno sempre la precedenza."""
    if not os.path.exists(percorso):
        return {}
    with open(percorso, "r", encoding="utf-8") as f:
        return json.load(f)


def trova_estratti(radice: str) -> list[str]:
    """Elenca i file di estratto conto nella radice e nelle sue sottocartelle.

    Cosi' basta creare una cartella nuova ("02. Amex gold", una carta futura)
    perche' venga letta, senza toccare il codice.
    """
    trovati = []
    for cartella, _sub, file in os.walk(radice):
        for nome in sorted(file):
            if nome.startswith(("~$", ".")):
                continue
            if nome.lower().endswith((".xlsx", ".xls", ".pdf")):
                trovati.append(os.path.join(cartella, nome))
    return sorted(trovati)


def costruisci(radice_dati: str, file_override: str,
               file_regole: str = "") -> dict:
    regole_personali = _carica_override(file_regole) if file_regole else {}
    transazioni = []
    letti_per_tipo = {"amex": 0, "fineco": 0}

    for percorso in trova_estratti(radice_dati):
        try:
            if percorso.lower().endswith((".xlsx", ".xls")):
                transazioni += parser_amex.leggi_file(percorso)
                letti_per_tipo["amex"] += 1
            else:
                transazioni += parser_fineco.leggi_file(percorso)
                letti_per_tipo["fineco"] += 1
        except Exception as e:
            # un file illeggibile non deve fermare tutto il resto
            print(f"  ATTENZIONE: non riesco a leggere «{os.path.basename(percorso)}»: {e}")

    # --- deduplica: gli estratti si sovrappongono fra loro ---------------
    uniche: dict[str, object] = {}
    duplicati = 0
    for t in transazioni:
        if t.id in uniche:
            duplicati += 1
            continue
        uniche[t.id] = t
    tx = sorted(uniche.values(), key=lambda t: t.data)

    for t in tx:
        t.citta = modello.citta_normalizzata(t.citta)
        categorie.categorizza(t, regole_personali)
        portali.analizza(t)

    viaggi = categorie.rileva_viaggi(tx)

    # --- le tue correzioni vincono su tutto ------------------------------
    override = _carica_override(file_override)
    applicati = 0
    for t in tx:
        o = override.get(t.id)
        if not o:
            continue
        applicati += 1
        for campo in ("categoria", "macro", "viaggio"):
            if o.get(campo):
                setattr(t, campo, o[campo])
        if o.get("escludi") is not None:
            t.escludi = bool(o["escludi"])
        t.da_rivedere = False

    return {
        "transazioni": [t.to_dict() for t in tx],
        "viaggi": viaggi,
        "acquisti_online": portali.riepilogo(tx),
        "statistiche": _statistiche(tx, viaggi),
        "diagnostica": {
            "letti": len(transazioni),
            "duplicati_scartati": duplicati,
            "univoci": len(tx),
            "override_applicati": applicati,
            "da_rivedere": sum(1 for t in tx if t.da_rivedere),
            "file_excel": letti_per_tipo["amex"],
            "file_pdf": letti_per_tipo["fineco"],
            "conti": sorted({t.conto for t in tx if t.conto}),
        },
    }


def _statistiche(tx: list, viaggi: list) -> dict:
    """Riepiloghi mensili e per categoria, piu' gli indicatori di risparmio."""
    spese = [t for t in tx if not t.escludi and t.importo < 0
             and t.macro not in ("Entrate", "Risparmio")]
    entrate = [t for t in tx if not t.escludi and t.importo > 0
               and t.macro == "Entrate"]
    # gli accantonamenti non sono spesa: sono risparmio gia' in corso
    accantonati = [t for t in tx if not t.escludi and t.macro == "Risparmio"
                   and t.importo < 0]

    mensili = defaultdict(lambda: {"spese": 0.0, "entrate": 0.0,
                                   "per_macro": defaultdict(float)})
    for t in spese:
        m = t.data[:7]
        mensili[m]["spese"] += -t.importo
        mensili[m]["per_macro"][t.macro] += -t.importo
    for t in entrate:
        mensili[t.data[:7]]["entrate"] += t.importo
    for t in accantonati:
        mensili[t.data[:7]]["accantonato"] = \
            mensili[t.data[:7]].get("accantonato", 0.0) + -t.importo

    # Un mese e' confrontabile solo se TUTTE le fonti lo coprono.
    #  - senza lo stipendio si vedrebbero le spese ma non le entrate,
    #    simulando un deficit inesistente;
    #  - senza gli estratti di una carta si vedrebbero le entrate ma non
    #    tutte le spese, simulando un risparmio che non c'e'.
    # Entrambi i casi sono capitati davvero con questi dati.
    mesi_con_stipendio = {t.data[:7] for t in tx
                          if t.categoria == "Stipendio" and t.importo > 0}

    copertura = {}
    for t in tx:
        if not t.conto or not t.data:
            continue
        primo, ultimo = copertura.get(t.conto, (t.data[:7], t.data[:7]))
        copertura[t.conto] = (min(primo, t.data[:7]), max(ultimo, t.data[:7]))
    # intersezione dei periodi: il tratto in cui ogni conto ha dati
    inizio_comune = max((p for p, _ in copertura.values()), default="0000-00")
    fine_comune = min((u for _, u in copertura.values()), default="9999-99")

    mesi_completi = {m for m in mesi_con_stipendio
                     if inizio_comune <= m <= fine_comune}

    serie = []
    for mese in sorted(mensili):
        v = mensili[mese]
        serie.append({
            "mese": mese,
            "spese": round(v["spese"], 2),
            "entrate": round(v["entrate"], 2),
            "accantonato": round(v.get("accantonato", 0.0), 2),
            "risparmio": round(v["entrate"] - v["spese"], 2),
            "completo": mese in mesi_completi,
            "per_macro": {k: round(x, 2) for k, x in v["per_macro"].items()},
        })

    per_categoria = defaultdict(float)
    for t in spese:
        per_categoria[t.categoria] += -t.importo

    completi = [s for s in serie if s["completo"]]
    media_spese = (sum(s["spese"] for s in completi) / len(completi)) if completi else 0
    media_entrate = (sum(s["entrate"] for s in completi) / len(completi)) if completi else 0
    # l'accantonato va misurato sugli stessi mesi, altrimenti si gonfia
    accantonato_completi = sum(s["accantonato"] for s in completi)

    return {
        "mensili": serie,
        "per_categoria": [{"categoria": k, "totale": round(v, 2)}
                          for k, v in sorted(per_categoria.items(),
                                             key=lambda x: -x[1])],
        "totale_spese": round(sum(-t.importo for t in spese), 2),
        "totale_entrate": round(sum(t.importo for t in entrate), 2),
        "mesi_completi": len(completi),
        "media_spese_mensili": round(media_spese, 2),
        "media_entrate_mensili": round(media_entrate, 2),
        "risparmio_medio": round(media_entrate - media_spese, 2),
        "totale_viaggi": round(sum(v["totale"] for v in viaggi), 2),
        "totale_accantonato": round(sum(-t.importo for t in accantonati), 2),
        "accantonato_medio": round(accantonato_completi / len(completi), 2) if completi else 0,
        "mesi_incompleti": [s["mese"] for s in serie if not s["completo"]],
        "copertura_conti": {c: {"da": p, "a": u} for c, (p, u) in sorted(copertura.items())},
        "periodo_confrontabile": {"da": inizio_comune, "a": fine_comune},
    }
