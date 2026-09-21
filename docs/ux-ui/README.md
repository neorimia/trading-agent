# Audit UX/UI — Local trading agent console

**Data auditului:** 2026-09-21
**Aplicație:** `apps/console` (Angular 19+ standalone, PrimeNG, temă dark-only), rulată local la `http://127.0.0.1:4200/`
**Autor:** audit automatizat (navigare live + inspecție de cod sursă), fără modificări de interfață

## Cum s-a făcut auditul
Am navigat live, cu automatizare de browser, prin toate cele 10 rute definite în `apps/console/src/app/app.routes.ts`, la lățime desktop (1440px) și mobil (390px), am citit consola browser-ului pentru erori, și am corelat fiecare observație vizuală cu sursa de cod relevantă (componentă, șablon, stil) pentru acuratețe. Nu am modificat nicio interfață, nu am scris cod de producție, nu am instalat dependențe.

## Pagini analizate și starea lor

| Pagină | Rută | Fișier | Stare |
|---|---|---|---|
| Dashboard | `/` | [dashboard.md](dashboard.md) | Auditat complet (desktop + mobil) |
| Market overview | `/market` | [market.md](market.md) | Auditat desktop; mobil neconfirmat |
| Asset detail | `/market/:symbol` | [asset-detail.md](asset-detail.md) | Auditat desktop (BTCUSD); mobil neconfirmat |
| Strategy center | `/strategies` | [strategies.md](strategies.md) | Auditat desktop; mobil neconfirmat |
| Orders and positions | `/orders` | [orders.md](orders.md) | Auditat complet (desktop + mobil) |
| Risk management | `/risk` | [risk.md](risk.md) | Auditat complet (desktop + mobil) |
| Research and intelligence | `/research` | [research.md](research.md) | Auditat desktop; mobil neconfirmat |
| Asset discovery | `/discovery` | [discovery.md](discovery.md) | Auditat doar starea goală — date reale neevaluate |
| Agent activity | `/agent` | [activity.md](activity.md) | Auditat desktop; mobil neconfirmat |
| Settings and security | `/settings` | [settings.md](settings.md) | Auditat desktop; mobil neconfirmat |

Nu există o pagină de login separată — accesul e controlat printr-un token de operator opțional (`/settings`) și un `permissionGuard` care momentan permite mereu vizualizarea (mutațiile sunt blocate la nivel de componentă pentru rolul `observer`).

## Top 10 probleme globale

1. **[P0] Valorile numerice financiare sunt afișate cu precizie brută de float, needitate, pe aproape toată aplicația** (Dashboard, Market, Asset detail, Orders). Cel mai grav și mai răspândit defect din audit — vezi task global mai jos.
2. **[P0] Tokenul de operator din Settings e introdus într-un câmp needeghizat (plaintext)** — risc de securitate/UX direct. Vezi `settings.md`.
3. **[P0] Barele de progres din Risk nu au nicio culoare de severitate** — pe pagina dedicată riscului, lipsește exact semnalul vizual care contează cel mai mult. Vezi `risk.md`.
4. **[P1] Culoarea semantică pentru P&L (`pnlClass`) e aplicată inconsecvent** — prezentă pe Dashboard/Market/Risk, absentă pe Orders, pentru aceeași categorie de date. Vezi `orders.md`.
5. **[P1] Dublă afișare a banner-ului HALTED** pe Dashboard (și probabil alte pagini) — redundanță vizuală și consum de spațiu, mai ales pe mobil. Vezi `dashboard.md`.
6. **[P1] Tabelele late (Orders, probabil Market) nu au strategie responsive** — pe mobil, coloanele sunt pur și simplu tăiate la marginea ecranului, fără indicator de scroll orizontal. Vezi `orders.md` și `design-system-recommendations.md`.
7. **[P1] Ordinele "rejected" nu au motiv vizibil** — zeci de rânduri "rejected, qty 0" fără explicație, subminând încrederea și capacitatea de debugging a operatorului. Vezi `orders.md`.
8. **[P1] Jurnalul de audit (Activity) nu are rezumat uman-lizibil per eveniment** — fiecare intrare arată doar `tip · UUID`, forțând expandare manuală pentru a înțelege ce s-a întâmplat. Vezi `activity.md`.
9. **[P1] Flag-urile critice de siguranță din Settings (Live flag, Withdraw enabled) nu au culoare semantică** — text simplu pentru exact informația pe care operatorul trebuie s-o poată verifica dintr-o privire. Vezi `settings.md`.
10. **[P1] Istoricul de ordine și jurnalul de audit nu au paginare/filtrare avansată** — ambele cresc nelimitat, cu un singur filtru text simplu. Vezi `orders.md` și `activity.md`.

