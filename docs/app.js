/* Le mie spese — app di sola lettura, i dati arrivano cifrati.
   Nessuna libreria esterna: i grafici sono SVG costruiti a mano. */
'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let DATI = null;             // contenuto decifrato
let CORREZIONI = {};         // scelte su singoli movimenti
let REGOLE = {};             // esercente -> categoria, vale per tutti i suoi movimenti
let VISTA_RIVEDI = 'classificare';
let QUANTI_MOSTRARE = 25;
let PAGINA = 'panoramica';
let CATEGORIA_APERTA = null;
let PORTALE_APERTO = null;
let DIMENSIONE = 'mese';        // come raggruppare dentro una categoria
let GRUPPO_APERTO = null;       // gruppo espanso al secondo livello
let SOTTOGRUPPO_APERTO = null;  // sottogruppo espanso fino ai movimenti
let VIAGGIO_APERTO = null;

const eur = (n, dec = 0) => new Intl.NumberFormat('it-IT', {
  style: 'currency', currency: 'EUR',
  minimumFractionDigits: dec, maximumFractionDigits: dec }).format(n || 0);
const MESI = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu',
              'lug', 'ago', 'set', 'ott', 'nov', 'dic'];
const meseBreve = (m) => { const [a, x] = m.split('-'); return MESI[+x - 1] + ' ' + a.slice(2); };
/* "2026-08-16" si legge male a colpo d'occhio: meglio "16 ago 2026" */
const dataIt = (iso, conAnno = true) => {
  if (!iso || iso.length < 10) return iso || '';
  const [a, m, g] = iso.split('-');
  return `${+g} ${MESI[+m - 1]}${conAnno ? ' ' + a : ''}`;
};
const colore = (i) => getComputedStyle(document.documentElement)
  .getPropertyValue('--serie-' + (i + 1)).trim() || '#2a78d6';

/* ================= 1. SBLOCCO E DECIFRATURA ================= */

async function derivaChiave(password, salt) {
  const materiale = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 250000, hash: 'SHA-256' },
    materiale, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
}

async function decifra(buffer, password) {
  const dati = new Uint8Array(buffer);
  const salt = dati.slice(0, 16);
  const iv = dati.slice(16, 28);
  const cifrato = dati.slice(28);
  const chiave = await derivaChiave(password, salt);
  const compresso = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, chiave, cifrato);
  // i dati viaggiano compressi: molti meno megabyte da scaricare in mobilita'
  const flusso = new Blob([compresso]).stream()
    .pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(flusso).text());
}

/* Verifica cosa manca PRIMA di tentare: un messaggio generico manderebbe
   a cercare una password sbagliata quando il problema e' un altro. */
function diagnosiAmbiente() {
  if (!window.isSecureContext || !(window.crypto && crypto.subtle)) {
    return {
      titolo: 'Serve una connessione sicura',
      testo: 'Il browser consente di decifrare i dati solo su indirizzi ' +
        'HTTPS oppure su localhost. Stai aprendo la pagina su ' +
        `<b>${location.protocol}//${location.host}</b>, quindi la funzione è ` +
        'disattivata. Una volta pubblicato su GitHub Pages (che è HTTPS) ' +
        'funzionerà. Per provarlo adesso dal telefono, avvia sul PC ' +
        '<code>prova_in_locale.bat</code>, che ora usa HTTPS.',
    };
  }
  if (typeof DecompressionStream === 'undefined') {
    return {
      titolo: 'Browser troppo datato',
      testo: 'Manca il supporto alla decompressione (DecompressionStream). ' +
        'Aggiorna il browser: serve Safari 16.4+, Chrome 80+ o Firefox 113+.',
    };
  }
  return null;
}

function mostraErrore(titolo, testo) {
  const box = $('#errore-sblocco');
  box.innerHTML = titolo ? `<b>${titolo}</b><br>${testo}` : testo;
  box.hidden = false;
}

async function sblocca(password, ricorda) {
  $('#errore-sblocco').hidden = true;

  const problema = diagnosiAmbiente();
  if (problema) { mostraErrore(problema.titolo, problema.testo); return; }

  $('#stato-sblocco').hidden = false;
  $('#btn-sblocca').disabled = true;
  try {
    let risposta;
    try {
      risposta = await fetch('data.enc', { cache: 'no-cache' });
    } catch (e) {
      throw new Error('RETE');
    }
    if (!risposta.ok) throw new Error('MANCA_FILE');
    const buffer = await risposta.arrayBuffer();
    if (buffer.byteLength < 64) throw new Error('MANCA_FILE');

    DATI = await decifra(buffer, password);

    if (ricorda) localStorage.setItem('spese_pw', password);
    else localStorage.removeItem('spese_pw');
    CORREZIONI = JSON.parse(localStorage.getItem('spese_correzioni') || '{}');
    REGOLE = JSON.parse(localStorage.getItem('spese_regole') || '{}');
    applicaCorrezioni();
    $('#sblocco').hidden = true;
    $('#app').hidden = false;
    avvia();
  } catch (e) {
    localStorage.removeItem('spese_pw');
    const codice = String(e && e.message || e);
    if (codice === 'RETE') {
      mostraErrore('Dati non raggiungibili',
        'Il file <code>data.enc</code> non è stato scaricato. Controlla che il ' +
        'PC che fa da server sia acceso e sulla stessa rete.');
    } else if (codice === 'MANCA_FILE') {
      mostraErrore('File dei dati assente',
        'Manca <code>data.enc</code>. Lancia <code>aggiorna.bat</code> sul PC.');
    } else if (e && (e.name === 'OperationError' || codice.includes('operation-specific'))) {
      // e' l'errore che AES-GCM restituisce quando la chiave non corrisponde
      mostraErrore('Password errata', 'Riprova: è la password che hai usato ' +
        'in <code>aggiorna.bat</code> quando hai generato i dati.');
    } else {
      mostraErrore('Non riesco ad aprire i dati', `Dettaglio tecnico: ${codice}`);
    }
  } finally {
    $('#stato-sblocco').hidden = true;
    $('#btn-sblocca').disabled = false;
  }
}

/* avviso immediato all'apertura, senza aspettare il tentativo */
(function preavviso() {
  const problema = diagnosiAmbiente();
  if (problema) {
    mostraErrore(problema.titolo, problema.testo);
    $('#btn-sblocca').disabled = true;
  }
})();

$('#form-sblocco').addEventListener('submit', (e) => {
  e.preventDefault();
  sblocca($('#password').value, $('#ricorda').checked);
});

/* Chiave stabile di un esercente: toglie il codice d'ordine finale ma resta
   una sottostringa del testo originale, cosi' la regola funziona anche in
   Python quando rigeneri il sito. */
function chiaveEsercente(t) {
  let v = (t.merchant || t.descrizione || '').toUpperCase().trim();
  v = v.replace(/\s{2,}.*$/, '');          // "NOME      CITTA" -> "NOME"
  v = v.replace(/\*[A-Z0-9]{6,}$/, '');    // codice ordine dopo l'asterisco
  v = v.replace(/\s+\d{6,}$/, '');         // codice numerico finale
  v = v.replace(/\s+CARTA N\..*$/i, '');
  return v.trim().slice(0, 40);
}

/* le correzioni salvate sul telefono valgono subito, senza rigenerare il sito */
function applicaCorrezioni() {
  const per_id = new Map(DATI.transazioni.map((t) => [t.id, t]));

  // 1. regole per esercente: valgono per tutti i suoi movimenti
  const chiavi = Object.keys(REGOLE);
  if (chiavi.length) {
    DATI.transazioni.forEach((t) => {
      const testo = `${t.merchant} ${t.descrizione}`.toUpperCase();
      for (const k of chiavi) {
        if (testo.includes(k)) {
          t.categoria = REGOLE[k];
          if (t.categoria === 'Pranzo') t.macro = 'Ordinario';
          t.da_rivedere = false;
          break;
        }
      }
    });
  }

  // 2. correzioni sul singolo movimento: hanno l'ultima parola
  for (const [id, c] of Object.entries(CORREZIONI)) {
    const t = per_id.get(id);
    if (!t) continue;
    if (c.categoria) t.categoria = c.categoria;
    if (c.macro) t.macro = c.macro;
    t.da_rivedere = false;
  }
}

/* ================= 2. FILTRI ================= */

function periodoSelezionato() {
  const scelta = $('#periodo').value;
  const mesi = (DATI.statistiche.mensili || []).map((m) => m.mese).sort();
  if (!mesi.length) return { da: '0000-00', a: '9999-99' };
  const ultimo = mesi[mesi.length - 1];

  if (scelta === 'tutto') return { da: mesi[0], a: ultimo };
  if (scelta === 'anno') return { da: ultimo.slice(0, 4) + '-01', a: ultimo };
  if (scelta === 'custom') {
    return { da: $('#da-mese').value || mesi[0], a: $('#a-mese').value || ultimo };
  }
  const n = parseInt(scelta, 10);
  const idx = Math.max(0, mesi.length - n);
  return { da: mesi[idx], a: ultimo };
}

function movimentiFiltrati() {
  const { da, a } = periodoSelezionato();
  const macro = $('#filtro-macro').value;
  const conto = $('#filtro-conto').value;
  return DATI.transazioni.filter((t) => {
    if (t.escludi) return false;
    const m = t.data.slice(0, 7);
    if (m < da || m > a) return false;
    if (macro && t.macro !== macro) return false;
    if (conto && t.conto !== conto) return false;
    return true;
  });
}

/* Le serie mensili vengono ricostruite dai movimenti filtrati, non prese
   pre-calcolate: altrimenti i grafici resterebbero fermi mentre le tessere
   cambiano, e il filtro sembrerebbe non funzionare. */
function mesiFiltrati() {
  const { da, a } = periodoSelezionato();
  const macro = $('#filtro-macro').value;
  const perMese = {};

  // parti da tutti i mesi del periodo, cosi' i vuoti restano visibili
  DATI.statistiche.mensili.forEach((m) => {
    if (m.mese >= da && m.mese <= a) {
      perMese[m.mese] = { mese: m.mese, spese: 0, entrate: 0, accantonato: 0,
                          risparmio: 0, completo: m.completo, per_macro: {} };
    }
  });

  const conto = $('#filtro-conto').value;
  DATI.transazioni.forEach((t) => {
    if (t.escludi) return;
    if (conto && t.conto !== conto && t.macro !== 'Entrate') return;
    const m = t.data.slice(0, 7);
    const riga = perMese[m];
    if (!riga) return;

    if (t.macro === 'Entrate') {
      // il filtro per tipo di spesa non deve cancellare le entrate:
      // servono a calcolare quanto resta ogni mese
      if (t.importo > 0) riga.entrate += t.importo;
      return;
    }
    if (t.macro === 'Risparmio') {
      if (t.importo < 0) riga.accantonato += -t.importo;
      return;
    }
    if (macro && t.macro !== macro) return;
    if (t.importo < 0) {
      riga.spese += -t.importo;
      riga.per_macro[t.macro] = (riga.per_macro[t.macro] || 0) + -t.importo;
    }
  });

  return Object.values(perMese)
    .map((r) => ({ ...r, risparmio: r.entrate - r.spese }))
    .sort((a, b) => a.mese.localeCompare(b.mese));
}

/* ================= 3. GRAFICI (SVG) ================= */

const NS = 'http://www.w3.org/2000/svg';
const el = (tag, attr = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attr)) n.setAttribute(k, v);
  return n;
};

function scalaBella(max) {
  if (max <= 0) return { max: 100, passo: 25 };
  const grezzo = max / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(grezzo)));
  const passo = [1, 2, 2.5, 5, 10].map((x) => x * mag).find((x) => x >= grezzo) || mag * 10;
  return { max: Math.ceil(max / passo) * passo, passo };
}

function creaSvg(contenitore, altezza) {
  contenitore.innerHTML = '';
  const larghezza = Math.max(contenitore.clientWidth || 320, 280);
  const svg = el('svg', {
    viewBox: `0 0 ${larghezza} ${altezza}`, width: larghezza, height: altezza,
    role: 'img',
  });
  contenitore.appendChild(svg);
  return { svg, W: larghezza, H: altezza };
}

function assi(svg, W, H, margini, scala, etichette) {
  const { alto, basso, sx, dx } = margini;
  const utileH = H - alto - basso;
  for (let v = 0; v <= scala.max + 0.001; v += scala.passo) {
    const y = alto + utileH - (v / scala.max) * utileH;
    svg.appendChild(el('line', {
      x1: sx, x2: W - dx, y1: y, y2: y, class: 'griglia-linea',
    }));
    const t = el('text', { x: sx - 6, y: y + 4, class: 'asse', 'text-anchor': 'end' });
    t.textContent = v >= 1000 ? (v / 1000) + 'k' : v;
    svg.appendChild(t);
  }
  // etichette dei mesi: diradate se sono troppe per lo spazio
  const passo = Math.ceil(etichette.length / Math.max(3, Math.floor((W - sx - dx) / 52)));
  etichette.forEach((testo, i) => {
    if (i % passo !== 0 && i !== etichette.length - 1) return;
    const x = sx + (utileW(W, margini) / Math.max(etichette.length, 1)) * (i + 0.5);
    const t = el('text', { x, y: H - basso + 15, class: 'asse', 'text-anchor': 'middle' });
    t.textContent = testo;
    svg.appendChild(t);
  });
}
const utileW = (W, m) => W - m.sx - m.dx;

function legenda(contenitore, voci) {
  contenitore.innerHTML = '';
  voci.forEach((v) => {
    const d = document.createElement('span');
    d.className = 'voce-legenda';
    d.innerHTML = `<i class="chiave" style="background:${v.colore}"></i>${v.nome}`;
    contenitore.appendChild(d);
  });
}

