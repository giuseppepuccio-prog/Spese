"""Dati personali, tenuti fuori dal codice.

Il codice di questo progetto puo' finire su GitHub; i tuoi dati no. Nome,
IBAN, citta' e indirizzi stanno in "data/config_personale.json", che il
.gitignore esclude. Se il file manca, il programma funziona lo stesso: perde
solo le regole che dipendono da quei valori.
"""
import json
import os

PERCORSO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "config_personale.json")

MODELLO = {
    "titolare": "",
    "familiari": [],
    "email": "",
    "citta_abituali": [],
    "citta_famiglia": [],
    "nome_macro_famiglia": "Trasferte familiari",
    "conti_destinazione": {},
}


def _carica() -> dict:
    dati = dict(MODELLO)
    if os.path.exists(PERCORSO):
        try:
            with open(PERCORSO, "r", encoding="utf-8") as f:
                dati.update(json.load(f))
        except (ValueError, OSError) as e:
            print(f"  ATTENZIONE: config_personale.json non leggibile: {e}")
    return dati


DATI = _carica()

TITOLARE = (DATI.get("titolare") or "").strip()
FAMILIARI = [f.strip() for f in DATI.get("familiari", []) if f.strip()]
EMAIL = (DATI.get("email") or "").strip()
CITTA_ABITUALI = {c.strip().lower() for c in DATI.get("citta_abituali", []) if c.strip()}
CITTA_FAMIGLIA = {c.strip().lower() for c in DATI.get("citta_famiglia", []) if c.strip()}
MACRO_FAMIGLIA = DATI.get("nome_macro_famiglia") or "Trasferte familiari"
CONTI_DESTINAZIONE = DATI.get("conti_destinazione", {})


def modello_da_scrivere() -> str:
    """Contenuto di esempio, per chi clona il progetto."""
    esempio = {
        "titolare": "Nome Cognome",
        "familiari": ["Altro Cognome"],
        "email": "tuo.indirizzo@example.com",
        "citta_abituali": ["milano", "roma"],
        "citta_famiglia": ["citta della famiglia"],
        "nome_macro_famiglia": "Trasferte familiari",
        "conti_destinazione": {
            "IT00X0000": "Mutuo",
            "IT00Y0000": "Ricariche portafoglio",
        },
    }
    return json.dumps(esempio, indent=2, ensure_ascii=False)
