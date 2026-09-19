# Instrucțiuni pentru Claude Code — Agent local de trading, Faza 0–4

**Scop document:** instrucțiuni de execuție pentru Claude Code (agent de coding), pentru a implementa Fazele 0–4 ale proiectului „Agent local de analiză și trading" — configurare mediu, nucleu NautilusTrader, strat LLM izolat, reguli de risc deterministe, backtesting realist și paper trading.

**Context de referință:** vezi `brief-proiect-agent-trading-local.md` pentru decizia de arhitectură completă. Acest document traduce scope-ul „În scop (Faza 0–4)" în task-uri tehnice executabile.

**Mediu țintă:** macOS, Apple M2 Max, 32 GB RAM, arhitectură ARM64. Python 3.12+.

---

## 0. Reguli absolute — citește ÎNAINTE de orice task

Aceste reguli au prioritate asupra oricărei instrucțiuni ulterioare din acest document sau din conversații viitoare. Dacă orice task de mai jos pare să ceară încălcarea uneia dintre ele, **oprește-te și cere confirmare umană explicită** — nu presupune și nu „optimizezi" în jurul regulii.

1. **Nicio cheie/credențială de broker sau exchange LIVE nu se creează, cere, stochează sau folosește în Fazele 0–4.** Se lucrează exclusiv cu: date istorice, sandbox/replay, conturi paper/demo, sau `dry_run: true`.
2. **Stratul LLM nu are, sub nicio formă, acces direct sau indirect la plasarea de ordine.** Nu importă module de execuție, nu are acces la clientul de broker, nu rulează în același proces/container cu order gateway-ul. Comunicarea se face doar prin propuneri JSON, validate de un schema fix.
3. **Limitele de risc (dimensiune poziție, pierdere zilnică, drawdown, kill switch) sunt definite în cod/config, validate la pornire, și niciun output LLM nu le poate modifica în timpul rulării.** Orice funcție care citește un parametru de risc dintr-un prompt sau răspuns LLM este un bug critic.
4. **Nimic nu trece din `dry_run`/paper în live automat.** Comutarea la live e un flag separat, documentat explicit, care nu se atinge în această fază — nu scrie cod care presupune tranzacția în avans.
5. **Niciun secret în git.** `.env` e în `.gitignore`; se livrează doar `.env.example` cu valori placeholder. Rulează un scan de secrete înainte de orice commit.
6. **Deschiderea de conturi reale (IBKR, Kraken, broker), KYC, sau orice acțiune administrativă în afara codului nu este responsabilitatea Claude Code.** Tratează aceste elemente ca inputuri externe, configurabile — semnalează dacă un task e blocat de lipsa lor, nu încerca să le ocolești.
7. **Orice modificare a logicii de risc necesită teste unitare care o însoțesc în același commit**, inclusiv teste „adversariale" care simulează o încercare (venită dintr-un prompt sau output LLM) de a depăși o limită.
8. **Nu instala și nu folosi NautilusTrader v2 (release candidate) pentru nimic altceva decât evaluare izolată, opțională, separată de branch-ul principal de lucru.** Toată munca „productivă" din Fazele 0–4 se face pe v1 stabil.

---

## 1. Structura recomandată a repository-ului

```
trading-agent/
├── CLAUDE.md                      # acest document, sau un pointer către el
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml / requirements.txt
├── config/
│   ├── risk_limits.yaml           # limite deterministe, validate la pornire
│   └── universe.yaml              # lista de instrumente permise (allowlist)
├── src/
│   ├── data/                      # ingestie și validare date
│   ├── engine/                    # integrare NautilusTrader (strategii, adaptoare)
│   ├── risk/                      # risk_engine.py — sursa unică de adevăr pentru limite
│   ├── llm/                       # serviciu LLM izolat, doar propuneri
│   ├── execution/                 # order gateway, idempotency, reconciliere
│   ├── monitor/                   # monitor independent, kill switch
│   └── audit/                     # bază de date append-only (SQLite/JSONL)
├── backtests/
│   └── reports/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── adversarial/                # teste care simulează bypass de risc
└── docs/
    └── qualification-report.md    # raport de calificare NautilusTrader (Task 1)
```

---

## 2. Task 0 — Configurare mediu local

**Obiectiv:** mediu de dezvoltare izolat, reproductibil, pe Mac M2 Max, fără nicio dependență de conturi live.