/* --- tooltip condiviso --- */
const tip = $('#tooltip');
function mostraTip(x, y, html) {
  tip.innerHTML = html;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let px = x + 12, py = y - r.height - 12;
  if (px + r.width > innerWidth - 8) px = innerWidth - r.width - 8;
  if (py < 8) py = y + 18;
  tip.style.left = Math.max(8, px) + 'px';
  tip.style.top = py + 'px';
}
const nascondiTip = () => { tip.hidden = true; };
document.addEventListener('pointerdown', (e) => {
  if (!e.target.closest('.grafico')) nascondiTip();
});

/* --- grafico a linee: spese ed entrate --- */
function graficoAndamento() {
  const dati = mesiFiltrati();
  const box = $('#graf-andamento');
  if (!dati.length) { box.innerHTML = '<p class="muted piccolo">Nessun dato nel periodo.</p>'; return; }

  const m = { alto: 12, basso: 26, sx: 38, dx: 10 };
  const { svg, W, H } = creaSvg(box, 220);
  const uW = utileW(W, m), uH = H - m.alto - m.basso;
  const max = Math.max(...dati.map((d) => Math.max(d.spese, d.entrate)));
  const scala = scalaBella(max);
  assi(svg, W, H, m, scala, dati.map((d) => meseBreve(d.mese)));

  const px = (i) => m.sx + (uW / dati.length) * (i + 0.5);
  const py = (v) => m.alto + uH - (v / scala.max) * uH;
  const serie = [
    { nome: 'Spese', colore: colore(0), val: (d) => d.spese },
    { nome: 'Entrate', colore: colore(1), val: (d) => d.entrate },
  ];
  legenda($('#legenda-andamento'), serie);

  serie.forEach((s) => {
    const d = dati.map((v, i) => `${i ? 'L' : 'M'}${px(i)},${py(s.val(v))}`).join(' ');
    svg.appendChild(el('path', {
      d, fill: 'none', stroke: s.colore, 'stroke-width': 2,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round',
    }));
    dati.forEach((v, i) => {
      // anello del colore della superficie: i punti restano leggibili se si sovrappongono
      svg.appendChild(el('circle', {
        cx: px(i), cy: py(s.val(v)), r: 4, fill: s.colore,
        stroke: 'var(--superficie)', 'stroke-width': 2,
      }));
    });
  });

  // crosshair: una fascia invisibile per mese cattura tocco e passaggio del mouse
  const linea = el('line', { class: 'linea-base', y1: m.alto, y2: m.alto + uH, opacity: 0 });
  svg.appendChild(linea);
  dati.forEach((v, i) => {
    const zona = el('rect', {
      x: m.sx + (uW / dati.length) * i, y: m.alto,
      width: uW / dati.length, height: uH, fill: 'transparent',
    });
    const attiva = (e) => {
      linea.setAttribute('x1', px(i)); linea.setAttribute('x2', px(i));
      linea.setAttribute('opacity', 1);
      mostraTip(e.clientX, e.clientY,
        `<div class="riga"><b>${meseBreve(v.mese)}</b></div>` +
        serie.map((s) => `<div class="riga"><span><i class="chiave" style="display:inline-block;background:${s.colore}"></i> ${s.nome}</span><b>${eur(s.val(v))}</b></div>`).join('') +
        `<div class="riga"><span>Differenza</span><b>${eur(v.entrate - v.spese)}</b></div>`);
    };
    zona.addEventListener('pointerenter', attiva);
    zona.addEventListener('pointerdown', attiva);
    zona.addEventListener('pointermove', attiva);
    zona.addEventListener('pointerleave', () => { linea.setAttribute('opacity', 0); nascondiTip(); });
    svg.appendChild(zona);
  });
}

/* --- barre impilate: ordinario / vacanze / lavoro --- */
function graficoMacro() {
  const dati = mesiFiltrati();
  const box = $('#graf-macro');
  if (!dati.length) { box.innerHTML = '<p class="muted piccolo">Nessun dato nel periodo.</p>'; return; }

  const tipi = ['Ordinario', 'Vacanze', 'Lavoro SACE', 'Famiglia Palermo'];
  const serie = tipi.map((nome, i) => ({ nome, colore: colore(i) }));
  legenda($('#legenda-macro'), serie);

  const m = { alto: 12, basso: 26, sx: 38, dx: 10 };
  const { svg, W, H } = creaSvg(box, 200);
  const uW = utileW(W, m), uH = H - m.alto - m.basso;
  const tot = dati.map((d) => tipi.reduce((s, k) => s + (d.per_macro[k] || 0), 0));
  const scala = scalaBella(Math.max(...tot, 1));
  assi(svg, W, H, m, scala, dati.map((d) => meseBreve(d.mese)));

  const passo = uW / dati.length;
  const larg = Math.min(26, passo * 0.62);
  dati.forEach((d, i) => {
    let cumulato = 0;
    const x = m.sx + passo * (i + 0.5) - larg / 2;
    tipi.forEach((k, j) => {
      const v = d.per_macro[k] || 0;
      if (v <= 0) return;
      const h = (v / scala.max) * uH;
      const y = m.alto + uH - (cumulato / scala.max) * uH - h;
      // 2px di stacco fra i segmenti: si distinguono senza bordi
      svg.appendChild(el('rect', {
        x, y, width: larg, height: Math.max(1, h - 2),
        fill: colore(j), rx: 3,
      }));
      cumulato += v;
    });
    const zona = el('rect', { x: m.sx + passo * i, y: m.alto, width: passo, height: uH, fill: 'transparent' });
    const attiva = (e) => mostraTip(e.clientX, e.clientY,
      `<div class="riga"><b>${meseBreve(d.mese)}</b></div>` +
      tipi.map((k, j) => `<div class="riga"><span><i class="chiave" style="display:inline-block;background:${colore(j)}"></i> ${k}</span><b>${eur(d.per_macro[k] || 0)}</b></div>`).join(''));
    zona.addEventListener('pointerenter', attiva);
    zona.addEventListener('pointerdown', attiva);
    zona.addEventListener('pointerleave', nascondiTip);
    svg.appendChild(zona);
  });
}

/* --- barre sopra/sotto zero: quanto resta ogni mese --- */
function graficoRisparmio() {
  const dati = mesiFiltrati();
  const box = $('#graf-risparmio');
  if (!dati.length) { box.innerHTML = '<p class="muted piccolo">Nessun dato nel periodo.</p>'; return; }

  const m = { alto: 14, basso: 26, sx: 38, dx: 10 };
  const { svg, W, H } = creaSvg(box, 180);
  const uW = utileW(W, m), uH = H - m.alto - m.basso;
  const valori = dati.map((d) => d.risparmio);
  const estremo = Math.max(...valori.map(Math.abs), 1);
  const scala = scalaBella(estremo);
  const zero = m.alto + uH / 2;
  const py = (v) => zero - (v / scala.max) * (uH / 2);

  [scala.max, 0, -scala.max].forEach((v) => {
    svg.appendChild(el('line', {
      x1: m.sx, x2: W - m.dx, y1: py(v), y2: py(v),
      class: v === 0 ? 'linea-base' : 'griglia-linea',
    }));
    const t = el('text', { x: m.sx - 6, y: py(v) + 4, class: 'asse', 'text-anchor': 'end' });
    t.textContent = v >= 1000 ? (v / 1000) + 'k' : (v <= -1000 ? (v / 1000) + 'k' : v);
    svg.appendChild(t);
  });

  const passo = uW / dati.length;
  const larg = Math.min(24, passo * 0.6);
  dati.forEach((d, i) => {
    const x = m.sx + passo * (i + 0.5) - larg / 2;
    const v = d.risparmio;
    const h = Math.abs(v / scala.max) * (uH / 2);
    svg.appendChild(el('rect', {
      x, y: v >= 0 ? py(v) : zero, width: larg, height: Math.max(1, h),
      fill: v >= 0 ? 'var(--positivo)' : 'var(--critico)', rx: 3,
    }));
    const zona = el('rect', { x: m.sx + passo * i, y: m.alto, width: passo, height: uH, fill: 'transparent' });
    const attiva = (e) => mostraTip(e.clientX, e.clientY,
      `<div class="riga"><b>${meseBreve(d.mese)}</b></div>
       <div class="riga"><span>Entrate</span><b>${eur(d.entrate)}</b></div>
       <div class="riga"><span>Spese</span><b>${eur(d.spese)}</b></div>
       <div class="riga"><span>Resta</span><b>${eur(v)}</b></div>` +
      (d.accantonato ? `<div class="riga"><span>Messi da parte</span><b>${eur(d.accantonato)}</b></div>` : ''));
    zona.addEventListener('pointerenter', attiva);
    zona.addEventListener('pointerdown', attiva);
    zona.addEventListener('pointerleave', nascondiTip);
    svg.appendChild(zona);
  });

  const et = el('text', { x: m.sx, y: H - 4, class: 'asse' });
  et.textContent = 'sopra lo zero = hai risparmiato';
  svg.appendChild(et);
}

/* --- barre orizzontali: categorie --- */
function graficoCategorie() {
  const movimenti = movimentiFiltrati().filter((t) => t.importo < 0
    && t.macro !== 'Entrate' && t.macro !== 'Risparmio');
  const agg = {};
  movimenti.forEach((t) => { agg[t.categoria] = (agg[t.categoria] || 0) + -t.importo; });
  const voci = Object.entries(agg).map(([categoria, totale]) => ({ categoria, totale }))
    .sort((a, b) => b.totale - a.totale).slice(0, 14);

  const box = $('#graf-categorie');
  if (!voci.length) { box.innerHTML = '<p class="muted piccolo">Nessuna spesa nel periodo.</p>'; return; }

  const rigaH = 30, m = { alto: 4, basso: 4, sx: 0, dx: 0 };
  const { svg, W, H } = creaSvg(box, voci.length * rigaH + 8);
  const max = voci[0].totale;
  const larghezzaEtichetta = Math.min(140, Math.max(96, W * 0.36));
  const spazioCifra = 74;
  const uW = W - larghezzaEtichetta - spazioCifra;

  voci.forEach((v, i) => {
    const y = m.alto + i * rigaH;
    const nome = el('text', { x: 0, y: y + rigaH / 2 + 4, class: 'etichetta-diretta' });
    nome.textContent = v.categoria.length > 20 ? v.categoria.slice(0, 19) + '…' : v.categoria;
    svg.appendChild(nome);

    const w = Math.max(2, (v.totale / max) * uW);
    svg.appendChild(el('rect', {
      x: larghezzaEtichetta, y: y + 6, width: w, height: rigaH - 15,
      fill: colore(0), rx: 4,
    }));
    const cifra = el('text', {
      x: larghezzaEtichetta + w + 7, y: y + rigaH / 2 + 4, class: 'etichetta-diretta',
    });
    cifra.textContent = eur(v.totale);
    svg.appendChild(cifra);

    const zona = el('rect', { x: 0, y, width: W, height: rigaH, fill: 'transparent',
      style: 'cursor:pointer' });
    zona.addEventListener('click', () => { CATEGORIA_APERTA = v.categoria; disegnaCategorie(); });
    zona.addEventListener('pointerenter', (e) => {
      const q = movimenti.filter((t) => t.categoria === v.categoria).length;
      mostraTip(e.clientX, e.clientY,
        `<div class="riga"><b>${v.categoria}</b></div>
         <div class="riga"><span>Totale</span><b>${eur(v.totale, 2)}</b></div>
         <div class="riga"><span>Movimenti</span><b>${q}</b></div>
         <div class="riga muted piccolo">Tocca per i dettagli</div>`);
    });
    zona.addEventListener('pointerleave', nascondiTip);
    svg.appendChild(zona);
  });
}

/* ================= 4. PAGINE ================= */

function tessere() {
  const mov = movimentiFiltrati();
  const spese = mov.filter((t) => t.importo < 0 && !['Entrate', 'Risparmio'].includes(t.macro));
  const entrate = mov.filter((t) => t.macro === 'Entrate' && t.importo > 0);
  const messiDaParte = mov.filter((t) => t.macro === 'Risparmio' && t.importo < 0);
  const totSpese = spese.reduce((s, t) => s + -t.importo, 0);
  const totEntrate = entrate.reduce((s, t) => s + t.importo, 0);
  const nMesi = new Set(mov.map((t) => t.data.slice(0, 7))).size || 1;
  const saldo = totEntrate - totSpese;

  const vacanze = spese.filter((t) => t.macro === 'Vacanze').reduce((s, t) => s + -t.importo, 0);
  const dati = [
    { etichetta: 'Spese', valore: eur(totSpese), nota: `${eur(totSpese / nMesi)} al mese` },
    { etichetta: 'Entrate', valore: eur(totEntrate), nota: `${nMesi} mesi nel periodo` },
    { etichetta: 'Differenza', valore: eur(saldo), nota: saldo >= 0 ? 'in positivo' : 'in negativo',
      classe: saldo >= 0 ? 'pos' : 'neg' },
    { etichetta: 'Messi da parte', valore: eur(messiDaParte.reduce((s, t) => s + -t.importo, 0)),
      nota: vacanze ? `vacanze: ${eur(vacanze)}` : 'accantonamenti' },
  ];
  $('#tessere').innerHTML = dati.map((d) => `
    <div class="tessera">
      <div class="etichetta">${d.etichetta}</div>
      <div class="valore ${d.classe || ''}">${d.valore}</div>
      <div class="nota">${d.nota}</div>
    </div>`).join('');
}

