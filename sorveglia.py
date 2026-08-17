"""Sorveglia le cartelle degli estratti e rigenera il sito quando cambiano.

Lo lanci una volta e resta in ascolto: appena copi un nuovo estratto conto in
una qualsiasi sottocartella, l'app si aggiorna da sola.

Due accortezze:
  - attende che il file smetta di cambiare prima di leggerlo, altrimenti su
    OneDrive verrebbe letto a metà sincronizzazione;
  - la password serve per cifrare, quindi va data una volta all'avvio.
    Puoi salvarla protetta con la cifratura di Windows (DPAPI): resta
    leggibile solo dal tuo utente su questo PC.
"""
import ctypes
import ctypes.wintypes as wt
import getpass
import os
import subprocess
import sys
import time

RADICE = os.path.dirname(os.path.abspath(__file__))
BASE_DATI = r"C:\Users\giuse\OneDrive\Documenti\07. Spese Personali"
FILE_PASSWORD = os.path.join(RADICE, "data", "password.protetta")
ESTENSIONI = (".xlsx", ".xls", ".pdf")
INTERVALLO = 20        # secondi fra un controllo e l'altro
ATTESA_STABILE = 8     # secondi di immobilita' prima di considerare finita la copia


# --------------------------------------------------------------------------
# Password protetta con DPAPI: la cifratura e' legata al tuo account Windows
# --------------------------------------------------------------------------
class BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(dati: bytes) -> BLOB:
    buf = ctypes.create_string_buffer(dati, len(dati))
    return BLOB(len(dati), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _estrai(blob: BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def proteggi(testo: str) -> bytes:
    dentro, fuori = _blob(testo.encode("utf-8")), BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(dentro), "spese", None, None, None, 0, ctypes.byref(fuori))
    if not ok:
        raise OSError("CryptProtectData non riuscita")
    dati = _estrai(fuori)
    ctypes.windll.kernel32.LocalFree(fuori.pbData)
    return dati


def rileggi(dati: bytes) -> str:
    dentro, fuori = _blob(dati), BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(dentro), None, None, None, None, 0, ctypes.byref(fuori))
    if not ok:
        raise OSError("CryptUnprotectData non riuscita")
    testo = _estrai(fuori).decode("utf-8")
    ctypes.windll.kernel32.LocalFree(fuori.pbData)
    return testo


def ottieni_password() -> str:
    if os.path.exists(FILE_PASSWORD):
        try:
            with open(FILE_PASSWORD, "rb") as f:
                return rileggi(f.read())
        except OSError:
            print("Password salvata non leggibile: la richiedo di nuovo.")

    password = getpass.getpass("Password del sito: ")
    if len(password) < 8:
        print("Servono almeno 8 caratteri.")
        return ""
    risposta = input("Vuoi salvarla per i prossimi avvii? [s/N] ").strip().lower()
    if risposta == "s":
        os.makedirs(os.path.dirname(FILE_PASSWORD), exist_ok=True)
        with open(FILE_PASSWORD, "wb") as f:
            f.write(proteggi(password))
        print(f"Salvata in {FILE_PASSWORD}")
        print("È cifrata con il tuo account Windows: un altro utente non può leggerla.")
    return password


# --------------------------------------------------------------------------
# Sorveglianza
# --------------------------------------------------------------------------
def istantanea() -> dict:
    """Nome file -> (dimensione, data di modifica)."""
    stato = {}
    for cartella, _sub, file in os.walk(BASE_DATI):
        for nome in file:
            if nome.startswith(("~$", ".")) or not nome.lower().endswith(ESTENSIONI):
                continue
            percorso = os.path.join(cartella, nome)
            try:
                s = os.stat(percorso)
                stato[percorso] = (s.st_size, int(s.st_mtime))
            except OSError:
                pass
    return stato


def rigenera(password: str) -> bool:
    print("\n  Aggiornamento in corso...")
    esito = subprocess.run(
        [os.path.join(RADICE, ".venv", "Scripts", "python.exe"),
         os.path.join(RADICE, "build.py"), "--password", password],
        cwd=RADICE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if esito.returncode == 0:
        for riga in (esito.stdout or "").splitlines():
            if riga.strip().startswith(("movimenti unici", "spese totali",
                                        "viaggi rilevati", "file letti")):
                print("   ", riga.strip())
        print("  Fatto: ricarica l'app sul telefono.\n")
        return True
    print("  ERRORE durante l'aggiornamento:")
    print((esito.stdout or "")[-800:])
    print((esito.stderr or "")[-800:])
    return False


def main() -> int:
    if not os.path.isdir(BASE_DATI):
        print(f"Cartella non trovata:\n  {BASE_DATI}")
        return 1

    password = ottieni_password()
    if not password:
        return 1

    print("=" * 60)
    print("  SORVEGLIANZA ESTRATTI CONTO")
    print("=" * 60)
    print(f"\n  Cartella: {BASE_DATI}")
    print(f"  Controllo ogni {INTERVALLO} secondi.")
    print("  Copia i nuovi estratti: l'app si aggiorna da sola.")
    print("\n  CTRL+C per fermare.\n")

    precedente = istantanea()
    print(f"  {len(precedente)} file già presenti. In ascolto...")

    try:
        while True:
            time.sleep(INTERVALLO)
            attuale = istantanea()
            if attuale == precedente:
                continue

            nuovi = [p for p in attuale if p not in precedente]
            modificati = [p for p in attuale
                          if p in precedente and attuale[p] != precedente[p]]
            rimossi = [p for p in precedente if p not in attuale]

            for p in nuovi:
                print(f"  + {os.path.basename(p)}")
            for p in modificati:
                print(f"  ~ {os.path.basename(p)} (modificato)")
            for p in rimossi:
                print(f"  - {os.path.basename(p)} (rimosso)")

            # aspetta che le dimensioni si stabilizzino: OneDrive potrebbe
            # essere ancora a metà sincronizzazione
            print("  Attendo che la copia sia completa...")
            stabile = False
            while not stabile:
                time.sleep(ATTESA_STABILE)
                verifica = istantanea()
                stabile = (verifica == attuale)
                attuale = verifica

            rigenera(password)
            precedente = attuale
    except KeyboardInterrupt:
        print("\n  Sorveglianza interrotta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
