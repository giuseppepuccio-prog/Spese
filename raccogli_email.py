"""Raccoglie gli estratti conto inviati via e-mail e li mette nelle cartelle.

Come si usa:
  1. Scarichi l'estratto dal portale Amex o Fineco.
  2. Lo alleghi a una mail che mandi a te stesso con la parola chiave
     nell'oggetto (default: "spese").
  3. Lanci questo script (o `aggiorna.bat`, che lo richiama da solo).

Riconosce il tipo dal contenuto, non dal nome: un Excel con il foglio
"Dettagli transazione" e' Amex, un PDF che nomina Fineco e' l'estratto conto.
Cosi' non importa come si chiama il file che inoltri.
"""
import email
import hashlib
import imaplib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timedelta
from email.header import decode_header

RADICE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(RADICE, "data", "email_config.json")
REGISTRO = os.path.join(RADICE, "data", "email_elaborate.json")
BASE_DATI = r"C:\Users\giuse\OneDrive\Documenti\07. Spese Personali"
CARTELLA_AMEX = os.path.join(BASE_DATI, "00. Amex")
CARTELLA_FINECO = os.path.join(BASE_DATI, "01. Fineco")

MODELLO_CONFIG = {
    "server": "imap.gmail.com",
    "utente": "",   # compila con il tuo indirizzo
    "password_app": "",
    "parola_chiave_oggetto": "spese",
    "cartella": "INBOX",
    "giorni_indietro": 90,
}

ISTRUZIONI = """
Compila 'password_app' con una password per app di Google:
  1. Apri  https://myaccount.google.com/apppasswords
  2. Serve la verifica in due passaggi attiva sull'account
  3. Crea una password per "Posta" e incollala nel file

Non e' la password del tuo account Google: e' un codice separato, revocabile
in qualsiasi momento, che consente solo di leggere la posta.
"""


