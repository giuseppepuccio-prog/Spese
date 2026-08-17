"""Riconosce dove hai comprato (portale) e come hai pagato (strumento).

Sono due cose diverse e vanno tenute separate:
  - "PAYPAL *BONPRIXSRL"  -> portale BonPrix, strumento PayPal
  - "SUMUP*IN PRATI SRL"  -> negozio fisico che usa SumUp come POS: nessun portale
  - "AMAZON.IT*R060A3S14" -> portale Amazon (il codice e' l'ordine, va ignorato)

Il prefisso di un processore di pagamento non implica un acquisto online:
3CPAYMENT, SumUp, Dojo, Rapyd e simili stanno nei negozi fisici.
"""
import re

# prefissi dei processori: <sigla>*<venditore reale>
PREFISSI_PAGAMENTO = [
    (r"^PAYPAL\s*\*\s*", "PayPal"),
    (r"^MGP\s*\*\s*", "Mangopay"),
    (r"^HPY\s*\*\s*", "HiPay"),
    (r"^SUMUP\s*\*\s*", "SumUp"),
    (r"^3CPAYMENT\s*\*\s*", "3C Payment"),
    (r"^CKO\s*\*\s*", "Checkout.com"),
    (r"^RAPYD\s*\*\s*", "Rapyd"),
    (r"^DOJO\s*\*\s*", "Dojo"),
    (r"^SQ\s*\*\s*", "Square"),
    (r"^IZ\s*\*\s*", "iZettle"),
    (r"^ZETTLE\s*\*\s*", "Zettle"),
    (r"^VIVA\s*\*\s*", "Viva Wallet"),
    (r"^AXEPTA\s*\*\s*", "Axepta"),
    (r"^MYPOS\s*\*\s*", "myPOS"),
    (r"^SATISPAY\s*\*\s*", "Satispay"),
    (r"^NEXI\s*\*\s*", "Nexi"),
    (r"^STRIPE\s*\*\s*", "Stripe"),
    (r"^KLARNA\s*\*?\s*", "Klarna"),
    (r"^SCALAPAY\s*\*?\s*", "Scalapay"),
]

# Portali di acquisto: (nome mostrato, pattern, tipo).
# Il tipo tiene separati mondi che non vanno sommati: un hotel su Booking
# non e' shopping, e sommarlo agli acquisti falserebbe la lettura.
# L'ordine conta: il primo riscontro vince.
PORTALI = [
    ("Amazon",        r"\bAMAZON\b|\bAMZN\b|AMAZON\.IT|AMZN MKTP", "Shopping online"),
    ("Veepee",        r"VEEPEE|VENTE\s*PRIVEE|VENTEPRIVEE", "Shopping online"),
    ("BonPrix",       r"BONPRIX", "Shopping online"),
    ("ePrice",        r"\bEPRICE\b", "Shopping online"),
    ("Vinted",        r"\bVINTED\b", "Shopping online"),
    ("eBay",          r"\bEBAY\b", "Shopping online"),
    ("Zalando",       r"ZALANDO", "Shopping online"),
    ("Shein",         r"\bSHEIN\b", "Shopping online"),
    ("Temu",          r"\bTEMU\b", "Shopping online"),
    ("AliExpress",    r"ALIEXPRESS|\bALIBABA\b", "Shopping online"),
    ("Yoox",          r"\bYOOX\b|\bOUTLETICI\b", "Shopping online"),
    ("Asos",          r"\bASOS\b", "Shopping online"),
    ("Subito",        r"\bSUBITO\.IT\b", "Shopping online"),
    ("Wish",          r"\bWISH\.COM\b", "Shopping online"),
    ("Decathlon",     r"DECATHLON", "Shopping online"),
    ("Leroy Merlin",  r"LEROYMERLIN|LEROY MERLIN", "Shopping online"),
    ("IKEA",          r"\bIKEA\b", "Shopping online"),
    ("Booking",       r"BOOKING\.COM|BOOKING HOLDINGS|HOTEL ON BOOKING", "Viaggi online"),
    ("Airbnb",        r"AIRBNB", "Viaggi online"),
    ("Expedia",       r"EXPEDIA|HOTELS\.COM|AGODA", "Viaggi online"),
    ("App Store",     r"ITUNES|APPSTORE|ITUNESAPPST|APPLE\.COM/BILL", "Store digitali"),
    ("Google Play",   r"GOOGLE\s*PLAY|GOOGLE\s*\*", "Store digitali"),
    ("PlayStation Store", r"PLAYSTATION|\bPSN\b", "Store digitali"),
    ("Steam",         r"\bSTEAM(GAMES|POWERED)?\b", "Store digitali"),
]
TIPO_PORTALE = {nome: tipo for nome, _, tipo in PORTALI}