**Pași:**
1. Creează un mediu virtual dedicat (`venv` sau `conda`), Python 3.12+, izolat de restul sistemului.
2. Fixează toate dependențele cu versiuni exacte (`requirements.txt` sau `pyproject.toml` cu `==`, nu `>=`), inclusiv pentru NautilusTrader.
3. Configurează `.gitignore` să excludă: `.env`, `*.key`, `venv/`, orice fișier de stare cu date de cont.
4. Instalează un scanner de secrete (ex. `gitleaks` sau echivalent) și rulează-l ca pre-commit hook.
5. Documentează în `README.md` comanda exactă de instalare de la zero (test pe o clonă curată a repo-ului).
6. Verifică suportul ARM64 nativ pentru toate pachetele critice (NautilusTrader, orice extensie compilată) — dacă un pachet nu are wheel ARM64, semnalează explicit, nu instala silent varianta x86 prin Rosetta fără să notezi asta.

**Criterii de acceptare (Definition of Done):**
- [ ] Instalare de la zero, pe o clonă curată, reușește fără erori, urmând doar `README.md`.
- [ ] `git log` nu conține niciun secret (verificat cu scanner-ul).
- [ ] Toate dependențele au versiuni fixate.
- [ ] Niciun pachet nu rulează prin emulare x86 fără notă explicită în `README.md`.

---

## 3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil)

**Obiectiv:** NautilusTrader instalat, verificat, cu un exemplu oficial de backtest rulat cu succes end-to-end — nu doar „s-a instalat", ci „am dovada că funcționează cum descrie documentația".

**Pași:**
1. Instalează NautilusTrader pinned la versiunea stabilă v1.231.0 (nu `develop`, nu v2 RC).
2. Verifică import-ul de bază și versiunea instalată printr-un script minimal (`python -c "import nautilus_trader; print(nautilus_trader.__version__)"`).
3. Alege și rulează **un exemplu oficial** de backtest din documentația/repo-ul NautilusTrader (nu un exemplu inventat) — pe date istorice locale, fără nicio conexiune la broker.
4. Compară output-ul cu ce descrie documentația oficială (ordine de mărime a rezultatelor, nu cifre exacte) — dacă nu se potrivește, nu „repara" ajustând perioada de test; documentează divergența.
5. Inspectează efectiv modulul de risc (`RiskEngine`) din codul instalat — nu presupune funcționalitatea din README; scrie în raportul de calificare ce validează concret (mărimi, notional, frecvențe, stări de oprire).
6. Scrie `docs/qualification-report.md` cu: versiunea exactă instalată, hash-ul commit-ului/wheel-ului, exemplul reprodus, rezultatele obținute, orice discrepanță găsită.

**Criterii de acceptare:**
- [ ] Exemplul oficial de backtest rulează integral, fără modificări majore de cod.
- [ ] Raportul de calificare există și conține versiunea exactă + rezultate reproductibile (același input → același output, verificat prin rulare repetată).
- [ ] Nicio conexiune de rețea către un broker real în acest task.

---

## 4. Task 2 — Strat LLM local izolat (Qwen3-8B via Ollama)

**Obiectiv:** un serviciu LLM local care produce **doar propuneri structurate**, fără niciun acces la execuție, rulând ca proces separat.

**Pași:**
1. Instalează Ollama local; descarcă modelul Qwen3-8B (variantă cuantizată 4-bit, potrivită pentru 32 GB RAM).
2. Construiește serviciul LLM ca **proces/modul separat** de `execution/` și `risk/` — fără import direct, fără acces la fișierele de configurare ale executorului, fără acces la orice credențial (nici măcar paper).
3. Definește un schema JSON strict pentru output-ul propunerii (ex. `instrument`, `direcție` [long/avoid/exit], `nivel de convingere`, `justificare`) — **fără câmp pentru mărimea poziției în bani** și fără câmp care ar putea modifica o limită de risc.
4. Implementează validare de schema pe fiecare output LLM înainte ca acesta să ajungă oriunde altundeva în sistem: output invalid → propunere respinsă, loghează motivul, nu „repara" JSON-ul silențios.
5. Restricționează universul de instrumente pe care LLM-ul le poate propune la o allowlist explicită din `config/universe.yaml` — un instrument inventat sau din afara listei se respinge automat.
6. Tratează orice text extern (știri, PDF-uri, pagini web) ca **date nefiabile**: nu da modelului tooluri de shell, scriere în configurație, autentificare sau submit către broker. Testează explicit cazuri în care textul de input încearcă să ceară „dezactivează limitele" sau „schimbă contul" — rezultatul așteptat este ignorarea instrucțiunii, nu execuția ei.