/* --- barre affiancate: stesso mese, due anni a confronto --- */
function graficoConfronto() {
  const box = $('#graf-confronto');
  const scheda = $('#scheda-confronto');
  const perAnno = {};
  DATI.statistiche.mensili.forEach((m) => {
    const [anno, mese] = m.mese.split('-');
    (perAnno[anno] = perAnno[anno] || {})[mese] = m.spese;
  });
  const anni = Object.keys(perAnno).sort();
  if (anni.length < 2) { scheda.hidden = true; return; }
  scheda.hidden = false;

  const [precedente, corrente] = [anni[anni.length - 2], anni[anni.length - 1]];
  // solo i mesi in cui entrambi gli anni hanno dati: altrimenti il confronto mente
  const mesi = Object.keys(perAnno[corrente])
    .filter((m) => perAnno[precedente][m] !== undefined).sort();

  if (!mesi.length) {
    scheda.hidden = true;
    return;
  }

  const totC = mesi.reduce((s, m) => s + perAnno[corrente][m], 0);
  const totP = mesi.reduce((s, m) => s + perAnno[precedente][m], 0);
  const diff = totC - totP;
  const pct = totP ? (diff / totP * 100) : 0;
  $('#nota-confronto').innerHTML =
    `Sui ${mesi.length} mesi confrontabili hai speso <b>${eur(Math.abs(diff))}
     ${diff >= 0 ? 'in più' : 'in meno'}</b> del ${precedente}
     (${pct >= 0 ? '+' : ''}${pct.toFixed(0)}%).`;

  const serie = [
    { nome: precedente, colore: colore(0) },
    { nome: corrente, colore: colore(1) },
  ];
  legenda($('#legenda-confronto'), serie);

  const m = { alto: 12, basso: 26, sx: 38, dx: 10 };
  const { svg, W, H } = creaSvg(box, 200);
  const uW = utileW(W, m), uH = H - m.alto - m.basso;
  const scala = scalaBella(Math.max(...mesi.map((x) =>
    Math.max(perAnno[corrente][x], perAnno[precedente][x])), 1));
  assi(svg, W, H, m, scala, mesi.map((x) => MESI[+x - 1]));

  const passo = uW / mesi.length;
  const larg = Math.min(13, passo * 0.34);
  mesi.forEach((mese, i) => {
    const centro = m.sx + passo * (i + 0.5);
    [[precedente, -1], [corrente, 1]].forEach(([anno, lato], j) => {
      const v = perAnno[anno][mese];
      const h = (v / scala.max) * uH;
      // 2px di stacco fra le due barre dello stesso mese
      svg.appendChild(el('rect', {
        x: centro + (lato < 0 ? -larg - 1 : 1), y: m.alto + uH - h,
        width: larg, height: Math.max(1, h), fill: colore(j), rx: 3,
      }));
    });
    const zona = el('rect', { x: m.sx + passo * i, y: m.alto, width: passo,
      height: uH, fill: 'transparent' });
    const attiva = (e) => {
      const a = perAnno[precedente][mese], b = perAnno[corrente][mese];
      mostraTip(e.clientX, e.clientY,
        `<div class="riga"><b>${MESI[+mese - 1]}</b></div>
         <div class="riga"><span><i class="chiave" style="display:inline-block;background:${colore(0)}"></i> ${precedente}</span><b>${eur(a)}</b></div>
         <div class="riga"><span><i class="chiave" style="display:inline-block;background:${colore(1)}"></i> ${corrente}</span><b>${eur(b)}</b></div>
         <div class="riga"><span>Differenza</span><b>${b - a >= 0 ? '+' : ''}${eur(b - a)}</b></div>`);
    };
    zona.addEventListener('pointerenter', attiva);
    zona.addEventListener('pointerdown', attiva);
    zona.addEventListener('pointerleave', nascondiTip);
    svg.appendChild(zona);
  });
}

/* --- come si dividono le spese fra conto corrente e carte --- */
function ripartizioneConti() {
  const box = $('#scheda-conti');
  const spese = movimentiFiltrati().filter((t) => t.importo < 0
    && !['Entrate', 'Risparmio'].includes(t.macro));
  const agg = {};
  spese.forEach((t) => { agg[t.conto] = (agg[t.conto] || 0) + -t.importo; });
  const voci = Object.entries(agg).sort((a, b) => b[1] - a[1]);
  if (voci.length < 2) { box.hidden = true; return; }
  box.hidden = false;

  const totale = voci.reduce((s, v) => s + v[1], 0);

  // Fin dove arrivano i dati di ciascuna fonte: un estratto non ancora
  // emesso fa sembrare "sparite" spese che semplicemente non sono arrivate.
  const cop = DATI.statistiche.copertura_conti || {};
  const ultimoMese = Object.values(cop).reduce((m, c) => (c.a > m ? c.a : m), '');
  const indietro = Object.entries(cop)
    .filter(([, c]) => c.a < ultimoMese)
    .map(([nome, c]) => `<li><b>${nome}</b>: fino a ${meseBreve(c.a)}</li>`);

  box.innerHTML = `<h2>Dove passano le spese</h2>
    <p class="muted piccolo">Ripartizione fra conto corrente e carte nel periodo.</p>
    ${indietro.length ? `<div class="avviso-dati">
      <b>Attenzione ai mesi recenti.</b> Non tutte le fonti arrivano allo stesso
      punto: le spese pagate con questi conti dopo la data indicata non ci sono
      ancora, perché l'estratto non è stato emesso.
      <ul style="margin:6px 0 0;padding-left:18px">${indietro.join('')}</ul>
    </div>` : ''}
    ${voci.map(([conto, valore], i) => {
      const quota = totale ? valore / totale * 100 : 0;
      return `<div style="margin-top:11px">
        <div style="display:flex;justify-content:space-between;gap:10px">
          <span><i class="chiave" style="display:inline-block;background:${colore(i)}"></i>
            ${conto}</span>
          <span class="cifra">${eur(valore)}</span>
        </div>
        <div style="height:8px;border-radius:99px;background:var(--griglia);
          overflow:hidden;margin-top:6px">
          <div style="width:${quota}%;height:100%;background:${colore(i)};
            border-radius:99px"></div>
        </div>
        <div class="meta">${quota.toFixed(0)}% del totale</div>
      </div>`;
    }).join('')}`;
}

/* --- proiezione di fine anno, dichiarando i mesi su cui si basa --- */
function proiezione() {
  const box = $('#scheda-proiezione');
  const mensili = DATI.statistiche.mensili;
  if (!mensili.length) { box.hidden = true; return; }

  const annoCorrente = mensili[mensili.length - 1].mese.slice(0, 4);
  const diQuestAnno = mensili.filter((m) => m.mese.startsWith(annoCorrente));
  if (diQuestAnno.length < 2) { box.hidden = true; return; }
  box.hidden = false;

  // l'ultimo mese e' quasi sempre parziale: escluderlo evita una stima bassa
  const completi = diQuestAnno.slice(0, -1);
  const base = completi.length ? completi : diQuestAnno;
  const media = base.reduce((s, m) => s + m.spese, 0) / base.length;
  const speso = diQuestAnno.reduce((s, m) => s + m.spese, 0);
  const stima = speso + media * (12 - diQuestAnno.length);

  box.innerHTML = `
    <h2>Proiezione ${annoCorrente}</h2>
    <p class="muted piccolo">Stima ottenuta applicando ai mesi mancanti la tua
      media di ${eur(media)}, calcolata su ${base.length} mesi completi.</p>
    <div class="riga-elenco">
      <div class="desc"><strong>Speso finora</strong>
        <div class="meta">${diQuestAnno.length} mesi</div></div>
      <div class="cifra">${eur(speso)}</div></div>
    <div class="riga-elenco">
      <div class="desc"><strong>Stima a fine anno</strong>
        <div class="meta">se mantieni questo ritmo</div></div>
      <div class="cifra">${eur(stima)}</div></div>`;
}

function disegnaPanoramica() {
  tessere();
  graficoAndamento();
  graficoMacro();
  graficoRisparmio();
  graficoConfronto();
  ripartizioneConti();
  proiezione();
}

