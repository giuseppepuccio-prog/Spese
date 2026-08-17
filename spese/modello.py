"""Modello dati comune ad Amex e Fineco."""
from dataclasses import dataclass, field, asdict
import hashlib
import re


@dataclass
class Transazione:
    data: str = ""              # ISO yyyy-mm-dd, data in cui la spesa e' avvenuta
    data_registrazione: str = ""  # data contabile (Fineco: data operazione banca)
    descrizione: str = ""       # testo grezzo dell'estratto conto
    merchant: str = ""          # esercente ripulito
    citta: str = ""
    paese: str = ""             # codice/nome paese come riportato dalla fonte
    importo: float = 0.0        # negativo = uscita, positivo = entrata
    fonte: str = ""             # "amex" | "fineco"
    conto: str = ""             # es. "Amex Platino", "Fineco c/c"
    riferimento: str = ""       # id transazione della fonte, se presente
    categoria_fonte: str = ""   # categoria gia' fornita da Amex
    file_origine: str = ""
    valuta_estera: bool = False   # pagato in valuta non euro
    dettagli_valuta: str = ""     # importo originale, commissione, cambio

    # popolati dalla categorizzazione
    categoria: str = ""
    macro: str = ""             # Ordinario | Vacanze | Lavoro SACE
    portale: str = ""           # Amazon, Veepee, BonPrix... dove hai comprato
    tipo_portale: str = ""      # Shopping online | Viaggi online | Store digitali
    strumento: str = ""         # PayPal, Satispay, SumUp... come hai pagato
    venditore: str = ""         # esercente reale, ripulito dai prefissi dei POS
    viaggio: str = ""           # id viaggio, se la spesa appartiene a un viaggio
    da_rivedere: bool = False
    motivo_revisione: str = ""
    escludi: bool = False       # giroconti, pagamenti carta: non sono spesa reale
    motivo_esclusione: str = ""

    @property
    def id(self) -> str:
        """Impronta stabile: stessa transazione => stesso id, anche da file diversi."""
        if self.riferimento:
            base = f"{self.fonte}|{self.riferimento}"
        else:
            base = (f"{self.fonte}|{self.data}|{self.importo:.2f}|"
                    f"{_norm(self.descrizione)}")
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()


# sigle che devono restare maiuscole quando si normalizza una citta'
SIGLE = {"RM", "MI", "TO", "NA", "PA", "BO", "FI", "VE", "GE", "BA", "CT",
         "UK", "US", "NL", "DE", "FR", "ES", "CH", "AT", "BE", "SE"}


# Abbreviazioni che i PDF Fineco producono troncando i nomi lunghi.
ESPANSIONI = {
    "montalto di c": "Montalto di Castro",
    "montalto di cas": "Montalto di Castro",
    "montalto di castr": "Montalto di Castro",
    "s montalto di c": "Montalto di Castro",
    "piancastagn": "Piancastagnaio",
    "piancastagnai": "Piancastagnaio",
    "trezzano sul na": "Trezzano sul Naviglio",
    "trezzano s n": "Trezzano sul Naviglio",
    "sesto san g": "Sesto San Giovanni",
    "san giuliano mi": "San Giuliano Milanese",
    "san donato mi": "San Donato Milanese",
    "cesano bosc": "Cesano Boscone",
    "gioia t": "Gioia Tauro",
    "reggio c": "Reggio Calabria",
    "san zenone al": "San Zenone al Lambro",
    "castel san g": "Castel San Giovanni",
}

# Nel campo "città" Amex infila anche URL e numeri verdi: non sono luoghi.
RE_NON_CITTA = re.compile(
    r"^\s*(www\.|https?:)|\.(com|it|net|org)\b|^\d[\d\s\-/]{5,}$|^\+?\d{6,}$",
    re.I)


def citta_normalizzata(citta: str) -> str:
    """Amex scrive "ROMA", Fineco "Roma": senza uniformarle la stessa città
    comparirebbe due volte nei raggruppamenti, con importi divisi a metà."""
    c = re.sub(r"\s+", " ", (citta or "")).strip(" .,-")
    if not c or RE_NON_CITTA.search(c):
        return ""
    # gli esercenti francesi antepongono il CAP: "84vedene", "93saint-denis"
    c = re.sub(r"^\d{2,5}\s*[/-]?\s*(?=[A-Za-z])", "", c).strip(" .,-/")
    if not c or c.isdigit():
        return ""
    if c.upper() in SIGLE:
        return c.upper()
    # una città di una o due lettere è un residuo di troncatura, non un nome
    if len(c) <= 2:
        return ""
    esteso = ESPANSIONI.get(c.lower())
    if esteso:
        return esteso
    minuscole = {"di", "de", "del", "della", "da", "dei", "san", "santa",
                 "sul", "sui", "al", "in", "a", "e", "the", "of", "on"}
    parole = c.lower().split()
    fuori = []
    for i, p in enumerate(parole):
        fuori.append(p if (i > 0 and p in minuscole) else p.capitalize())
    return " ".join(fuori)
