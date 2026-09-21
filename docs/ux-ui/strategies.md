# Strategy center

**Ruta:** `/strategies`
**Componentă:** `apps/console/src/app/features/strategies.page.ts` (cea mai mare pagină din consolă — 381 linii)
**Data auditului:** 2026-09-21

## Scopul paginii
Gestionarea strategiilor de trading: listă, parametri, ciclu de viață (enable/disable/status), backtest și istoric de versiuni imuabile.

## Utilizatorul țintă
Operatorul/dezvoltatorul de strategii care ajustează parametri și rulează backtest-uri înainte de a promova o strategie.

## Acțiunea principală
Editarea parametrilor unei strategii și "Propose new version" / rularea unui backtest.

## Rezumatul problemelor
Pagina e funcțional cea mai completă din aplicație (versiuni imuabile, backtest, lifecycle actions) și are bune practici de siguranță ("no button here ever reaches a live Kraken order"). Problemele sunt de claritate a formularelor lungi, un amestec de limbă română/engleză, și lipsa de confirmare vizuală după acțiuni precum "Propose new version".

## Probleme P0/P1/P2/P3

### P1 — Amestec de limbă română și engleză în conținut
Descrierea strategiei EMA trend filter e integral în română ("Pe ETH/BTC, un trend confirmat de EMA(fast)>=EMA(slow) persistă suficient cât un long-only cu costurile Kraken curente..."), în timp ce toate etichetele UI din jur sunt în engleză ("Parameters", "Lifecycle actions", "Clone as"). Pentru un produs altfel complet în engleză, asta pare un artefact de conținut de test/seed, nu o decizie de design.
- **Verificat live:** `/strategies`, panoul de detaliu "EMA trend filter".

### P1 — Niciun feedback vizual confirmat pentru "Propose new version" / "Apply status" / "Clone"
Formularul de parametri ("editing writes a new immutable version") e o acțiune cu consecințe reale (creează o versiune nouă) dar butonul "Propose new version" nu are lângă el nicio indicație despre ce se întâmplă după click (toast, mesaj inline, redirect la versiunea nouă). Nu am putut testa click-ul în această sesiune (evitat conform regulilor auditului — "nu modifica interfața").

### P2 — Formular lung de parametri fără grupare vizuală
Parametrii (`fast_ema_period`, `slow_ema_period`, `adx_period`, `min_adx`, `atr_period`, `atr_stop_mult`, `atr_target_mult`) sunt afișați ca o listă verticală simplă de input-uri fără grupare logică (ex. "Trend" vs. "Risk/Exit"), ceea ce îngreunează scanarea pentru o strategie cu mulți parametri.

### P2 — Numele generat pentru "Clone as" pare trunchiat
Input-ul de clonare arată valoarea `baseline_ema_cross_co` care pare a fi un nume trunchiat (ex. `baseline_ema_cross_confirmed`). Trebuie verificat dacă e trunchiere reală de string sau doar lățimea input-ului care ascunde restul textului fără a permite scroll/select vizibil al conținutului complet.

### P3 — Badge-urile de status ("experimental", "enabled", "Backtest", "Live (locked)") sunt multe și diverse ca și culoare/formă în același rând
Șase badge-uri diferite apar pe un singur rând de titlu ("EMA trend filter"), ceea ce e informativ dar vizual aglomerat — ar putea fi grupate (status ciclu de viață vs. capabilități).

## Observații UX
- Mesajul lede ("Strategies only produce buy/sell/hold signals. RiskEngine still sizes every order and no button here ever reaches a live Kraken order.") e un exemplu excelent de prevenire a erorilor de percepție asupra riscului — de păstrat ca pattern pe toate paginile cu acțiuni.
- "Version history (read-only, immutable snapshots)" comunică corect imuabilitatea — bun pentru auditabilitate.
- Badge-ul roșu "Live (locked)" comunică vizual că live trading e blocat pentru această strategie — bun.

## Observații UI
- Layout pe 2 coloane (listă strategii în stânga, detaliu în dreapta) e potrivit pentru tipul de conținut.
- Butonul "Disable" din colțul din dreapta sus al panoului de detaliu e un buton secundar simplu (fără culoare de avertizare), deși dezactivarea unei strategii active e o acțiune cu impact — merită severity `warn` sau `danger` pentru consistență cu restul aplicației (ex. "Clear halt flag" e roșu).
- Tabelul de backtest ("Asset/Timeframe/Cost/Start/End/Run backtest") e dens dar clar la 1440px.

