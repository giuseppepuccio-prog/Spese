"""Lettura degli estratti conto Fineco (.pdf trimestrali).

Il PDF ha due colonne numeriche distinte, USCITE ed ENTRATE, che nel testo
estratto sarebbero indistinguibili. Le separiamo con la posizione orizzontale:
gli importi sono allineati a destra, le uscite finiscono prima dell'inizio
della colonna ENTRATE. Verificato su dati reali (cedola BTP = entrata,
ritenuta = uscita, addebito Amex = uscita).
"""
import os
import re

import pdfplumber

from . import config
from .modello import Transazione

RE_DATA = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")
RE_IMPORTO = re.compile(r"^[+-]?\d{1,3}(?:\.\d{3})*,\d{2}$")
RE_DATA_OP = re.compile(r"Data Operazione\s+(\d{2}/\d{2}/\d{2})", re.I)
RE_CARTA = re.compile(r"\s*Carta N\..*$", re.I)
RE_SALDO = re.compile(r"Saldo (iniziale|finale)", re.I)

# Movimenti che spostano denaro fra strumenti dell'utente: non sono spese.
# Il nome del titolare arriva dalla configurazione, non dal codice.
_T = re.escape(config.TITOLARE) if config.TITOLARE else ""
RE_GIROCONTO = re.compile(
    r"American Express Italia|Giroconto|Bonifico a Proprio Favore"
    + (rf"|Ordinante:\s*{_T}\s+Beneficiario:\s*{_T}" if _T else ""), re.I)


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", ".").lstrip("+"))


def _data_iso(s: str, sep: str = ".") -> str:
    g, m, a = s.split(sep)
    return f"20{a}-{m}-{g}"


def _righe_per_pagina(pagina):
    """Raggruppa le parole in righe visive, tollerando piccoli scarti verticali."""
    righe: dict[int, list] = {}
    for w in pagina.extract_words():
        chiave = round(w["top"] / 3.0)
        righe.setdefault(chiave, []).append(w)
    return [sorted(v, key=lambda t: t["x0"]) for _, v in sorted(righe.items())]


def _colonne(pagina) -> dict | None:
    """Individua le x delle intestazioni USCITE / ENTRATE / DESCRIZIONE."""
    hdr = {}
    for w in pagina.extract_words():
        u = w["text"].upper()
        if u in ("USCITE", "ENTRATE", "DESCRIZIONE") and u not in hdr:
            hdr[u] = w
    if "ENTRATE" not in hdr or "DESCRIZIONE" not in hdr:
        return None
    return {"confine": hdr["ENTRATE"]["x0"], "descrizione": hdr["DESCRIZIONE"]["x0"]}


# citta' composte da piu' parole che altrimenti verrebbero troncate
CITTA_COMPOSTE = (
    "Gioia Tauro", "Reggio Calabria", "Reggio Emilia", "La Spezia", "San Zenone",
    "Montalto di Castro", "Vibo Valentia", "Villa San Giovanni", "Torre del Greco",
    "Castel San Giovanni", "Forte dei Marmi", "Santa Marinella", "Ostia Lido",
    "Fiumicino Aeroporto", "Milano Malpensa", "Roma Fiumicino", "Sesto San Giovanni",
    # localita' estere incontrate nei viaggi
    "San Sebastian", "Fort William", "Kyle of Lochalsh", "Le Mans",
    "Saint Jean", "La Rochelle", "Den Haag", "Las Palmas", "Los Angeles",
    "New York", "San Francisco", "Palma de Mallorca",
)


