# Dashboard

**Ruta:** `/` (exact)
**Componentă:** `apps/console/src/app/features/dashboard.page.ts`
**Data auditului:** 2026-09-21

## Scopul paginii
Ecranul de start al operatorului: starea contului de paper trading (equity, cash, P&L, drawdown), expunerea curentă și planul sesiunii de azi (nivele tehnice, watchlist, calendar). Este pagina pe care operatorul o vede prima dată la fiecare vizită.

## Utilizatorul țintă
Operatorul uman al agentului (singurul rol observat: `operator`), care verifică rapid "e totul în regulă?" înainte de a decide dacă intervine.

## Acțiunea principală
Scanare rapidă a stării contului + link către "Open orders" dacă ceva cere atenție.

## Rezumatul problemelor
Pagina comunică bine intenția ("Numbers are facts from the local engine, not forecasts") dar valorile numerice cheie (P&L, drawdown) sunt afișate brute, neformatate, ceea ce le face ilizibile și rupe layout-ul cardurilor. Nu există stare de loading vizibilă distinctă pe ecran (skeleton-ul există în cod dar nu am putut-o declanșa live) și nu există separare vizuală clară a secțiunii "Today's session" pe ecrane late.

## Probleme P0/P1/P2/P3

### P0 — Valorile financiare sunt afișate cu precizie brută de float, ilizibile
Cardurile "Unrealized P&L" și "Drawdown" afișează șiruri precum `5.357063999999999999999999906`, care depășesc lățimea cardului și se suprapun vizual cu cardul alăturat. Pe mobil, textul este tăiat la marginea ecranului (overflow, fără wrap).
- **Verificat live:** ecran desktop 1440px și mobil 390px, `/`.
- **Sursă:** `apps/console/src/app/shared/metric-card.ts:8` — `{{ value() }}` interpolează direct string-ul primit de la API, fără `Intl.NumberFormat`/`toFixed`.

### P1 — Dublă bannerizare a stării HALTED
Când agentul e oprit de urgență, apar simultan un banner roșu de sus ("HALTED: stale_heartbeat...") și un al doilea banner tot roșu imediat sub el ("Agent HALTED - stale_heartbeat"), cu text aproape identic. Consumă spațiu vertical semnificativ, mai ales pe mobil, fără informație suplimentară.
- **Sursă probabilă:** `apps/console/src/app/app.html:53-71` (mesajul global `state.halted()`) suprapus cu un mesaj echivalent randat în `dashboard.page.ts`/`agent-state.service.ts`.

### P2 — Nicio unitate/simbol monetar lângă cifre
Equity, Cash, P&L nu au un simbol de monedă sau sufix de unitate vizibil (ex. USD). Pentru un agent care ar putea rula pe mai multe instrumente/quote currencies în viitor, lipsa unității e un risc de citire greșită.

### P3 — "Today's session" nu are ierarhie vizuală puternică față de cardurile de sus
Secțiunea ocupă jumătate din ecran dar folosește aceeași greutate tipografică pentru etichete ca și cardurile de metrici, făcând scanarea mai lentă.

## Observații UX
- Mesajul lede ("Numbers are facts from the local engine, not forecasts") e un exemplu bun de microcopy care setează încredere corectă — de păstrat ca pattern pe toate paginile cu date.
- Linkul "Open orders" din colțul din dreapta sus al cardului "Today's session" e singura cale rapidă spre acțiune; restul paginii e strict informativ, ceea ce e corect pentru un dashboard "read-only".
- Nu există niciun CTA principal fals — pagina nu împinge operatorul spre nicio acțiune riscantă, ceea ce e potrivit pentru rolul ei.

