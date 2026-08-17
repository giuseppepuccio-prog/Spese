"""Genera il sito: legge gli estratti, categorizza, cifra e prepara i file.

Uso:
    python build.py                 chiede la password
    python build.py --password xxx  password da riga di comando

Il file prodotto (sito/data.enc) e' cifrato con AES-256-GCM: su GitHub finisce
solo un blob illeggibile, che il browser decifra con la tua password.
"""
import argparse
import getpass
import gzip
import hashlib
import json
import os
import re
import sys
from datetime import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from spese.pipeline import costruisci
from spese import risparmio as mod_risparmio

RADICE = os.path.dirname(os.path.abspath(__file__))
# tutte le sottocartelle vengono lette: gli Excel come estratti carta,
# i PDF come estratti del conto corrente
BASE_DATI = r"C:\Users\giuse\OneDrive\Documenti\07. Spese Personali"
FILE_OVERRIDE = os.path.join(RADICE, "data", "override.json")
FILE_REGOLE = os.path.join(RADICE, "data", "regole_personali.json")
SITO = os.path.join(RADICE, "sito")

ITERAZIONI = 250_000  # PBKDF2: alto abbastanza da rendere lento un attacco


def cifra(dati: bytes, password: str) -> bytes:
    """salt(16) | iv(12) | ciphertext — formato letto dal browser via Web Crypto."""
    salt = os.urandom(16)
    iv = os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=ITERAZIONI)
    chiave = kdf.derive(password.encode("utf-8"))
    testo_cifrato = AESGCM(chiave).encrypt(iv, dati, None)
    return salt + iv + testo_cifrato


def aggiorna_versione_sito() -> None:
    """Aggiunge ?v=<impronta> a CSS e JS in index.html.

    Senza questo il telefono continuerebbe a mostrare la versione in cache
    anche dopo un aggiornamento, e le correzioni sembrerebbero non applicate.
    """
    indice = os.path.join(SITO, "index.html")
    if not os.path.exists(indice):
        return

    impronta = hashlib.sha1()
    for nome in ("app.js", "style.css"):
        percorso = os.path.join(SITO, nome)
        if os.path.exists(percorso):
            with open(percorso, "rb") as f:
                impronta.update(f.read())
    versione = impronta.hexdigest()[:8]

    with open(indice, "r", encoding="utf-8") as f:
        html = f.read()
    nuovo = re.sub(r'(href="style\.css)(\?v=[a-f0-9]+)?"',
                   rf'\1?v={versione}"', html)
    nuovo = re.sub(r'(src="app\.js)(\?v=[a-f0-9]+)?"',
                   rf'\1?v={versione}"', nuovo)
    if nuovo != html:
        with open(indice, "w", encoding="utf-8") as f:
            f.write(nuovo)
        print(f"  versione sito       : {versione}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", help="password di cifratura del sito")
    ap.add_argument("--dati", default=BASE_DATI,
                    help="cartella che contiene gli estratti conto")
    args = ap.parse_args()

    password = args.password or getpass.getpass("Password per proteggere i dati: ")
    if len(password) < 8:
        print("ERRORE: usa una password di almeno 8 caratteri.")
        return 1

    print(f"Lettura degli estratti conto da:\n  {args.dati}\n")
    dati = costruisci(args.dati, FILE_OVERRIDE, FILE_REGOLE)
    dati["risparmio"] = mod_risparmio.analizza(dati["transazioni"],
                                               dati["statistiche"])
    dati["generato_il"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    d = dati["diagnostica"]
    s = dati["statistiche"]
    print(f"  file letti          : {d['file_excel']} Excel, {d['file_pdf']} PDF")
    print(f"  movimenti letti     : {d['letti']}")
    print(f"  duplicati scartati  : {d['duplicati_scartati']}")
    print(f"  movimenti unici     : {d['univoci']}")
    print(f"  da rivedere         : {d['da_rivedere']}")
    print(f"  viaggi rilevati     : {len(dati['viaggi'])}")
    print(f"  spese totali        : {s['totale_spese']:,.2f} EUR")
    print("  conti riconosciuti  :")
    for c in d["conti"]:
        print(f"      - {c}")

    grezzo = json.dumps(dati, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compresso = gzip.compress(grezzo, 9)
    cifrato = cifra(compresso, password)

    os.makedirs(SITO, exist_ok=True)
    percorso = os.path.join(SITO, "data.enc")
    with open(percorso, "wb") as f:
        f.write(cifrato)

    aggiorna_versione_sito()

    # copia di sicurezza dei dati in chiaro, solo sul PC (mai su GitHub)
    os.makedirs(os.path.join(RADICE, "data"), exist_ok=True)
    with open(os.path.join(RADICE, "data", "ultimo_export.json"), "wb") as f:
        f.write(grezzo)

    print(f"\nFatto. {len(grezzo)/1024:.0f} KB -> {len(cifrato)/1024:.0f} KB cifrati")
    print(f"  {percorso}")
    print("\nOra puoi pubblicare la cartella 'sito' su GitHub Pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