## Probleme comune între pagini

- **Formatare numerică lipsă** — apare pe Dashboard, Market, Asset detail, Orders (nu și pe Risk, unde valorile din acest build sunt întâmplător mici). Cauza e comună: componentele randează direct string-uri brute primite din API, fără nicio funcție de formatare (`{{ value() }}` fără pipe, fără `toFixed`/`Intl.NumberFormat`).
- **Tabele late fără strategie responsive** — Orders (confirmat live), probabil Market și Risk (limite de tabel).
- **Culoare semantică (`pnlClass`, `p-tag`) aplicată inconsecvent** — prezentă în unele locuri (Dashboard, Market, Strategies, header) dar absentă în altele (Orders uP&L, Risk circuit breaker, Settings boolean flags) pentru date de aceeași natură.
- **Liste/istorice fără paginare** — Orders (order history) și Activity (audit trail) au ambele risc de creștere nelimitată fără control de filtrare avansată.
- **Stări de eroare needocumentate/neconfirmate live** — nicio pagină cu acțiuni de scriere (Strategies, Risk, Settings, Orders approval) nu a putut fi testată cu un eșec real de API în această sesiune.

## Inconsistențe de design system

- `pnlClass` (culoare verde/roșu pentru P&L) aplicată în 3 din 4 locuri relevante (lipsă pe Orders).
- Flag-uri booleene de siguranță afișate uneori ca `p-tag` colorat (Trading mode în header), alteori ca text simplu (Live flag, Withdraw enabled în Settings; Circuit breaker în Risk).
- Butonul "Disable" din Strategies nu folosește `severity="danger"`/`"warn"`, spre deosebire de toate celelalte acțiuni cu impact din aplicație.
- Amestec de limbă română/engleză pe conținutul seed din Strategies, în timp ce restul UI e integral în engleză.

## Componente care trebuie standardizate

- **Tabel responsive** — o singură soluție reutilizabilă (scroll orizontal cu indicator, sau fallback card-list pe mobil) pentru Orders, Market, Risk.
- **Formatare numerică** — o singură funcție/pipe centralizată, aplicată peste tot unde apar prețuri, P&L, indicatori tehnici.
- **Indicator de severitate** (verde/galben/roșu) — extins de la `pnlClass` la un helper generic reutilizabil pentru bare de progres, flag-uri booleene, și orice altă stare cu prag de risc.
- **Rezumat de eveniment uman-lizibil** — pattern nou necesar pentru Activity, posibil reutilizabil și pentru notificări viitoare.

## Tokens recomandate
Vezi detaliile complete în [design-system-recommendations.md](design-system-recommendations.md). Pe scurt: aplicația are deja o bază solidă de tokens de culoare (`--ok`/`--bad`/`--warn`/`--paper`/`--live`) și tipografie (`IBM Plex Sans` + `IBM Plex Mono`) — recomandarea principală e **aplicarea consecventă** a ce există deja, nu crearea unei palete noi. Singurul gol structural identificat e absența unor tokens de spacing explicite (valorile sunt hardcodate în `rem` per regulă).

## Prioritizare globală

Conform criteriilor cerute (siguranță/risc financiar → blocarea fluxurilor → claritatea datelor → accesibilitate → responsive → consistență → performanță → polish vizual):

