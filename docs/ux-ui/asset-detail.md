# Asset detail

**Ruta:** `/market/:symbol` (dinamică — testat live cu `:symbol = BTCUSD`)
**Componentă:** `apps/console/src/app/features/asset.page.ts`
**Data auditului:** 2026-09-21

**Notă despre parametrul rutei:** `:symbol` este ticker-ul instrumentului (ex. `BTCUSD`, `ETHUSD`, `AAPL`). Comportamentul documentat aici e valabil pentru orice simbol din allowlist; simbolurile fără venue confirmat (ex. `AAPL`) ar putea avea stări diferite (neconfirmat live — vezi limitări).

## Scopul paginii
Detaliu tehnic pentru un singur instrument: chart candlestick (TradingView), snapshot de indicatori tehnici, semnalul curent al agentului (propunere, nu ordin), și un formular de "Run research analysis".

## Utilizatorul țintă
Operatorul care vrea să înțeleagă *de ce* agentul propune o direcție pe un instrument anume, înainte de a decide dacă aprobă sau ignoră.

## Acțiunea principală
Rulare analiză de research (`Run analysis`) — acțiune fără efect asupra pieței, doar informativă.

## Rezumatul problemelor
Chart-ul TradingView e bine integrat. Problema majoră (consistentă cu restul aplicației) e afișarea brută a tuturor indicatorilor tehnici (EMA, RSI, ATR, volume z) cu 10+ zecimale, ceea ce transformă un panou menit să fie "citit dintr-o privire" într-un bloc de text greu de parsat. Secțiunea "Position / orders" e goală fără niciun mesaj explicativ.

## Probleme P0/P1/P2/P3

### P0 — Toți indicatorii tehnici sunt afișați cu precizie brută
`EMA fast: 83110.91624960330140594613384`, `RSI 14: 84.15994181415162955009870813`, `ATR 14: 726.8285714285714285714285714` — niciunul dintre acești indicatori are vreo utilitate practică dincolo de 2-4 zecimale. E cel mai grav caz din toată aplicația al problemei globale de formatare (vezi `design-system-recommendations.md`).
- **Verificat live:** `/market/BTCUSD`, desktop 1440px, secțiunea "Technical snapshot".

### P1 — "Position / orders" e o secțiune goală fără mesaj
Sub "Agent signal (proposal)", secțiunea "Position / orders" nu afișează nimic quando nu există o poziție deschisă pe acel instrument — nici text, nici EmptyState. Utilizatorul nu poate distinge "nu am încărcat încă" de "nu ai poziție pe acest activ".
- **Sursă probabilă:** `apps/console/src/app/features/asset.page.ts` — secțiunea corespunzătoare "Position / orders".

### P2 — Limbaj mixt tehnic fără explicații pentru non-experți
Etichete precum "ADX confirms trend", "ema_cross fast=10 slow=20", "confidence 1" presupun cunoștințe de analiză tehnică. Pentru un produs care se adresează unui singur operator (probabil expert), e acceptabil, dar merită un tooltip minim pe "confidence" (scală 0-1? 0-10?) pentru claritate.

### P3 — "funding: unknown" / "open interest: unknown" ocupă spațiu fără valoare
Corect din punct de vedere al onestității datelor (nu inventează valori), dar vizual cele două rânduri "unknown" tind să se piardă lângă restul tabelului dens — ar putea fi vizual dezactivate (opacity redusă) pentru a semnala "indisponibil în acest build" mai clar decât text simplu.

## Observații UX
- Mesajul lede ("Candles use bar close time (lookahead-safe). Analyses are research reports, not orders. Position size stays engine-owned.") e excelent — comunică exact granițele de siguranță ale paginii.
- Separarea clară "Technical snapshot" (fapte) vs. "Agent signal (proposal)" (interpretare) respectă cerința de a distinge semnal de ordin — de păstrat.
- Formularul "Run research analysis" are un mesaj explicit "Level 1 copilot. Never places an order. recommended_action is not executable." — foarte bun pentru prevenirea erorilor de percepție.

## Observații UI
- Chart-ul TradingView ocupă spațiu generos și e lizibil, cu EMA fast/slow suprapuse pe candele — bun.
- Selectorul de Timeframe (1h) e plasat corect în dreapta sus a chart-ului, dar nu am putut confirma dacă schimbarea lui reactualizează și panourile de dedesubt (Technical snapshot) sau doar chart-ul.
- Cele două coloane ("Technical snapshot" / "Agent signal") au înălțimi inegale — coloana din dreapta rămâne goală mult sub conținutul propriu-zis, creând un dezechilibru vizual clar la 1440px.

