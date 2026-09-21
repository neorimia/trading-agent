# Orders and positions

**Ruta:** `/orders`
**Componentă:** `apps/console/src/app/features/orders.page.ts`
**Data auditului:** 2026-09-21

## Scopul paginii
Aprobări umane în așteptare, poziții curente deschise, și istoricul complet de ordine (paper trading în acest build).

## Utilizatorul țintă
Operatorul care verifică dacă e nevoie să aprobe/respingă un ordin, sau care investighează de ce ordinele anterioare au fost respinse.

## Acțiunea principală
Aprobare/respingere a unei propuneri de ordin în așteptare (când există).

## Rezumatul problemelor
Cea mai gravă problemă de date din întreaga aplicație e vizibilă aici: coloana uP&L a poziției afișează float brut needitat, IAR — spre deosebire de Dashboard/Market/Risk — nu are deloc culoare semantică (pnl-pos/pnl-neg), inconsistent față de restul aplicației. Istoricul de ordine e o listă lungă, nepaginată, dominată de zeci de rânduri "rejected, qty 0" fără niciun motiv de respingere vizibil, iar rândurile "filled" au coloana Instrument goală.

## Probleme P0/P1/P2/P3

### P0 — uP&L brut, needitat, ȘI fără culoare semantică (inconsistent cu restul aplicației)
Coloana "uP&L" din tabelul "Positions" afișează `5.357063999999999999999999906` ca text simplu monospace, fără clasa `pnl-pos`/`pnl-neg`/`pnl-zero` aplicată pe Dashboard, Market și Risk pentru aceeași categorie de date.
- **Sursă:** `apps/console/src/app/features/orders.page.ts:79` — `<td class="mono">{{ row.unrealized_pnl ?? '-' }}</td>` — nu apelează `pnlClass`, spre deosebire de `dashboard.page.ts:46`, `market.page.ts:64`, `risk.page.ts:133`.

### P1 — Ordine "rejected" fără motiv vizibil
Zeci de rânduri consecutive arată `buy ETHUSD qty=0 status=rejected` fără nicio coloană care să explice *de ce* au fost respinse (risc? validare? venue offline?). Pentru un agent de trading, a nu putea explica de ce propriile ordine au fost respinse e un risc de încredere și de debugging pentru operator.
- **Verificat live:** `/orders`, desktop 1440px, tabelul "Order history".

### P1 — Rândurile "filled" au coloana Instrument goală
La rândurile cu status `filled`, coloana "Instrument" apare goală, în timp ce toate rândurile "rejected" o au populată (`ETHUSD`). Inconsecvență de date care creează confuzie asupra cărui instrument aparține un fill.

### P1 — Istoric de ordine nepaginat, fără filtrare pe dată/instrument
Singurul filtru disponibil e "Filter status" (text). Cu zeci de rânduri deja vizibile într-o sesiune scurtă de paper trading, tabelul va deveni impracticabil de navigat pe termen lung fără paginare, sortare pe dată, sau filtrare pe instrument.

### P2 — Coloana "Correlation" ocupă mult spațiu cu UUID-uri brute
Fiecare rând afișează un UUID complet (`47d80672-ff97-4dbf-8eff-ab88c26f8a38`), util pentru debugging/audit dar rar necesar la scanare vizuală. Ar putea fi trunchiat cu opțiune de copiere completă la click.

### P3 — Timestamp-uri ISO8601 brute (`2026-09-19T20:02:54.385600Z`)
Corecte pentru audit, dar greu de citit rapid comparativ cu un format relativ/local (ex. "19 Sept, 20:02 UTC").

## Observații UX
- Mesajul lede ("PAPER TRADING - every live order would show notional, price, fee and estimated risk. Live approve is blocked in this build.") comunică foarte bine limitarea build-ului curent — excelent exemplu de transparență.
- Starea goală pentru "Pending human approval" ("No pending approvals — The agent is not waiting on an operator decision.") e clară și liniștitoare, cu iconiță de check — bun pattern de reutilizat.
- Distincția "Positions" (curent) vs. "Order history" (istoric complet) e logică și ușor de urmărit.

## Observații UI
- Tabelul "Positions" e compact și clar cât timp are un singur rând; nu a putut fi verificat cu poziții multiple.
- Tabelul "Order history" e dens, monospace, consistent cu restul aplicației, dar lățimea (10 coloane) depășește confortabil 1440px, apropiindu-se de marginea ferestrei.

## Observații de accesibilitate
- Inputul "Filter status" ar trebui verificat pentru `<label>` asociat (vizual ascuns acceptabil).
- Coloanele de tabel (10 coloane în Order history) — verificați dacă `<th scope="col">` e prezent pentru navigare corectă cu screen reader pe tabele late.

## Observații responsive
- **Mobil (390px), confirmat live:** tabelul "Order history" NU se adaptează — rămâne un tabel lat, tăiat la marginea ecranului (se văd doar Time/Mode/Instrument/Side/Qty/Status/parțial Fill, restul coloanelor ies din viewport fără indicator vizual de scroll orizontal). Utilizatorul nu are niciun semnal că mai există conținut la dreapta.
- Recomand verificarea acelorași probleme pe tabelul "Positions" cu mai multe poziții simultane.

