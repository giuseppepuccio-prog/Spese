"""Categorizzazione delle spese.

Tre livelli:
  1. CATEGORIA  (Ristoranti, Trasporti, Spesa alimentare, ...)
  2. MACRO      (Ordinario | Vacanze | Lavoro SACE)
  3. VIAGGIO    (le spese di vacanza vicine nel tempo diventano un viaggio)

Le regole sono volutamente in chiaro e in italiano: puoi modificarle a mano.
Le correzioni fatte dall'app hanno sempre la precedenza (vedi override.json).
"""
import re
from datetime import date, timedelta

from . import config

# Il nome del titolare serve a riconoscere i bonifici verso se stessi, ma non
# deve stare nel codice: arriva da data/config_personale.json.
_TITOLARE = re.escape(config.TITOLARE.upper()) if config.TITOLARE else ""
_NOMI_FAMILIARI = "|".join(re.escape(f.upper()) for f in config.FAMILIARI)
_RE_FAMILIARI = (
    (_NOMI_FAMILIARI + "|" if _NOMI_FAMILIARI else "")
    + (rf"BEN:\s*(?!{_TITOLARE})|BENEFICIARIO:\s*(?!{_TITOLARE})"
       if _TITOLARE else r"BEN:\s+[A-Z]")
)

# ---------------------------------------------------------------------------
# Piattaforme: la sede legale NON indica dove hai speso.
# Verificato sui dati: PayPal risulta Lussemburgo, Booking Olanda,
# Dott perfino Cile. Escluderle evita centinaia di false "vacanze".
# ---------------------------------------------------------------------------
PIATTAFORME = (
    "PAYPAL", "AMAZON", "AMZN", "BOOKING HOLDINGS", "GYMPASS", "WELLHUB",
    "OPENAI", "GOOGLE", "APPLE", "ITUNES", "NETFLIX", "SPOTIFY", "DISNEY",
    "AUDIBLE", "MICROSOFT", "ADOBE", "DROPBOX", "LINKEDIN", "MEta", "VINTED",
    "SATISPAY", "SUMUP", "NEXI", "STRIPE", "REVOLUT", "AIRALO", "PLAYSTATION",
    "STEAM", "UBER EATS", "DELIVEROO", "GLOVO", "JUSTEAT", "JUST EAT",
    "CVMAKER", "QUILLBOT", "RAKUTEN", "TRENITALIA", "ITALO", "FILX",
    "DOTT", "CKO*DOTT", "PLAYTOMIC", "PERFECTDRAFT", "MGP*VINTED",
)

# Booking merita un trattamento a parte: e' un intermediario, ma un hotel
# prenotato li' e' comunque un alloggio. Il paese pero' non e' attendibile.
INTERMEDIARI_VIAGGIO = ("BOOKING.COM", "HOTEL ON BOOKING", "AIRBNB", "EXPEDIA",
                        "HOTELS.COM", "TRIVAGO", "AGODA")