## Observații de accesibilitate
- Chart-ul TradingView e un widget extern (iframe probabil) — verificați dacă are un `title`/`aria-label` descriptiv pentru screen reader-e, sau cel puțin un rezumat textual alăturat al nivelurilor cheie (deja parțial acoperit de "Technical snapshot").
- Selectorul de Timeframe trebuie verificat pentru operare completă cu tastatura (dropdown nativ vs. custom).

## Observații responsive
- Nu am testat explicit pagina de detaliu pe mobil în această sesiune (limitare a auditului). Chart-ul TradingView, la lățimi înguste, are risc ridicat de a deveni ilizibil sau de a forța scroll orizontal — recomand verificare directă prioritară, având în vedere că e o pagină cu grafic.

## Stările lipsă
- **Empty (Position/orders):** confirmat gol fără mesaj (vezi P1).
- **Loading:** neconfirmat live pentru chart sau pentru "Run analysis" (există un buton, dar starea de "se procesează" nu a fost observată).
- **Error:** ce se întâmplă dacă "Run analysis" eșuează (LLM indisponibil, timeout)? Neconfirmat live.

## Task-uri pentru Cursor

### [P0] Rotunjește toți indicatorii tehnici la 2-4 zecimale relevante

**Problemă:** EMA, RSI, ATR, volume z sunt afișați cu 10-16 zecimale, contrar oricărei utilități practice pentru citire umană.

**Modificare recomandată:** Aplică formatarea numerică centralizată (vezi `design-system-recommendations.md`): prețuri (EMA fast/slow, swing high/low) la 2 zecimale, RSI/ADX la 1-2 zecimale, volume z la 2 zecimale.

**Fișiere/componente probabile:** `apps/console/src/app/features/asset.page.ts`.

**Comportament:** `83110.91624960330140594613384` → `83110.92`; `84.15994181415162955009870813` → `84.16`.

**Criterii de acceptare:**
- Niciun indicator din "Technical snapshot" nu afișează mai mult de 2-4 zecimale.
- Valorile rămân corecte numeric (doar afișarea e rotunjită, nu calculul intern).

**Testare:**
- Captură desktop pe `/market/BTCUSD` și `/market/ETHUSD`, confirmă lizibilitatea tabelului.

---

### [P1] Adaugă un mesaj explicit când nu există poziție/ordine pe activ

**Problemă:** Secțiunea "Position / orders" e complet goală fără niciun indiciu vizual, ambiguă între "se încarcă" și "nu ai poziție".

**Modificare recomandată:** Reutilizează componenta `EmptyState` existentă (`apps/console/src/app/shared/empty-state.ts`) cu un mesaj de tipul "No open position on {symbol}".

**Fișiere/componente probabile:** `apps/console/src/app/features/asset.page.ts`.

**Criterii de acceptare:**
- Secțiunea "Position / orders" afișează întotdeauna fie datele poziției, fie un `EmptyState` explicit — niciodată gol fără text.

**Testare:**
- Verificare pe un simbol fără poziție deschisă (ex. AAPL) și pe unul cu poziție (ETHUSD, conform datelor din Orders).

## Componentele afectate
Panoul "Technical snapshot", panoul "Agent signal (proposal)", secțiunea "Position / orders", formularul "Run research analysis".

## Riscuri și dependențe
Formatarea numerică e partajată cu Dashboard/Market/Orders/Risk — un singur task global, nu implementări separate.

## Ce nu trebuie modificat
- Mesajele de siguranță ("Analyses are research reports, not orders", "Never places an order") — sunt esențiale pentru prevenirea confuziei semnal/ordin.
- Integrarea TradingView și overlay-urile EMA pe chart.

## Screenshot-uri / referințe vizuale
Capturi live desktop 1440px (`ss_39159tptt`, `ss_8235iwux3`) pentru `/market/BTCUSD`, sesiunea din 2026-09-21.

## Limitări ale acestui audit pentru pagină
Nu am testat `:symbol` pentru simboluri fără venue confirmat (AAPL, MSFT) și nu am testat comportamentul responsive al chart-ului.