## Stările lipsă
- **Loading:** neconfirmat live.
- **Error (aprobare eșuată):** neconfirmat live — nu a existat nicio aprobare în așteptare în timpul auditului.
- **Empty (order history):** neconfirmat (istoricul avea deja date).

## Task-uri pentru Cursor

### [P0] Aplică `pnlClass` pe coloana uP&L din tabelul Positions

**Problemă:** uP&L nu are culoare semantică (verde/roșu) în Orders, deși aceeași dată e colorată consecvent pe Dashboard, Market și Risk — inconsistență de design system pe o pagină financiară.

**Modificare recomandată:** Înlocuiește `<td class="mono">{{ row.unrealized_pnl ?? '-' }}</td>` cu `<td class="mono" [class]="pnlClass(row.unrealized_pnl)">{{ row.unrealized_pnl ?? '-' }}</td>`, la fel ca în `risk.page.ts:133`.

**Fișiere/componente probabile:** `apps/console/src/app/features/orders.page.ts:79`.

**Criterii de acceptare:**
- uP&L pozitiv apare verde, negativ apare roșu, zero apare neutru — identic cu comportamentul din Dashboard/Market/Risk.

**Testare:**
- Verificare vizuală cu o poziție cu uP&L pozitiv și una (simulată/mockuită) cu uP&L negativ.

---

### [P1] Afișează motivul de respingere pentru ordinele "rejected"

**Problemă:** Operatorul nu poate distinge de ce ordinele au fost respinse (risc, validare, venue) fără să sape în loguri externe consolei.

**Modificare recomandată:** Adaugă o coloană "Reason" sau o iconiță expandabilă pe rând care arată motivul de respingere primit de la API (dacă backend-ul îl expune deja; dacă nu, flag pentru echipa de backend să-l adauge la payload).

**Fișiere/componente probabile:** `apps/console/src/app/features/orders.page.ts`, `apps/console/src/app/core/models.ts` (model de order/tip de răspuns).

**Criterii de acceptare:**
- Fiecare rând `rejected` afișează un motiv lizibil (text sau tooltip la hover/focus pe status).
- Dacă backend-ul nu expune încă motivul, task-ul documentează explicit dependența (vezi „Riscuri și dependențe”).

**Testare:**
- Verificare pe minim 5 rânduri `rejected` din istoricul curent că motivul e vizibil și coerent cu contextul (ex. qty=0 sugerează validare de sizing eșuată).

---

### [P1] Adaugă paginare/filtrare pe dată și instrument la Order history

**Problemă:** Tabelul crește nelimitat fără paginare, sortare pe dată, sau filtrare pe instrument — doar un filtru text de status.

**Modificare recomandată:** Adaugă paginare (PrimeNG `p-table` cu `[paginator]="true"`) și un al doilea filtru pentru instrument, plus interval de dată opțional.

**Fișiere/componente probabile:** `apps/console/src/app/features/orders.page.ts`.

**Criterii de acceptare:**
- Tabelul afișează maximum 20-25 rânduri per pagină, cu control de paginare vizibil.
- Filtrare funcțională pe instrument, independentă de filtrul de status.

**Testare:**
- Test cu 100+ rânduri mock, confirmă paginare corectă și performanță de randare.

---

### [P1] Corectează coloana Instrument goală pe rândurile "filled"

**Problemă:** Rândurile cu status `filled` nu afișează instrumentul, deși informația probabil există în payload (celelalte coloane — qty, fill, correlation — sunt populate corect).

**Modificare recomandată:** Verifică maparea `row.instrument` pentru rândurile de tip fill; corectează sursa de date sau maparea din `orders.page.ts`.

**Fișiere/componente probabile:** `apps/console/src/app/features/orders.page.ts`, sursa API pentru order history.

**Criterii de acceptare:**
- Toate rândurile din Order history (indiferent de status) afișează instrumentul corect.

**Testare:**
- Verificare pe toate rândurile `filled` vizibile în istoricul curent.

## Componentele afectate
Tabelul "Positions", tabelul "Order history", starea goală "Pending human approval".

## Riscuri și dependențe
Task-ul „motiv de respingere” (P1) poate necesita ca backend-ul (`src/execution/broker.py`, `src/risk/risk_engine.py`) să expună un câmp `rejection_reason` dacă nu există deja — verificați înainte de a estima implementarea doar pe frontend.

## Ce nu trebuie modificat
- Mesajul „Live approve is blocked in this build” și logica de blocare a aprobării live.
- Starea goală pentru „No pending approvals”.

## Screenshot-uri / referințe vizuale
Capturi live desktop 1440px (`ss_9717ft20z`, `ss_800183rmf`) și mobil 390px (`ss_0879odesb`), sesiunea din 2026-09-21.