# ---------------------------------------------------------------------------
# Regole di categoria: (categoria, espressione regolare sul testo)
# Il primo riscontro vince, quindi l'ordine conta.
# ---------------------------------------------------------------------------
REGOLE_CATEGORIA: list[tuple[str, str]] = [
    # La causale cambia nel tempo: "Sace Spa - Conto Stipendi" fino a marzo
    # 2026, poi "Sace S.p.a. - Servizi Assicurativi del Commercio Estero".
    # Cercare la sola sigla evita di perdere lo stipendio a ogni riformulazione.
    ("Stipendio",            r"\bSACE\b|CONTO STIPENDI|EMOLUMENTI|\bSTIPENDIO\b|"
                             r"\bCEDOLINO\b|TREDICESIMA"),
    ("Entrate famiglia",     r"\bINPS\b|ASSEGNO UNICO"),
    # I bonifici verso conti propri non sono tutti uguali: alcuni pagano i
    # mutui, uno ricarica Satispay. Li distinguiamo dall'IBAN di destinazione
    # (vedi CONTI_DESTINAZIONE) prima di applicare queste regole generiche.
    ("Risparmio e accantonamenti",
                             r"PIANO BONIFICO|PIANO DI ACCUMULO|\bPAC\b|"
                             + (rf"BEN:\s*{_TITOLARE}|BENEFICIARIO:\s*{_TITOLARE}"
                                if _TITOLARE else r"BONIFICO A PROPRIO FAVORE")),
    ("Investimenti",         r"\bBTP\b|CED\.SU|RIT\.CED|DOSSIER|\bFONDI\b|OBBLIGAZ|\bAZIONI\b|\bETF\b"),
    # "Protocollo Delega" e' come Fineco registra i pagamenti F24 e i tributi
    ("Imposte e bolli",      r"IMPOSTA DI BOLLO|\bIMPOSTA\b|\bBOLLO\b|\bF24\b|\bTASSE\b|"
                             r"\bTARI\b|\bIMU\b|PROTOCOLLO DELEGA|DELEGA N|TRIBUT|"
                             r"AGENZIA ENTRATE|\bCANONE RAI\b"),
    ("Assicurazioni",        r"GENERALI|UNIPOL|ALLIANZ|AXA\b|ZURICH|CATTOLICA|REALE MUTUA|"
                             r"ASSICURA|POLIZZA|VERTI|GENIALLOYD|PRIMA\.IT"),
    ("Commissioni bancarie", r"CANONE MENSILE|SPESE CONTO|QUOTA ASSOCIATIVA|QUOTA ANNUALE|"
                             r"COMMISSIONI CONTO|SPESE DI TENUTA|INTERESSI PASSIVI|"
                             r"ADDEBITO PENALE|MANCATO PAGAMENTO|SPESE INSOLUTO|"
                             r"COMMISSIONE SDD|SPESE INVIO"),
    ("Donazioni",            r"TELETHON|FONDAZIONE|DONAZIONE|CROCE ROSSA|UNICEF|\bAIRC\b"),
    ("Alloggio",             r"HOTEL|ALBERGO|\bB&B\b|BED AND BREAKFAST|OSTELLO|RESORT|AGRITURISM|"
                             r"BOOKING|AIRBNB|\bMOXY\b|MERCURE|\bIBIS\b|HILTON|MARRIOTT|"
                             r"NOVOTEL|SHERATON|BEST WESTERN|\bNH \b|RESIDENCE|LOCANDA|"
                             r"RIFUGIO|BAITA|ALPLINA|ALPINA"),
    ("Spesa alimentare",     r"SUPERMERCAT|ESSELUNGA|COOP\b|CONAD|CARREFOUR|LIDL|EUROSPIN|PENNY|"
                             r"PAM\b|BENNET|IPERAL|TIGROS|SAINSBURY|TESCO|ALIMENTARI|MACELLERIA|"
                             r"PANIFICIO|FRUTTA|MERCATO"),
    ("Ristoranti e bar",     r"RISTORANT|TRATTORIA|OSTERIA|PIZZER|BAR\b|CAFF|CAFE|BISTRO|"
                             r"PASTICCERIA|GELATER|BRACER|SUSHI|BURGER|MCDONALD|STARBUCKS|"
                             r"DELIVEROO|GLOVO|UBER EATS|JUST ?EAT|FAST FOOD|ENOTECA|BIRRER"),
    # I distributori si presentano con mille nomi: ADS, "filling station",
    # "staz. servizio", "aire de". Riconoscere le formule evita di doverli
    # classificare uno per uno ogni volta che si fa benzina in un posto nuovo.
    ("Carburante",           r"\bENI\b|\bIP\b|\bQ8\b|TAMOIL|\bESSO\b|SHELL|\bAGIP\b|BENZIN|"
                             r"CARBURANT|DISTRIBUTORE|AREA SERVIZIO|AREA DI SERVIZIO|"
                             r"\bADS\b|FILLING STATION|STAZ\.?\s*SERVIZIO|STAZIONE SERVIZIO|"
                             r"\bAIRE DE\b|PETROL|\bBP\b|KEROPUR|\bTOTAL\b|REPSOL|CEPSA"),
    # Il contante sparisce dalla tracciabilita': tenerlo a parte evita di
    # attribuirlo a caso. Va prima dei trasporti perche' la descrizione del
    # prelievo contiene "N° Atm", che altrimenti verrebbe letto come ATM Milano.
    ("Prelievi contante",    r"PRELEVAMENTO|\bPRELIEVO\b|CASH WITHDRAWAL|ANTICIPO CONTANTI"),
    # I confini di parola sono indispensabili: senza, "DOTT" catturava
    # "dottore" e "prodotti", e "AVIS" qualsiasi parola che lo contenesse.
    # I radiotaxi si presentano con mille sigle ("Radiotaxi EP 28", "Taxiblu
    # 4040", "6645 - Lione 50"): serve il prefisso, non la parola isolata.
    ("Trasporti",            r"RADIOTAX|TAXIBLU|TAXI\s?\d|SAMARCANDA|\bTAXI\b|"
                             r"\b6645\s*-|\b3570\b|APPTAXI|WETAXI|ITTAXI|"
                             r"\bUBER\b|FREENOW|\bITALO\b|TRENITALIA|TRENORD|"
                             r"\bATM\b(?!\s*\d)|\bATAC\b|\bMETRO\b|AUTOSTRAD|TELEPASS|"
                             r"PARCHEGG|PARKING|AUTONOLEGG|NOLEGG|RENT A CAR|\bHERTZ\b|"
                             r"\bAVIS\b|\bSIXT\b|COOLTRA|\bDOTT\b|\bLIME\b|\bBIRD\b|"
                             r"LUL TICKET|AEROPORT|RYANAIR|EASYJET|ITA AIRWAYS|ALITALIA|"
                             r"LUFTHANSA|AIR FRANCE|GRANDI NAVI|TRAGHETT|FLIXBUS|\bGNV\b"),
    ("Salute e farmacia",    r"FARMACI|PARAFARM|MEDIC|DENTIST|ANALISI|LABORATORIO|OSPEDAL|"
                             r"POLIAMBULATOR|OTTIC|FISIOTERAP|VETERINAR"),
    ("Sport e benessere",    r"PALESTRA|GYM|FITNESS|WELLHUB|GYMPASS|PISCINA|PADEL|TENNIS|"
                             r"PLAYTOMIC|SCI\b|SKIPASS|SCUOLA SCI|KRISTAL|CENTRO SPORTIV"),
    ("Abbonamenti digitali", r"NETFLIX|SPOTIFY|DISNEY|OPENAI|CHATGPT|GOOGLE|ICLOUD|APPLE|ITUNES|"
                             r"AUDIBLE|MICROSOFT|ADOBE|DROPBOX|PRIME VIDEO|DAZN|SKY\b|NOW TV|"
                             r"QUILLBOT|AIRALO|SUBSCR|CVMAKER|LINKEDIN"),
    ("Figli e istruzione",   r"SCUOLA|ASILO|NIDO|UNIVERSIT|LIBRI|CARTOLER|MENSA|CENTRO ESTIV|"
                             r"BABY|GIOCATTOL|CHICCO|PRENATAL"),
    # i confini di parola sono necessari: senza, "IREN" catturava "Siren Coffee"
    ("Casa e utenze",        r"\bENEL\b|\bA2A\b|\bHERA\b|\bIREN\b|\bACEA\b|SORGENIA|ILLUMIA|"
                             r"EDISON|\bTIM SPA\b|\bTIM\b|VODAFONE|WINDTRE|FASTWEB|\bILIAD\b|"
                             r"CONDOMINI|AFFITTO|\bMUTUO\b|\bIKEA\b|LEROY|BRICO|\bOBI\b|"
                             r"MANUTENZ|IDRAULIC|ELETTRICIST|MULTISERVIZI|\bAMA\b|RIFIUTI"),
    ("Tempo libero",         r"CINEMA|TEATRO|MUSEO|MOSTRA|CONCERT|TICKETONE|VIVATICKET|"
                             r"EFTELING|STUDIO TOUR|PARCO|ZOO|ACQUARIO|LIBRERIA|FELTRINELLI|"
                             r"MONDADORI|PLAYSTATION|STEAM|NINTENDO"),
    ("Shopping",             r"\bZARA\b|H&M|\bOVS\b|UNIQLO|DECATHLON|\bNIKE\b|ADIDAS|RINASCENTE|"
                             r"\bCOIN\b|ABBIGLIAMENT|CALZATUR|SCARPE|VINTED|AMAZON|AMZN|"
                             r"MEDIAWORLD|UNIEURO|APPLE STORE|PROFUMER|SEPHORA|DOUGLAS|"
                             r"HERMES|BONPRIX|EPRICE|VEEPEE|ZALANDO|SHEIN|TEMU|IPERCOOP"),
    # --- aggiunte dopo l'analisi dei tuoi movimenti reali -----------------
    ("Servizi professionali", r"STUDIO |NOTAIO|AVVOCAT|COMMERCIALIST|GEOMETRA|REGISTERSPA|"
                              r"ARUBA|REGISTER\.IT|CONSULEN"),
    ("Trasferimenti familiari", _RE_FAMILIARI),
    ("Pagamenti Satispay",   r"SATISPAY"),
]