function disegnaCategorie() {
  graficoCategorie();
  const mov = movimentiFiltrati().filter((t) => t.importo < 0
    && !['Entrate', 'Risparmio'].includes(t.macro));
  const agg = {};
  mov.forEach((t) => { agg[t.categoria] = (agg[t.categoria] || 0) + -t.importo; });
  const righe = Object.entries(agg).sort((a, b) => b[1] - a[1]);
  const totale = righe.reduce((s, r) => s + r[1], 0);

  // il totale di quanto si sta guardando: senza, i numeri delle barre non
  // hanno un riferimento e non si capisce quanto pesa il filtro attivo
  const nMesi = new Set(mov.map((t) => t.data.slice(0, 7))).size || 1;
  const macro = $('#filtro-macro').value;
  const conto = $('#filtro-conto').value;
  $('#tessere-categorie').innerHTML = [
    { etichetta: 'Totale filtrato', valore: eur(totale),
      nota: `${righe.length} categorie` },
    { etichetta: 'Al mese', valore: eur(totale / nMesi), nota: `su ${nMesi} mesi` },
    { etichetta: 'Movimenti', valore: mov.length,
      nota: `media ${eur(totale / Math.max(mov.length, 1), 2)}` },
    { etichetta: 'Su base annua', valore: eur(totale / nMesi * 12),
      nota: 'a questo ritmo' },
  ].map((d) => `<div class="tessera"><div class="etichetta">${d.etichetta}</div>
      <div class="valore">${d.valore}</div><div class="nota">${d.nota}</div></div>`).join('');

  const attivi = [macro && `tipo: ${macro}`, conto && `carta: ${conto}`]
    .filter(Boolean).join(' · ');
  $('#nota-categorie').innerHTML = 'Tocca una categoria per esplorarla.'
    + (attivi ? ` <b>Filtri attivi — ${attivi}</b>` : '');
  $('#tabella-categorie').innerHTML = `<table><thead><tr>
      <th>Categoria</th><th class="num">Totale</th><th class="num">%</th>
      <th></th></tr></thead><tbody>
      ${righe.map(([c, v]) => `<tr><td>${c}</td><td class="num">${eur(v, 2)}</td>
        <td class="num">${(100 * v / totale).toFixed(1)}%</td>
        <td class="num"><button class="chip esplora" data-cat="${c}">Esplora</button></td>
        </tr>`).join('')}
    </tbody></table>`;

  $('#tabella-categorie').querySelectorAll('.esplora').forEach((b) => {
    b.addEventListener('click', () => {
      CATEGORIA_APERTA = b.dataset.cat;
      GRUPPO_APERTO = null;
      disegnaCategorie();
      $('#dettaglio-categoria').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  disegnaBudget(righe);
  graficoPortali();

  const box = $('#dettaglio-categoria');
  if (!CATEGORIA_APERTA) { box.innerHTML = ''; return; }

  const dentro = mov.filter((t) => t.categoria === CATEGORIA_APERTA);
  if (!dentro.length) { box.innerHTML = ''; CATEGORIA_APERTA = null; return; }

  box.innerHTML = `<div class="scheda">
      <div id="drill-categoria"></div>
      <p class="muted piccolo" style="margin-top:16px">Andamento mese per mese</p>
      <div class="grafico" id="graf-andamento-categoria"></div>
    </div>`;

  pannelloDrill(dentro, CATEGORIA_APERTA, $('#drill-categoria'), () => {
    CATEGORIA_APERTA = null;
    GRUPPO_APERTO = null;
    disegnaCategorie();
  });
  graficoCategoriaNelTempo(CATEGORIA_APERTA);
}

/* ---------- ACQUISTI SUI PORTALI ----------
   I portali si ricalcolano dai movimenti filtrati, come tutto il resto,
   cosi' periodo e filtri valgono anche qui. */
const TIPI_PORTALE = ['Shopping online', 'Viaggi online', 'Store digitali'];

function datiPortali() {
  const mov = movimentiFiltrati().filter((t) => t.importo < 0 && t.portale
    && !['Entrate', 'Risparmio'].includes(t.macro));
  const perPortale = {}, perTipo = {}, perMese = {};
  mov.forEach((t) => {
    const v = perPortale[t.portale] = perPortale[t.portale]
      || { portale: t.portale, tipo: t.tipo_portale || '', totale: 0, movimenti: 0 };
    v.totale += -t.importo;
    v.movimenti += 1;
    const tipo = t.tipo_portale || 'Shopping online';
    v.tipo = tipo;
    perTipo[tipo] = (perTipo[tipo] || 0) + -t.importo;
    const m = t.data.slice(0, 7);
    (perMese[m] = perMese[m] || {})[tipo] = (perMese[m][tipo] || 0) + -t.importo;
  });
  return {
    mov,
    portali: Object.values(perPortale).sort((a, b) => b.totale - a.totale),
    perTipo, perMese,
    totale: mov.reduce((s, t) => s + -t.importo, 0),
  };
}

function graficoPortali() {
  const scheda = $('#scheda-portali');
  const d = datiPortali();
  if (!d.portali.length) {
    scheda.hidden = true;
    return;
  }
  scheda.hidden = false;

  const speseTotali = movimentiFiltrati()
    .filter((t) => t.importo < 0 && !['Entrate', 'Risparmio'].includes(t.macro))
    .reduce((s, t) => s + -t.importo, 0);
  const nMesi = new Set(movimentiFiltrati().map((t) => t.data.slice(0, 7))).size || 1;
  const shopping = d.perTipo['Shopping online'] || 0;

  $('#nota-portali').innerHTML =
    `<b>${eur(d.totale)}</b> in totale, pari al
     ${(100 * d.totale / Math.max(speseTotali, 1)).toFixed(0)}% delle spese
     (${eur(d.totale / nMesi)} al mese).
     Di cui <b>${eur(shopping)}</b> di shopping vero e proprio` +
    (d.perTipo['Viaggi online']
      ? `, ${eur(d.perTipo['Viaggi online'])} di viaggi` : '') +
    (d.perTipo['Store digitali']
      ? ` e ${eur(d.perTipo['Store digitali'])} di store digitali` : '') + '.';

  // --- barre orizzontali per portale, colorate per tipo
  const box = $('#graf-portali');
  const voci = d.portali.slice(0, 12);
  const rigaH = 30;
  const { svg, W, H } = creaSvg(box, voci.length * rigaH + 8);
  const max = voci[0].totale;
  const largEtichetta = Math.min(130, Math.max(88, W * 0.32));
  const uW = W - largEtichetta - 78;

  voci.forEach((v, i) => {
    const y = 4 + i * rigaH;
    const idxTipo = Math.max(0, TIPI_PORTALE.indexOf(v.tipo));
    const nome = el('text', { x: 0, y: y + rigaH / 2 + 4, class: 'etichetta-diretta' });
    nome.textContent = v.portale.length > 17 ? v.portale.slice(0, 16) + '…' : v.portale;
    svg.appendChild(nome);

    const w = Math.max(2, (v.totale / max) * uW);
    svg.appendChild(el('rect', { x: largEtichetta, y: y + 6, width: w,
      height: rigaH - 15, fill: colore(idxTipo), rx: 4 }));
    const cifra = el('text', { x: largEtichetta + w + 7, y: y + rigaH / 2 + 4,
      class: 'etichetta-diretta' });
    cifra.textContent = eur(v.totale);
    svg.appendChild(cifra);

    const zona = el('rect', { x: 0, y, width: W, height: rigaH,
      fill: 'transparent', style: 'cursor:pointer' });
    zona.addEventListener('click', () => {
      PORTALE_APERTO = PORTALE_APERTO === v.portale ? null : v.portale;
      disegnaCategorie();
    });
    zona.addEventListener('pointerenter', (e) => mostraTip(e.clientX, e.clientY,
      `<div class="riga"><b>${v.portale}</b></div>
       <div class="riga"><span>Totale</span><b>${eur(v.totale, 2)}</b></div>
       <div class="riga"><span>Acquisti</span><b>${v.movimenti}</b></div>
       <div class="riga"><span>Scontrino medio</span><b>${eur(v.totale / v.movimenti, 2)}</b></div>
       <div class="riga muted piccolo">Tocca per i dettagli</div>`));
    zona.addEventListener('pointerleave', nascondiTip);
    svg.appendChild(zona);
  });

  graficoOnlineMese(d);
  dettaglioPortale(d);
}

/* --- quanto pesa l'online mese per mese, diviso per tipo --- */
function graficoOnlineMese(d) {
  const box = $('#graf-online-mese');
  const mesi = mesiFiltrati().map((m) => m.mese);
  if (mesi.length < 2) { box.innerHTML = ''; $('#legenda-online').innerHTML = ''; return; }

  const presenti = TIPI_PORTALE.filter((t) => d.perTipo[t]);
  legenda($('#legenda-online'), presenti.map((t) => ({
    nome: t, colore: colore(TIPI_PORTALE.indexOf(t)) })));

  const m = { alto: 12, basso: 26, sx: 38, dx: 10 };
  const { svg, W, H } = creaSvg(box, 170);
  const uW = utileW(W, m), uH = H - m.alto - m.basso;
  const totali = mesi.map((x) => presenti.reduce(
    (s, t) => s + ((d.perMese[x] || {})[t] || 0), 0));
  const scala = scalaBella(Math.max(...totali, 1));
  assi(svg, W, H, m, scala, mesi.map(meseBreve));

  const passo = uW / mesi.length;
  const larg = Math.min(24, passo * 0.6);
  mesi.forEach((mese, i) => {
    let cumulato = 0;
    const x = m.sx + passo * (i + 0.5) - larg / 2;
    presenti.forEach((tipo) => {
      const v = (d.perMese[mese] || {})[tipo] || 0;
      if (v <= 0) return;
      const h = (v / scala.max) * uH;
      const y = m.alto + uH - (cumulato / scala.max) * uH - h;
      svg.appendChild(el('rect', { x, y, width: larg,
        height: Math.max(1, h - 2), fill: colore(TIPI_PORTALE.indexOf(tipo)), rx: 3 }));
      cumulato += v;
    });
    const zona = el('rect', { x: m.sx + passo * i, y: m.alto, width: passo,
      height: uH, fill: 'transparent' });
    const attiva = (e) => mostraTip(e.clientX, e.clientY,
      `<div class="riga"><b>${meseBreve(mese)}</b></div>` +
      presenti.map((t) => `<div class="riga"><span><i class="chiave"
        style="display:inline-block;background:${colore(TIPI_PORTALE.indexOf(t))}"></i>
        ${t}</span><b>${eur((d.perMese[mese] || {})[t] || 0)}</b></div>`).join('') +
      `<div class="riga"><span>Totale</span><b>${eur(totali[i])}</b></div>`);
    zona.addEventListener('pointerenter', attiva);
    zona.addEventListener('pointerdown', attiva);
    zona.addEventListener('pointerleave', nascondiTip);
    svg.appendChild(zona);
  });
}

function dettaglioPortale(d) {
  const box = $('#dettaglio-portale');
  if (!PORTALE_APERTO) { box.innerHTML = ''; return; }
  const acquisti = d.mov.filter((t) => t.portale === PORTALE_APERTO)
    .sort((a, b) => a.importo - b.importo);
  if (!acquisti.length) { box.innerHTML = ''; PORTALE_APERTO = null; return; }

  const totale = acquisti.reduce((s, t) => s + -t.importo, 0);
  const perCat = {};
  acquisti.forEach((t) => { perCat[t.categoria] = (perCat[t.categoria] || 0) + -t.importo; });

  box.innerHTML = `<div style="border-top:1px solid var(--griglia);margin-top:14px;
      padding-top:12px">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
      <h2>${PORTALE_APERTO}</h2>
      <button class="secondario" id="chiudi-portale">Chiudi</button>
    </div>
    <p class="muted piccolo">${acquisti.length} acquisti · ${eur(totale)} ·
      scontrino medio ${eur(totale / acquisti.length, 2)}</p>
    ${Object.entries(perCat).sort((a, b) => b[1] - a[1]).map(([c, v]) =>
      `<div class="riga-elenco"><div class="desc"><strong>${c}</strong></div>
       <div class="cifra">${eur(v)}</div></div>`).join('')}
    <p class="muted piccolo" style="margin-top:12px">Acquisti più grandi</p>
    ${acquisti.slice(0, 15).map((t) => `<div class="riga-elenco">
      <div class="desc"><strong>${(t.venditore || t.merchant).slice(0, 44)}</strong>
        <div class="meta">${dataIt(t.data)}${t.strumento ? ' · ' + t.strumento : ''}</div>
      </div><div class="cifra">${eur(t.importo, 2)}</div></div>`).join('')}
  </div>`;
  $('#chiudi-portale').addEventListener('click', () => {
    PORTALE_APERTO = null; disegnaCategorie();
  });
}

/* ---------- DRILL DOWN: esplorare dentro una categoria ----------
   Le chiavi di raggruppamento sono quelle che rispondono a domande diverse:
   da chi, dove, quando, con quale carta, per quale motivo. */
const DIMENSIONI = [
  { id: 'esercente', nome: 'Esercente',
    valore: (t) => (t.venditore || t.merchant || t.descrizione || '')
      .replace(/\s{2,}.*$/, '').slice(0, 34) || 'Senza nome' },
  { id: 'citta', nome: 'Località',
    valore: (t) => (t.citta || '').trim() || 'Non indicata' },
  { id: 'paese', nome: 'Paese',
    valore: (t) => {
      const p = (t.paese || '').trim().toUpperCase();
      if (!p || p === 'IT' || p === 'ITALY' || p === 'ITALIA') return 'Italia';
      return p.length === 2 ? p : p.charAt(0) + p.slice(1).toLowerCase();
    } },
  { id: 'mese', nome: 'Mese', valore: (t) => t.data.slice(0, 7),
    ordina: 'chiave' },
  { id: 'macro', nome: 'Tipo', valore: (t) => t.macro || 'Ordinario' },
  { id: 'conto', nome: 'Carta', valore: (t) => t.conto || 'Non indicato' },
  { id: 'portale', nome: 'Portale', valore: (t) => t.portale || 'Fuori dai portali' },
  { id: 'strumento', nome: 'Pagamento',
    valore: (t) => t.strumento || 'Carta diretta' },
  { id: 'viaggio', nome: 'Viaggio', valore: (t) => {
      if (!t.viaggio) return 'Fuori dai viaggi';
      const v = (DATI.viaggi || []).find((x) => x.id === t.viaggio);
      return v ? v.luogo : t.viaggio;
    } },
];

function raggruppa(mov, dimId) {
  const dim = DIMENSIONI.find((d) => d.id === dimId) || DIMENSIONI[0];
  const gruppi = {};
  mov.forEach((t) => {
    const k = dim.valore(t);
    const g = gruppi[k] = gruppi[k] || { chiave: k, totale: 0, movimenti: [] };
    g.totale += -t.importo;
    g.movimenti.push(t);
  });
  const elenco = Object.values(gruppi);
  return dim.ordina === 'chiave'
    ? elenco.sort((a, b) => a.chiave.localeCompare(b.chiave))
    : elenco.sort((a, b) => b.totale - a.totale);
}

/* Mostra solo le chiavi che dividono davvero: con un gruppo solo, o con
   tanti gruppi quanti i movimenti, il raggruppamento non informa. */
function dimensioniUtili(mov) {
  return DIMENSIONI.filter((d) => {
    const distinti = new Set(mov.map(d.valore)).size;
    return distinti > 1 && distinti < mov.length;
  });
}

/* Il secondo livello risponde alla domanda naturale successiva: aperto un
   mese si vuole sapere da chi, aperto un esercente si vuole sapere quando. */
const SECONDO_LIVELLO = {
  mese: 'esercente', esercente: 'mese', citta: 'esercente', paese: 'citta',
  macro: 'categoria', conto: 'esercente', portale: 'esercente',
  strumento: 'esercente', viaggio: 'citta',
};

function pannelloDrill(mov, titolo, contenitore, chiudi) {
  const utili = dimensioniUtili(mov);
  if (!utili.some((d) => d.id === DIMENSIONE)) {
    DIMENSIONE = utili.length ? utili[0].id : 'esercente';
  }
  const gruppi = raggruppa(mov, DIMENSIONE);
  const totale = mov.reduce((s, t) => s + -t.importo, 0);
  const max = Math.max(...gruppi.map((g) => g.totale), 1);
  const media = totale / Math.max(gruppi.length, 1);

  const dimSotto = DIMENSIONE === 'mese' ? 'esercente'
    : (SECONDO_LIVELLO[DIMENSIONE] || 'esercente');
  const nomeSotto = (DIMENSIONI.find((d) => d.id === dimSotto) || {}).nome || '';

  contenitore.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
      <h2>${titolo}</h2>
      <button class="secondario" id="chiudi-drill">Chiudi</button>
    </div>
    <p class="muted piccolo">${mov.length} movimenti · ${eur(totale)} ·
      in media ${eur(totale / mov.length, 2)} ciascuno</p>

    <p class="muted piccolo" style="margin:12px 0 6px">Raggruppa per</p>
    <div class="chip-riga">
      ${utili.map((d) => `<button class="chip ${d.id === DIMENSIONE ? 'attivo' : ''}"
        data-dim="${d.id}">${d.nome}</button>`).join('')}
    </div>

    <div style="margin-top:12px">
      ${gruppi.slice(0, 40).map((g) => {
        const aperto = GRUPPO_APERTO === g.chiave;
        const quota = (g.totale / max) * 100;
        const nome = DIMENSIONE === 'mese' ? meseBreve(g.chiave) : g.chiave;
        // scarto dalla media: dice subito se quel mese è stato pesante
        const scarto = media ? (g.totale - media) / media * 100 : 0;
        const segno = scarto >= 0 ? '+' : '';
        const colScarto = Math.abs(scarto) < 15 ? 'var(--muto)'
          : (scarto > 0 ? 'var(--critico)' : 'var(--positivo)');

        let dentro = '';
        if (aperto) {
          const sotto = raggruppa(g.movimenti, dimSotto);
          const maxS = Math.max(...sotto.map((s) => s.totale), 1);
          dentro = `<div class="gruppo-dettaglio">
            <p class="muted piccolo" style="margin:2px 0 8px">Per ${nomeSotto.toLowerCase()}</p>
            ${sotto.slice(0, 25).map((s) => {
              const chiaveS = `${g.chiave}||${s.chiave}`;
              const apertoS = SOTTOGRUPPO_APERTO === chiaveS;
              return `<div class="sottogruppo" data-sotto="${chiaveS.replace(/"/g, '&quot;')}">
                <div class="sotto-testa">
                  <div style="min-width:0;flex:1">
                    <div style="display:flex;justify-content:space-between;gap:10px">
                      <span>${apertoS ? '▾ ' : '▸ '}${dimSotto === 'mese'
                        ? meseBreve(s.chiave) : s.chiave}</span>
                      <span class="cifra">${eur(s.totale)}</span>
                    </div>
                    <div style="height:4px;border-radius:99px;background:var(--griglia);
                      overflow:hidden;margin:4px 0 2px">
                      <div style="width:${(s.totale / maxS) * 100}%;height:100%;
                        background:${colore(2)};border-radius:99px"></div>
                    </div>
                    <div class="meta">${s.movimenti.length} movimenti</div>
                  </div>
                </div>
                ${apertoS ? `<div class="movimenti-finali">
                  ${s.movimenti.slice().sort((a, b) => a.importo - b.importo)
                    .slice(0, 30).map((t) => rigaMovimento(t)).join('')}
                </div>` : ''}
              </div>`;
            }).join('')}
            ${sotto.length > 25
              ? `<p class="muted piccolo">…e altri ${sotto.length - 25} gruppi</p>` : ''}
          </div>`;
        }

        return `<div class="gruppo" data-gruppo="${String(g.chiave).replace(/"/g, '&quot;')}">
          <div class="gruppo-testa">
            <div style="min-width:0;flex:1">
              <div style="display:flex;justify-content:space-between;gap:10px">
                <strong>${aperto ? '▾ ' : '▸ '}${nome}</strong>
                <span class="cifra">${eur(g.totale)}</span>
              </div>
              <div style="height:6px;border-radius:99px;background:var(--griglia);
                overflow:hidden;margin:5px 0 3px">
                <div style="width:${quota}%;height:100%;background:${colore(0)};
                  border-radius:99px"></div>
              </div>
              <div class="meta">${g.movimenti.length} movimenti ·
                ${(100 * g.totale / totale).toFixed(0)}% del totale ·
                <span style="color:${colScarto}">${segno}${scarto.toFixed(0)}% sulla media</span>
              </div>
            </div>
          </div>
          ${dentro}
        </div>`;
      }).join('')}
      ${gruppi.length > 40
        ? `<p class="muted piccolo">Mostrati i primi 40 gruppi su ${gruppi.length}.</p>`
        : ''}
    </div>`;

  contenitore.querySelectorAll('.chip[data-dim]').forEach((b) => {
    b.addEventListener('click', () => {
      DIMENSIONE = b.dataset.dim;
      GRUPPO_APERTO = null;
      disegna();
    });
  });
  contenitore.querySelectorAll('.gruppo-testa').forEach((r) => {
    r.addEventListener('click', () => {
      const k = r.closest('[data-gruppo]').dataset.gruppo;
      GRUPPO_APERTO = GRUPPO_APERTO === k ? null : k;
      SOTTOGRUPPO_APERTO = null;
      disegna();
    });
  });
  contenitore.querySelectorAll('.sotto-testa').forEach((r) => {
    r.addEventListener('click', (e) => {
      e.stopPropagation();   // non richiudere il gruppo che lo contiene
      const k = r.closest('[data-sotto]').dataset.sotto;
      SOTTOGRUPPO_APERTO = SOTTOGRUPPO_APERTO === k ? null : k;
      disegna();
    });
  });
  const btn = contenitore.querySelector('#chiudi-drill');
  if (btn) btn.addEventListener('click', chiudi);
}

/* --- come si muove una singola categoria, con la sua media --- */
function graficoCategoriaNelTempo(categoria) {
  const box = $('#graf-andamento-categoria');
  if (!box) return;
  const perMese = {};
  mesiFiltrati().forEach((m) => { perMese[m.mese] = 0; });
  // deve rispettare tutti i filtri attivi, non solo il periodo: altrimenti
  // il grafico mostra numeri diversi dall'elenco che ha sopra
  movimentiFiltrati().forEach((t) => {
    if (t.importo >= 0 || t.categoria !== categoria) return;
    const m = t.data.slice(0, 7);
    if (m in perMese) perMese[m] += -t.importo;
  });
  const mesi = Object.keys(perMese).sort();
  if (mesi.length < 2) { box.innerHTML = ''; return; }

  const m = { alto: 10, basso: 24, sx: 38, dx: 10 };
  const { svg, W, H } = creaSvg(box, 150);
  const uW = utileW(W, m), uH = H - m.alto - m.basso;
  const valori = mesi.map((x) => perMese[x]);
  const scala = scalaBella(Math.max(...valori, 1));
  assi(svg, W, H, m, scala, mesi.map(meseBreve));

  const passo = uW / mesi.length;
  const larg = Math.min(22, passo * 0.6);
  const media = valori.reduce((s, v) => s + v, 0) / valori.length;
  const yMedia = m.alto + uH - (media / scala.max) * uH;

  mesi.forEach((mese, i) => {
    const v = perMese[mese];
    const h = (v / scala.max) * uH;
    svg.appendChild(el('rect', {
      x: m.sx + passo * (i + 0.5) - larg / 2, y: m.alto + uH - h,
      width: larg, height: Math.max(1, h), fill: colore(0), rx: 3,
    }));
    const zona = el('rect', { x: m.sx + passo * i, y: m.alto, width: passo,
      height: uH, fill: 'transparent' });
    const attiva = (e) => mostraTip(e.clientX, e.clientY,
      `<div class="riga"><b>${meseBreve(mese)}</b></div>
       <div class="riga"><span>${categoria}</span><b>${eur(v, 2)}</b></div>
       <div class="riga"><span>Media</span><b>${eur(media)}</b></div>`);
    zona.addEventListener('pointerenter', attiva);
    zona.addEventListener('pointerdown', attiva);
    zona.addEventListener('pointerleave', nascondiTip);
    svg.appendChild(zona);
  });

  svg.appendChild(el('line', {
    x1: m.sx, x2: W - m.dx, y1: yMedia, y2: yMedia,
    stroke: 'var(--muto)', 'stroke-width': 1, 'stroke-dasharray': '4 3',
  }));
  const et = el('text', { x: W - m.dx, y: yMedia - 5, class: 'asse',
    'text-anchor': 'end' });
  et.textContent = 'media ' + eur(media);
  svg.appendChild(et);
}

/* --- tetti di spesa mensili, con stato dichiarato a parole --- */
function disegnaBudget(righe) {
  const tetti = JSON.parse(localStorage.getItem('spese_budget') || '{}');
  const nMesi = new Set(movimentiFiltrati().map((t) => t.data.slice(0, 7))).size || 1;
  const principali = righe.slice(0, 8);

  $('#elenco-budget').innerHTML = principali.map(([cat, tot]) => {
    const media = tot / nMesi;
    const tetto = tetti[cat];
    if (!tetto) {
      return `<div class="riga-elenco" data-cat="${cat}">
        <div class="desc"><strong>${cat}</strong>
          <div class="meta">${eur(media)} al mese in media</div></div>
        <button class="secondario imposta" data-cat="${cat}">Imposta tetto</button>
      </div>`;
    }
    const quota = Math.min(100, media / tetto * 100);
    // lo stato non e' affidato al solo colore: c'e' simbolo e parola
    const stato = media > tetto
      ? { c: 'var(--critico)', t: '✕ superato', d: `di ${eur(media - tetto)}` }
      : media > tetto * 0.85
        ? { c: 'var(--attenzione)', t: '! quasi al limite', d: `restano ${eur(tetto - media)}` }
        : { c: 'var(--positivo)', t: '✓ nel budget', d: `restano ${eur(tetto - media)}` };
    return `<div class="riga-elenco" style="display:block" data-cat="${cat}">
      <div style="display:flex;justify-content:space-between;gap:10px">
        <strong>${cat}</strong>
        <span class="cifra">${eur(media)} / ${eur(tetto)}</span>
      </div>
      <div style="height:8px;border-radius:99px;background:var(--griglia);
        overflow:hidden;margin:7px 0 4px">
        <div style="width:${quota}%;height:100%;background:${stato.c};border-radius:99px"></div>
      </div>
      <div class="meta" style="display:flex;justify-content:space-between">
        <span style="color:${stato.c}">${stato.t}</span>
        <span>${stato.d} · <a href="#" class="imposta" data-cat="${cat}">modifica</a></span>
      </div>
    </div>`;
  }).join('');

  $('#elenco-budget').querySelectorAll('.imposta').forEach((b) => {
    b.addEventListener('click', (e) => {
      e.preventDefault();
      const cat = b.dataset.cat;
      const attuale = tetti[cat] || '';
      const valore = prompt(`Tetto mensile per «${cat}» in euro:`, attuale);
      if (valore === null) return;
      const n = parseFloat(String(valore).replace(',', '.'));
      if (!isFinite(n) || n <= 0) delete tetti[cat];
      else tetti[cat] = n;
      localStorage.setItem('spese_budget', JSON.stringify(tetti));
      disegnaCategorie();
    });
  });
}

function rigaMovimento(t) {
  const nome = (t.merchant || t.descrizione || '').slice(0, 60);
  return `<div class="riga-elenco">
    <div class="desc">
      <strong>${nome}</strong>
      <div class="meta">${dataIt(t.data)} · ${t.conto}${t.citta ? ' · ' + t.citta : ''}</div>
    </div>
    <div class="cifra">${eur(t.importo, 2)}</div>
  </div>`;
}

function disegnaViaggi() {
  const { da, a } = periodoSelezionato();
  const tutti = (DATI.viaggi || []).slice().sort((a, b) => b.inizio.localeCompare(a.inizio));
  const viaggi = tutti.filter((v) => v.inizio.slice(0, 7) >= da && v.inizio.slice(0, 7) <= a);
  const box = $('#elenco-viaggi');
  if (!viaggi.length) {
    box.innerHTML = `<div class="scheda"><p class="muted">${tutti.length
      ? 'Nessun viaggio nel periodo selezionato. Allarga il periodo per vedere gli altri '
        + tutti.length + '.'
      : `Nessun viaggio rilevato. Vengono riconosciuti automaticamente dai gruppi
         di spese all'estero ravvicinate nel tempo.`}</p></div>`;
    return;
  }
  box.innerHTML = viaggi.map((v) => {
    const spese = DATI.transazioni.filter((t) => t.viaggio === v.id && t.importo < 0);
    const perCat = {};
    spese.forEach((t) => { perCat[t.categoria] = (perCat[t.categoria] || 0) + -t.importo; });
    const top = Object.entries(perCat).sort((a, b) => b[1] - a[1]).slice(0, 5);
    const giorni = Math.max(1, Math.round(
      (new Date(v.fine) - new Date(v.inizio)) / 86400000) + 1);
    const aperto = VIAGGIO_APERTO === v.id;
    return `<div class="scheda" data-viaggio="${v.id}">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline">
        <h2>${v.luogo}</h2><div class="cifra">${eur(v.totale)}</div>
      </div>
      <p class="muted piccolo">${dataIt(v.inizio, false)} → ${dataIt(v.fine)} ·
         ${giorni} giorni · ${v.movimenti} movimenti ·
         ${eur(v.totale / giorni)} al giorno</p>
      ${aperto ? `<div class="drill-viaggio"></div>`
        : top.map(([c, x]) => `<div class="riga-elenco">
            <div class="desc"><strong>${c}</strong></div>
            <div class="cifra">${eur(x)}</div></div>`).join('') +
          `<div class="azioni"><button class="chip apri-viaggio"
            data-id="${v.id}">Esplora il viaggio</button></div>`}
    </div>`;
  }).join('');

  box.querySelectorAll('.apri-viaggio').forEach((b) => {
    b.addEventListener('click', () => {
      VIAGGIO_APERTO = b.dataset.id;
      GRUPPO_APERTO = null;
      disegnaViaggi();
    });
  });

  if (VIAGGIO_APERTO) {
    const v = viaggi.find((x) => x.id === VIAGGIO_APERTO);
    const cont = box.querySelector('.drill-viaggio');
    if (v && cont) {
      const spese = DATI.transazioni.filter((t) => t.viaggio === v.id && t.importo < 0);
      pannelloDrill(spese, v.luogo, cont, () => {
        VIAGGIO_APERTO = null;
        GRUPPO_APERTO = null;
        disegnaViaggi();
      });
    }
  }
}

/* Elenco delle categorie proposte: quelle gia' presenti nei dati piu' le
   poche che potrebbero non esserci ancora. */
function categorieDisponibili() {
  const dai_dati = new Set(DATI.transazioni
    .map((t) => t.categoria)
    .filter((c) => c && c !== 'Da classificare'));
  ['Pranzo', 'Regali', 'Animali', 'Abbigliamento', 'Altro']
    .forEach((c) => dai_dati.add(c));
  return [...dai_dati].sort();
}

/* --- i non classificati, raggruppati per esercente --- */
function disegnaClassificare() {
  const { da, a } = periodoSelezionato();
  const mov = DATI.transazioni.filter((t) => !t.escludi && t.importo < 0
    && t.categoria === 'Da classificare'
    && !CORREZIONI[t.id]
    && t.data.slice(0, 7) >= da && t.data.slice(0, 7) <= a);

  // raggruppa: una sola decisione copre tutti i movimenti dell'esercente
  const gruppi = {};
  mov.forEach((t) => {
    const k = chiaveEsercente(t);
    const g = gruppi[k] = gruppi[k] || { chiave: k, totale: 0, movimenti: [] };
    g.totale += -t.importo;
    g.movimenti.push(t);
  });
  const elenco = Object.values(gruppi).sort((a, b) => b.totale - a.totale);
  const totale = elenco.reduce((s, g) => s + g.totale, 0);

  $('#intro-classificare').innerHTML = elenco.length
    ? `<h2>${elenco.length} esercenti da sistemare</h2>
       <p class="muted piccolo">Valgono <b>${eur(totale)}</b> in tutto.
       Scegli la categoria una volta sola: vale per tutti i movimenti di quel
       negozio, anche quelli futuri. Si parte da quelli che pesano di più.</p>`
    : `<h2>Non c'è più niente da classificare</h2>
       <p class="muted piccolo">Ricordati di scaricare le regole qui sotto e
       metterle sul PC, così restano anche dopo il prossimo aggiornamento.</p>`;

  const categorie = categorieDisponibili();
  const visibili = elenco.slice(0, QUANTI_MOSTRARE);

  $('#elenco-classificare').innerHTML = visibili.map((g) => {
    const t = g.movimenti[0];
    const luogo = t.citta ? ` · ${t.citta}` : '';
    return `<div class="scheda" data-chiave="${g.chiave.replace(/"/g, '&quot;')}">
      <div style="display:flex;justify-content:space-between;gap:10px">
        <strong>${g.chiave}</strong>
        <span class="cifra">${eur(g.totale)}</span>
      </div>
      <div class="meta">${g.movimenti.length} movimenti${luogo} ·
        dal ${dataIt(g.movimenti[g.movimenti.length - 1].data, false)}
        al ${dataIt(g.movimenti[0].data)}</div>
      <div class="meta" style="margin-top:4px;opacity:.75">${
        (t.descrizione || '').slice(0, 70)}</div>
      <select class="scelta-categoria" style="margin-top:9px">
        <option value="">Scegli una categoria…</option>
        ${categorie.map((c) => `<option value="${c}">${c}</option>`).join('')}
      </select>
    </div>`;
  }).join('');

  $('#btn-altri').hidden = elenco.length <= QUANTI_MOSTRARE;
  $('#btn-altri').textContent =
    `Mostrane altri (${elenco.length - QUANTI_MOSTRARE} rimasti)`;

  $('#elenco-classificare').querySelectorAll('.scelta-categoria').forEach((sel) => {
    sel.addEventListener('change', () => {
      const chiave = sel.closest('[data-chiave]').dataset.chiave;
      if (!sel.value) return;
      REGOLE[chiave] = sel.value;
      localStorage.setItem('spese_regole', JSON.stringify(REGOLE));
      applicaCorrezioni();
      disegnaClassificare();
      aggiornaPallino();
    });
  });

  aggiornaBoxExport();
}

function disegnaRivedere() {
  disegnaClassificare();
  const { da, a } = periodoSelezionato();
  const daRivedere = DATI.transazioni.filter((t) => t.da_rivedere && !CORREZIONI[t.id]
    && t.data.slice(0, 7) >= da && t.data.slice(0, 7) <= a);
  $('#intro-rivedere').innerHTML = daRivedere.length
    ? `<h2>${daRivedere.length} movimenti da sistemare</h2>
       <p class="muted piccolo">Gli estratti conto non riportano l'orario, quindi
       pranzo e cena non sono distinguibili in automatico. Scegli tu: la scelta
       resta salvata su questo telefono.</p>`
    : `<h2>Tutto a posto</h2><p class="muted piccolo">Non c'è nulla da rivedere.</p>`;

  const box = $('#elenco-rivedere');
  box.innerHTML = daRivedere.slice(0, 80).map((t) => `
    <div class="scheda" data-id="${t.id}">
      <div class="riga-elenco" style="border:0;padding-bottom:4px">
        <div class="desc"><strong>${(t.merchant || t.descrizione).slice(0, 50)}</strong>
          <div class="meta">${t.data} · ${t.citta || t.conto}</div></div>
        <div class="cifra">${eur(t.importo, 2)}</div>
      </div>
      <p class="muted piccolo">${t.motivo_revisione || ''}</p>
      <div class="azioni">
        ${t.motivo_revisione && t.motivo_revisione.includes('cena')
          ? `<button data-scelta="cena">Cena di lavoro</button>
             <button class="secondario" data-scelta="pranzo">Pranzo</button>
             <button class="secondario" data-scelta="personale">Spesa personale</button>`
          : `<button data-scelta="vacanza">Vacanza</button>
             <button class="secondario" data-scelta="lavoro">Lavoro SACE</button>
             <button class="secondario" data-scelta="personale">Ordinario</button>`}
      </div>
    </div>`).join('');

  box.querySelectorAll('button[data-scelta]').forEach((b) => {
    b.addEventListener('click', () => {
      const id = b.closest('[data-id]').dataset.id;
      const scelte = {
        cena:      { macro: 'Lavoro SACE', categoria: 'Ristoranti e bar' },
        pranzo:    { macro: 'Ordinario', categoria: 'Pranzo' },
        personale: { macro: 'Ordinario' },
        vacanza:   { macro: 'Vacanze' },
        lavoro:    { macro: 'Lavoro SACE' },
      };
      CORREZIONI[id] = scelte[b.dataset.scelta];
      localStorage.setItem('spese_correzioni', JSON.stringify(CORREZIONI));
      applicaCorrezioni();
      disegnaRivedere();
      aggiornaPallino();
    });
  });

  aggiornaBoxExport();
}

