# Asset discovery

**Ruta:** `/discovery`
**Componentă:** `apps/console/src/app/features/discovery.page.ts`
**Data auditului:** 2026-09-21

## Scopul paginii
Descoperirea de candidați noi de active (crypto) pe baza unui scor de oportunitate determinist, cu componentele scorului afișate individual, niciodată colapsate într-un singur număr fără context.

## Utilizatorul țintă
Operatorul care evaluează periodic dacă merită extins universul de instrumente tranzacționabile.

## Acțiunea principală
Filtrare (status, scor minim) + "Load" pentru a vedea candidați.

## Rezumatul problemelor
Pagina afișa doar starea goală în timpul auditului ("No discovery candidates"), care e implementată clar și corect. Nu am putut evalua tabelul/lista de candidați reali, layout-ul componentelor de scor, sau comportamentul de sortare — cea mai mare limitare a acestui audit specific paginii.

## Probleme P0/P1/P2/P3

### P2 — Filtrul "Min. opportunity score" nu indică scala așteptată
Placeholder-ul e generic ("Min. opportunity score") fără a indica intervalul valid (0-1? 0-100?), ceea ce poate duce la introducerea unei valori greșite fără feedback (ex. utilizator introduce "50" pe o scală 0-1).
- **Verificat live:** `/discovery`, desktop 1440px.

### P3 — Dropdown-ul "All statuses" nu arată opțiunile posibile fără interacțiune
Standard pentru un `<select>`/dropdown PrimeNG, dar merită verificat dacă valorile posibile (ex. "new", "reviewed", "rejected") sunt suficient de auto-explicative pentru un utilizator nou.

## Observații UX
- Mesajul lede ("Research candidates only — never an order. Every component score is shown individually; nothing is collapsed into a single number.") e un exemplu excelent de transparență algoritmică — previne încrederea oarbă într-un scor compus. De păstrat neapărat când vor exista candidați reali de afișat.
- Starea goală ("No discovery candidates / The discovery store is empty, or no run has produced candidates matching these filters yet.") distinge corect două cauze posibile (store gol vs. filtre prea restrictive) în același mesaj — bună practică.

## Observații UI
- Layout minimal, consecvent cu restul paginilor cu filtre (input + dropdown + buton Load aliniate orizontal).
- Nu am putut evalua vizual cum arată un candidat individual (card? rând de tabel? cu ce componente de scor vizibile) — necesită date reale pentru un audit UI complet.

## Observații de accesibilitate
- Dropdown-ul de status și inputul de scor minim ar trebui verificate pentru `<label>` asociat.
- Iconița din starea goală (`pi-...`) are `aria-hidden="true"` conform implementării `EmptyState` — bun, textul alăturat oferă informația.

## Observații responsive
- Nu am testat `/discovery` pe mobil (limitare a auditului). Layout-ul simplu de filtre sugerează risc redus, dar tabelul/lista de candidați (needvaluat) ar putea avea aceleași riscuri de overflow observate pe Orders/Market dacă folosește un tabel lat cu multe componente de scor.

## Stările lipsă
- **Empty:** confirmat, bine implementat.
- **Loading:** neconfirmat live la "Load".
- **Error:** neconfirmat live.
- **Populated (cu candidați reali):** **nu a putut fi evaluat** — cea mai importantă limitare a acestui audit. Recomand un audit de urmărire după ce store-ul de discovery conține date reale (ex. după un run de pipeline conform `docs/` din modulul Kraken discovery).

## Task-uri pentru Cursor

### [P2] Indică scala scorului de oportunitate în placeholder sau label

**Problemă:** "Min. opportunity score" nu specifică intervalul valid, risc de input greșit fără validare vizibilă.

**Modificare recomandată:** Actualizează placeholder-ul la ceva de tipul "Min. score (0–1)" sau adaugă un hint sub input, în funcție de scala reală folosită de scoring engine (`src/discovery/` sau echivalent — verificați sursa scorului înainte de a alege textul).

**Fișiere/componente probabile:** `apps/console/src/app/features/discovery.page.ts`.

**Criterii de acceptare:**
- Utilizatorul înțelege din UI, fără a citi cod, ce interval de valori e acceptat de filtrul de scor minim.

**Testare:**
- Verificare vizuală a placeholder-ului/hintului actualizat.

---

### [P1] Programează un audit de urmărire pe pagina Discovery cu date reale

**Problemă:** Acest audit nu a putut evalua componenta centrală a paginii — lista/tabelul de candidați cu scoruri individuale — pentru că store-ul era gol în timpul sesiunii.

**Modificare recomandată:** Nu e un task de implementare UI, ci un task de proces: rulați pipeline-ul de discovery pentru a popula date, apoi repetați auditul UX/UI specific acestei pagini (layout de card/tabel, lizibilitatea componentelor de scor, sortare, acțiuni disponibile per candidat).

**Fișiere/componente probabile:** N/A (proces, nu cod).

**Criterii de acceptare:**
- Există un audit UX/UI complet al stării "populated" a paginii Discovery, cu capturi și task-uri concrete.

**Testare:** N/A.

## Componentele afectate
Filtrele de status și scor minim, starea goală (`EmptyState`), lista/tabelul de candidați (neevaluat).

## Riscuri și dependențe
Orice task de redesign al listei de candidați trebuie amânat până la auditul de urmărire (vezi task P1 de mai sus) — nu proiectați layout-ul "orbește", fără date reale.

## Ce nu trebuie modificat
- Mesajul despre transparența scorului ("nothing is collapsed into a single number") — principiu de produs explicit, nu doar UI.
- Formularea dublă a stării goale (store gol vs. filtre restrictive).

## Screenshot-uri / referințe vizuale
Captură live desktop 1440px (`ss_2735awkj4`), sesiunea din 2026-09-21.

## Limitări ale acestui audit pentru pagină
Store-ul de discovery era gol în timpul sesiunii de audit; nu a putut fi evaluată starea "populated" a paginii. Acesta e cel mai important gol al auditului curent — vezi task P1 de mai sus.