# Merchant riconosciuti uno per uno: piu' precisi delle regole generiche.
# Aggiungine liberamente, oppure usa "regole_personali.json" dall'app.
MERCHANT_NOTI = {
    "Ristoranti e bar": ("IL FARO 2.0", "SINGITA", "COL D'ORCIA",
                         "DE SLOOTHAAK", "HUISBROUWERIJ", "ALP LAGHET",
                         "RICCIARDI", "BEANY GREEN", "COMPTOIR", "ZACCAGNINO",
                         "DEROMA FARINE", "LA MENAGERE", "HAMASEI", "IL CHIANTI",
                         "PASTICCERIA", "DOLCE MONTALTO", "SIREN COFFEE",
                         # aggiunti dopo l'analisi dei movimenti reali
                         "JUST IN CASE", "CAPOCORRENTE", "CHOP GLASGOW",
                         "GINGER FOOD", "FRANCO MANCA", "ITSU", "MOZZARELLINO",
                         "MIND THE GAP", "DOPPIO MALTO", "ARAMARK", "FAURO 2016",
                         "IN PRATI", "MAN SOLON", "ARMONIA DI ANGELI",
                         "LA BOTTEGA DEI MAESTRI", "TABACCHERIA", "NTV ON BOARD",
                         "GRUPPO ILLIRIA", "DORECA",
                         "PRET A MANGER", "BENUGO", "BAGEL FACTORY", "COSTA ",
                         "CASTLE ARMS", "GREAT GLEN", "CAFFE NERO"),
    "Spesa alimentare": ("MEGLIO FRESCO", "CALLMEWINE", "CO-OP", "MARKET DI SEBASTIANI",
                         "MEGA MALL", "CANTINE", "ENOTECA",
                         "MORRISONS", "WAITROSE", "MARKS & SPENCER", "ALDI", "ASDA"),
    "Trasporti":       ("DISCOVERCARS", "PARKING LUDOVISI", "AREA SERVIZIO",
                        "JPMORGANMOB", "JP MORGAN MOBILITY", "GNV AURIGA",
                        "CARONTE TOU", "CAPITAL CARS", "EMV CARTE ITALIANE",
                        "EASYPARK", "TELEPASS"),
    "Sport e benessere": ("VALLE BIANCA", "SPORT MIX", "SIMPLE LIFE", "CST ITALIA",
                          "SCUOLA KRISTAL", "VIRGINACTI", "VIRGIN ACTIVE",
                          "QCTERME", "QC TERME"),
    "Abbonamenti digitali": ("ANTHROPIC", "CLAUDE", "GAMMA.APP", "FIVERR",
                             "NETWORK LINE", "RCS MEDIAGROUP", "CORRIERE",
                             "IL SOLE 24", "REPUBBLICA"),
    "Alloggio":        ("PARADU TUSCAN", "SANDMAN", "MOXY", "ROSA ALPLINA",
                        "THE INN AT", "ARDGOUR"),
    "Tempo libero":    ("PERFECTDRAFT", "EFTELING", "JUVENTUS", "TICKET SHOP",
                        "STADIO", "MUSEO",
                        "WARNER BROS", "WB STUDIO", "HISTORIC ENVIRONMENT",
                        "NATIONAL TRUST", "HOUSE OF SCOTLAND"),
    "Shopping":        ("CAMICISSIMA", "EXCEED FOOTWEAR", "VALIGERIA", "MEDIA WORLD",
                        "GEOX", "LILLYWHITES", "OVS ", "PIAZZA ITALIA",
                        "COTSWOLD OUTDOOR", "SOCKNESS", "PHONE CLINIC"),
    "Figli e istruzione": ("BIMBIEBIMBE", "BIMBI E BIMBE"),
    # allarme e vigilanza: spesa di casa a tutti gli effetti
    "Casa e utenze":   ("VERISURE", "SICURITALIA", "IVRI", "ALLARME",
                        "SERVIZIO ELETTRICO", "ENEL ENERGIA", "PLENITUDE",
                        "ACQUEDOTTO", "GAS NATURAL", "ESTRA", "AGSM"),
}