1. **Siguranță/risc:** mascarea tokenului de operator (P0), culoarea de severitate pe barele de risc (P0), culoarea pe flag-urile Settings (P1).
2. **Claritatea datelor:** formatarea numerică globală (P0) — afectează încrederea în produs pe 4 pagini simultan.
3. **Consistență:** `pnlClass` pe Orders, `p-tag` pe Circuit breaker, severity pe butonul Disable.
4. **Blocare fluxuri/claritate operațională:** motiv de respingere pe Orders, rezumat de eveniment pe Activity.
5. **Responsive:** strategie de tabel pentru mobil.
6. **Polish:** microcopy (Research), traducere conținut seed (Strategies), grupare formular (Strategies).

## Ordinea recomandată de implementare

1. Formatare numerică centralizată (afectează 4 pagini deodată — implementați o singură dată, apoi aplicați).
2. Mascarea tokenului de operator (Settings) — izolat, rapid, risc de securitate.
3. Culoare de severitate pe barele de progres (Risk) — izolat, impact mare pe siguranță percepută.
4. `pnlClass` pe Orders + `p-tag` pe Circuit breaker + flag-uri Settings — grup mic de fix-uri de consistență.
5. Deduplicarea banner-ului HALTED.
6. Strategie de tabel responsive — aplicată apoi pe Orders, Market, Risk.
7. Motiv de respingere pe Orders + rezumat de eveniment pe Activity (necesită posibil suport de backend — verificați dependențele înainte).
8. Paginare/filtrare avansată pe Orders și Activity.
9. Polish: microcopy Research, traducere/documentare limbă Strategies, grupare formular parametri.