function aggiornaBoxExport() {
  const nC = Object.keys(CORREZIONI).length;
  const nR = Object.keys(REGOLE).length;
  $('#box-export').hidden = (nC + nR) === 0;
  $('#btn-export-regole').hidden = nR === 0;
  $('#btn-export').hidden = nC === 0;
  const pezzi = [];
  if (nR) pezzi.push(`${nR} regole per esercente`);
  if (nC) pezzi.push(`${nC} correzioni singole`);
  $('#conteggio-correzioni').textContent = pezzi.length
    ? pezzi.join(' e ') + ' salvate su questo telefono.' : '';
}

function scarica(nomeFile, contenuto) {
  const blob = new Blob([contenuto], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = nomeFile;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

$('#btn-export').addEventListener('click', () =>
  scarica('override.json', JSON.stringify(CORREZIONI, null, 2)));
$('#btn-export-regole').addEventListener('click', () =>
  scarica('regole_personali.json', JSON.stringify(REGOLE, null, 2)));

$$('.tab-rivedi').forEach((b) => b.addEventListener('click', () => {
  VISTA_RIVEDI = b.dataset.vista;
  $$('.tab-rivedi').forEach((x) => x.classList.toggle('attivo', x === b));
  $('#vista-classificare').hidden = VISTA_RIVEDI !== 'classificare';
  $('#vista-dubbi').hidden = VISTA_RIVEDI !== 'dubbi';
}));

$('#btn-altri').addEventListener('click', () => {
  QUANTI_MOSTRARE += 25;
  disegnaClassificare();
});

/* Ricalcolo sul periodo scelto, riusando le soglie decise in Python.
   Solo i mesi con stipendio accreditato: gli altri mostrerebbero le spese
   senza le entrate, simulando un rosso che non esiste. */
const CAT_FISSE = ['Casa e utenze', 'Assicurazioni', 'Abbonamenti digitali',
  'Commissioni bancarie', 'Imposte e bolli', 'Servizi professionali',
  'Mutuo Siena', 'Mutuo Milano'];
const CAT_COMPRIMIBILI = ['Ristoranti e bar', 'Shopping', 'Tempo libero',
  'Pagamenti Satispay'];

function calcolaRisparmio() {
  const base = DATI.risparmio || {};
  const completi = mesiFiltrati().filter((m) => m.completo);
  if (!completi.length) {
    return { disponibile: false, messaggio: base.messaggio ||
      'Nel periodo selezionato non ci sono mesi con lo stipendio accreditato. ' +
      'Allarga il periodo, oppure carica gli estratti Fineco mancanti.' };
  }

  const n = completi.length;
  const mesiValidi = new Set(completi.map((m) => m.mese));
  const entrataMedia = completi.reduce((s, m) => s + m.entrate, 0) / n;
  const spesaMedia = completi.reduce((s, m) => s + m.spese, 0) / n;
  const accantonato = completi.reduce((s, m) => s + m.accantonato, 0) / n;
  const margine = entrataMedia - spesaMedia;

  // La media include tredicesima e premi. Il mese tipico (mediana) racconta
  // invece la gestione ordinaria: le due cose possono avere segno opposto,
  // e vederle insieme evita di credersi in attivo mentre si erode il conto.
  const mediana = (v) => {
    const x = v.slice().sort((a, b) => a - b);
    const h = Math.floor(x.length / 2);
    return x.length % 2 ? x[h] : (x[h - 1] + x[h]) / 2;
  };
  const entrataTipica = mediana(completi.map((m) => m.entrate));
  const spesaTipica = mediana(completi.map((m) => m.spese));
  const margineTipico = entrataTipica - spesaTipica;

  const perCat = {};
  const abbon = {};
  DATI.transazioni.forEach((t) => {
    if (t.escludi || t.importo >= 0) return;
    if (t.macro === 'Entrate' || t.macro === 'Risparmio') return;
    if (!mesiValidi.has(t.data.slice(0, 7))) return;
    perCat[t.categoria] = (perCat[t.categoria] || 0) + -t.importo;
    if (t.categoria === 'Abbonamenti digitali') {
      const k = (t.merchant || t.descrizione).slice(0, 32);
      abbon[k] = (abbon[k] || 0) + -t.importo;
    }
  });

  const somma = (elenco) => elenco.reduce((s, c) => s + (perCat[c] || 0), 0) / n;
  const leve = CAT_COMPRIMIBILI
    .filter((c) => perCat[c] && perCat[c] / n >= 30)
    .map((c) => ({ categoria: c, media_mensile: perCat[c] / n,
      risparmio_annuo_20: perCat[c] / n * 0.2 * 12 }))
    .sort((a, b) => b.media_mensile - a.media_mensile);

  const avvisi = [];
  if (margine < 0) {
    avvisi.push(`Nel periodo scelto le spese superano le entrate di
      ${eur(Math.abs(margine))} al mese: il saldo complessivo cala. Prima di
      fissare un obiettivo conviene capire se dipende dalle spese o da entrate
      che non compaiono negli estratti caricati.`);
  } else if (margineTipico < 0) {
    avvisi.push(`Attenzione al modo in cui si forma questo risultato: nel mese
      <b>ordinario</b> spendi ${eur(Math.abs(margineTipico))} più di quanto
      incassi. Il bilancio resta positivo solo grazie ai mesi con tredicesima e
      premi. Sono entrate che non puoi dare per scontate: se il tuo obiettivo
      è risparmiare con regolarità, il margine va trovato nelle spese di tutti
      i mesi.`);
  }
  // due motivi diversi di esclusione: vanno distinti, non sommati
  const periodo = DATI.statistiche.periodo_confrontabile || {};
  const scartati = mesiFiltrati().filter((m) => !m.completo).map((m) => m.mese);
  const senzaCarte = scartati.filter((m) =>
    !(periodo.da <= m && m <= periodo.a));
  const senzaStipendio = scartati.filter((m) => !senzaCarte.includes(m));

  if (senzaStipendio.length) {
    avvisi.push(`${senzaStipendio.length} mesi sono esclusi perché manca
      l'estratto Fineco con lo stipendio:
      ${senzaStipendio.slice(0, 6).map(meseBreve).join(', ')}${
      senzaStipendio.length > 6 ? '…' : ''}.`);
  }
  if (senzaCarte.length) {
    avvisi.push(`Altri ${senzaCarte.length} mesi sono esclusi perché non tutte
      le carte li coprono: mostrerebbero le entrate senza tutte le spese, e
      farebbero sembrare il risparmio più alto di quello reale. Il periodo
      confrontabile va da ${meseBreve(periodo.da || '')} a
      ${meseBreve(periodo.a || '')}.`);
  }

  return {
    disponibile: true, mesi_analizzati: n,
    entrata_tipica: entrataMedia, spesa_tipica: spesaMedia,
    entrata_mese_tipico: entrataTipica, spesa_mese_tipico: spesaTipica,
    margine_mese_tipico: margineTipico,
    margine_teorico: margine, gia_accantonato_mese: accantonato,
    tasso_risparmio_attuale: entrataMedia ? +(margine / entrataMedia * 100).toFixed(1) : 0,
    in_deficit: margine < 0,
    spese_fisse_mese: somma(CAT_FISSE),
    fondo_emergenza_min: spesaMedia * 3, fondo_emergenza_max: spesaMedia * 6,
    obiettivi: [
      { nome: 'Prudente', quota: 0.10,
        descrizione: 'Il 10% delle entrate: la soglia minima consigliata.' },
      { nome: 'Equilibrato', quota: 0.15,
        descrizione: 'Il 15%: costruisce un fondo di emergenza in tempi ragionevoli.' },
      { nome: 'Ambizioso', quota: 0.20,
        descrizione: 'Il 20%: richiede di ridurre le spese comprimibili.' },
    ].map((o) => ({ ...o,
      importo_mensile: entrataMedia * o.quota,
      annuo: entrataMedia * o.quota * 12,
      sforzo: Math.max(0, entrataMedia * o.quota - margine) })),
    leve,
    abbonamenti: Object.entries(abbon).sort((a, b) => b[1] - a[1]).slice(0, 12)
      .map(([nome, totale]) => ({ nome, totale })),
    avvisi,
  };
}

function disegnaRisparmio() {
  const r = calcolaRisparmio();
  const box = $('#contenuto-risparmio');
  if (!r.disponibile) {
    box.innerHTML = `<div class="scheda avviso"><h2>Dati insufficienti</h2>
      <p class="muted piccolo">${r.messaggio || ''}</p></div>`;
    return;
  }
  const barra = (quota, colore) => `<div style="height:8px;border-radius:99px;
      background:var(--griglia);overflow:hidden;margin-top:6px">
      <div style="width:${Math.min(100, quota)}%;height:100%;background:${colore};
      border-radius:99px"></div></div>`;

  box.innerHTML = `
    ${(r.avvisi || []).map((a) => `<div class="scheda avviso">
       <h2>Attenzione</h2><p class="piccolo">${a}</p></div>`).join('')}

    <div class="scheda">
      <h2>La tua situazione</h2>
      <p class="muted piccolo">Calcolata su ${r.mesi_analizzati} mesi con stipendio registrato.</p>
      <div class="riga-elenco"><div class="desc"><strong>Entrate tipiche</strong>
        <div class="meta">valore mediano mensile</div></div>
        <div class="cifra">${eur(r.entrata_tipica)}</div></div>
      <div class="riga-elenco"><div class="desc"><strong>Spese tipiche</strong>
        <div class="meta">di cui ${eur(r.spese_fisse_mese)} fisse</div></div>
        <div class="cifra">${eur(r.spesa_tipica)}</div></div>
      <div class="riga-elenco"><div class="desc"><strong>Spostati su altri conti</strong>
        <div class="meta">bonifici ricorrenti verso i tuoi conti</div></div>
        <div class="cifra">${eur(r.gia_accantonato_mese)}</div></div>
      <div class="riga-elenco"><div class="desc"><strong>Risparmio effettivo</strong>
        <div class="meta">media dei mesi, tredicesima e premi compresi</div></div>
        <div class="cifra"
          style="color:${r.margine_teorico >= 0 ? 'var(--positivo)' : 'var(--critico)'}">
          ${eur(r.margine_teorico)}</div></div>
      <div class="riga-elenco"><div class="desc"><strong>Nel mese ordinario</strong>
        <div class="meta">senza le entrate straordinarie:
          ${eur(r.entrata_mese_tipico)} contro ${eur(r.spesa_mese_tipico)}</div></div>
        <div class="cifra"
          style="color:${r.margine_mese_tipico >= 0 ? 'var(--positivo)' : 'var(--critico)'}">
          ${eur(r.margine_mese_tipico)}</div></div>
      <p class="piccolo" style="margin-top:10px">Tasso di risparmio reale:
        <b>${r.tasso_risparmio_attuale}%</b> delle entrate.
        ${r.in_deficit ? 'Sotto zero: il saldo complessivo sta calando.' : ''}</p>
      ${barra(Math.max(0, r.tasso_risparmio_attuale) * 5,
              r.in_deficit ? 'var(--critico)' : 'var(--serie-1)')}
    </div>

    <div class="scheda">
      <h2>Fondo di emergenza</h2>
      <p class="muted piccolo">La prima tappa: da 3 a 6 mesi di spese su un conto
        separato e sempre disponibile. Serve a non intaccare gli investimenti
        quando arriva un imprevisto.</p>
      <div class="riga-elenco"><div class="desc"><strong>Obiettivo minimo</strong>
        <div class="meta">3 mesi di spese</div></div>
        <div class="cifra">${eur(r.fondo_emergenza_min)}</div></div>
      <div class="riga-elenco"><div class="desc"><strong>Obiettivo pieno</strong>
        <div class="meta">6 mesi di spese</div></div>
        <div class="cifra">${eur(r.fondo_emergenza_max)}</div></div>
    </div>

    <div class="scheda">
      <h2>Tre livelli di risparmio</h2>
      <p class="muted piccolo">Da versare su un conto separato il giorno stesso
        dello stipendio, non a fine mese con quel che resta.</p>
      ${r.obiettivi.map((o) => `
        <div class="riga-elenco">
          <div class="desc"><strong>${o.nome} · ${Math.round(o.quota * 100)}%</strong>
            <div class="meta">${o.descrizione}</div>
            <div class="meta">${o.sforzo > 0
              ? 'Servono ' + eur(o.sforzo) + ' di spese in meno ogni mese'
              : 'Già alla tua portata'}</div>
          </div>
          <div class="cifra">${eur(o.importo_mensile)}<div class="meta"
            style="font-weight:400">${eur(o.annuo)}/anno</div></div>
        </div>`).join('')}
    </div>

    <div class="scheda">
      <h2>Dove puoi intervenire</h2>
      <p class="muted piccolo">Le voci su cui hai margine reale, con il risparmio
        che otterresti tagliandole del 20%.</p>
      ${(r.leve || []).map((l) => `
        <div class="riga-elenco">
          <div class="desc"><strong>${l.categoria}</strong>
            <div class="meta">${eur(l.media_mensile)} al mese</div></div>
          <div class="cifra">−${eur(l.risparmio_annuo_20)}<div class="meta"
            style="font-weight:400">all'anno</div></div>
        </div>`).join('') || '<p class="muted piccolo">Nessuna voce comprimibile rilevante.</p>'}
    </div>

    <div class="scheda">
      <h2>Addebiti ricorrenti</h2>
      <p class="muted piccolo">Riconosciuti dalla regolarità: stesso esercente,
        stessa cifra, per almeno tre mesi. Sono quelli che restano attivi senza
        che te ne accorga.</p>
      ${(() => {
        const abb = r.abbonamenti || [];
        const attivi = abb.filter((a) => a.attivo);
        const chiusi = abb.filter((a) => !a.attivo);
        const annuo = attivi.reduce((s, a) => s + a.stima_annua, 0);
        const riga = (a) => `
          <div class="riga-elenco">
            <div class="desc"><strong>${a.nome}</strong>
              <div class="meta">${eur(a.rata, 2)} · ${a.addebiti} addebiti ·
                dal ${dataIt(a.dal, false)}${a.attivo
                  ? ` · ultimo ${dataIt(a.ultimo, false)}`
                  : ` · <span style="color:var(--muto)">fermo da ${a.giorni_fermo} giorni</span>`}
              </div>
            </div>
            <div class="cifra">${eur(a.stima_annua)}<div class="meta"
              style="font-weight:400">all'anno</div></div>
          </div>`;
        return (attivi.length
          ? `<p class="piccolo" style="margin:10px 0 4px"><b>${attivi.length} attivi</b>,
               ${eur(annuo)} all'anno</p>` + attivi.map(riga).join('')
          : '<p class="muted piccolo">Nessun addebito ricorrente attivo.</p>')
          + (chiusi.length
            ? `<p class="muted piccolo" style="margin:16px 0 4px">Non più addebitati
                 — utile per confermare che una disdetta ha avuto effetto</p>`
              + chiusi.map(riga).join('')
            : '');
      })()}
    </div>`;
}

/* ================= RISTORANTI E BAR =================
   La categoria più comprimibile: qui non basta il totale, serve capire
   dove, quanto spesso e con che scontrino. */
/* Icone disegnate a mano: poche centinaia di byte, nessuna richiesta di rete,
   e prendono il colore dal tema perché usano currentColor. */
const ICONE = {
  caffe: 'M4 8h11v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V8zM15 9h2a2 2 0 0 1 0 4h-2M3 20h13',
  panino: 'M3 9a6 3 0 0 1 18 0M3 12h18M3 15a6 3 0 0 0 18 0',
  piatto: 'M5 4v6a2 2 0 0 0 4 0V4M7 10v10M14 4c-1 2-1 5 0 6s3 0 3 0V4M17 10v10',
  calice: 'M7 3h10l-1 6a4 4 0 0 1-8 0zM12 13v7M8 20h8',
  scooter: 'M5 17a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM19 17a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM7 15h10M14 15l-2-8h-3M12 7h4l2 6',
};

function icona(nome, colore) {
  const d = ICONE[nome];
  if (!d) return '';
  return `<svg viewBox="0 0 24 24" width="17" height="17" fill="none"
    stroke="${colore || 'currentColor'}" stroke-width="1.6" stroke-linecap="round"
    stroke-linejoin="round" aria-hidden="true"
    style="flex:none;vertical-align:-3px"><path d="${d}"/></svg>`;
}

const FASCE = [
  { nome: 'Caffè e colazione', max: 7, icona: 'caffe' },
  { nome: 'Pranzo veloce', max: 20, icona: 'panino' },
  { nome: 'Pranzo o cena', max: 45, icona: 'piatto' },
  { nome: 'Cena importante', max: Infinity, icona: 'calice' },
];
const DELIVERY = ['DELIVEROO', 'GLOVO', 'UBER EATS', 'JUST EAT', 'JUSTEAT'];

function zonaRisto(t) {
  const c = (t.citta || '').trim().toLowerCase();
  const paese = (t.paese || '').trim().toUpperCase();
  if (paese && !['IT', 'ITALY', 'ITALIA'].includes(paese)) return 'Estero';
  if (c === 'roma') return 'Roma';
  if (c === 'milano') return 'Milano';
  return 'Altre località';
}
const ZONE = ['Roma', 'Milano', 'Altre località', 'Estero'];

function datiRistoranti() {
  const mov = movimentiFiltrati().filter((t) => t.importo < 0
    && t.categoria === 'Ristoranti e bar');
  const nMesi = new Set(mesiFiltrati().map((m) => m.mese)).size || 1;
  return { mov, nMesi, totale: mov.reduce((s, t) => s + -t.importo, 0) };
}

function disegnaRistoranti() {
  const { mov, nMesi, totale } = datiRistoranti();
  if (!mov.length) {
    $('#tessere-risto').innerHTML =
      '<div class="scheda"><p class="muted">Nessuna spesa in ristoranti nel periodo.</p></div>';
    ['#graf-risto-citta', '#graf-risto-mese', '#graf-risto-fasce',
     '#risto-delivery', '#risto-locali', '#risto-leve']
      .forEach((s) => { $(s).innerHTML = ''; });
    return;
  }

  const perZona = {};
  ZONE.forEach((z) => { perZona[z] = { tot: 0, n: 0 }; });
  mov.forEach((t) => {
    const z = zonaRisto(t);
    perZona[z].tot += -t.importo;
    perZona[z].n += 1;
  });

  // --- tessere
  $('#tessere-risto').innerHTML = [
    { etichetta: 'Totale', valore: eur(totale), nota: `${eur(totale / nMesi)} al mese` },
    { etichetta: 'Uscite', valore: mov.length,
      nota: `${(mov.length / nMesi).toFixed(1)} al mese` },
    { etichetta: 'Scontrino medio', valore: eur(totale / mov.length, 2),
      nota: 'per singola uscita' },
    { etichetta: 'Su base annua', valore: eur(totale / nMesi * 12), nota: 'se il ritmo resta questo' },
  ].map((d) => `<div class="tessera"><div class="etichetta">${d.etichetta}</div>
      <div class="valore">${d.valore}</div><div class="nota">${d.nota}</div></div>`).join('');

  // --- barre per zona, con il pallino del colore usato nel grafico mensile
  const voci = ZONE.filter((z) => perZona[z].n > 0);
  const max = Math.max(...voci.map((z) => perZona[z].tot), 1);
  $('#graf-risto-citta').innerHTML = voci.map((z) => {
    const v = perZona[z];
    const col = colore(ZONE.indexOf(z));
    return `<div class="barra-voce">
      <div class="barra-testa">
        <span class="barra-nome"><i class="chiave" style="background:${col}"></i>${z}</span>
        <span class="cifra">${eur(v.tot)}</span>
      </div>
      <div class="barra-guida"><div class="barra-piena"
        style="width:${(v.tot / max) * 100}%;background:${col}"></div></div>
      <div class="meta">${v.n} uscite · media ${eur(v.tot / v.n, 2)} ·
        ${(100 * v.tot / totale).toFixed(0)}% del totale</div>
    </div>`;
  }).join('');

  const roma = perZona['Roma'], milano = perZona['Milano'];
  $('#nota-risto-citta').innerHTML =
    `A Roma <b>${eur(roma.tot)}</b> in ${roma.n} uscite (media ${eur(roma.tot / Math.max(roma.n, 1), 2)}), ` +
    `a Milano <b>${eur(milano.tot)}</b> in ${milano.n} (media ${eur(milano.tot / Math.max(milano.n, 1), 2)}). ` +
    (roma.n && milano.n
      ? (roma.tot / roma.n > milano.tot / milano.n
        ? 'A Roma spendi di più per singola uscita.'
        : 'A Milano spendi di più per singola uscita.')
      : '');

  graficoRistoMese(mov);
  graficoRistoFasce(mov, totale);
  ristoDelivery(mov, totale, nMesi);
  ristoLocali(mov);
  ristoLeve(mov, totale, nMesi, perZona);
}

function graficoRistoMese(mov) {
  const box = $('#graf-risto-mese');
  const mesi = mesiFiltrati().map((m) => m.mese);
  if (mesi.length < 2) { box.innerHTML = ''; $('#legenda-risto').innerHTML = ''; return; }

  const dati = {};
  mesi.forEach((m) => { dati[m] = {}; });
  mov.forEach((t) => {
    const m = t.data.slice(0, 7);
    if (!(m in dati)) return;
    const z = zonaRisto(t);
    dati[m][z] = (dati[m][z] || 0) + -t.importo;
  });
  const presenti = ZONE.filter((z) => mov.some((t) => zonaRisto(t) === z));
  legenda($('#legenda-risto'), presenti.map((z) => ({
    nome: z, colore: colore(ZONE.indexOf(z)) })));

  const m = { alto: 12, basso: 26, sx: 38, dx: 10 };
  const { svg, W, H } = creaSvg(box, 180);
  const uW = utileW(W, m), uH = H - m.alto - m.basso;
  const totali = mesi.map((x) => presenti.reduce((s, z) => s + (dati[x][z] || 0), 0));
  const scala = scalaBella(Math.max(...totali, 1));
  assi(svg, W, H, m, scala, mesi.map(meseBreve));

  const passo = uW / mesi.length;
  const larg = Math.min(24, passo * 0.6);
  mesi.forEach((mese, i) => {
    let cum = 0;
    const x = m.sx + passo * (i + 0.5) - larg / 2;
    presenti.forEach((z) => {
      const v = dati[mese][z] || 0;
      if (v <= 0) return;
      const h = (v / scala.max) * uH;
      svg.appendChild(el('rect', { x, y: m.alto + uH - (cum / scala.max) * uH - h,
        width: larg, height: Math.max(1, h - 2), fill: colore(ZONE.indexOf(z)), rx: 3 }));
      cum += v;
    });
    const zona = el('rect', { x: m.sx + passo * i, y: m.alto, width: passo,
      height: uH, fill: 'transparent' });
    const attiva = (e) => mostraTip(e.clientX, e.clientY,
      `<div class="riga"><b>${meseBreve(mese)}</b></div>` +
      presenti.map((z) => `<div class="riga"><span><i class="chiave"
        style="display:inline-block;background:${colore(ZONE.indexOf(z))}"></i> ${z}</span>
        <b>${eur(dati[mese][z] || 0)}</b></div>`).join('') +
      `<div class="riga"><span>Totale</span><b>${eur(totali[i])}</b></div>`);
    zona.addEventListener('pointerenter', attiva);
    zona.addEventListener('pointerdown', attiva);
    zona.addEventListener('pointerleave', nascondiTip);
    svg.appendChild(zona);
  });
}

function graficoRistoFasce(mov, totale) {
  const conteggi = FASCE.map(() => ({ tot: 0, n: 0 }));
  mov.forEach((t) => {
    const v = -t.importo;
    let i = FASCE.findIndex((f) => v <= f.max);
    if (i < 0) i = FASCE.length - 1;
    conteggi[i].tot += v;
    conteggi[i].n += 1;
  });
  const max = Math.max(...conteggi.map((c) => c.tot), 1);
  const nTot = mov.length;

  $('#graf-risto-fasce').innerHTML = FASCE.map((f, i) => {
    const c = conteggi[i];
    const col = colore(i);
    const limite = f.max === Infinity ? 'oltre 45 €' : `fino a ${f.max} €`;
    const quotaSpesa = 100 * c.tot / totale;
    const quotaVolte = 100 * c.n / nTot;
    return `<div class="barra-voce">
      <div class="barra-testa">
        <span class="barra-nome">${icona(f.icona, col)}${f.nome}</span>
        <span class="cifra">${eur(c.tot)}</span>
      </div>
      <div class="barra-guida"><div class="barra-piena"
        style="width:${(c.tot / max) * 100}%;background:${col}"></div></div>
      <div class="meta">${limite} · ${c.n} volte ·
        <b>${quotaSpesa.toFixed(0)}% della spesa</b> in ${quotaVolte.toFixed(0)}% delle uscite</div>
    </div>`;
  }).join('');
}

function ristoDelivery(mov, totale, nMesi) {
  const consegna = mov.filter((t) => DELIVERY.some((d) =>
    (t.merchant + ' ' + t.descrizione).toUpperCase().includes(d)));
  const box = $('#risto-delivery');
  if (!consegna.length) { box.hidden = true; return; }
  box.hidden = false;
  const tot = consegna.reduce((s, t) => s + -t.importo, 0);
  box.innerHTML = `<h2 style="display:flex;align-items:center;gap:7px">
      ${icona('scooter', 'var(--serie-2)')}Consegna a domicilio</h2>
    <p class="muted piccolo">Deliveroo, Glovo e simili: costano più del ritiro
      diretto e si ordinano senza pensarci.</p>
    <div class="riga-elenco">
      <div class="desc"><strong>${consegna.length} ordini</strong>
        <div class="meta">${(consegna.length / nMesi).toFixed(1)} al mese ·
          scontrino medio ${eur(tot / consegna.length, 2)}</div></div>
      <div class="cifra">${eur(tot)}<div class="meta" style="font-weight:400">
        ${(100 * tot / totale).toFixed(0)}% dei ristoranti</div></div>
    </div>`;
}

function ristoLocali(mov) {
  const agg = {};
  mov.forEach((t) => {
    const k = (t.venditore || t.merchant || '').replace(/\s{2,}.*$/, '').slice(0, 30)
      || 'Senza nome';
    const g = agg[k] = agg[k] || { tot: 0, n: 0, citta: t.citta };
    g.tot += -t.importo;
    g.n += 1;
  });
  const top = Object.entries(agg).sort((a, b) => b[1].tot - a[1].tot).slice(0, 12);
  $('#risto-locali').innerHTML = `<h2>I locali dove torni</h2>
    <p class="muted piccolo">Ordinati per spesa totale: sono le abitudini, non
      le eccezioni, a fare il totale di fine anno.</p>
    ${top.map(([nome, g]) => `<div class="riga-elenco">
      <div class="desc"><strong>${nome}</strong>
        <div class="meta">${g.n} volte${g.citta ? ' · ' + g.citta : ''} ·
          media ${eur(g.tot / g.n, 2)}</div></div>
      <div class="cifra">${eur(g.tot)}</div></div>`).join('')}`;
}

function ristoLeve(mov, totale, nMesi, perZona) {
  const alMese = totale / nMesi;
  const consegna = mov.filter((t) => DELIVERY.some((d) =>
    (t.merchant + ' ' + t.descrizione).toUpperCase().includes(d)));
  const totConsegna = consegna.reduce((s, t) => s + -t.importo, 0);
  const care = mov.filter((t) => -t.importo > 45);
  const totCare = care.reduce((s, t) => s + -t.importo, 0);
  const piccole = mov.filter((t) => -t.importo <= 7);
  const totPiccole = piccole.reduce((s, t) => s + -t.importo, 0);
  const medio = totale / mov.length;

  const leve = [
    { nome: 'Una uscita in meno alla settimana',
      spiega: `Con uno scontrino medio di ${eur(medio, 2)}, quattro uscite in meno al mese.`,
      anno: medio * 4 * 12 },
    { nome: 'Metà degli ordini a domicilio',
      spiega: `${consegna.length} ordini nel periodo, ${eur(totConsegna)} in tutto. Ritirando di persona si evita anche il costo di consegna.`,
      anno: totConsegna / nMesi * 12 * 0.5, salta: consegna.length < 3 },
    { nome: 'Una cena importante in meno al mese',
      spiega: `${care.length} uscite sopra i 45 € per ${eur(totCare)}: sono ${(100 * totCare / totale).toFixed(0)}% del totale in ${(100 * care.length / mov.length).toFixed(0)}% delle volte.`,
      anno: (totCare / Math.max(care.length, 1)) * 12, salta: care.length < 3 },
    { nome: 'Caffè e colazioni: un terzo in meno',
      spiega: `${piccole.length} volte per ${eur(totPiccole)}. Singolarmente trascurabili, insieme no.`,
      anno: totPiccole / nMesi * 12 / 3, salta: totPiccole < 100 },
  ].filter((l) => !l.salta).sort((a, b) => b.anno - a.anno);

  $('#risto-leve').innerHTML = `<h2>Dove puoi intervenire</h2>
    <p class="muted piccolo">Spendi ${eur(alMese)} al mese in ristoranti e bar,
      ${eur(alMese * 12)} su base annua. Ecco cosa cambierebbe ciascuna scelta,
      calcolato sulle tue abitudini reali.</p>
    ${leve.map((l) => `<div class="riga-elenco">
      <div class="desc"><strong>${l.nome}</strong>
        <div class="meta">${l.spiega}</div></div>
      <div class="cifra" style="color:var(--positivo)">−${eur(l.anno)}
        <div class="meta" style="font-weight:400">all'anno</div></div>
    </div>`).join('')}
    <p class="muted piccolo" style="margin-top:12px">Le voci non si sommano
      fra loro: alcune riguardano le stesse uscite.</p>`;
}

function disegnaMovimenti() {
  const q = ($('#cerca').value || '').toLowerCase();
  const mov = movimentiFiltrati()
    .filter((t) => !q || (t.merchant + ' ' + t.descrizione + ' ' + t.categoria)
      .toLowerCase().includes(q))
    .sort((a, b) => b.data.localeCompare(a.data))
    .slice(0, 300);
  $('#elenco-movimenti').innerHTML = `<div class="scheda">
    ${mov.length ? mov.map((t) => `<div class="riga-elenco">
        <div class="desc"><strong>${(t.merchant || t.descrizione).slice(0, 52)}</strong>
          <div class="meta"><span class="pillola">${t.categoria}</span>${dataIt(t.data)} · ${t.conto}</div>
        </div><div class="cifra">${eur(t.importo, 2)}</div></div>`).join('')
      : '<p class="muted piccolo">Nessun movimento trovato.</p>'}
    </div>`;
}
$('#cerca').addEventListener('input', disegnaMovimenti);

/* ================= 5. NAVIGAZIONE ================= */

const TITOLI = {
  panoramica: 'Panoramica', categorie: 'Categorie', viaggi: 'Viaggi',
  rivedere: 'Da rivedere', ristoranti: 'Ristoranti e bar',
  risparmio: 'Risparmio', movimenti: 'Movimenti',
};

function vai(pagina) {
  PAGINA = pagina;
  $$('.pagina').forEach((s) => { s.hidden = s.id !== 'pag-' + pagina; });
  $$('.barra button').forEach((b) => b.classList.toggle('attivo', b.dataset.pagina === pagina));
  $('#titolo-sezione').textContent = TITOLI[pagina];
  // il periodo vale ovunque; il tipo di spesa non ha senso dove non si applica
  $('#filtri').hidden = false;
  $('#filtro-macro').hidden = ['rivedere', 'risparmio'].includes(pagina);
  $('#filtri-custom').hidden = $('#periodo').value !== 'custom';
  nascondiTip();
  disegna();
}

$$('.barra button').forEach((b) => b.addEventListener('click', () => vai(b.dataset.pagina)));

function aggiornaPallino() {
  const dubbi = DATI.transazioni.filter((t) => t.da_rivedere && !CORREZIONI[t.id]).length;
  const daFare = DATI.transazioni.filter((t) => !t.escludi && t.importo < 0
    && t.categoria === 'Da classificare' && !CORREZIONI[t.id]).length;
  $('#pallino').hidden = (dubbi + daFare) === 0;
}

function disegna() {
  const { da, a } = periodoSelezionato();
  $('#sottotitolo-periodo').textContent =
    `${meseBreve(da)} → ${meseBreve(a)} · aggiornato il ${DATI.generato_il || '—'}`;
  if (PAGINA === 'panoramica') disegnaPanoramica();
  if (PAGINA === 'categorie') disegnaCategorie();
  if (PAGINA === 'viaggi') disegnaViaggi();
  if (PAGINA === 'rivedere') disegnaRivedere();
  if (PAGINA === 'ristoranti') disegnaRistoranti();
  if (PAGINA === 'risparmio') disegnaRisparmio();
  if (PAGINA === 'movimenti') disegnaMovimenti();
}

$('#periodo').addEventListener('change', () => {
  $('#filtri-custom').hidden = $('#periodo').value !== 'custom';
  ricordaPeriodo();
  disegna();
});
$('#filtro-macro').addEventListener('change', disegna);
$('#filtro-conto').addEventListener('change', disegna);

/* I campi <input type="month"> sul telefono aprono il selettore di sistema,
   che non sempre emette "change" quando lo chiudi: senza questi ascoltatori
   il periodo sembra non cambiare mai. Il pulsante Aggiorna resta come via
   sicura, indipendente dal comportamento del browser. */
const aggiornaPeriodo = () => { ricordaPeriodo(); disegna(); };
['change', 'input', 'blur'].forEach((evento) => {
  $('#da-mese').addEventListener(evento, aggiornaPeriodo);
  $('#a-mese').addEventListener(evento, aggiornaPeriodo);
});
$('#btn-aggiorna').addEventListener('click', aggiornaPeriodo);

$('#btn-tema').addEventListener('click', () => {
  const attuale = document.documentElement.getAttribute('data-theme');
  const scuro = attuale === 'dark' || (!attuale &&
    matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.setAttribute('data-theme', scuro ? 'light' : 'dark');
  localStorage.setItem('spese_tema', scuro ? 'light' : 'dark');
  disegna();
});

let attesa;
addEventListener('resize', () => { clearTimeout(attesa); attesa = setTimeout(disegna, 180); });

/* Il filtro per carta si popola dai dati e compare solo se serve davvero:
   con un conto e una sola carta sarebbe una scelta inutile. */
function preparaFiltroConti() {
  const conti = [...new Set(DATI.transazioni
    .filter((t) => !t.escludi).map((t) => t.conto).filter(Boolean))].sort();
  const select = $('#filtro-conto');
  select.innerHTML = '<option value="">Tutti i conti</option>' +
    conti.map((c) => `<option value="${c}">${c}</option>`).join('');
  select.hidden = conti.length < 3;
}

/* Periodo iniziale: da gennaio 2026. Se hai già scelto un periodo diverso,
   l'app riapre su quello invece di riportarti sempre al punto di partenza. */
const PERIODO_INIZIALE = '2026-01';

function impostaPeriodoIniziale() {
  const mesi = DATI.statistiche.mensili.map((m) => m.mese).sort();
  if (!mesi.length) return;
  const ultimo = mesi[mesi.length - 1];

  const salvato = JSON.parse(localStorage.getItem('spese_periodo') || 'null');
  if (salvato && salvato.scelta) {
    $('#periodo').value = salvato.scelta;
    $('#da-mese').value = salvato.da || mesi[0];
    $('#a-mese').value = salvato.a || ultimo;
  } else {
    $('#periodo').value = 'custom';
    $('#da-mese').value = mesi.includes(PERIODO_INIZIALE) ? PERIODO_INIZIALE : mesi[0];
    $('#a-mese').value = ultimo;
  }
  $('#filtri-custom').hidden = $('#periodo').value !== 'custom';
}

function ricordaPeriodo() {
  localStorage.setItem('spese_periodo', JSON.stringify({
    scelta: $('#periodo').value,
    da: $('#da-mese').value,
    a: $('#a-mese').value,
  }));
}

function avvia() {
  impostaPeriodoIniziale();
  preparaFiltroConti();
  aggiornaPallino();
  vai('panoramica');
}

/* tema salvato e sblocco automatico se la password e' memorizzata */
const temaSalvato = localStorage.getItem('spese_tema');
if (temaSalvato) document.documentElement.setAttribute('data-theme', temaSalvato);
const pwSalvata = localStorage.getItem('spese_pw');
if (pwSalvata) { $('#password').value = pwSalvata; sblocca(pwSalvata, true); }