# Categorie Amex native -> nostre categorie (segnale gia' affidabile)
MAPPA_AMEX = {
    "ristoranti": "Ristoranti e bar",
    "fast food": "Ristoranti e bar",
    "supermercato": "Spesa alimentare",
    "alimentari vari": "Spesa alimentare",
    "alberghi": "Alloggio",
    "autonoleggio": "Trasporti",
    "taxi - noleggio auto con conducente": "Trasporti",
    "farmacia": "Salute e farmacia",
    "vendita servizi via internet": "Abbonamenti digitali",
    "goods": "Shopping",
    "abbigliamento": "Shopping",
    "trasporti": "Trasporti",
    "carburante": "Carburante",
    "divertimento": "Tempo libero",
}

# Categorie che rappresentano una presenza fisica: solo queste possono
# diventare "Vacanze" quando avvengono all'estero.
CATEGORIE_FISICHE = {
    "Alloggio", "Ristoranti e bar", "Spesa alimentare", "Trasporti",
    "Carburante", "Tempo libero", "Shopping", "Sport e benessere",
}

# Categorie che a Roma valgono come trasferta di lavoro
LAVORO_ALLOGGIO = {"Alloggio"}
LAVORO_PASTI = {"Ristoranti e bar"}

PAESI_ITALIA = {"ITALY", "ITALIA", "IT", ""}

# Le localita' in cui vivi o torni abitualmente: qui non sei in viaggio.
# I valori arrivano da data/config_personale.json, fuori dal codice.
CITTA_ABITUALI = config.CITTA_ABITUALI

# Trasferte familiari ricorrenti: non sono vacanze, ma vanno viste a parte
# perche' hanno un ritmo e un peso propri.
CITTA_FAMIGLIA = config.CITTA_FAMIGLIA
MACRO_FAMIGLIA = config.MACRO_FAMIGLIA


