# Design system — recomandări

**Data auditului:** 2026-09-21
**Context:** Aplicația (`apps/console`) e Angular 19+ standalone, folosind PrimeNG cu un preset custom (`apps/console/src/app/core/console.preset.ts`) și un fișier global de stiluri (`apps/console/src/styles.scss`, ~1000 linii) cu tokens CSS deja definite. **Acesta nu e un greenfield** — există deja o bază solidă de tokens și componente reutilizabile (`MetricCard`, `PageHeader`, `PageSkeleton`, `EmptyState`, `ConfirmDanger`). Recomandările de mai jos consolidează și extind ce există deja, nu propun un limbaj vizual nou.

## Color tokens (existente, de păstrat și extins)

Deja definite în `:root` (`styles.scss:3-17`):

```
--bg: #12141a        --bg-elev: #1b1e25     --bg-sunken: #0e1014
--stroke: #2c3038     --text: #e6e8ee        --muted: #8b909c
--paper: #4d6b8a      --live: #b45a1e
--ok: #3d9a6a          --bad: #c45b5b          --warn: #c9a227
--error-bg: #3a1c1c    --warn-bg: #3a3218
```

**Recomandare:** aceste tokens sunt bine alese pentru un tool financiar sobru (nu saturate, nu "neon terminal"). Problema nu e lipsa tokens, e **aplicarea inconsistentă** — vezi secțiunea „Inconsistențe" din `README.md`. Nu introduceți o paletă nouă; auditați și extindeți acoperirea celei existente.

**Task recomandat:** adăugați un token intermediar `--warn-strong` sau reutilizați `--warn`/`--bad` pentru pragurile de severitate ale barelor de progres din Risk (vezi `risk.md`).

## Semantic colors

- Succes/pozitiv → `--ok` (deja folosit prin `pnl-pos`)
- Eroare/negativ/pericol → `--bad` (deja folosit prin `pnl-neg` și `severity="danger"`)
- Atenție → `--warn`
- **Regulă nouă recomandată:** orice valoare booleană cu implicații de siguranță (live flag, withdraw enabled, halted, venue disconnected) trebuie randată printr-un `p-tag`/badge colorat, niciodată ca text simplu. Momentan aplicat parțial (header, Trading mode) dar nu peste tot (Settings, Risk circuit breaker) — vezi task-urile din `settings.md` și `risk.md`.

## Dark mode

Aplicația e **dark-only** (`color-scheme: dark` hardcodat, `.theme-dark` pe `<div class="app">`). Nu am identificat niciun toggle sau suport pentru light mode. Pentru un tool intern, single-operator, asta e o alegere rezonabilă — **nu recomandăm adăugarea light mode** ca prioritate; ar fi efort semnificativ pentru zero cerere observată. Dacă apare cerință de accesibilitate pentru fotosensibilitate/contrast, tratați separat ca temă de accesibilitate, nu ca "light mode" complet.

## Typography scale

Definit în `styles.scss:22,45-67`: `IBM Plex Sans` (UI) + `IBM Plex Mono` (date numerice, prin clasa `.mono`), bază `14px`.

```
h1: 1.65rem / 600   h2: 1.05rem / 600   h3: 0.95rem / 600
body: 14px (root)   .lede/.muted: culoare --muted
```

**Recomandare:** scala e minimală (doar 3 nivele de heading + body), ceea ce e potrivit pentru densitatea de informație a unei console. Nu extindeți cu mai multe nivele fără nevoie clară — riscul e mai multă inconsistență, nu mai multă claritate.

## Spacing scale

Nu am identificat un token explicit de spacing (`--space-1`, `--space-2` etc.) — valorile din `styles.scss` folosesc `rem` direct în fiecare regulă (`0.55rem`, `1.1rem`, `0.7rem`...). Funcțional dar greu de auditat pentru consistență.