## Observații UI
- Grid de carduri (`Equity` hero + `Cash`/`Realized P&L`/`Unrealized P&L`/`Drawdown`/`Orders today`) — layout clar pe desktop, dar celula "Drawdown" rămâne goală vizual dacă valoarea overflow-uiește din celula vecină (vezi P0).
- Culoare verde e folosită pentru P&L pozitiv (`pnl-pos`), dar Drawdown nu are nicio semantică de culoare (ar trebui să fie roșu/portocaliu când crește).
- Tabelul "Exposure" (Key/Notional) e un tabel cu un singur rând vizibil în sesiunea curentă — nu e clar dacă poate avea mai multe rânduri sau dacă ar trebui să fie un card simplu în acel caz.

## Observații de accesibilitate
- `<main id="content" tabindex="-1">` + skip-link sunt implementate corect (`app.html:1,116`) — bun.
- Statusul din header (`agent halted`, `venue connected` etc.) e comunicat prin puncte colorate + text alăturat, deci nu se bazează doar pe culoare — bun.
- Cardurile de metrici (`metric-card.ts`) nu au niciun `aria-label` care să lege eticheta de valoare într-un mod mai robust pentru screen reader-e cu structuri neobișnuite de citire, dar folosirea de `<p>` succesive e acceptabilă semantic.
- Nu am identificat un `<h2>`/`<h3>` explicit pentru "Paper book (simulated)" vs restul paginii — verificați ierarhia de headinguri în `dashboard.page.ts` pentru a confirma că nu se sare de la `h1` direct la text bold fără heading real.

## Observații responsive
- **Mobil (390px):** header-ul (brand + telemetrie + butoane + 2 bannere) ocupă ~35% din înălțimea ecranului înainte de a ajunge la conținut. Nu există meniu hamburger — nav-ul cu 9 itemi se transformă în 2 rânduri de linkuri text, ceea ce e funcțional dar consumă spațiu permanent (sticky top nu se aplică navului, dar header-ul chrome e sticky).
- Valoarea "Unrealized P&L" e tăiată la marginea dreaptă a ecranului pe mobil — vezi P0.
- Nu am putut testa tablet/landscape în această sesiune (limitare a auditului, vezi raportul central).

## Stările lipsă
- **Loading:** există `PageSkeleton` în cod (`shared/page-skeleton.ts`) dar nu am reușit să o observăm live (răspunsul local e prea rapid); trebuie confirmat manual că apare la prima încărcare cu conexiune lentă.
- **Eroare:** există banner global de eroare de conexiune (`state.connectionError()`), dar nu am putut declanșa un scenariu real de API căzut pentru a confirma comportamentul exact pe Dashboard.
- **Empty:** dacă `portfolio()` e null, comportamentul exact al paginii (skeleton vs. gol) nu a fost confirmat live.

## Task-uri pentru Cursor

### [P0] Formatează toate valorile numerice financiare înainte de afișare

**Problemă:** `MetricCard` și alte componente randează string-uri brute primite din API (ex. `5.357063999999999999999999906`), ceea ce produce text ilizibil, overflow de layout și pierde încrederea utilizatorului într-un produs financiar.

**Modificare recomandată:** Adaugă o funcție/pipe centralizată de formatare numerică (ex. `formatQuote(value, { decimals, currency })` folosind `Intl.NumberFormat`) și aplic-o în `MetricCard` (parametru `value` să accepte `number`, nu doar `string` brut), plus în toate tabelele care afișează prețuri/P&L/indicatori (Dashboard, Market, Asset detail, Orders, Risk).

**Fișiere/componente probabile:** `apps/console/src/app/shared/metric-card.ts`, `apps/console/src/app/core/models.ts` (lângă `pnlClass`), toate `*.page.ts` care afișează valori numerice.

**Comportament:** Valorile monetare se rotunjesc la 2-6 zecimale în funcție de instrument (crypto poate avea nevoie de mai multe zecimale la preț mic), niciodată mai mult de ~8 caractere vizibile fără truncare explicită cu tooltip pentru precizia completă.