def citta_famiglia(citta: str) -> bool:
    return (citta or "").strip().lower() in CITTA_FAMIGLIA


# Le navi verso la Sicilia sono il viaggio verso la famiglia: biglietti e
# consumazioni a bordo vanno sotto quella voce.
RE_NAVI = re.compile(
    r"\bGNV\b|GRANDI NAVI|M-?N GNV|CARONTE|TIRRENIA|\bSNAV\b|LIBERTY LINES|"
    r"SIREMAR|\bMOBY\b|GRIMALDI|TRAGHET|TRAGHETTILINES|NAVIGAZIONE|"
    r"COMPAGNIA DELLE ISOLE|ALILAURO|USTICA LINES", re.I)

# Compagnie che collegano la Sicilia: qui la destinazione e' implicita.
RE_COMPAGNIE_SICILIA = re.compile(
    r"\bGNV\b|GRANDI NAVI|M-?N GNV|CARONTE|SIREMAR|LIBERTY LINES|\bSNAV\b|"
    r"ALILAURO|USTICA LINES|TIRRENIA", re.I)

# Porti di altre rotte: una nave che parte o arriva qui non va in Sicilia.
# Traghettilines vende per tutte le destinazioni, quindi conta il porto.
PORTI_ALTRE_ROTTE = {
    "portoferraio", "piombino", "rio marina", "cavo", "porto azzurro",
    "olbia", "golfo aranci", "porto torres", "cagliari", "arbatax",
    "livorno", "capraia", "giglio", "porto santo stefano", "ponza",
    "ischia", "capri", "procida", "lipari", "vulcano", "salina",
}


def e_nave(t) -> bool:
    return bool(RE_NAVI.search(f"{t.merchant} {t.descrizione}"))


def e_nave_per_sicilia(t) -> bool:
    """Vero solo per le traversate da e per la Sicilia.

    I traghetti per l'Elba o la Sardegna sono vacanze: metterli sotto le
    trasferte familiari gonfierebbe una voce con spese di tutt'altra natura.
    """
    if not e_nave(t):
        return False
    if (t.citta or "").strip().lower() in PORTI_ALTRE_ROTTE:
        return False
    return bool(RE_COMPAGNIE_SICILIA.search(f"{t.merchant} {t.descrizione}"))
# Comuni dell'hinterland che valgono come la citta' di riferimento
HINTERLAND = {
    "assago", "corsico", "vanzaghello", "sesto san giovanni", "rozzano",
    "buccinasco", "cesano boscone", "trezzano sul naviglio", "opera",
    "san donato milanese", "san giuliano milanese", "segrate", "pieve emanuele",
    "fiumicino", "ostia", "ciampino", "pomezia", "guidonia",
}


def citta_abituale(citta: str) -> bool:
    c = (citta or "").strip().lower()
    if not c:
        return False
    return c in CITTA_ABITUALI or c in HINTERLAND

RE_VALUTA_ESTERA = re.compile(r"foreign spend amount", re.I)


# ---------------------------------------------------------------------------
# Bonifici verso conti propri: l'IBAN di destinazione dice cosa sono davvero.
# Riconoscerli dall'importo sarebbe fragile (le rate cambiano); l'IBAN no.
# ---------------------------------------------------------------------------
CONTI_DESTINAZIONE = config.CONTI_DESTINAZIONE
# quando l'IBAN non e' leggibile nel PDF, l'importo ricorrente basta a capire
IMPORTI_RICORRENTI = {
    float(k): v for k, v in (config.DATI.get("importi_ricorrenti") or {}).items()
}

RE_IBAN = re.compile(r"IBAN:\s*([A-Z]{2}[0-9A-Z]{7,})", re.I)


def _conto_destinazione(t) -> str:
    """Categoria di un bonifico verso un conto proprio, se riconoscibile."""
    testo = t.descrizione or ""
    if not re.search(r"PIANO BONIFICO|BEN:|BENEFICIARIO:", testo, re.I):
        return ""

    m = RE_IBAN.search(testo)
    if m:
        iban = m.group(1).upper()
        for prefisso, categoria in CONTI_DESTINAZIONE.items():
            if iban.startswith(prefisso):
                return categoria
        return ""   # IBAN noto ma non fra quelli mappati: resta accantonamento

    # IBAN illeggibile: ci si affida all'importo, ma solo per i casi ricorrenti
    return IMPORTI_RICORRENTI.get(round(abs(t.importo), 2), "")


def _testo(t) -> str:
    return f"{t.merchant} {t.descrizione} {t.categoria_fonte}".upper()


def e_piattaforma(t) -> bool:
    testo = _testo(t)
    return any(p.upper() in testo for p in PIATTAFORME)


def e_intermediario_viaggio(t) -> bool:
    testo = _testo(t)
    return any(p in testo for p in INTERMEDIARI_VIAGGIO)


