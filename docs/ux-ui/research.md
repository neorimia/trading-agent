# Research and intelligence

**Ruta:** `/research`
**Componentă:** `apps/console/src/app/features/research.page.ts`
**Data auditului:** 2026-09-21

## Scopul paginii
Feed de context extern (știri, evenimente) relevant pentru instrumentele urmărite, cu semnalarea explicită a nivelului de încredere ("stale / unverified").

## Utilizatorul țintă
Operatorul care vrea context de piață înainte de a interpreta un semnal al agentului.

## Acțiunea principală
Filtrare pe instrument + "Load" pentru a reîncărca feed-ul.

## Rezumatul problemelor
Pagina respectă foarte bine cerința de a distinge informație confirmată de estimare ("stale / unverified" pe fiecare card), dar are microcopy ciudat ("published unknown"), fără filtrare pe categorie deși descrierea paginii promite una ("protocol upgrades, unlocks, listings, regulation"), și carduri foarte dense de text fără o ierarhie vizuală puternică între titlu/sursă/rezumat.

## Probleme P0/P1/P2/P3

### P1 — Descrierea paginii promite filtrare pe categorie care nu există în UI
Lede-ul spune "Crypto categories include protocol upgrades, unlocks, listings, and regulation", sugerând că utilizatorul poate filtra pe aceste categorii, dar singurul control vizibil e un filtru de instrument și un buton "Load". Fie categoriile nu sunt încă filtrabile (funcționalitate lipsă), fie sunt afișate altundeva neobservat.
- **Verificat live:** `/research`, desktop 1440px.

### P2 — Microcopy "published unknown" e confuz
Formatul "published unknown · fetched 2026-09-19T23:37:29.181236+03:00 · event n/a" amestecă o etichetă lipsă ("unknown") cu un timestamp tehnic complet needitat (microsecunde + offset de fus orar), fără spațiere/punctuație care să clarifice ce înseamnă fiecare termen pentru un utilizator care scanează rapid.

### P2 — "confidence 0" fără context numeric
Fiecare card arată "confidence 0" — nu e clar dacă scala e 0-1, 0-10, sau 0-100, și "0" pentru toate știrile vizibile sugerează fie o problemă de date (toate știrile au încredere zero?), fie o valoare implicită neconfigurată încă.

### P3 — Cardurile repetă titlul complet în corpul textului
Fiecare card afișează titlul o dată ca headline bold și încă o dată la începutul paragrafului de rezumat (ex. "SEC Issues... SEC Issues... The SEC is taking a significant step forward..."), redundanță care lungește inutil cardurile.

## Observații UX
- Badge-ul "stale / unverified" pe fiecare card e exact tipul de semnal cerut pentru un agent de trading — diferențiază clar informație confirmată de informație neconfirmată. De păstrat și de extins (ex. un badge verde "verified" quando aplicabil, pentru contrast).
- Mesajul lede ("External context is untrusted. Contradictions are shown, never resolved silently.") e un exemplu excelent de onestitate asupra limitelor sistemului.

## Observații UI
- Cardurile sunt late și consumă toată lățimea disponibilă (1440px) pentru text care ar putea fi lizibil confortabil la o lățime mai mică — pe ecrane late, liniile de text foarte lungi (>90 caractere) reduc lizibilitatea.
- Nu există nicio imagine/iconiță pe surse (ex. sec_press_rss vs. federal_reserve_press_rss) — un identificator vizual (favicon/iconiță per sursă) ar accelera scanarea.

## Observații de accesibilitate
- Linkurile de sursă (`sec_press_rss`, `federal_reserve_press_rss`) sunt linkuri reale (subliniate, albastre) — bun pentru navigare cu tastatura/screen reader.
- Verificați dacă badge-ul "stale / unverified" are și un echivalent text pentru screen reader dincolo de culoarea portocalie (pare să aibă, fiind text, nu doar culoare — bun).

## Observații responsive
- Nu am testat `/research` pe mobil în această sesiune (limitare a auditului). Cardurile late de text ar trebui să se comporte relativ bine la lățime redusă (text care se reflow-uiește natural), dar recomand verificare directă a densității de informație pe ecran mic.

## Stările lipsă
- **Loading:** neconfirmat live la apăsarea "Load".
- **Error:** neconfirmat live (sursă externă indisponibilă).
- **Empty:** neconfirmat live (niciun rezultat pentru un filtru de instrument specific).

## Task-uri pentru Cursor

### [P1] Clarifică sau implementează filtrarea pe categorie promisă în lede

**Problemă:** Textul paginii promite categorii ("protocol upgrades, unlocks, listings, regulation") dar UI-ul nu oferă niciun control de filtrare pe ele, creând o așteptare neîndeplinită.

**Modificare recomandată:** Adaugă un dropdown/set de chip-uri de filtrare pe categorie lângă filtrul de instrument existent, populat din valorile reale disponibile în date; dacă funcționalitatea nu e încă implementată în backend, ajustează textul lede să nu promită ceva inexistent.

**Fișiere/componente probabile:** `apps/console/src/app/features/research.page.ts`.

**Criterii de acceptare:**
- Fie există un control funcțional de filtrare pe categorie, fie textul lede nu mai menționează filtrare pe categorii ca funcționalitate disponibilă.

**Testare:**
- Verificare că filtrul (dacă implementat) reduce corect lista de carduri afișate.

---

### [P2] Reformatează metadatele "published / fetched / event" într-un format lizibil

**Problemă:** "published unknown · fetched 2026-09-19T23:37:29.181236+03:00 · event n/a" e greu de parsat vizual, amestecă etichete lipsă cu timestamp-uri tehnice.

**Modificare recomandată:** Formatează fetched ca dată/oră relativă scurtă (ex. "2 days ago" sau "19 Sept, 23:37"), ascunde câmpurile complet necunoscute (`n/a`) în loc să le afișezi explicit, sau grupează-le vizual distinct (etichetă gri, mai mic).

**Fișiere/componente probabile:** `apps/console/src/app/features/research.page.ts`.

**Criterii de acceptare:**
- Metadatele fiecărui card sunt lizibile dintr-o privire, fără timestamp ISO brut cu microsecunde.

**Testare:**
- Verificare vizuală pe minim 5 carduri diferite din feed.

## Componentele afectate
Lista de carduri de research, filtrul de instrument, badge-ul de încredere.

## Riscuri și dependențe
Filtrarea pe categorie (P1) poate necesita suport nou din backend dacă datele nu sunt deja etichetate pe categorie — verificați `src/data/` înainte de a estima ca fiind doar frontend.

## Ce nu trebuie modificat
- Badge-ul "stale / unverified" și mesajul despre contradicții nerezolvate silențios — esențiale pentru onestitatea datelor.

## Screenshot-uri / referințe vizuale
Captură live desktop 1440px (`ss_3512lzttk`), sesiunea din 2026-09-21.