## Dependențe între task-uri
- Task-urile de „motiv de respingere" (Orders) și „rezumat eveniment" (Activity) pot necesita expunerea unor câmpuri noi din backend (`src/execution/broker.py`, `src/risk/risk_engine.py`, `src/control/`) — nu le estimați ca fiind doar frontend fără verificare prealabilă.
- Formatarea numerică (task #1) trebuie implementată o singură dată, central, înainte de a fi aplicată pe fiecare pagină — evitați soluții izolate per pagină care ar reintroduce inconsistență.

## Quick wins (impact mare, efort mic)
- Mascarea inputului de token (`type="password"`) — o linie de cod, rezolvă un risc de securitate/UX real.
- `pnlClass` pe coloana uP&L din Orders — o linie de cod, aliniază 4 pagini.
- `severity="danger"` pe butonul "Disable" din Strategies.
- Eliminarea dublei bannerizări HALTED de pe Dashboard.
- Tooltip pe badge-urile "confirmed"/"research-only" din Market.

## Redesign-uri mai complexe
- Strategia unică de tabel responsive (Orders, Market, Risk) — necesită decizie de design (scroll orizontal vs. card-list) înainte de implementare.
- Rezumatul uman-lizibil per tip de eveniment în Activity — necesită mapare tip-eveniment → mesaj, coordonată cu structura reală a payload-urilor din backend.
- Paginare + filtrare avansată pe Orders și Activity.
- Grupare vizuală a formularului de parametri din Strategies.

## Riscuri
- Modificarea formatării numerice trebuie să afecteze doar afișarea, niciodată valorile interne folosite în calcule de risc/execuție — separați clar formatarea de logica de business.
- Pragurile de severitate pentru barele de risc (verde/galben/roșu) sunt o decizie operațională, nu doar vizuală — necesită validare din partea echipei de risc/produs înainte de a fi hardcodate.
- Niciun task din acest audit nu recomandă ascunderea, atenuarea sau reformularea informațiilor despre pierderi, erori, sau stări de halt — dimpotrivă, majoritatea task-urilor P0/P1 cer *mai multă* vizibilitate pe aceste stări (culoare, rezumat, motiv), nu mai puțină.

## Criterii globale de succes
- Nicio valoare financiară afișată în UI nu depășește precizia relevantă pentru citire umană (max. 2-6 zecimale, în funcție de context).
- Fiecare stare cu implicații de siguranță (halted, live flag, withdraw enabled, limite de risc aproape de prag) e comunicată prin culoare + text, niciodată prin text simplu izolat.
- Niciun tabel sau card nu produce overflow vizual la 1440px sau 390px lățime.
- Toate acțiunile de scriere au feedback vizual explicit de succes/eroare.
- Consecvență 100% în aplicarea `pnlClass`/severity pe toate paginile care afișează date financiare de aceeași natură.

## Limitări ale acestui audit
- **Discovery** — store-ul era gol în timpul sesiunii; nu a fost evaluată starea "populated" (lista reală de candidați cu componente de scor). Necesită audit de urmărire după un run de pipeline.
- **Stări de eroare** — nu am putut declanșa live niciun scenariu real de eșec API (server căzut, scriere eșuată, backtest eșuat, aprobare respinsă) pe nicio pagină. Recomand un audit dedicat cu API-ul indisponibil/simulat.
- **Loading states** — `PageSkeleton` există în cod dar răspunsurile locale au fost prea rapide pentru a-l observa live pe orice pagină; necesită test cu network throttling.
- **Responsive tabletă** (769–1199px) — netestat în această sesiune; doar desktop (1440px) și mobil (390px) au fost verificate live.
- **Responsive mobil** — confirmat live doar pe Dashboard, Orders și Risk; celelalte 7 pagini au fost evaluate doar la 1440px, cu riscuri semnalate prin analogie (nu confirmate direct).
- **Contrast de culoare** — nu am putut rula un instrument automat (axe-core/Lighthouse) în această sesiune; observațiile de contrast sunt vizuale, nu măsurate.
- **Login/roluri multiple** — aplicația pare să aibă un singur rol activ observabil (`operator`); comportamentul complet pentru rolul `observer` (menționat în banner: "Observer role: viewing only") nu a fost testat direct (necesită un token/context diferit).

## Livrare finală

**Pagini analizate:** Dashboard, Market, Asset detail, Strategy center, Orders and positions, Risk management, Research and intelligence, Asset discovery, Agent activity, Settings and security — toate cele 10 rute din `app.routes.ts`.

**Fișiere Markdown create:**
- `docs/ux-ui/README.md` (acest fișier)
- `docs/ux-ui/design-system-recommendations.md`
- `docs/ux-ui/dashboard.md`
- `docs/ux-ui/market.md`
- `docs/ux-ui/asset-detail.md`
- `docs/ux-ui/strategies.md`
- `docs/ux-ui/orders.md`
- `docs/ux-ui/risk.md`
- `docs/ux-ui/research.md`
- `docs/ux-ui/discovery.md`
- `docs/ux-ui/activity.md`
- `docs/ux-ui/settings.md`

**Probleme critice (P0):** formatare numerică brută pe 4 pagini, token de operator needeghizat (Settings), bare de risc fără culoare de severitate (Risk).

**Primele 10 task-uri recomandate pentru Cursor:** vezi secțiunea „Top 10 probleme globale" de mai sus — fiecare are un task corespunzător detaliat în fișierul paginii respective.

**Ordinea de implementare:** vezi secțiunea dedicată de mai sus.

**Quick wins:** vezi secțiunea dedicată de mai sus.

**Redesign-uri majore:** strategia de tabel responsive, rezumatul de evenimente din Activity, paginarea Orders/Activity.

**Componente globale de refactorizat:** formatare numerică centralizată, helper de severitate reutilizabil, strategie de tabel responsive.

**Pagini care nu au putut fi verificate complet:** Discovery (stare "populated" neevaluată din lipsă de date).

**Limitări generale ale auditului:** vezi secțiunea dedicată de mai sus — în principal, stările de eroare și loading nu au putut fi declanșate live, iar testarea responsive completă (toate paginile × toate breakpoint-urile) nu a fost posibilă în bugetul acestei sesiuni.
