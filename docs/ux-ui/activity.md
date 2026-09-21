# Agent activity

**Ruta:** `/agent` (etichetă în navigare: "Activity")
**Componentă:** `apps/console/src/app/features/agent.page.ts`
**Data auditului:** 2026-09-21

## Scopul paginii
Jurnal de audit append-only al tuturor acțiunilor operatorului și agentului (audit trail), cu payload complet expandabil per eveniment.

## Utilizatorul țintă
Operatorul care investighează "ce s-a întâmplat și când" — inclusiv pentru scopuri de conformitate/audit post-factum.

## Acțiunea principală
Scanarea cronologică a evenimentelor; expandarea unui "Payload" pentru detalii.

## Rezumatul problemelor
Pagina implementează corect principiul "append-only audit trail" cu timeline vizual clar (linie + puncte), dar fiecare eveniment e etichetat generic ("operator_action") urmat doar de un UUID, fără niciun rezumat uman-lizibil al acțiunii reale — utilizatorul trebuie să expandeze "Payload" la fiecare rând pentru a înțelege ce s-a întâmplat, ceea ce anulează scopul unui audit trail scanabil rapid.

## Probleme P0/P1/P2/P3

### P1 — Evenimentele nu au rezumat uman-lizibil, doar tip generic + UUID
Fiecare intrare arată `operator_action · 91cb3679-f999-42e2-8b38-ec11eb2daa7f`, identic ca formă indiferent dacă acțiunea a fost "Start agent", "Clear halt flag" sau altceva. Diferențierea reală există doar în "Payload" (colapsat implicit), forțând expandare manuală rând cu rând pentru a înțelege istoricul — contrar scopului declarat al paginii ("Human decisions and errors stay visible").
- **Verificat live:** `/agent`, desktop 1440px.
- **Excepție pozitivă observată:** un eveniment arată `reconciliation_ok · 2abd6dfe-...`, deci tipul de eveniment variază și ar putea fi folosit pentru un rezumat mai bogat dacă payload-ul e parsat.

### P2 — Nicio filtrare pe tip de eveniment sau interval de dată
La fel ca la Orders, un jurnal de audit care crește constant are nevoie de filtrare (tip eveniment, interval de dată) pentru a rămâne util pe termen lung — momentan pagina afișează tot istoricul cronologic fără control.

### P3 — "Payload" e etichetă generică pentru un buton expandabil
Un dezvoltator înțelege "payload" ca date brute JSON; un operator non-tehnic ar putea beneficia de o etichetă mai orientată spre acțiune (ex. "Details").

## Observații UX
- Mesajul lede ("Append-only audit trail. Proposals and analyses are not orders. Human decisions and errors stay visible.") stabilește corect așteptarea de imuabilitate și transparență — de păstrat.
- Timeline-ul vizual (linie verticală + puncte) e un pattern potrivit pentru date cronologice și ușor de urmărit vizual.

## Observații UI
- Fiecare rând de timeline are propriul accordion "Payload" — consecvent, dar repetitiv vizual la scroll lung (multe casete identice "Payload ▾" una sub alta).
- Timestamp-urile ISO8601 complete (cu milisecunde) sunt corecte pentru audit dar grele de citit în scanare rapidă, la fel ca pe Orders.

## Observații de accesibilitate
- Accordion-urile "Payload" trebuie verificate pentru `aria-expanded`/`aria-controls` corecte (comportament standard PrimeNG `p-accordion`, dar de confirmat în implementare).
- Timeline-ul vizual (puncte + linie) e probabil decorativ — verificați că informația (timestamp + tip eveniment) e disponibilă integral ca text pentru screen reader, nu doar poziția vizuală pe linie.

## Observații responsive
- Nu am testat `/agent` pe mobil (limitare a auditului). Structura de listă verticală simplă (fără tabel lat) sugerează risc redus de overflow, dar accordion-urile "Payload" ar trebui verificate pentru lizibilitate pe ecran îngust dacă payload-ul conține JSON formatat.

## Stările lipsă
- **Loading:** neconfirmat live.
- **Empty:** neconfirmat live (jurnalul avea deja evenimente).
- **Error:** neconfirmat live.

## Task-uri pentru Cursor

### [P1] Adaugă rezumat uman-lizibil per tip de eveniment în audit trail

**Problemă:** Toate evenimentele arată identic ("operator_action · uuid"), forțând expandarea manuală a payload-ului pentru a înțelege ce s-a întâmplat efectiv — ineficient pentru un jurnal menit să fie "scanabil".

**Modificare recomandată:** Adaugă o funcție de mapare `summarizeEvent(event)` care extrage din payload un rezumat scurt pe tipuri cunoscute de eveniment (ex. `operator_action` cu `action: 'start_agent'` → "Started paper agent"; `reconciliation_ok` → "Reconciliation passed"). Afișează rezumatul lângă tipul evenimentului, păstrând accordion-ul "Payload" pentru detalii complete.

**Fișiere/componente probabile:** `apps/console/src/app/features/agent.page.ts`, `apps/console/src/app/core/models.ts` (tipuri de evenimente).

**Comportament:** `operator_action · Started paper agent` în loc de `operator_action · 91cb3679-f999-42e2-8b38-ec11eb2daa7f`; UUID-ul rămâne disponibil (ex. mono, mai mic, sau doar în payload expandat).

**Criterii de acceptare:**
- Minimum evenimentele generate de acțiunile documentate în UI (start agent, stop, emergency stop, clear halt, save risk limits, propose strategy version) au un rezumat uman-lizibil vizibil fără expandare.
- Evenimentele necunoscute/nemapate cad graceful pe formatul actual (tip + id), fără eroare.

**Testare:**
- Generează manual câte un eveniment din fiecare acțiune de mai sus (în paper mode) și confirmă că rezumatul apare corect în `/agent`.

---

### [P2] Adaugă filtrare pe tip de eveniment și interval de dată

**Problemă:** Jurnalul crește nelimitat fără niciun control de filtrare, la fel ca istoricul de ordine.

**Modificare recomandată:** Adaugă un dropdown de filtrare pe tip de eveniment și un selector de interval de dată, similar cu propunerea de la `/orders`.

**Fișiere/componente probabile:** `apps/console/src/app/features/agent.page.ts`.

**Criterii de acceptare:**
- Utilizatorul poate filtra evenimentele afișate pe tip și pe interval de dată.

**Testare:**
- Verificare cu jurnalul curent (conține deja `operator_action` și `reconciliation_ok`) că filtrarea reduce corect lista.

## Componentele afectate
Timeline-ul de evenimente, accordion-urile "Payload".

## Riscuri și dependențe
Rezumatul uman-lizibil (P1) depinde de o mapare stabilă tip-eveniment → mesaj; coordonați cu structura reală a payload-urilor din backend (`src/control/`) înainte de a hardcoda mapări care s-ar putea schimba.

## Ce nu trebuie modificat
- Natura append-only, needitabilă a jurnalului.
- Mesajul „Human decisions and errors stay visible”.

## Screenshot-uri / referințe vizuale
Captură live desktop 1440px (`ss_9617dlkco`), sesiunea din 2026-09-21.
