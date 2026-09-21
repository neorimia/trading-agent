# Settings and security

**Ruta:** `/settings`
**Componentă:** `apps/console/src/app/features/settings.page.ts`
**Data auditului:** 2026-09-21

## Scopul paginii
Afișarea stării de configurare și securitate a instanței (mediu, mod de trading, credențiale Kraken prezente/absente, flag-uri de siguranță), plus setarea unui token local de operator pentru autentificare în browser.

## Utilizatorul țintă
Operatorul care verifică rapid dacă instanța e configurată corect și în siguranță înainte de a avea încredere în ea (ex. înainte de a porni agentul).

## Acțiunea principală
Introducerea și salvarea unui "Local operator token" (Bearer token).

## Rezumatul problemelor
Cea mai importantă problemă e de securitate/UX: input-ul de Bearer token e un câmp de text simplu, needeghizat (`pInputText`, fără `type="password"`), afișând tokenul în clar pe ecran în timp ce e tastat sau lipit. În plus, valorile boolean critice pentru siguranță (`Live flag`, `Withdraw enabled`) sunt afișate ca text simplu "false"/"true" fără nicio culoare semantică, deși sunt exact genul de flag pe care operatorul trebuie să-l poată verifica dintr-o privire, fără să citească fiecare cuvânt.

## Probleme P0/P1/P2/P3

### P0 — Tokenul de operator e introdus într-un câmp needeghizat (plaintext)
Inputul "Bearer token" nu are `type="password"`, deci orice persoană care se uită peste umărul operatorului (sau o captură de ecran/screen share accidental) vede tokenul complet în clar. Pentru un câmp explicit descris ca fiind folosit pentru autentificare ("Matches CONTROL_OPERATOR_TOKEN if set"), lipsa mascării e o breșă de UX de securitate.
- **Verificat live:** `/settings`, secțiunea "Local operator token".
- **Sursă:** `apps/console/src/app/features/settings.page.ts:47` — `<input pInputText [(ngModel)]="token" placeholder="Bearer token" aria-label="Operator token" />` fără `type="password"`.

### P1 — Flag-urile critice de siguranță ("Live flag", "Withdraw enabled") nu au culoare semantică
`Live flag: false`, `Broker paper mode: false`, `Withdraw enabled: false` apar ca text alb simplu, indistinct de câmpuri non-critice precum "Environment: development". Exact aceste trei valori sunt cele pe care un operator trebuie să le poată verifica instantaneu înainte de a avea încredere că instanța e în siguranță "paper-only" — text simplu obligă la citire atentă cuvânt cu cuvânt.
- **Verificat live:** `/settings`, desktop 1440px.

### P2 — Pagina nu clarifică explicit că valorile de configurare sunt read-only
Cu excepția secțiunii "Local operator token", toate celelalte 12 rânduri par a fi doar informative (nu există input-uri lângă ele), dar nimic din pagină nu spune explicit "aceste valori sunt setate din fișierul de configurare/variabile de mediu și nu pot fi editate din UI" — un operator nou ar putea încerca să dea click pe "development" așteptând un dropdown editabil.

### P3 — Nu există un buton "Show/Hide" pentru token după salvare
Chiar dacă P0 e rezolvat (mascare implicită), ar fi util un toggle explicit "arată/ascunde" pentru cazurile în care operatorul vrea să verifice ce a introdus înainte de submit.

## Observații UX
- Mesajul lede ("Secrets are never shown. Live trading stays blocked until the paper gate is passed.") comunică bine intenția de securitate a paginii — ironic că exact acest mesaj contrastează cu inputul de token needeghizat (P0).
- Structura listă-simplă (etichetă + valoare) e ușor de scanat pentru o pagină majoritar read-only.
- "Kraken spot key: present" / "Kraken spot secret: present" (fără a afișa valorile) e implementarea corectă a principiului "secrets are never shown" pentru acele câmpuri — bun.

## Observații UI
- Layout de listă simplă, fără carduri sau tabel — potrivit pentru conținut majoritar static.
- Badge-ul albastru "paper" pentru "Trading mode" e singurul element colorat din tot tabelul de stare, ceea ce îl face să iasă în evidență corect (e cea mai importantă informație din pagină) — dar contrastează cu lipsa de culoare pe restul flag-urilor critice (P1).

## Observații de accesibilitate
- Inputul de token are deja `aria-label="Operator token"` — bun.
- Verificați dacă lista de 12 perechi etichetă/valoare folosește o structură semantică adecvată (ex. `<dl>/<dt>/<dd>` sau tabel), nu doar `<div>`-uri vizual aliniate, pentru citire corectă cu screen reader ca pereche etichetă-valoare.

