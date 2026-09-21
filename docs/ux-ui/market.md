# Market overview

**Ruta:** `/market`
**Componentă:** `apps/console/src/app/features/market.page.ts`
**Data auditului:** 2026-09-21

## Scopul paginii
Listă a universului de instrumente permise (allowlist), cu preț, variație, volum, spread și vârstă a datelor, plus statutul venue-ului (confirmed / research-only).

## Utilizatorul țintă
Operatorul care vrea o vedere rapidă asupra pieței înainte de a intra pe un instrument specific.

## Acțiunea principală
Filtrare/scanare rapidă a instrumentelor + navigare către pagina de detaliu a unui simbol (`/market/:symbol`).

## Rezumatul problemelor
Aceeași problemă sistemică de formatare numerică de pe Dashboard apare aici pe coloanele "Change" și "Vol." (zecimale brute, needitate). Coloana "Age" arată constant "n/a" fără explicație, iar badge-urile de status ("confirmed" / "research-only") sunt clare dar nu au un tooltip care să explice diferența pentru un utilizator nou.

## Probleme P0/P1/P2/P3

### P0 — Coloanele "Change" și "Vol." afișează float brut, needitat
Valori precum `0.5328064495877205763027875799` sau `0.006479812313188385` apar direct din API fără rotunjire. Într-un tabel, acest lucru lărgește coloana și face scanarea imposibilă cu ochiul liber — exact opusul scopului unei pagini de "market overview".
- **Verificat live:** `/market`, desktop 1440px.
- Legat de task-ul global din `design-system-recommendations.md`.

### P1 — Coloana "Age" e mereu "n/a", fără explicație
Toate rândurile afișează "n/a" în coloana Age (vârsta datelor), dar nu există niciun tooltip/hint care să spună dacă asta înseamnă "date live, fără vârstă calculabilă" sau "date lipsă". Pentru un produs care insistă corect pe distincția date live vs. istorice, o coloană mereu goală subminează acel mesaj.

### P2 — Badge-urile "confirmed" / "research-only — no execution venue" nu au tooltip explicativ
Distincția e importantă (poți tranzacționa vs. doar cercetare) dar textul portocaliu e trunchiat vizual lângă marginea tabelului pe ecrane mai mici și nu explică *de ce* (ex. "no venue configured pentru NASDAQ").

### P3 — Simbolurile fără preț (`AAPL`, `MSFT`) arată liniuțe (—) pe toate coloanele
E corect că nu există date, dar un rând complet gol de liniuțe se pierde vizual lângă rândurile cu date; ar putea beneficia de o stare "muted row" mai explicită.

## Observații UX
- Filtrul de simbol ("Filter symbol") e simplu și eficient pentru o listă mică; la o listă mai mare ar avea nevoie de filtrare pe venue/status.
- Steaua (☆) de lângă fiecare simbol sugerează o funcție de "favorite" dar nu am putut confirma dacă e funcțională sau doar decorativă — verificați comportamentul la click.
- Sortarea pe coloane (săgeți lângă "Symbol"/"Venue") e prezentă — bun semn de maturitate UI.

## Observații UI
- Tabel dens, monospace pentru cifre — coerent cu restul aplicației.
- Contrastul badge-ului portocaliu ("research-only") pe fundal închis pare acceptabil, dar trebuie verificat cu un instrument de contrast (nu am putut rula axe/Lighthouse în această sesiune).
- Nu există paginare — la un allowlist mic (4 rânduri) nu e o problemă, dar dacă universul crește, tabelul are nevoie de paginare sau scroll virtualizat.

## Observații de accesibilitate
- Header-ele de tabel par corecte semantic (`<th>` cu text), dar verificați dacă sortarea pe coloană are `aria-sort` setat corect pentru screen reader-e.
- Steaua de favorite (dacă e interactivă) trebuie să aibă `aria-label` (ex. "Add AAPL to favorites") — nu doar o iconiță fără text.
- Inputul de filtrare are placeholder "Filter symbol" dar trebuie confirmat că are și un `<label>` asociat (vizual ascuns e acceptabil).

