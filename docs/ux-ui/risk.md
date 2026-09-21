# Risk management

**Ruta:** `/risk`
**Componentă:** `apps/console/src/app/features/risk.page.ts`
**Data auditului:** 2026-09-21

## Scopul paginii
Vizualizarea și editarea limitelor de risc (max daily loss, max drawdown, max orders/zi, max notional/ordin), resetarea flag-ului de halt, și un raport de stress/shock P&L.

## Utilizatorul țintă
Operatorul responsabil de guvernanța riscului — cea mai sensibilă pagină din aplicație din perspectiva siguranței financiare.

## Acțiunea principală
"Clear halt flag" (când agentul e oprit) sau editarea unei limite de risc urmată de scrierea în YAML.

## Rezumatul problemelor
Pagina are cele mai bune practici de siguranță din toată aplicația (confirmare cu token tastat "MAX_DAILY_LOSS", explicație clară că schimbările necesită restart). Cea mai mare slăbiciune e vizuală: cele trei bare de progres (Daily loss/Drawdown/Orders remaining) sunt toate afișate identic, albe, indiferent de cât de aproape e limita de a fi atinsă — exact pagina unde un semnal vizual de urgență ar conta cel mai mult.

## Probleme P0/P1/P2/P3

### P0 — Barele de progres nu au nicio culoare de severitate
`p-progressbar` pentru Daily loss/Drawdown/Orders remaining sunt randate fără `severity` sau clasă condițională — toate apar albe/neutre, indiferent dacă limita rămasă e 95% sau 5%. Pe pagina dedicată riscului, absența unui semnal vizual de "aproape de limită" (galben/roșu) e o lacună de siguranță, nu doar de estetică.
- **Verificat live:** `/risk`, desktop 1440px, secțiunea de bare sub cardurile de sumar.
- **Sursă:** `apps/console/src/app/features/risk.page.ts:65,69,73` — `<p-progressbar [value]="remainingPct(...)" [showValue]="false" />` fără logică de culoare condiționată.

### P1 — "Circuit breaker: HALTED" e text simplu, fără tag/culoare
Spre deosebire de header-ul global unde `trading_mode` e afișat ca `<p-tag>` colorat, valoarea "HALTED" din cardul "Circuit breaker" e text alb simplu — subminează vizibilitatea unei stări critice chiar pe pagina unde ar trebui să fie cea mai proeminentă.

### P2 — Bara "Orders remaining" pare parțial goală fără explicație numerică vizibilă pe bară
`[showValue]="false"` ascunde procentul de pe toate cele trei bare; utilizatorul trebuie să coreleze manual cardul de sus (ex. "8" din 10) cu bara de dedesubt — un pic de redundanță redusă ar ajuta lizibilitatea rapidă.

### P3 — "position sizing is engine-owned" apare ca text în coloana "Remaining" a rândului "Max notional / order", nu ca valoare
E corect informativ, dar rupe vizual coerența tabelului (celelalte rânduri au numere, acesta are propoziție) — ar putea fi o notă separată sub tabel.

## Observații UX
- Mesajul lede ("Limits are the source of truth in YAML. Writes require typing MAX_DAILY_LOSS and a restart before they apply.") e un exemplu excelent de prevenire a erorilor — operatorul știe exact ce se întâmplă înainte să scrie.
- Dialogul de confirmare cu token tastat pentru salvarea limitelor și pentru "Clear halt flag" (`apps/console/src/app/shared/confirm-danger.ts`) e o practică solidă de siguranță — necesită motiv (`reason`) obligatoriu în plus față de tastarea token-ului. Recomand acest pattern ca referință pentru orice altă acțiune periculoasă din aplicație.
- Banner-ul roșu de halt cu instrucțiunea explicită "Clearing the flag does not restart the agent or resume orders" previne o presupunere periculoasă (că un clear = resume automat) — de păstrat.

## Observații UI
- Cele 4 carduri de sumar (Daily loss/Drawdown/Orders remaining/Circuit breaker) sunt clare și bine aliniate la 1440px.
- Tabelul de limite (Configured/Consumed/Remaining) e clar și ușor de citit, cu valori mici (0, 200, 500) — nu suferă de problema de formatare numerică observată pe alte pagini, pentru că valorile din acest build sunt mici.
- Butonul "Clear halt flag" folosește corect `severity="danger"` — consecvent cu restul aplicației.