def _pulisci_descrizione(testo: str) -> tuple[str, str, str]:
    """Da "Bottamedi Michele & C. Andalo It Carta N. ..." ricava
    (merchant, citta, paese)."""
    # Solo i pagamenti con carta hanno il formato "<Esercente> <Citta> <Paese>".
    # Su un bonifico le ultime due lettere non sono un paese: senza questo
    # controllo, la coda di un bonifico produceva paesi inesistenti.
    con_carta = bool(RE_CARTA.search(testo))

    testo = RE_CARTA.sub("", testo).strip()
    testo = re.sub(r"\s+", " ", testo)
    if not con_carta:
        return testo, "", ""

    m = re.match(r"^(.+?)\s+([A-Z][a-z])$", testo)
    if not m:
        return testo, "", ""
    resto, paese = m.group(1).strip(), m.group(2).upper()

    # la citta' e' l'ultima parola, salvo i casi composti noti
    for citta in CITTA_COMPOSTE:
        if resto.lower().endswith(citta.lower()):
            merchant = resto[: -len(citta)].strip()
            return (merchant or resto), citta, paese

    parti = resto.rsplit(" ", 1)
    if len(parti) == 2 and len(parti[0]) > 2:
        merchant, citta = parti[0].strip(), parti[1].strip()
        # Fineco tronca i nomi lunghi: "Montalto di Castro" diventa
        # "Montalto di C", e prendere l'ultima parola darebbe citta' = "C".
        # In quel caso si recuperano le parole precedenti.
        if len(citta) <= 2:
            pezzi = merchant.split()
            recuperate = []
            while pezzi and len(recuperate) < 2:
                ultima = pezzi[-1]
                if len(ultima) <= 3 or ultima[0].isupper():
                    recuperate.insert(0, pezzi.pop())
                else:
                    break
            if recuperate:
                citta = " ".join(recuperate + [citta])
                merchant = " ".join(pezzi) or merchant
        return merchant, citta, paese
    return resto, "", paese


def leggi_file(percorso: str) -> list[Transazione]:
    nome_file = os.path.basename(percorso)
    transazioni: list[Transazione] = []
    conteggio: dict[str, int] = {}

    with pdfplumber.open(percorso) as pdf:
        for pagina in pdf.pages:
            col = _colonne(pagina)
            if not col:
                continue

            corrente: Transazione | None = None
            for toks in _righe_per_pagina(pagina):
                testi = [t["text"] for t in toks]

                # una riga di movimento inizia con due date affiancate
                if len(testi) >= 3 and RE_DATA.match(testi[0]) and RE_DATA.match(testi[1]):
                    importi = [t for t in toks
                               if RE_IMPORTO.match(t["text"])
                               and t["x1"] < col["descrizione"] - 2]
                    if not importi:
                        continue
                    imp_tok = importi[0]
                    valore = _num(imp_tok["text"])
                    entrata = imp_tok["x1"] > col["confine"]

                    descr = " ".join(t["text"] for t in toks
                                     if t["x0"] >= col["descrizione"] - 6)
                    if RE_SALDO.search(descr):
                        corrente = None
                        continue

                    corrente = Transazione(
                        data=_data_iso(testi[0]),
                        data_registrazione=_data_iso(testi[0]),
                        descrizione=descr.strip(),
                        importo=valore if entrata else -valore,
                        fonte="fineco",
                        conto="Fineco c/c",
                        file_origine=nome_file,
                    )
                    transazioni.append(corrente)

                elif corrente is not None and toks:
                    # riga di continuazione: solo testo nella fascia descrizione
                    if toks[0]["x0"] >= col["descrizione"] - 6:
                        corrente.descrizione += " " + " ".join(testi)
                    else:
                        corrente = None

    # rifinitura: data reale della spesa, esercente, giroconti, id stabile
    for t in transazioni:
        m = RE_DATA_OP.search(t.descrizione)
        if m:
            t.data = _data_iso(m.group(1), "/")
        t.merchant, t.citta, t.paese = _pulisci_descrizione(t.descrizione)
        if RE_GIROCONTO.search(t.descrizione):
            t.escludi = True
            t.motivo_esclusione = "Giroconto o pagamento carta (già contato su Amex)"

        # due movimenti identici lo stesso giorno esistono davvero:
        # un progressivo evita che la deduplica ne cancelli uno
        chiave = f"{t.data}|{t.importo:.2f}|{t.descrizione[:60]}"
        conteggio[chiave] = conteggio.get(chiave, 0) + 1
        t.riferimento = f"{chiave}#{conteggio[chiave]}"

    return transazioni


def leggi_cartella(cartella: str) -> list[Transazione]:
    out: list[Transazione] = []
    for nome in sorted(os.listdir(cartella)):
        if nome.lower().endswith(".pdf"):
            out.extend(leggi_file(os.path.join(cartella, nome)))
    return out