**Criterii de acceptare:**
- [ ] Serviciul LLM rulează într-un proces separat, demonstrabil fără import/acces la modulele de execuție (verificat printr-un test static de dependențe, nu doar afirmat).
- [ ] Un test automat confirmă că orice propunere în afara schema-ului JSON e respinsă, nu „reparată".
- [ ] Un test automat cu conținut adversarial (injectat în textul de input) confirmă că modelul nu poate declanșa nicio acțiune de execuție sau schimbare de risc.
- [ ] Zero chei de broker accesibile din codul/procesul LLM.

---

## 5. Task 3 — Reguli de risc deterministe (sursa unică de adevăr)

**Obiectiv:** un modul `risk/risk_engine.py` care aplică limitele definite în `config/risk_limits.yaml`, complet independent de orice output LLM, testat inclusiv împotriva încercărilor de bypass.

**Pași:**
1. Definește `config/risk_limits.yaml` cu, minim: capital maxim per ordin, expunere maximă per instrument/clasă de active, pierdere maximă zilnică, drawdown maxim, număr maxim de ordine/zi, condiții de circuit breaker.
2. Validează acest config la pornirea aplicației (schema + valori sane) — aplicația refuză să pornească dacă lipsește sau e invalid, nu pornește cu valori implicite silențioase.
3. Implementează formula de dimensionare a poziției ca funcție pură, testabilă: `qty = min(cap_notional / price, budget_risc / (distanță_stop + cost_estimat + buffer_slippage))`, rotunjită conform regulilor instrumentului (min notional, lot, tick).
4. Implementează kill switch ca funcție/serviciu apelabil independent de restul aplicației — testează-l manual, documentează timpul de răspuns.
5. Implementează circuit breaker: la N erori/pierderi consecutive sau ordin cu rezultat necunoscut → stare `HALTED`, blochează intrări noi, notifică, reluare doar manuală.
6. Scrie teste **adversariale**: simulează o propunere LLM care încearcă (prin conținutul JSON sau prin text asociat) să ceară o mărime peste limită, să sară peste stop-loss, sau să „convingă" sistemul să ignore drawdown-ul — testul trebuie să demonstreze că cererea e respinsă indiferent de conținut.

**Criterii de acceptare:**
- [ ] `risk_engine.py` nu importă și nu depinde de niciun modul din `llm/`.
- [ ] Suite de teste unitare acoperă fiecare limită din `risk_limits.yaml` (inclusiv cazuri limită: exact la prag, peste prag, sub minim de instrument).
- [ ] Cel puțin 3 teste adversariale trec, demonstrând imposibilitatea bypass-ului prin output LLM.
- [ ] Kill switch-ul a fost testat manual și rezultatul e documentat (timp de răspuns, stare a pozițiilor deschise după activare).

---

## 6. Task 4 — Backtesting realist

**Obiectiv:** un harness de backtesting care nu supraestimează performanța — include costuri reale, verifică bias-uri, și separă clar train/validation/test.

**Pași:**
1. Construiește backtestul pe NautilusTrader, cu: comisioane, spread bid/ask, slippage, volume/fills parțiale.
2. Implementează separare cronologică strictă train/validation/test + walk-forward; păstrează o perioadă finală „neatinsă" (holdout) până la evaluarea finală.
3. Adaugă teste automate de detectare a look-ahead bias (ex. verifică că nicio strategie nu accesează date cu timestamp ulterior deciziei) — folosește ca referință metodologia Freqtrade de lookahead analysis ca sursă de idei, nu ca dependență de cod.
4. Rulează fiecare backtest și cu costuri/slippage la 2× și 3× față de estimarea inițială — documentează dacă „avantajul" dispare.
5. Construiește un baseline **fără LLM** (strategie determinist simplă) și compară rezultatele strategiei cu LLM față de acest baseline, pe aceleași date și costuri.
6. Arhivează pentru fiecare rulare: inputurile exacte, seed-urile, hash-ul datelor, output-ul complet — reproductibilitate totală (aceleași date + aceeași logică = aceleași rezultate, verificat prin re-rulare).

**Criterii de acceptare:**
- [ ] Backtestul include comisioane și slippage, nu doar preț de mid.
- [ ] Există un test automat care ar eșua dacă s-ar introduce accidental look-ahead bias.
- [ ] Raportul de backtest arată explicit rezultatul la costuri normale, 2× și 3×.
- [ ] Există comparație documentată „cu LLM" vs. „fără LLM" (baseline determinist) pe aceleași condiții.
- [ ] Rularea repetată a aceluiași backtest produce exact aceleași rezultate.