def valuta_estera(t) -> bool:
    """Pagato in valuta non-euro: prova certa di presenza fisica all'estero."""
    if getattr(t, "valuta_estera", False):
        return True
    return bool(RE_VALUTA_ESTERA.search(getattr(t, "dettagli_valuta", "") or ""))


def estero_fisico(t) -> bool:
    """Vero se la spesa e' avvenuta fisicamente fuori dall'Italia."""
    if valuta_estera(t):
        return True
    paese = (t.paese or "").strip().upper()
    if paese in PAESI_ITALIA:
        return False
    # paese estero ma merchant-piattaforma: sede legale, non luogo reale
    if e_piattaforma(t) and not e_intermediario_viaggio(t):
        return False
    return True


def a_roma(t) -> bool:
    testo = f"{t.citta} {t.merchant} {t.descrizione}".upper()
    return bool(re.search(r"\bROMA\b|\bROME\b", testo))


def regola_personale(t, regole_personali: dict | None = None):
    """Cerca una tua regola per questo movimento.

    Il valore puo' essere una stringa (solo categoria) oppure un oggetto
    {"categoria": ..., "macro": ...} quando serve forzare anche il
    raggruppamento: un negozio a Palermo puo' essere shopping ordinario,
    non una spesa della trasferta familiare.
    """
    testo = _testo(t)
    for chiave, valore in (regole_personali or {}).items():
        if chiave.startswith("_"):
            continue    # righe di commento nel file delle regole
        if chiave.upper() in testo:
            if isinstance(valore, dict):
                return valore.get("categoria", ""), valore.get("macro", "")
            return valore, ""
    return "", ""


def assegna_categoria(t, regole_personali: dict | None = None) -> str:
    """Ordine: tue regole personali, esercenti noti, categoria Amex, regole generali."""
    testo = _testo(t)

    # 1. le regole che hai creato tu dall'app vincono su tutto
    categoria, _macro = regola_personale(t, regole_personali)
    if categoria:
        return categoria

    # 2. esercenti riconosciuti singolarmente
    for categoria, nomi in MERCHANT_NOTI.items():
        if any(n in testo for n in nomi):
            return categoria

    # 3. bonifici verso conti propri: mutui e ricariche, letti dall'IBAN
    destinazione = _conto_destinazione(t)
    if destinazione:
        return destinazione

    # 4. categoria fornita da Amex
    nativa = (t.categoria_fonte or "").strip().lower().split("\n")[0].strip()
    if nativa in MAPPA_AMEX:
        return MAPPA_AMEX[nativa]

    # 4. regole generali
    for categoria, pattern in REGOLE_CATEGORIA:
        if re.search(pattern, testo, re.I):
            return categoria

    if t.importo > 0:
        return "Altre entrate"
    return "Da classificare"


# movimenti che non sono spese: storni, respinti, giroconti
RE_NON_SPESA = re.compile(
    r"PAGAMENTO RESPINTO|STORNO|INSOLUTO|RIACCREDITO|ANNULL", re.I)


def categorizza(t, regole_personali: dict | None = None) -> None:
    """Assegna categoria, macro e segnala i casi da rivedere. Modifica t."""
    t.categoria = assegna_categoria(t, regole_personali)

    # una macro imposta a mano vince su ogni deduzione automatica
    _cat, macro_forzata = regola_personale(t, regole_personali)
    if macro_forzata and not t.escludi:
        t.macro = macro_forzata
        t.da_rivedere = False
        return

    if not t.escludi and RE_NON_SPESA.search(_testo(t)):
        t.escludi = True
        t.motivo_esclusione = "Storno o pagamento respinto (non è una spesa)"

    if t.escludi:
        t.macro = "Escluso"
        return

    # i soldi che metti da parte non sono spesa: sono risparmio
    if t.categoria == "Risparmio e accantonamenti":
        t.macro = "Risparmio"
        return

    if t.importo > 0 and t.categoria in ("Stipendio", "Entrate famiglia",
                                         "Investimenti", "Altre entrate"):
        t.macro = "Entrate"
        return

    # --- Roma: trasferta di lavoro SACE ---------------------------------
    if a_roma(t):
        if t.categoria in LAVORO_ALLOGGIO:
            t.macro = "Lavoro SACE"
            return
        if t.categoria in LAVORO_PASTI:
            # senza orario nei dati non si distingue pranzo da cena:
            # decidi tu dall'app, la scelta viene poi ricordata
            t.macro = "Lavoro SACE"
            t.da_rivedere = True
            t.motivo_revisione = "Ristorante a Roma: è cena di lavoro o pranzo?"
            return

    # --- Navi per la Sicilia: sono il viaggio verso la famiglia ----------
    if e_nave(t):
        t.categoria = "Trasporti"
        if e_nave_per_sicilia(t):
            t.macro = MACRO_FAMIGLIA
            return
        t.macro = "Ordinario"   # altre rotte: sarà il rilevatore viaggi a decidere
        return

    # --- Trasferte familiari: né vacanza né spesa di casa ----------------
    if citta_famiglia(t.citta) and t.categoria in CATEGORIE_FISICHE:
        t.macro = MACRO_FAMIGLIA
        return

    # --- Estero fisico: vacanza -----------------------------------------
    if estero_fisico(t) and t.categoria in CATEGORIE_FISICHE:
        t.macro = "Vacanze"
        return

    # Un hotel prenotato via Booking puo' essere ovunque: il raggruppamento
    # in viaggi lo assegnera' alla vacanza giusta, se ce n'e' una.
    if e_intermediario_viaggio(t) and t.categoria == "Alloggio":
        t.macro = "Ordinario"
        t.da_rivedere = True
        t.motivo_revisione = "Alloggio prenotato online: vacanza o lavoro?"
        return

    t.macro = "Ordinario"