## Observații responsive
- Nu am testat `/settings` pe mobil în această sesiune (limitare a auditului). Structura de listă simplă etichetă/valoare sugerează risc redus de overflow, dar recomand verificare directă, în special pentru inputul de token + buton "Save token" alăturat.

## Stările lipsă
- **Success (token salvat):** neconfirmat live — există feedback vizual după "Save token"?
- **Error (token invalid/salvare eșuată):** neconfirmat live.
- **Loading:** neconfirmat live.

## Task-uri pentru Cursor

### [P0] Maschează inputul de Bearer token ca și câmp de parolă

**Problemă:** Tokenul de operator e vizibil în clar în timp ce e introdus, risc de expunere accidentală (screen share, captură de ecran, persoană care privește peste umăr).

**Modificare recomandată:** Adaugă `type="password"` pe input (sau folosește componenta PrimeNG `p-password` cu `[feedback]="false"` pentru a evita sugestii de complexitate irelevante pentru un token), plus opțional un buton "show/hide" (iconiță ochi) pentru verificare voluntară.

**Fișiere/componente probabile:** `apps/console/src/app/features/settings.page.ts:47`.

**Comportament:** Tokenul apare ca puncte/asteriscuri în mod implicit; operatorul poate opțional să-l dezvăluie temporar printr-un toggle explicit.

**Criterii de acceptare:**
- Inputul de token nu afișează niciodată caracterele în clar fără o acțiune explicită de "show" din partea utilizatorului.
- Comportamentul de salvare (`[(ngModel)]="token"`, `Save token`) rămâne funcțional identic.

**Testare:**
- Verificare vizuală că textul tastat/lipit în câmp apare mascat implicit; testare toggle show/hide dacă implementat.

---

### [P1] Colorează semantic flag-urile critice de siguranță (Live flag, Withdraw enabled, Broker paper mode)

**Problemă:** Aceste trei valori boolean sunt cele mai importante din pagină pentru încrederea operatorului că instanța e sigură, dar sunt afișate identic cu restul câmpurilor informative neutre.

**Modificare recomandată:** Aplică o culoare semantică pe valoare (ex. verde/`--ok` pentru starea sigură așteptată — `false` la Live flag și Withdraw enabled — și roșu/`--bad` dacă vreodată sunt `true`), folosind un `<p-tag>` sau clasă CSS condiționată, la fel cum "Trading mode" folosește deja un `p-tag` albastru.

**Fișiere/componente probabile:** `apps/console/src/app/features/settings.page.ts`.

**Criterii de acceptare:**
- "Live flag", "Withdraw enabled" și "Broker paper mode" au un indicator vizual color (nu doar text) care comunică instant dacă starea e sigură sau riscantă.
- Restul câmpurilor pur informative (Environment, Operator role etc.) rămân neutre, pentru a nu dilua semnalul.

**Testare:**
- Verificare vizuală pe starea curentă (toate `false`, deci "sigure") — culoarea trebuie să comunice clar "sigur"; dacă e posibil de simulat, verificați și starea `true` pentru contrast.

---

### [P2] Clarifică faptul că valorile de configurare sunt read-only

**Problemă:** Nu există niciun indiciu textual că cele 12 rânduri de stare nu sunt editabile din UI, doar secțiunea de token.

**Modificare recomandată:** Adaugă un mic subtitlu/hint deasupra listei principale (ex. "Read-only — set via environment/config file") pentru a preveni încercări de editare și confuzie.

**Fișiere/componente probabile:** `apps/console/src/app/features/settings.page.ts`.

**Criterii de acceptare:**
- Un operator nou înțelege, fără să dea click, că lista principală e read-only și unde se schimbă efectiv aceste valori.

**Testare:**
- Verificare vizuală a hintului adăugat.

## Componentele afectate
Lista de stare configurare, secțiunea "Local operator token".

## Riscuri și dependențe
Niciunul semnificativ — toate task-urile sunt izolate la această pagină.

## Ce nu trebuie modificat
- Mesajul „Secrets are never shown” și implementarea „present”/”not configured” pentru chei/secrete Kraken — deja corect implementat.
- Faptul că live trading rămâne blocat până la trecerea paper gate-ului.

## Screenshot-uri / referințe vizuale
Capturi live desktop 1440px (`ss_9311f5qmz`, `ss_88286s5b8`), sesiunea din 2026-09-21.