## Observații de accesibilitate
- Bare de progres (`p-progressbar`) fără `[showValue]` — verificați dacă PrimeNG expune `aria-valuenow`/`aria-valuemax` automat; dacă nu, adăugați explicit pentru screen reader-e, având în vedere criticitatea informației.
- Formularul de editare a limitelor (`max_daily_loss`, `max_drawdown` etc.) — verificați `<label for>` pe fiecare input.
- Dialogul de confirmare cu token necesită verificare de focus management (focus mutat automat pe primul câmp la deschidere) — `AutoFocus` e deja folosit în `confirm-danger.ts`, bun semn.

## Observații responsive
- **Mobil (390px), confirmat live:** cardurile de sumar se reorganizează corect într-un grid pe 3 coloane (Daily loss/Drawdown/Orders) + un rând separat pentru Circuit breaker — comportament responsive funcțional, cel mai bun observat în audit până la acest punct.
- Nu am putut confirma comportamentul tabelului de limite (Configured/Consumed/Remaining) mai jos pe pagină la 390px — verificare recomandată dat fiind tiparul de tabele late tăiate observat pe Orders.

## Stările lipsă
- **Loading:** neconfirmat live.
- **Error (scriere limite eșuată):** neconfirmat live — ce se întâmplă dacă YAML writeback eșuează?
- **Success (limite salvate):** neconfirmat live — există feedback vizual explicit după "Write YAML"?

## Task-uri pentru Cursor

### [P0] Colorează barele de progres în funcție de proximitatea față de limită

**Problemă:** Barele "Daily loss remaining", "Drawdown remaining", "Orders remaining" sunt neutre/albe indiferent de valoare, eliminând semnalul vizual de urgență pe pagina dedicată riscului.

**Modificare recomandată:** Adaugă o funcție `riskSeverity(remainingPct: number): 'ok' | 'warn' | 'danger'` (ex. >50% remaining = ok/verde, 20-50% = warn/galben, <20% = danger/roșu) și aplic-o ca styleClass/clasă CSS condiționată pe fiecare `p-progressbar`, folosind token-urile existente `--ok`/`--warn`/`--bad` din `styles.scss`.

**Fișiere/componente probabile:** `apps/console/src/app/features/risk.page.ts:65,69,73`, `apps/console/src/styles.scss`.

**Comportament:** La 95% remaining bara e verde; la 15% remaining bara devine roșie, semnalând vizual urgența fără ca operatorul să citească cifrele.

**Criterii de acceptare:**
- Fiecare bară de progres schimbă culoare vizibil în funcție de prag (verde/galben/roșu).
- Pragurile sunt configurabile/documentate (nu hard-codate fără explicație în cod).
- Testat cu date mock la 90%, 40%, 10% remaining pentru fiecare din cele 3 limite.

**Testare:**
- Captură vizuală pentru fiecare din cele 3 stări de prag, pe fiecare din cele 3 bare.

---

### [P1] Afișează "Circuit breaker" ca tag colorat, nu text simplu

**Problemă:** Valoarea "HALTED"/"ARMED" (sau echivalent) din cardul Circuit breaker e text alb simplu, subestimând vizual o stare critică.

**Modificare recomandată:** Înlocuiește textul cu `<p-tag>` colorat (severity `danger` pentru HALTED, `success` pentru starea normală), consecvent cu `trading_mode` din header (`app.html:6`).

**Fișiere/componente probabile:** `apps/console/src/app/features/risk.page.ts`.

**Criterii de acceptare:**
- Starea Circuit breaker e vizibil colorată (roșu pentru halted), la fel de proeminentă ca badge-ul "PAPER"/"LIVE" din header.

**Testare:**
- Verificare vizuală în stare halted și în stare normală (dacă poate fi simulată local).

## Componentele afectate
Cele 3 bare de progres, cardul "Circuit breaker", tabelul de limite, dialogurile de confirmare (`ConfirmDanger`).

## Riscuri și dependențe
Pragurile de severitate (P0) trebuie stabilite împreună cu echipa de risc/produs — nu sunt o alegere pur vizuală, ci un semnal operațional. Nu implementați praguri arbitrare fără confirmare.

## Ce nu trebuie modificat
- Fluxul de confirmare cu token tastat + motiv obligatoriu pentru salvarea limitelor și pentru clear halt — e cel mai bun pattern de siguranță din aplicație, folosiți-l ca referință, nu-l simplificați.
- Mesajul „Clearing the flag does not restart the agent or resume orders”.

## Screenshot-uri / referințe vizuale
Capturi live desktop 1440px (`ss_5954hwl3d`) și mobil 390px (`ss_5487g1xol`), sesiunea din 2026-09-21.