# ---------------------------------------------------------------------------
# Raggruppamento in viaggi
# ---------------------------------------------------------------------------
def _nome_luogo(gruppo: list) -> str:
    """Un itinerario tocca piu' citta': chiamarlo con una sola sarebbe fuorviante.

    Un viaggio Edimburgo-Highlands-Glasgow-Londra non e' "London".
    """
    from collections import Counter

    # la citta' di un portale e' la sua sede legale, non il luogo del viaggio
    citta = Counter(t.citta.strip() for t in gruppo
                    if t.citta and len(t.citta.strip()) > 2
                    and not e_intermediario_viaggio(t) and not e_piattaforma(t))
    if not citta:
        paesi = [t.paese for t in gruppo if t.paese]
        return max(set(paesi), key=paesi.count).title() if paesi else "Viaggio"

    totale = sum(citta.values())
    prime = citta.most_common(3)
    # se una citta' domina, e' un soggiorno in un posto solo
    if prime[0][1] / totale >= 0.6 or len(prime) == 1:
        return prime[0][0]
    if len(prime) == 2:
        return f"{prime[0][0]} e {prime[1][0]}"
    return f"{prime[0][0]}, {prime[1][0]} e {prime[2][0]}"


def fuori_sede(t) -> bool:
    """Spesa fisica in una localita' italiana diversa da quelle abituali.

    Il portale non dice dove sei: un hotel prenotato su Booking risulta
    ad Amsterdam, e OpenAI a Dublino. Vanno esclusi, altrimenti sembrerebbe
    che tu sia all'estero ogni mese.
    """
    if not t.citta or e_piattaforma(t) or e_intermediario_viaggio(t):
        return False
    if t.categoria not in CATEGORIE_FISICHE:
        return False
    if citta_famiglia(t.citta):
        return False    # trasferta familiare, non vacanza
    return not citta_abituale(t.citta)


def _giorni_consecutivi(gruppo: list) -> int:
    """Massimo numero di giorni distinti in una permanenza continua.

    E' il criterio che separa un viaggio da una spesa di passaggio: ad Andalo
    stai giorni di fila, ad Assago passi una volta ogni tanto.
    """
    giorni = sorted({date.fromisoformat(t.data) for t in gruppo})
    if not giorni:
        return 0
    massimo = attuale = 1
    for prec, cur in zip(giorni, giorni[1:]):
        if (cur - prec) <= timedelta(days=2):
            attuale += 1
            massimo = max(massimo, attuale)
        else:
            attuale = 1
    return massimo


def _abbonamenti_ricorrenti(transazioni: list) -> set[str]:
    """Esercenti che addebitano sempre la stessa cifra a intervalli regolari.

    Sono abbonamenti, non spese fatte sul posto: la citta' che riportano e'
    la sede della societa'. Senza questo controllo un servizio americano da
    59,99 EUR al trimestre risulterebbe come un viaggio in Florida ogni volta.
    """
    per_merchant: dict[str, list] = {}
    for t in transazioni:
        if t.escludi or t.importo >= 0 or not t.merchant:
            continue
        chiave = re.sub(r"\s{2,}.*$", "", t.merchant.upper()).strip()
        per_merchant.setdefault(chiave, []).append(t)

    ricorrenti = set()
    for chiave, elenco in per_merchant.items():
        if len(elenco) < 3:
            continue
        importi = {round(abs(t.importo), 2) for t in elenco}
        mesi = {t.data[:7] for t in elenco}
        # stesso importo esatto, in mesi diversi: e' una sottoscrizione
        if len(importi) == 1 and len(mesi) >= 3:
            ricorrenti.add(chiave)
    return ricorrenti


