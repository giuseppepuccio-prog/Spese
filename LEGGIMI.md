# Le mie spese — guida

App personale che unisce le spese **American Express** e **Fineco** in un unico
posto, le categorizza e le mostra su smartphone.

## Come è fatta

```
Estratti conto (sul PC)              Sito (su GitHub Pages)
  00. Amex\*.xlsx  ─┐
                    ├─> build.py ─> data.enc (cifrato) ─> index.html
  01. Fineco\*.pdf ─┘                                      su telefono
```

I dati **non escono mai in chiaro**: `build.py` li cifra con AES-256 usando la
tua password. Su GitHub finisce solo un file illeggibile; la decifratura avviene
nel browser del telefono.

## Uso quotidiano

**Aggiungere nuovi estratti conto**
1. Metti i file in una qualsiasi sottocartella di
   `OneDrive\Documenti\07. Spese Personali`. **Tutte le sottocartelle vengono
   lette**: gli Excel come estratti carta, i PDF come estratto del conto.
   Per una carta nuova basta creare una cartella, senza toccare il codice.
2. Doppio clic su **`aggiorna.bat`** e digita la password.
3. Pubblica: `git add -A && git commit -m "aggiorna" && git push`

Puoi ricaricare gli stessi file quante volte vuoi: i movimenti già presenti
vengono riconosciuti e non duplicati.

**Le carte vengono distinte da sole**: il nome ("Amex Oro", "Amex Platino") e
le ultime cifre si leggono dall'intestazione del file. Se hai più di due conti
compare in alto un filtro per scegliere quale guardare.

**Inviare gli estratti via e-mail**
Amex e Fineco non allegano nulla alle loro mail (mandano un link al portale).
Il flusso è: scarichi il file dal portale, lo **inoltri a te stesso** con la
parola `spese` nell'oggetto, e `aggiorna.bat` lo raccoglie da solo.
Al primo avvio `raccogli_email.py` crea `data\email_config.json` e spiega come
generare la password per app di Google.

**Provare in casa senza pubblicare** — doppio clic su `prova_in_locale.bat`.

## Le regole di classificazione

| Regola | Comportamento |
|---|---|
| Addebito Amex sul conto Fineco | escluso, altrimenti conteresti tutto due volte |
| Spesa all'estero in valuta non euro | Vacanze (prova certa di presenza fisica) |
| Spesa estera su PayPal, Amazon, Booking… | **non** vacanza: è solo la sede legale |
| Alberghi a Roma | Lavoro SACE |
| Ristoranti a Roma | da rivedere: scegli pranzo o cena dal telefono |
| Bonifici ricorrenti a te stesso | Risparmio, non spesa |

Le regole sono in chiaro in `spese/categorie.py`, in italiano: modificale pure.

## Acquisti sui portali

Oltre alla categoria, ogni spesa porta due informazioni indipendenti:

- **portale** — *dove* hai comprato: Amazon, Veepee, BonPrix, Booking…
- **strumento** — *come* hai pagato: PayPal, Satispay, SumUp…

Sono cose diverse e non vanno confuse. `PAYPAL *BONPRIXSRL` è un acquisto su
**BonPrix** pagato con **PayPal**. Al contrario `SUMUP*`, `3CPAYMENT*`,
`DOJO*` e `CKO*` sono terminali POS di **negozi fisici**: trattarli come
e-commerce gonfierebbe il totale degli acquisti online.

I portali sono divisi in *Shopping online*, *Viaggi online* e *Store
digitali*, perché sommare un hotel su Booking agli acquisti Amazon
darebbe un numero senza significato. Le regole stanno in `spese/portali.py`.

**Perché i ristoranti di Roma vanno rivisti a mano** — né Amex né Fineco
riportano l'orario della transazione, quindi pranzo e cena sono
indistinguibili. La scelta la fai tu con un tocco, una volta sola.

## Aggiornamento automatico

Doppio clic su **`sorveglia.bat`**: chiede la password una volta, poi resta in
ascolto. Appena copi un nuovo estratto in una qualsiasi sottocartella, il sito
si rigenera da solo — non devi lanciare nulla.

- Attende che il file smetta di cambiare prima di leggerlo, così un estratto
  ancora in sincronizzazione su OneDrive non viene letto a metà.
- La password puoi salvarla: viene cifrata con **DPAPI di Windows**, quindi
  resta leggibile solo dal tuo utente su questo PC. Per revocarla, cancella
  `data\password.protetta`.

Per farlo partire da solo all'accesso a Windows: premi `Win+R`, scrivi
`shell:startup`, e metti in quella cartella un collegamento a `sorveglia.bat`.

## Classificare le spese dal telefono

Nell'app, sezione **Rivedi**, ci sono due schede:

- **Da classificare** — le spese che le regole non riconoscono, raggruppate
  **per esercente** e ordinate per importo. Scegli la categoria una volta e
  vale per tutti i movimenti di quel negozio, anche quelli futuri.
- **Casi dubbi** — i ristoranti di Roma, dove va deciso pranzo o cena.

Per rendere definitive le scelte:
1. In fondo alla sezione, *Scarica regole esercenti* e *Scarica correzioni singole*
2. Copia `regole_personali.json` e `override.json` in `SpeseApp\data\`
3. Al prossimo aggiornamento vengono applicate da sole

Puoi anche scrivere `data\regole_personali.json` a mano:

```json
{
  "NOME ESERCENTE": "Spesa alimentare",
  "ALTRO NEGOZIO": "Shopping"
}
```

Basta che il testo compaia nella descrizione del movimento. Le regole per
esercente battono quelle automatiche; le correzioni sul singolo movimento
battono tutto.

## Pubblicare su GitHub (una volta sola)

```bash
cd C:\Users\giuse\SpeseApp
git init
git add -A
git commit -m "prima versione"
git branch -M main
git remote add origin https://github.com/TUO-UTENTE/spese.git
git push -u origin main
```

Poi su GitHub: **Settings → Pages → Source: Deploy from a branch →
Branch: main, cartella `/docs`**.

La cartella del sito si chiama `docs` per obbligo di GitHub Pages, che
pubblica soltanto dalla radice del repository o da una cartella con quel
nome esatto: altri nomi non compaiono nemmeno nell'elenco.

Il `.gitignore` esclude già gli estratti originali e i dati in chiaro: su
GitHub va solo il file cifrato. **Verifica sempre con `git status` che non
compaiano file `.pdf`, `.xlsx` o `.json` prima di pubblicare.**

## I tuoi dati non stanno nel codice

Nome, e-mail, IBAN e città abituali stanno in `data\config_personale.json`,
che il `.gitignore` esclude: su GitHub finisce solo il codice, che da solo
non dice nulla di te. Il modello da compilare è
`config_personale.esempio.json`.

Se quel file manca il programma funziona lo stesso, ma perde le regole che
dipendono da quei valori: riconoscimento dei mutui dall'IBAN, distinzione fra
trasferte familiari e vacanze, esclusione dei giroconti verso te stesso.

## Limiti noti

- **Serve una password lunga.** Il sito è pubblico: la sicurezza sta tutta nella
  password. Almeno 12 caratteri, non usata altrove.
- **Mesi senza estratto Fineco** vengono esclusi dai calcoli di risparmio,
  perché mostrerebbero le spese senza lo stipendio.
- **Le spese contanti non compaiono**: nessuna banca le vede.
- Il riconoscimento del viaggio richiede almeno 3 spese estere ravvicinate e
  80 € complessivi, così un caffè in aeroporto non diventa una vacanza.