# strumenti riconoscibili anche senza prefisso
STRUMENTI_DIRETTI = [
    ("Satispay", r"SATISPAY"),
    ("PayPal", r"\bPAYPAL\b"),
]

RE_CODICE_ORDINE = re.compile(
    r"\*?\s*[A-Z0-9]{8,}\d[A-Z0-9]*$|\s+\d{9,}$", re.I)


def _ripulisci(nome: str) -> str:
    """Toglie il codice d'ordine finale: senza, ogni acquisto Amazon
    sembrerebbe un negozio diverso."""
    nome = RE_CODICE_ORDINE.sub("", nome or "").strip()
    return re.sub(r"\s{2,}", " ", nome).strip(" -*")


def analizza(t) -> None:
    """Popola portale, strumento e venditore. Modifica t."""
    grezzo = (t.merchant or t.descrizione or "").strip()
    testo = grezzo.upper()

    strumento = ""
    venditore = grezzo
    for pattern, nome in PREFISSI_PAGAMENTO:
        if re.match(pattern, testo):
            strumento = nome
            venditore = re.sub(pattern, "", testo, flags=re.I).strip()
            break

    if not strumento:
        for nome, pattern in STRUMENTI_DIRETTI:
            if re.search(pattern, testo):
                strumento = nome
                break

    venditore = _ripulisci(venditore)
    t.venditore = venditore.title() if venditore.isupper() else venditore
    t.strumento = strumento

    # il portale si cerca sul venditore reale, non sul prefisso del POS
    da_esaminare = f"{venditore} {testo}"
    for nome, pattern, tipo in PORTALI:
        if re.search(pattern, da_esaminare, re.I):
            t.portale = nome
            t.tipo_portale = tipo
            return
    t.portale = ""
    t.tipo_portale = ""


def riepilogo(transazioni: list) -> dict:
    """Totali per portale e per strumento, piu' la serie mensile online."""
    per_portale, per_strumento, per_mese, per_tipo = {}, {}, {}, {}
    for t in transazioni:
        if t.escludi or t.importo >= 0 or t.macro in ("Entrate", "Risparmio"):
            continue
        importo = -t.importo
        if t.portale:
            tipo = TIPO_PORTALE.get(t.portale, "Shopping online")
            voce = per_portale.setdefault(
                t.portale, {"portale": t.portale, "tipo": tipo, "totale": 0.0,
                            "movimenti": 0, "categorie": {}, "primo": t.data,
                            "ultimo": t.data})
            voce["totale"] += importo
            voce["movimenti"] += 1
            voce["primo"] = min(voce["primo"], t.data)
            voce["ultimo"] = max(voce["ultimo"], t.data)
            voce["categorie"][t.categoria] = \
                voce["categorie"].get(t.categoria, 0.0) + importo
            per_tipo[tipo] = per_tipo.get(tipo, 0.0) + importo
            mese = per_mese.setdefault(t.data[:7], {})
            mese[tipo] = mese.get(tipo, 0.0) + importo
        if t.strumento:
            per_strumento[t.strumento] = per_strumento.get(t.strumento, 0.0) + importo

    for v in per_portale.values():
        v["scontrino_medio"] = round(v["totale"] / max(v["movimenti"], 1), 2)
        v["totale"] = round(v["totale"], 2)
        v["categorie"] = {k: round(x, 2) for k, x in
                          sorted(v["categorie"].items(), key=lambda i: -i[1])[:5]}

    return {
        "portali": sorted(per_portale.values(), key=lambda v: -v["totale"]),
        "per_tipo": [{"tipo": k, "totale": round(v, 2)} for k, v in
                     sorted(per_tipo.items(), key=lambda i: -i[1])],
        "strumenti": [{"nome": k, "totale": round(v, 2)} for k, v in
                      sorted(per_strumento.items(), key=lambda i: -i[1])],
        "mensile_online": [
            {"mese": k, **{t: round(x, 2) for t, x in v.items()}}
            for k, v in sorted(per_mese.items())],
    }