def carica_config():
    if not os.path.exists(CONFIG):
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(MODELLO_CONFIG, f, indent=2, ensure_ascii=False)
        print("Ho creato il file di configurazione:")
        print("   ", CONFIG)
        print(ISTRUZIONI)
        return None
    with open(CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("password_app"):
        print(f"Manca 'password_app' in:\n    {CONFIG}")
        print(ISTRUZIONI)
        return None
    return cfg


def _leggi_registro() -> set:
    if os.path.exists(REGISTRO):
        try:
            with open(REGISTRO, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (ValueError, OSError):
            return set()
    return set()


def _salva_registro(visti: set) -> None:
    os.makedirs(os.path.dirname(REGISTRO), exist_ok=True)
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(sorted(visti), f, indent=1)


def _decodifica(valore) -> str:
    if not valore:
        return ""
    fuori = []
    for testo, codifica in decode_header(valore):
        if isinstance(testo, bytes):
            fuori.append(testo.decode(codifica or "utf-8", errors="replace"))
        else:
            fuori.append(str(testo))
    return "".join(fuori)


def riconosci(nome: str, contenuto: bytes) -> str:
    """Restituisce 'amex', 'fineco' oppure '' se l'allegato non c'entra."""
    minuscolo = (nome or "").lower()

    if minuscolo.endswith((".xlsx", ".xls")):
        # un xlsx e' uno zip: cerchiamo le stringhe dei fogli senza aprirlo
        try:
            with zipfile.ZipFile(io.BytesIO(contenuto)) as z:
                testo = b"".join(
                    z.read(n) for n in z.namelist()
                    if n.endswith(".xml"))[:400_000].decode("utf-8", "ignore")
            if re.search(r"Dettagli transazione|American Express|Riepilogo transazioni",
                         testo, re.I):
                return "amex"
        except (zipfile.BadZipFile, KeyError, OSError):
            pass
        return "amex"  # un Excel inoltrato qui e' comunque un estratto carta

    if minuscolo.endswith(".pdf"):
        inizio = contenuto[:600_000]
        if re.search(rb"Fineco|FinecoBank|Estratto conto", inizio, re.I):
            return "fineco"
        return "fineco"

    return ""


def nome_libero(cartella: str, nome: str) -> str:
    """Evita di sovrascrivere: aggiunge un progressivo se il nome esiste."""
    base, est = os.path.splitext(nome)
    base = re.sub(r'[<>:"/\\|?*]', "_", base).strip() or "estratto"
    percorso = os.path.join(cartella, base + est)
    n = 2
    while os.path.exists(percorso):
        percorso = os.path.join(cartella, f"{base} ({n}){est}")
        n += 1
    return percorso


def gia_presente(cartella: str, contenuto: bytes) -> str:
    """Se un file identico c'e' gia', non lo riscriviamo."""
    impronta = hashlib.md5(contenuto).hexdigest()
    if not os.path.isdir(cartella):
        return ""
    for nome in os.listdir(cartella):
        percorso = os.path.join(cartella, nome)
        if not os.path.isfile(percorso):
            continue
        if os.path.getsize(percorso) != len(contenuto):
            continue
        with open(percorso, "rb") as f:
            if hashlib.md5(f.read()).hexdigest() == impronta:
                return nome
    return ""


def raccogli(cfg: dict) -> int:
    visti = _leggi_registro()
    salvati = 0

    dal = (datetime.now() - timedelta(days=int(cfg.get("giorni_indietro", 90)))
           ).strftime("%d-%b-%Y")
    chiave = cfg.get("parola_chiave_oggetto", "spese")

    print(f"Collegamento a {cfg['server']} come {cfg['utente']}...")
    try:
        server = imaplib.IMAP4_SSL(cfg["server"])
        server.login(cfg["utente"], cfg["password_app"])
    except imaplib.IMAP4.error as e:
        print("\nAccesso rifiutato:", e)
        print("Controlla la password per app. Se hai cambiato password Google,")
        print("va rigenerata.")
        return 0

    try:
        server.select(cfg.get("cartella", "INBOX"))
        criterio = f'(SINCE "{dal}" SUBJECT "{chiave}")'
        esito, risposta = server.search(None, criterio)
        if esito != "OK":
            print("Ricerca non riuscita.")
            return 0

        identificativi = risposta[0].split()
        print(f"Trovate {len(identificativi)} mail con «{chiave}» "
              f"nell'oggetto dagli ultimi {cfg.get('giorni_indietro', 90)} giorni.")

        for ident in identificativi:
            esito, dati = server.fetch(ident, "(RFC822)")
            if esito != "OK" or not dati or not dati[0]:
                continue
            messaggio = email.message_from_bytes(dati[0][1])

            id_messaggio = messaggio.get("Message-ID", "") or ident.decode()
            if id_messaggio in visti:
                continue

            oggetto = _decodifica(messaggio.get("Subject"))
            allegati_trovati = 0

            for parte in messaggio.walk():
                if parte.get_content_maintype() == "multipart":
                    continue
                nome = _decodifica(parte.get_filename())
                if not nome:
                    continue
                contenuto = parte.get_payload(decode=True)
                if not contenuto:
                    continue

                tipo = riconosci(nome, contenuto)
                if not tipo:
                    continue

                cartella = CARTELLA_AMEX if tipo == "amex" else CARTELLA_FINECO
                os.makedirs(cartella, exist_ok=True)

                doppione = gia_presente(cartella, contenuto)
                if doppione:
                    print(f"  = già presente come «{doppione}», salto")
                    allegati_trovati += 1
                    continue

                destinazione = nome_libero(cartella, nome)
                with open(destinazione, "wb") as f:
                    f.write(contenuto)
                print(f"  + {tipo.upper():6} {os.path.basename(destinazione)}")
                salvati += 1
                allegati_trovati += 1

            if allegati_trovati:
                visti.add(id_messaggio)
            elif oggetto:
                print(f"  - nessun allegato utile in «{oggetto[:50]}»")

        _salva_registro(visti)
    finally:
        try:
            server.close()
        except Exception:
            pass
        server.logout()

    return salvati


def main() -> int:
    cfg = carica_config()
    if not cfg:
        return 1
    print("=" * 58)
    print("  RACCOLTA ESTRATTI DA E-MAIL")
    print("=" * 58)
    salvati = raccogli(cfg)
    print()
    if salvati:
        print(f"Salvati {salvati} nuovi estratti conto.")
        print("Ora lancia aggiorna.bat per rigenerare il sito.")
    else:
        print("Nessun nuovo estratto da salvare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
