"""Lettura degli estratti conto American Express (.xlsx mensili).

Struttura osservata nei file reali:
  - foglio "Dettagli transazione": riga di intestazione con "Data|Descrizione|...",
    poi una riga per movimento
  - date in formato americano MM/DD/YYYY
  - importi positivi = addebiti, negativi = pagamenti/rimborsi
  - la colonna "Riferimento" e' un id univoco: perfetto per la deduplica
"""
import os
import re
from datetime import datetime, date

import openpyxl

from .modello import Transazione

INTESTAZIONI = ("data", "descrizione", "importo")

# Righe che non sono spese ma il saldo della carta pagato dal conto Fineco.
# "ADDEBITO IN C/C SALVO BUON FINE" e' la voce reale usata da Amex: senza
# escluderla i 58.573 EUR di saldi pagati risulterebbero come entrate.
RIGHE_PAGAMENTO = re.compile(
    r"PAGAMENTO\s+RICEVUTO|GRAZIE|ADDEBITO\s+DIRETTO|PAGAMENTO\s+EFFETTUATO|"
    r"ADDEBITO\s+IN\s+C/C|SALVO\s+BUON\s+FINE", re.I)


def _cella(v) -> str:
    return "" if v is None else str(v).strip()


def _data_iso(v) -> str:
    """Amex usa MM/DD/YYYY (a volte openpyxl restituisce gia' un datetime)."""
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = _cella(v)
    if not s:
        return ""
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _importo(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("€", "").replace(" ", "")
    # formato italiano 1.234,56 oppure americano 1,234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") \
            else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _merchant_e_citta(descrizione: str, indirizzo: str) -> tuple[str, str]:
    """Amex scrive "NOME ESERCENTE        CITTA": due o piu' spazi separano i campi."""
    parti = [p.strip() for p in re.split(r"\s{2,}", descrizione.strip()) if p.strip()]
    if len(parti) >= 2:
        return parti[0], parti[-1]
    # fallback: ultima riga dell'indirizzo, spesso la citta'
    righe = [r.strip() for r in (indirizzo or "").split("\n") if r.strip()]
    return descrizione.strip(), (righe[-1] if righe else "")


# tipi di carta Amex, dal piu' specifico al piu' generico
TIPI_CARTA = ("Platino", "Platinum", "Oro", "Gold", "Verde", "Green",
              "Business", "Blu", "Blue", "Centurion")


def _nome_carta(righe_intestazione) -> str:
    """Ricava "Amex Oro (…1002)" dalle righe sopra la tabella dei movimenti.

    Nell'intestazione compaiono una riga tipo "Carta <tipo> American
    Express® / <data>" e il numero mascherato "XXXX-XXXXXX-<cifre>".
    """
    testo_righe = []
    for r in righe_intestazione or []:
        for c in r:
            valore = _cella(c)
            if valore:
                testo_righe.append(valore)
    testo = " | ".join(testo_righe)

    tipo = ""
    for t in TIPI_CARTA:
        if re.search(rf"\b{t}\b", testo, re.I):
            tipo = {"platinum": "Platino", "gold": "Oro", "green": "Verde",
                    "blue": "Blu"}.get(t.lower(), t)
            break

    cifre = ""
    m = re.search(r"X{2,}[-\s]?X{2,}[-\s]?(\d{4,6})", testo)
    if m:
        cifre = m.group(1)[-5:]

    if tipo and cifre:
        return f"Amex {tipo} (…{cifre})"
    if tipo:
        return f"Amex {tipo}"
    if cifre:
        return f"Amex (…{cifre})"
    return "Amex"


def leggi_file(percorso: str) -> list[Transazione]:
    wb = openpyxl.load_workbook(percorso, data_only=True)
    nome_file = os.path.basename(percorso)
    transazioni: list[Transazione] = []

    for ws in wb.worksheets:
        righe = list(ws.iter_rows(values_only=True))
        idx_header = None
        for i, r in enumerate(righe):
            valori = [_cella(c).lower() for c in r]
            if all(any(h == v for v in valori) for h in INTESTAZIONI):
                idx_header = i
                break
        if idx_header is None:
            continue  # foglio "Riepilogo transazioni": nessun movimento

        # il nome della carta sta nell'intestazione, sopra i movimenti:
        # senza leggerlo, Platino e Oro finirebbero indistinguibili
        conto = _nome_carta(righe[:idx_header])

        col = {_cella(c).lower(): j for j, c in enumerate(righe[idx_header])
               if _cella(c)}

        def val(riga, nome):
            j = col.get(nome)
            return riga[j] if j is not None and j < len(riga) else None

        for riga in righe[idx_header + 1:]:
            if riga is None or all(c in (None, "") for c in riga):
                continue
            data = _data_iso(val(riga, "data"))
            imp = _importo(val(riga, "importo"))
            descr = _cella(val(riga, "descrizione"))
            if not data or imp is None or not descr:
                continue

            indirizzo = _cella(val(riga, "indirizzo"))
            merchant, citta = _merchant_e_citta(descr, indirizzo)
            if not citta:
                citta = _cella(val(riga, "città/stato")) or _cella(val(riga, "citta/stato"))

            # "Dettagli completi" mescola la categoria Amex con le info di
            # cambio ("Foreign Spend Amount: ... Commission Amount: ...").
            # Vanno separate: lasciarle insieme faceva finire le spese di
            # viaggio sotto "Commissioni bancarie".
            dettagli = _cella(val(riga, "dettagli completi"))
            categoria_amex, dettagli_valuta = "", ""
            for pezzo in dettagli.split("\n"):
                pezzo = pezzo.strip()
                if not pezzo:
                    continue
                if pezzo.lower().startswith("foreign spend"):
                    dettagli_valuta = pezzo
                elif not categoria_amex:
                    categoria_amex = pezzo

            t = Transazione(
                data=data,
                data_registrazione=data,
                descrizione=descr,
                merchant=merchant,
                citta=citta,
                paese=_cella(val(riga, "paese")),
                # Amex: addebito positivo -> per noi le uscite sono negative
                importo=-imp,
                fonte="amex",
                conto=conto,
                riferimento=_cella(val(riga, "riferimento")),
                categoria_fonte=categoria_amex,
                file_origine=nome_file,
                valuta_estera=bool(dettagli_valuta),
                dettagli_valuta=dettagli_valuta,
            )
            if RIGHE_PAGAMENTO.search(descr):
                t.escludi = True
                t.motivo_esclusione = "Pagamento del saldo carta (non è una spesa)"
            transazioni.append(t)

    return transazioni


def leggi_cartella(cartella: str) -> list[Transazione]:
    out: list[Transazione] = []
    for nome in sorted(os.listdir(cartella)):
        if nome.lower().endswith((".xlsx", ".xls")) and not nome.startswith("~$"):
            out.extend(leggi_file(os.path.join(cartella, nome)))
    return out