**Criterii de acceptare:**
- Niciun card sau celulă de tabel nu afișează mai mult de 8-10 caractere pentru o valoare numerică fără truncare intenționată.
- Valorile financiare folosesc `Intl.NumberFormat` sau echivalent, nu concatenare de string brut.
- Testat pe `/`, `/market`, `/market/:symbol`, `/orders`, `/risk` — niciun overflow de card la 1440px sau 390px lățime.

**Testare:**
- Screenshot desktop 1440px și mobil 390px pe fiecare din cele 5 pagini de mai sus, confirmând că textul nu depășește granițele cardului/celulei.
- Test unitar pentru funcția de formatare cu valori extreme (foarte mici, foarte mari, `NaN`, `null`).

---

### [P1] Elimină dubla afișare a banner-ului HALTED

**Problemă:** Când agentul este halted, două bannere roșii aproape identice apar unul sub altul, redundant și consumând spațiu vertical inutil (vezi captură `/` la 1440px).

**Modificare recomandată:** Păstrează un singur banner HALTED (cel din `app.html` cu detalii complete: motiv + instrucțiune de resume), elimină duplicatul specific paginii dacă există, sau fuzionează informația într-un singur component reutilizabil `<app-halt-banner>`.

**Fișiere/componente probabile:** `apps/console/src/app/app.html:53-61`, `apps/console/src/app/features/dashboard.page.ts` (sau serviciul care randează al doilea banner).

**Comportament:** Un singur banner HALTED vizibil, cu severity `error`, motivul afișat o singură dată, link/instrucțiune spre pagina Risk pentru reset.

**Criterii de acceptare:**
- Zero duplicare de text "HALTED" pe niciuna dintre cele 10 pagini când agentul e oprit.
- Bannerul rămas comunică: motivul opririi, faptul că tranzacțiile sunt blocate, și unde se face reset.

**Testare:**
- Simulează starea `halted=true` (mock sau halt real în paper mode) și verifică vizual fiecare pagină din navigare.

---

### [P2] Adaugă unitate/simbol monetar lângă valorile Equity/Cash/P&L

**Problemă:** Cifrele din carduri nu au un sufix/prefix de monedă, ceea ce poate crea ambiguitate dacă produsul va afișa vreodată mai multe quote currencies.

**Modificare recomandată:** Adaugă un `hint` sau sufix discret (`USD`) lângă fiecare valoare monetară, folosind slotul `hint()` deja disponibil în `MetricCard`.

**Fișiere/componente probabile:** `apps/console/src/app/features/dashboard.page.ts`, `apps/console/src/app/shared/metric-card.ts`.

**Criterii de acceptare:**
- Fiecare card monetar din Dashboard afișează explicit unitatea (ex. "USD") fără să aglomereze vizual cardul.

**Testare:**
- Verificare vizuală pe desktop și mobil că sufixul nu produce wrap urât sau overflow.

## Componentele afectate
`MetricCard`, `PageHeader`, banner-ul global de halt din `App`, tabelul "Exposure", secțiunea "Today's session".

## Riscuri și dependențe
Formatarea numerică (P0) trebuie coordonată cu Market, Asset detail, Orders și Risk pentru consistență — vezi task global în `design-system-recommendations.md`. Nu implementați formatarea per-pagină izolat, riscă să introducă comportamente diferite pentru aceeași dată.

## Ce nu trebuie modificat
- Textul lede „Numbers are facts from the local engine, not forecasts" — păstrează tonul.
- Structura de bannere de siguranță (observer/halted/venue disconnected) — doar deduplicarea (P1), nu eliminarea informației.
- Linkul „Open orders" și logica de badge pentru `state.pending()`.

## Screenshot-uri / referințe vizuale
Capturi realizate live la 1440×900 (`ss_2089xb9f4`) și 390×844 (`ss_1934ex32y`, `ss_0610rnwke`) în sesiunea de audit din 2026-09-21; nu sunt salvate ca fișiere în repo — reproduceți navigând la `/` cu agentul în stare `halted`.