## Observații responsive
- Nu am testat explicit `/market` pe mobil în această sesiune (limitare a auditului) — dat fiind tiparul observat pe `/orders`, e foarte probabil ca tabelul cu 7 coloane să sufere de tăiere/overflow la 390px. Recomand verificare directă înainte de a prioritiza fix-ul.

## Stările lipsă
- **Loading:** neconfirmat live.
- **Error:** neconfirmat live (ce se întâmplă dacă venue-ul Kraken pică în timp ce pagina e deschisă?).
- **Empty:** dacă allowlist-ul e gol, comportamentul exact (mesaj EmptyState vs. tabel gol) nu a fost confirmat.

## Task-uri pentru Cursor

### [P0] Rotunjește Change și Vol. la un număr fix de zecimale

**Problemă:** Coloanele "Change" și "Vol." afișează 15+ zecimale brute din API, imposibil de citit rapid într-un tabel de piață.

**Modificare recomandată:** Aplică aceeași funcție de formatare numerică centralizată propusă pentru Dashboard (`design-system-recommendations.md`) — Change ca procent cu 2 zecimale (`+0.53%`), Vol. cu 2-4 zecimale plus separator de mii dacă e cazul.

**Fișiere/componente probabile:** `apps/console/src/app/features/market.page.ts`.

**Comportament:** `0.5328064495877205763027875799` devine `+0.53%`; volumul lung devine o valoare scurtă cu tooltip pentru precizia completă la hover.

**Criterii de acceptare:**
- Nicio celulă din tabelul Market nu depășește ~8 caractere vizibile pentru valorile numerice.
- Semnul (+/-) și culoarea (verde/roșu) rămân aplicate corect după rotunjire.

**Testare:**
- Captură desktop 1440px cu date reale din Kraken (BTCUSD/ETHUSD), verificare vizuală că tabelul e compact și aliniat.

---

### [P1] Explică sau elimină coloana "Age" când e mereu n/a

**Problemă:** Coloana Age nu oferă niciodată informație utilă în starea curentă, ceea ce contrazice mesajul aplicației despre transparența vârstei datelor.

**Modificare recomandată:** Fie populează coloana cu vârsta reală a ultimului bar (secunde/minute de la ultima actualizare), fie adaugă un tooltip pe header care explică de ce e n/a în acest build (ex. "Age tracking not yet wired for this venue").

**Fișiere/componente probabile:** `apps/console/src/app/features/market.page.ts`, sursa de date din `api.service.ts`/`models.ts`.

**Criterii de acceptare:**
- Coloana Age fie afișează o valoare reală calculată, fie are un tooltip pe header care explică starea "n/a" în mod explicit.

**Testare:**
- Verificare manuală pe fiecare rând din `/market` că Age reflectă corect timpul de la ultima actualizare, sau că tooltip-ul apare la hover pe header.

---

### [P2] Adaugă tooltip pe badge-urile de status venue

**Problemă:** "confirmed" vs. "research-only — no execution venue" nu explică operatorului nou de ce un simbol nu poate fi tranzacționat.

**Modificare recomandată:** Adaugă `pTooltip` (PrimeNG) pe badge cu textul explicativ (ex. "No execution venue configured for NASDAQ in this build — data is for research only").

**Fișiere/componente probabile:** `apps/console/src/app/features/market.page.ts`.

**Criterii de acceptare:**
- Hover/focus pe badge afișează un tooltip explicativ, accesibil și din tastatură (focus, nu doar mouse hover).

**Testare:**
- Tab la badge cu tastatura, confirmă apariția tooltip-ului; testare cu screen reader că textul e anunțat.

## Componentele afectate
Tabelul principal de instrumente, badge-urile de status, inputul de filtrare.

## Riscuri și dependențe
Formatarea numerică depinde de task-ul global din `design-system-recommendations.md` — implementați o singură dată, reutilizați peste tot.

## Ce nu trebuie modificat
- Mesajul lede „Universe allowlist only. Prices are bar closes, not a live tape." — comunică corect natura datelor.
- Distincția „confirmed” vs. „research-only” ca și concept — doar clarificarea ei (P2).

## Screenshot-uri / referințe vizuale
Captură desktop 1440px realizată live (`ss_62754yje0`) în sesiunea din 2026-09-21.