**Task recomandat (P2, cross-page):** extrageți un set mic de tokens de spacing (`--space-xs: 0.35rem`, `--space-sm: 0.55rem`, `--space-md: 0.85rem`, `--space-lg: 1.35rem`) din valorile deja folosite predominant, apoi înlocuiți treptat valorile hardcodate. Nu e urgent — nu am observat probleme vizuale de spacing inconsistent grav, doar oportunitate de întreținere pe termen lung.

## Radii / borders / shadows

Toate componentele observate folosesc colțuri drepte (`border-radius: 0`, explicit în `p-skeleton borderRadius="0"`) și borduri subțiri `1px solid var(--stroke)`. E o alegere vizuală consecventă — "precis, auditabil", fără decorații — **de păstrat neapărat**, se potrivește exact cu tonul cerut pentru un trading agent.

Umbrele sunt minime: doar `box-shadow: inset 0 3px 0 var(--paper|--live)` pentru a marca modul paper/live pe header (`styles.scss:116-122`) — un detaliu subtil și eficient, de păstrat ca pattern (nu adăugați umbre decorative în altă parte).

## Buttons

`p-button` cu `severity`: implicit (neutru), `secondary`, `danger`. Observat consecvent pe majoritatea paginilor (Start agent/Stop, Emergency stop, Clear halt flag). **Excepție de inconsistență observată:** butonul "Disable" din Strategies (`strategies.md`) nu folosește `severity="warn"`/`danger"` deși dezactivează o strategie activă — aliniați la aceeași regulă ca restul acțiunilor cu impact.

## Inputs

`pInputText`/`pTextarea` simple, fără validare vizuală inline observată (stări de eroare pe câmp neconfirmate live). **Gol de securitate identificat:** inputul de token din Settings nu folosește `type="password"` — vezi `settings.md` P0. **Regulă nouă recomandată:** orice input care colectează o valoare secretă/sensibilă (token, cheie API) trebuie să fie mascat implicit.

## Cards

Pattern consecvent: bordură `1px solid var(--stroke)`, fundal `--bg-elev`, fără radius, fără umbră. `MetricCard` (`shared/metric-card.ts`) e reutilizată corect pe Dashboard. **Recomandare:** extindeți `MetricCard`/un component "stat card" echivalent pentru cardurile de sumar din Risk (Daily loss/Drawdown/Orders remaining/Circuit breaker), care momentan par implementate ad-hoc direct în `risk.page.ts` mai degrabă decât reutilizând `MetricCard`.

## Tables