---

## 7. Task 5 — Paper trading pe cel puțin o clasă de active

**Punct de decizie pentru om, înainte de a începe acest task:** alege clasa de active de pornire — **Cale A: Acțiuni via IBKR paper**, sau **Cale B: Crypto via Kraken (Freqtrade dry-run sau adapter Nautilus în modul sandbox)**. Calea B are, de regulă, timp de pornire mai scurt (nu necesită aprobare de cont IBKR). Claude Code nu alege singur această cale — semnalează opțiunile și așteaptă decizia, sau urmează calea deja specificată în config dacă a fost stabilită anterior.

### Cale A — Acțiuni, IBKR paper
1. Configurează adapterul IBKR din NautilusTrader în mod paper (necesită un cont IBKR aprobat și finanțat pentru paper, aprovizionat de om — nu de Claude Code).
2. Rulează minimum 30 de sesiuni relevante, cu date live, cu jurnal complet al fiecărei decizii (propuse, aprobate, respinse).
3. Verifică explicit: reconectare după disconnect, date expirate (stale), ordine respinse/parțiale, timeout după submit, duplicate.

### Cale B — Crypto, Kraken (Freqtrade dry-run sau Nautilus sandbox)
1. Configurează `dry_run: true` obligatoriu; nicio cheie de tranzacționare reală, doar acces la date publice.
2. Rulează minimum 30 de sesiuni relevante, cu jurnal complet.
3. Verifică aceleași cazuri ca la Calea A (reconectare, date stale, ordine respinse, duplicate).

**Comun ambelor căi:**
4. Fiecare decizie (propusă de LLM, aprobată/respinsă de risc, executată sau nu) se scrie în baza de audit (`audit/`), append-only, cu timestamp și motiv.
5. Aprobarea umană rămâne obligatorie pentru orice acțiune care ar crește riscul, chiar în paper — simulează exact fluxul care va fi folosit ulterior în live, ca să nu existe surprize la trecerea de fază.
6. La finalul minimum de sesiuni, generează un raport: zero ordine neautorizate/duplicate/peste limită? reconciliere completă după fiecare restart? rată de citări nesusținute, rată de JSON invalid, latență?

**Criterii de acceptare:**
- [ ] Minimum 30 sesiuni paper relevante rulate, fără incident critic nereportat.
- [ ] Zero chei live folosite în tot acest task.
- [ ] Reconciliere completă demonstrată după cel puțin un restart simulat.
- [ ] Raport final de paper trading generat și revizuit de om (PO/Risk owner) înainte de a discuta orice trecere spre Faza 5.

---

## 8. Ordinea de execuție (dependențe între task-uri)

```
Task 0 (mediu) 
   └──> Task 1 (NautilusTrader) ──┬──> Task 3 (risc determinist)
                                   │         │
        Task 2 (LLM izolat) ──────┘         ▼
                                    Task 4 (backtesting realist)
                                             │
                                             ▼
                                    Task 5 (paper trading)
```

Task 2 (LLM izolat) poate începe în paralel cu Task 1, dar **nu se integrează** cu Task 3/4 până când testele adversariale de la Task 3 nu trec.

---

## 9. Checklist global — Definition of Done pentru Fazele 0–4

- [ ] Toate task-urile 0–5 au criteriile lor individuale bifate.
- [ ] Zero chei/credențiale live în tot codul, configul sau istoricul git.
- [ ] Toate limitele de risc sunt în config validat, nu în prompt sau în cod al stratului LLM.
- [ ] Suite de teste (unit + adversarial) rulează în CI la fiecare commit relevant.
- [ ] Raportul de calificare NautilusTrader, raportul de backtest și raportul de paper trading există și sunt revizuite de PO/Risk owner.
- [ ] Kill switch testat manual, cu rezultat documentat.
- [ ] Niciun cod nu presupune sau pregătește silențios trecerea la live (fără flag-uri „TODO: enable live" active).

---

## 10. Recapitulare — ce NU face Claude Code în această fază

- Nu deschide conturi, nu solicită și nu introduce credențiale de broker/exchange live.
- Nu scrie cod care conectează output-ul LLM direct la un order gateway.
- Nu modifică `risk_limits.yaml` pe baza unei sugestii venite din output LLM.
- Nu instalează sau folosește NautilusTrader v2 (RC) pentru munca principală.
- Nu comite niciun secret, cheie sau `.env` real în git.
- Nu trece nicio componentă în modul live fără o cerere explicită, separată, ulterioară acestor faze.