def rileva_viaggi(transazioni: list, giorni_pausa: int = 3,
                  spesa_minima: float = 80.0,
                  spesa_minima_italia: float = 150.0) -> list[dict]:
    """Spese vicine nel tempo lontano da casa formano un viaggio.

    Sono candidate sia le spese all'estero sia quelle italiane fuori dalle
    localita' abituali. Un intervallo superiore a `giorni_pausa` chiude il
    viaggio in corso; i gruppi troppo piccoli vengono sciolti, perche' erano
    spese isolate (un caffe' in autostrada), non una vacanza.
    """
    abbonamenti = _abbonamenti_ricorrenti(transazioni)

    def e_abbonamento(t) -> bool:
        chiave = re.sub(r"\s{2,}.*$", "", (t.merchant or "").upper()).strip()
        return chiave in abbonamenti

    # un abbonamento non e' mai una spesa di viaggio, ovunque abbia sede
    for t in transazioni:
        if t.macro == "Vacanze" and e_abbonamento(t):
            t.macro = "Ordinario"

    for t in transazioni:
        if t.escludi or t.importo >= 0 or t.viaggio:
            continue
        if t.macro in ("Entrate", "Risparmio", "Lavoro SACE", "Vacanze",
                       MACRO_FAMIGLIA):
            continue
        if fuori_sede(t) and not e_abbonamento(t):
            t.macro = "Vacanze"

    candidate = sorted(
        [t for t in transazioni if t.macro == "Vacanze" and t.data],
        key=lambda t: t.data)
    if not candidate:
        return []

    # Il raggruppamento e' temporale. Dividere prima per localita' sembrava
    # piu' preciso, ma spezzava gli itinerari — un viaggio in auto tocca una
    # citta' al giorno — e i frammenti finivano sotto le soglie minime.
    # Le localita' danno il nome al viaggio, non lo delimitano.
    gruppi: list[list] = [[candidate[0]]]
    for t in candidate[1:]:
        prec = date.fromisoformat(gruppi[-1][-1].data)
        cur = date.fromisoformat(t.data)
        if (cur - prec) <= timedelta(days=giorni_pausa):
            gruppi[-1].append(t)
        else:
            gruppi.append([t])

    viaggi = []
    for gruppo in gruppi:
        totale = -sum(t.importo for t in gruppo if t.importo < 0)
        troppo_piccolo = totale < spesa_minima or len(gruppo) < 3

        # Per l'Italia serve una permanenza: due giorni di fila oppure un
        # pernottamento. Senza, pranzo e benzina in autostrada nello stesso
        # giorno diventerebbero un "viaggio".
        solo_italia = all(
            (t.paese or "").strip().upper() in PAESI_ITALIA for t in gruppo)
        if solo_italia and not troppo_piccolo:
            ha_alloggio = any(t.categoria == "Alloggio" for t in gruppo)
            if _giorni_consecutivi(gruppo) < 2 and not ha_alloggio:
                troppo_piccolo = True
            elif totale < spesa_minima_italia and not ha_alloggio:
                troppo_piccolo = True

        if troppo_piccolo:
            for t in gruppo:  # non era una vacanza: spesa isolata
                t.macro = "Ordinario"
            continue

        inizio, fine = gruppo[0].data, gruppo[-1].data
        luogo = _nome_luogo(gruppo)

        vid = f"{inizio}_{re.sub(r'[^A-Za-z0-9]+', '', luogo)[:20] or 'viaggio'}"
        for t in gruppo:
            t.viaggio = vid
        viaggi.append({
            # niente .title() qui: _nome_luogo ha gia' normalizzato le citta',
            # e riapplicarlo trasformerebbe la "e" di congiunzione in "E"
            "id": vid, "luogo": luogo, "inizio": inizio, "fine": fine,
            "totale": round(totale, 2), "movimenti": len(gruppo),
        })

    # Assorbe nel viaggio le spese rimaste fuori ma avvenute nelle stesse date:
    #  - alloggi prenotati online, il cui paese non e' attendibile
    #  - spese estere di categoria non riconosciuta (un negozio locale
    #    sconosciuto resta "Da classificare", ma se sei a Glasgow in quei
    #    giorni fa parte del viaggio a tutti gli effetti)
    for t in transazioni:
        if t.viaggio or t.escludi or t.importo >= 0:
            continue
        if t.macro in ("Entrate", "Risparmio", "Lavoro SACE", MACRO_FAMIGLIA):
            continue

        e_alloggio_online = (t.categoria == "Alloggio" and e_intermediario_viaggio(t))
        e_estero = estero_fisico(t)
        if not (e_alloggio_online or e_estero):
            continue
        # un abbonamento non diventa spesa di viaggio solo perche' l'addebito
        # e' caduto nei giorni in cui eri via
        if e_abbonamento(t):
            continue

        for v in viaggi:
            if v["inizio"] <= t.data <= v["fine"]:
                t.viaggio, t.macro = v["id"], "Vacanze"
                t.da_rivedere = False
                v["totale"] = round(v["totale"] - t.importo, 2)
                v["movimenti"] += 1
                break

    return viaggi