Cel mai inconsecvent element din aplicație:
- Formatare numerică: aplicată parțial (`pnlClass` pe Dashboard/Market/Risk, lipsă pe Orders — vezi task global „Formatare numerică" mai jos).
- Responsive: niciun tabel observat nu are strategie explicită de adaptare mobilă (card-list fallback, scroll orizontal cu indicator, sau ascundere de coloane secundare) — toate tabelele late (Orders, Market) sunt pur și simplu tăiate la marginea viewport-ului pe mobil.

**Task global recomandat (P1):** definiți o strategie unică de "tabel responsive" (ex. un wrapper `<div class="table-scroll">` cu `overflow-x: auto` + un indicator vizual de scroll, sau breakpoint la care tabelul devine listă de carduri) și aplicați-o o singură dată, reutilizabil, pe toate tabelele late.

## Badges

`p-tag`/badge custom (portocaliu pentru "experimental"/"research-only", verde pentru "enabled"/"confirmed", roșu pentru "Live (locked)") — vocabular vizual clar și deja consecvent între Strategies și Market. **De extins** la Settings și Risk circuit breaker, unde lipsește (vezi task-urile paginilor respective).

## Alerts / bannere

`p-message` cu `severity="warn"/"error"` — folosit consecvent pentru: observer role, connection error, halted, venue disconnected, alerts. **Problemă identificată:** posibilă dublare a mesajului HALTED între bannerul global din `app.html` și un al doilea banner similar (vezi `dashboard.md` P1) — de investigat și dedus la o singură sursă de adevăr pentru fiecare tip de alertă.

## Modals

`ConfirmDanger` (`shared/confirm-danger.ts`) e cel mai matur component din aplicație: modal cu motiv obligatoriu + opțional token tastat pentru confirmare (`requireTyped`). **Acesta e pattern-ul de referință pentru orice acțiune periculoasă nouă** — nu creați variante alternative de confirmare în alte pagini.

## Charts

Un singur chart observat (TradingView candlestick pe Asset detail) — widget extern, nu component intern. Nicio recomandare de sistem de chart intern în acest moment; dacă apar charturi native (ex. echity curve, drawdown chart) pe Dashboard/Risk, respectați paletă existentă (`--ok`/`--bad` pentru pozitiv/negativ, `--paper`/`--live` pentru mod) — nu introduceți culori noi de chart fără a le lega de tokens existente.

## Loading states

`PageSkeleton` (`shared/page-skeleton.ts`) — component reutilizabil, corect implementat cu `aria-busy="true" aria-live="polite"`. **Nu am putut confirma live pe nicio pagină că e efectiv folosit** (răspunsurile locale sunt prea rapide) — recomand un test manual cu network throttling pentru a confirma acoperirea reală pe toate cele 10 pagini.

## Empty states

`EmptyState` (`shared/empty-state.ts`) — component reutilizabil, folosit corect și consecvent pe Orders ("No pending approvals"), Strategies ("No backtest runs yet"), Discovery ("No discovery candidates"). **Gol identificat:** secțiunea "Position / orders" din Asset detail e goală fără a folosi acest component (vezi `asset-detail.md` P1) — corectați pentru consecvență 100%.

## Error states

Nu am putut declanșa/observa live nicio stare de eroare reală (API căzut, scriere eșuată, backtest eșuat) în această sesiune — **cea mai mare limitare a auditului**. Recomand un audit de urmărire dedicat stărilor de eroare, cu API-ul oprit/simulat pentru fiecare pagină cu acțiuni de scriere (Strategies, Risk, Settings, Orders approval).

## Responsive breakpoints

Nu am identificat breakpoints CSS explicite (`@media`) în extrasul verificat din `styles.scss` — comportamentul responsive observat live pare să provină parțial din flex-wrap natural (nav, header) mai degrabă decât din reguli explicite de breakpoint pentru tabele/grid-uri de carduri.

**Recomandare:** definiți minim 2 breakpoints explicite și documentate:
- `≤768px` (mobil) — nav-ul curent (fără hamburger) devine prioritate de redesign (vezi `README.md`).
- `769–1199px` (tabletă) — netestat în acest audit, recomand verificare directă înainte de a proiecta reguli specifice.

## Accessibility rules (bază existentă + recomandări)

**Deja implementat corect (de păstrat):**
- Skip link funcțional (`app.html:1`).
- `:focus-visible` cu outline vizibil global (`styles.scss:40-43`).
- Stările nu se bazează doar pe culoare (dot-uri de status + text alăturat în header).
- `aria-label` pe zone cheie (telemetrie, input de token).
- `aria-busy`/`aria-live` pe skeleton.

**Recomandări noi:**
1. Auditați `aria-sort` pe toate coloanele sortabile de tabel (Market confirmat cu sortare; verificați Orders/Risk).
2. Confirmați `<label for>` real (nu doar placeholder) pe toate input-urile de filtrare din Market/Research/Discovery/Strategies.
3. Rulați un audit automat (axe-core sau Lighthouse) pe toate cele 10 pagini — nu a fost posibil în această sesiune (vezi limitări în `README.md`) — pentru a valida contrastul real al textului `--muted` (#8b909c) pe fundal `--bg`/`--bg-elev`, care vizual pare la limită pe unele etichete mici.