## Observații de accesibilitate
- Formularul de parametri folosește input-uri simple cu etichete deasupra (`fast_ema_period`, etc.) — verificați dacă etichetele sunt `<label for>` reale sau doar text vizual, pentru compatibilitate cu screen reader-e.
- Butoanele lifecycle ("Apply status", "Clone") ar trebui să aibă `aria-describedby` care să indice consecința (creează o versiune nouă vs. modifică una existentă), având în vedere diferența critică între "imuabil" și "editabil" din acest domeniu.

## Observații responsive
- Nu am testat `/strategies` pe mobil în această sesiune. Layout-ul pe 2 coloane cu formular lung de parametri e un candidat cu risc ridicat de a deveni greu de utilizat pe ecrane înguste (multe input-uri, tabel de versiuni, tabel de backtest) — recomand verificare directă.

## Stările lipsă
- **Empty (backtest):** confirmat — "No backtest runs yet / No data from the control plane yet." — bine implementat.
- **Loading (Run backtest):** neconfirmat live (backtest-ul rulează async conform textului "Runs the shared backtest engine asynchronously") — trebuie verificat ce vede utilizatorul cât timp rulează.
- **Error (backtest eșuat):** neconfirmat live.
- **Success (Propose new version / Apply status):** neconfirmat live — vezi P1.

## Task-uri pentru Cursor

### [P1] Tradu conținutul seed în engleză sau documentează politica de limbă

**Problemă:** Descrierea strategiei "EMA trend filter" e în română, restul UI e în engleză, creând inconsistență de limbă în același ecran.

**Modificare recomandată:** Dacă politica de produs e "UI în engleză", tradu textul din `config/strategies.yaml` (sau sursa datelor seed) în engleză. Dacă politica e "conținut poate fi în limba autorului", documentează asta explicit și separă vizual (ex. etichetă "notes (ro)").

**Fișiere/componente probabile:** `config/strategies.yaml`, `apps/console/src/app/features/strategies.page.ts`.

**Criterii de acceptare:**
- Toate textele vizibile pe `/strategies` pentru o strategie dată sunt în aceeași limbă, sau există o etichetă clară care justifică amestecul.

**Testare:**
- Verificare vizuală pe toate cele 4 strategii listate.

---

### [P1] Adaugă feedback vizual explicit după "Propose new version" / "Apply status" / "Clone"

**Problemă:** Acțiuni care creează versiuni imuabile noi nu au confirmare vizuală clară a rezultatului, riscând ca operatorul să facă click de mai multe ori sau să nu știe dacă acțiunea a reușit.

**Modificare recomandată:** Adaugă un `p-message`/toast de succes ("Version 2 created") sau, minim, scroll automat + highlight temporar al noii intrări în "Version history" după succes.

**Fișiere/componente probabile:** `apps/console/src/app/features/strategies.page.ts`.

**Comportament:** După orice acțiune de scriere (propose/apply status/clone), utilizatorul primește confirmare explicită fără să caute în tabelul de istoric.

**Criterii de acceptare:**
- Fiecare acțiune de scriere produce un feedback vizibil (toast/mesaj inline) distinct de eroare.
- Erorile de scriere (ex. parametru invalid) produc un mesaj de eroare specific, nu doar eșec silențios.

**Testare:**
- Testare manuală: propune o versiune nouă, confirmă apariția feedback-ului și a noii intrări în "Version history".

---

### [P2] Grupează vizual parametrii formularelor de strategie

**Problemă:** 7 parametri afișați ca listă plată fac dificilă înțelegerea rapidă a categoriilor (trend vs. risc/exit).

**Modificare recomandată:** Grupează parametrii sub subtitluri (ex. "Trend detection": fast/slow EMA, ADX; "Risk & exit": ATR period/stop/target) folosind `<h3>` sau `fieldset`/`legend`.

**Fișiere/componente probabile:** `apps/console/src/app/features/strategies.page.ts`.

**Criterii de acceptare:**
- Parametrii sunt vizual grupați pe minim 2 categorii logice, cu heading vizibil per grup.

**Testare:**
- Verificare vizuală pe strategia "EMA trend filter" (cea mai complexă din listă).

## Componentele afectate
Lista de strategii, panoul de detaliu, formularul de parametri, secțiunea "Lifecycle actions", tabelul "Version history", formularul de backtest.

## Riscuri și dependențe
Task-ul de traducere (P1) depinde de o decizie de produs (politică de limbă), nu doar de implementare.

## Ce nu trebuie modificat
- Mesajul de siguranță despre RiskEngine și lipsa oricărui buton spre ordine live.
- Modelul de versionare imuabilă (istoric read-only).

## Screenshot-uri / referințe vizuale
Capturi live desktop 1440px (`ss_7004paen6`, `ss_3180ppbcy`), sesiunea din 2026-09-21.
