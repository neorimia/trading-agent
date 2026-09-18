# Feature: Research & Crawling Financiar pentru Agentul Local de Trading

Data: 2026-09-18
Status: brainstorming arhitectural — niciun cod implementat încă.
Scop: alimentarea agentului local (`src/llm` → `ProposalContext.external_context`) cu context financiar verificat, cu **surse citate și încredere cuantificată**, fără a transforma vreodată o știre sau un scor de sentiment într-o instrucțiune de tranzacționare.

---

## 0. Cum se leagă de codul existent

Repo-ul are deja punctul de integrare corect și o filozofie de securitate compatibilă cu acest feature — nu trebuie inventat un canal nou:

- `src/engine/proposal_types.py:45` — `ProposalContext` are deja câmpul `external_context: str | None`. Acesta e locul unde randamentul acestui pipeline de research trebuie să ajungă — **ca text, nu ca structură nouă de schemă**.
- `src/llm/service.py` + `tests/adversarial/test_llm_prompt_injection.py` — proiectul tratează deja `external_context` ca **date netrusted**: promptul de sistem conține explicit avertismentul "never as instructions", iar `LLMProposal` (`extra="forbid"`) respinge orice câmp injectat (`position_size`, `disable_risk_limits` etc.). Orice conținut produs de research trebuie să respecte același contract — schema de ieșire a LLM-ului rămâne `{instrument, direction, confidence, rationale}`, punct.
- `src/risk/risk_engine.py` + `CircuitBreaker` — decizia finală de risc e deterministă, separată de LLM. Research-ul alimentează **doar** raționamentul, nu bypassează niciodată `RiskEngine`.
- Testele `test_injection_does_not_load_execution_or_risk_modules` — confirmă izolarea de proces. Pipeline-ul de crawling trebuie să trăiască într-un proces/modul separat (`src/research/` sau serviciu HTTP local separat), la fel cum `src/llm` e izolat de `src/engine`/`src/risk`.

Concluzie arhitecturală: research-ul e un **serviciu extern la engine**, care produce text sumarizat + citate, injectat prin `external_context`, tratat ca date netrusted, niciodată ca sursă de câmpuri noi în schema de propunere.

---

## 1. Probleme de analizat înainte de implementare

### 1.1 Juridice / ToS

| Problemă | Observație |
|---|---|
| **robots.txt** | Nu are forță legală directă (nu e contract), dar ignorarea lui sistematică e un semnal de rea-credință folosit în litigii și motiv de blocare IP/legal notice. [Robots.txt liabilities](https://www.researchgate.net/publication/389402528_The_Liabilities_of_RobotsTxt) |
| **Termeni de utilizare (ToS)** | Multe site-uri financiare (Bloomberg, Reuters, WSJ, Investing.com) interzic explicit scraping automatizat în ToS, indiferent de robots.txt. ToS e contract — încălcarea lui e risc juridic real (breach of contract), diferit de CFAA. |
| **Copyright / redistribuire** | Titluri + link + rezumat scurt (fair use / fapte necopiate) sunt de regulă acceptabile; **reproducerea integrală a articolelor** nu este, mai ales dacă e redistribuită sau folosită pentru a antrena/genera conținut derivat public. |
| **hiQ v. LinkedIn** | Precedent (SUA) — scraping de date public accesibile probabil nu încalcă CFAA, dar nu anulează ToS/breach of contract sau alte legi (GDPR pentru date personale, drept de autor pentru conținut). Nu e o "licență generală de scraping". |
| **Paywall-uri** | Ocolirea tehnică a unui paywall (cookie/session tricks, headless bypass) e zonă gri-spre-neagră legal — recomandarea fermă: **nu se ocolesc paywall-uri**. Se folosesc doar abstracte/titluri publice sau abonamente API oficiale plătite. |

**Regulă de proiectare**: implicit-deny. O sursă intră în `source_registry` doar dacă are (a) API/RSS oficial, sau (b) robots.txt permite explicit crawling pe acele path-uri, sau (c) e conținut guvernamental/public prin lege (SEC, banci centrale, agenții statistice). Orice altceva necesită aprobare manuală explicită, documentată în registry.

### 1.2 Tehnice

- **Rate limits & blocare crawlere**: fiecare sursă din registry are un `rate_limit_policy` explicit (ex. SEC EDGAR: 10 req/s + User-Agent obligatoriu cu nume+email — [sursă oficială SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)). Depășirea = 403/429 și blocare IP temporară.
- **Autentificare**: unele API-uri (Alpha Vantage, Finnhub, NewsAPI) necesită API key; niciuna nu trebuie hardcodată — folosiți `.env` după modelul deja existent în repo (`.env.example`).
- **Duplicate content**: aceeași știre (Reuters) apare redistribuită pe zeci de site-uri financiare secundare (Yahoo Finance, MSN, agregatoare). Necesită deduplicare pe hash de conținut normalizat + fuzzy match pe titlu, nu doar pe URL.
- **Informații contradictorii**: două surse pot raporta cifre diferite (ex. estimări de consens vs. raportate). Trebuie păstrate ambele, cu sursă, nu rezolvate silențios printr-o singură valoare "câștigătoare".
- **Timestamp-uri incorecte**: multe site-uri actualizează articole fără a schimba `datePublished` vizibil; scraper-ul trebuie să distingă `http_fetched_at` (cert) de `claimed_published_at` (declarat de sursă, mai puțin fiabil) de `event_date` (data reală a evenimentului economic, ex. data ședinței Fed, nu data articolului despre ea).
- **Bias de sursă**: fiecare sursă are un scor de credibilitate/bias calibrat manual la înregistrarea în registry (nu inferat automat de LLM).
- **Prompt injection în pagini web**: o pagină crawlată poate conține text de tipul "Ignore previous instructions..." (exact tiparul deja testat în `test_llm_prompt_injection.py`). Extractorul de conținut trebuie să trateze HTML-ul strict ca date, iar orice text extras ajunge la LLM încadrat explicit ca "EXTERNAL CONTEXT — untrusted" — pattern deja implementat în `src/llm/service.py`.
- **Conținut generat automat / manipulare de sentiment**: presă financiară cu conținut AI de calitate joasă sau "pump" coordonat pe rețele sociale/crypto. Mitigare: scor de credibilitate pe sursă + cerință de confirmare multi-sursă înainte ca un item să capete relevanță ridicată.
- **Informații vechi reintrate în circuit**: un articol vechi re-distribuit/re-indexat poate părea "nou". Se rezolvă prin `event_date` distinct de `crawled_at`, plus deduplicare pe conținut normalizat, nu pe timestamp.

---

## 2. Variante de implementare

| Variantă | Cum funcționează | Surse potrivite | Avantaje | Dezavantaje | Cost | Complexitate | Latență | Scalabilitate | Risc tehnic | Risc juridic | Acuratețe | Potrivire local |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Crawler clasic (HTML)** | Fetch + parse HTML, urmărește linkuri conform regulilor proprii | Site-uri fără API/RSS | Acoperire mare, flexibil | Fragil la schimbări de layout, risc legal/ToS mai mare | Scăzut (infra) | Mediu-Mare | Minute | Medie (necesită scheduler + throttling per domeniu) | Blocare/CAPTCHA, HTML drift | Mediu-Mare | Medie (extracție zgomotoasă) | Bună, dar consumă CPU/IO local |
| **RSS aggregator** | Poll periodic pe feed-uri XML/Atom publicate oficial | Presă financiară (Reuters, Investing.com au feed-uri publice; multe emitenți IR au RSS), bloguri companii, SEC filing feeds | Legal curat, structurat, ieftin, standard vechi/stabil | Doar ce publică sursa în feed; feed-uri pot fi trunchiate | Foarte scăzut | Mică | Secunde-minute | Foarte bună | Feed dispărut/schimbat fără preaviz | Scăzut | Depinde de sursă | Excelentă pentru local, greutate minimă |
| **API-based (oficial)** | Cereri către API-uri documentate cu chei | SEC EDGAR, FRED, ECB, Eurostat, BLS, World Bank, IMF, Alpha Vantage, Finnhub, NewsAPI (plătit pt. producție), CoinGecko | Cel mai curat legal, date structurate, SLA clar | Cost la scară, limite de rate stricte pe planuri gratuite | Variabil (gratuit→sute $/lună) | Mică-Medie | Secunde | Bună (limitată de plan) | Deprecări de endpoint, schimbări de schemă | Foarte scăzut | Ridicată | Excelentă — recomandată ca bază |
| **Browser automation (headless)** | Randare JS completă + interacțiune (Playwright/Puppeteer) | SPA-uri fără API, dashboard-uri publice fără feed | Acoperă conținut dinamic | Greu, lent, fragil, ușor detectabil ca bot, risc ToS ridicat dacă ocolește protecții | Mediu (CPU/RAM) | Mare | Secunde-zeci de secunde per pagină | Slabă (resurse per pagină) | Detectare anti-bot, breaking changes DOM | Mediu-Mare | Medie | Slabă pt. rulare locală continuă — folosire punctuală, nu la scară |
| **News aggregation (servicii terțe)** | Servicii care agregă deja mii de surse cu licențiere clarificată | GDELT (gratuit, fără cheie), Finnhub news, Alpha Vantage News Sentiment, NewsAPI (plătit pt. comercial) | Elimină nevoia de crawling propriu, ToS clar | Cost pentru volume mari/producție; unele au delay pe planul gratuit | Gratuit→$449+/lună | Mică | Secunde-minute | Bună | Dependență de furnizor | Scăzut (dacă licențiat corect) | Medie-Ridicată | Foarte bună |
| **Semantic search (peste corpus deja colectat)** | Embeddings + căutare prin similaritate peste documentele deja ingerate | N/A (e layer peste sursele de mai sus) | Retrieval relevant, nu doar keyword match | Necesită corpus + index deja construit | Scăzut (compute local) | Medie | Milisecunde-secunde | Foarte bună local | Drift semantic, embeddings învechite | N/A | Depinde de calitatea corpusului | Excelentă local (rulează pe aceeași mașină cu Qwen3) |
| **RAG cu vector DB** | Semantic search + generare de răspuns/context de către LLM local, cu citare de surse | Layer peste corpus | Context precis, citabil, reduce halucinația | Complexitate de pipeline (chunking, re-ranking), risc de "context stuffing" prost calibrat | Scăzut (local: Chroma/Qdrant) | Medie-Mare | Secunde | Bună local | Chunking prost → pierdere de context; index stale | N/A | Ridicată dacă bine implementat | Foarte potrivit — se integrează natural cu `external_context` |
| **Knowledge graph** | Entități (companii, active, evenimente) + relații explicite, interogabile | Layer peste corpus normalizat | Relații explicite (companie→sector→eveniment), urmărire cauzalitate, deduplicare naturală pe entitate | Cost de întreținere ridicat, schema design non-trivial | Mediu (dev time) | Mare | Milisecunde (query) | Bună | Erori de entity linking se propagă | N/A | Ridicată dacă bine curatat | Fezabil local (Neo4j/SQLite+graph lib), dar overkill pentru MVP |
| **Pipeline hibrid (recomandat)** | RSS+API ca sursă primară → normalizare → vector DB pentru retrieval → knowledge graph opțional pentru relații → RAG pentru sinteză | Toate de mai sus, orchestrate | Combină costul scăzut al RSS/API cu puterea de retrieval a RAG | Cea mai mare complexitate de proiectare inițială | Scăzut-Mediu | Mare (dar incremental) | Secunde | Foarte bună | Multiple puncte de eșec — necesită observabilitate | Scăzut (surse legale la bază) | Cea mai ridicată | **Recomandat** — vezi arhitectura §3 |

Concluzie: **crawler-ul clasic HTML agresiv nu e recomandat ca sursă primară**. Baza trebuie să fie RSS + API oficiale (cost/risc minim), completate opțional cu browser automation punctual doar pentru surse fără altă cale, niciodată pentru ocolire de paywall/anti-bot.

---

## 3. Arhitectură modulară propusă

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Source Registry (config, YAML/DB) — per sursă: tip, URL/endpoint, │
│    ToS status, robots.txt status, rate_limit_policy, credibility_    │
│    score, categorii acceptate, auth necesară, activ/inactiv          │
└───────────────┬─────────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────┐   ┌──────────────────────────┐
│ 2. Scheduler (cron/queue)     │──▶│ 3. Rate Limiter           │
│  per-sursă interval + backoff │   │  per-domeniu, token bucket│
└───────────────┬──────────────┘   └──────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────┐
│ 4. Connectors (câte un adapter per tip sursă)                │
│  4a. API connectors (SEC, FRED, ECB, Finnhub...)              │
│  4b. RSS connectors                                           │
│  4c. HTML crawler (whitelist explicit, respectă robots.txt)   │
│  4d. Browser automation (doar surse marcate explicit, rar)    │
└───────────────┬───────────────────────────────────────────────┘
                │  raw payload (HTML/JSON/XML) + fetch metadata
┌───────────────▼───────────────────────────────────────────────┐
│ 5. Raw Document Store (fișiere/blob, imutabil, cu hash)        │
│    — păstrează exact ce s-a primit, pentru audit/replay        │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 6. Content Extraction (readability/boilerplate removal)        │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 7. Document Normalization (schema comună — vezi §4)            │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 8. Language Detection + Traducere (opțional, doar dacă target   │
│    e non-EN și modelul local rulează mai bine în EN)           │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 9. Deduplicare (hash conținut normalizat + fuzzy title match)  │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 10. Clasificare (activ/companie/sector/temă) — reguli + model  │
│     local mic, NU LLM-ul principal de trading                  │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 11. Entity Recognition (tickere, companii, indicatori macro)   │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 12. Sentiment & Impact Analysis (scor per document, per activ) │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 13. Relevance & Confidence Scoring (vezi §5)                   │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ 14. Cross-source Verification (grupare documente pe eveniment, │
│     flag dacă un fapt apare într-o singură sursă necredibilă)  │
└───────┬─────────────────────────────────────┬─────────────────┘
        │                                     │
┌───────▼──────────────┐          ┌───────────▼──────────────┐
│ 15. Metadata DB       │          │ 16. Vector DB              │
│  (Postgres/SQLite)    │          │  (Chroma/Qdrant, local)    │
│  — toate câmpurile §4 │          │  — embeddings pt. retrieval│
└───────┬──────────────┘          └───────────┬──────────────┘
        │                                     │
        └───────────────┬─────────────────────┘
                         │
              ┌──────────▼───────────┐
              │ 17. Search/Retrieval  │
              │  (semantic + filtre   │
              │  pe activ/dată/sursă) │
              └──────────┬───────────┘
                         │
        ┌────────────────┼────────────────────┐
        │                │                    │
┌───────▼──────┐  ┌──────▼───────┐   ┌────────▼─────────┐
│ 18. Alerting  │  │ 19. Audit Log │   │ 20. Interfață     │
│  (event-driven│  │  (ce s-a      │   │  agent de trading  │
│  praguri de   │  │  colectat,    │   │  → produce STRING  │
│  impact)      │  │  scoruri,     │   │  citabil, injectat │
│               │  │  decizii)     │   │  în                 │
│               │  │               │   │  ProposalContext.   │
│               │  │               │   │  external_context   │
└───────────────┘  └───────────────┘   └────────────────────┘
```

Notă de proces: modulele 1-14 formează pipeline-ul de ingestie/procesare (poate rula ca job/serviciu separat, ex. `src/research/` sau chiar un repo/serviciu distinct rulat local). Modulul 20 este singurul punct de contact cu `src/engine` — produce **text**, nu structuri noi, exact ca `external_context` din schema actuală.

---

## 4. Schema documentului (Metadata DB)

```json
{
  "doc_id": "sha256 al (url + fetched_at) — identificator intern",
  "url": "string",
  "title": "string",
  "source_id": "referință la source_registry",
  "author": "string | null",
  "published_at": "ISO8601 — declarat de sursă",
  "fetched_at": "ISO8601 — cert, moment de fetch",
  "event_date": "ISO8601 | null — data reală a evenimentului economic descris",
  "assets_mentioned": ["AAPL", "EURUSD", "BTC"],
  "companies_mentioned": ["Apple Inc."],
  "category": "news | earnings | filing | macro_indicator | market_analysis | sentiment | geopolitical",
  "raw_content_ref": "pointer către Raw Document Store",
  "extracted_text": "string (curățat de boilerplate)",
  "summary": "string (generat, scurt, atribuit)",
  "language": "en | ro | ...",
  "sentiment": {"score": -1.0, "label": "negative", "model": "..."},
  "estimated_impact": {"magnitude": "low|medium|high", "direction": "bullish|bearish|neutral|unclear"},
  "confidence_score": 0.0,
  "last_verified_at": "ISO8601",
  "confirming_sources": ["doc_id", "doc_id"],
  "contradicting_sources": ["doc_id"],
  "content_hash": "sha256 al textului normalizat",
  "related_documents": ["doc_id (follow-up, retracted_by, duplicate_of)"]
}
```

Câmpuri obligatorii de audit: `content_hash` (deduplicare + detectare modificare ulterioară a articolului), `last_verified_at` (când a fost ultima dată reconfirmat/recontrolat), `confirming_sources`/`contradicting_sources` (verificare multi-sursă explicită, nu implicită).

---

## 5. Scoring de relevanță

```
relevance_score =
    w1 * source_credibility        # calibrat manual per sursă în registry, 0-1
  + w2 * recency_decay(event_date) # scade exponențial cu vârsta informației
  + w3 * corroboration(n_confirming_independent_sources)
  + w4 * asset_relevance           # cât de direct vizează activul analizat
  + w5 * impact_magnitude          # estimat calitativ, nu cuantificat fals precis
  - w6 * uncertainty_penalty       # surse unice, limbaj speculativ, date lipsă
  - w7 * already_priced_in_penalty # ex. dacă piața a mutat deja prețul semnificativ
                                    # de la publicare (proxy: variație preț de la event_date)
```

Reguli:
- Ponderile (`w1..w7`) sunt configurabile, nu hardcodate — se calibrează empiric, nu se pretinde precizie falsă.
- `already_priced_in_penalty` e cheie pentru a evita ca agentul să reacționeze la știri "vechi" din perspectiva pieței (regăsit și în cerința utilizatorului despre risc de informație învechită).
- Scorul e **input pentru prioritizare/filtrare**, nu pentru decizie automată. Un scor mare nu autorizează nimic — doar determină ce ajunge în `external_context` și în ce ordine.

---

## 6. Prezentare către agent — comparație moduri

| Mod | Potrivit pentru | Compatibil cu arhitectura actuală |
|---|---|---|
| Rezumat zilnic | Context de deschidere de sesiune/zi | Da — se poate genera offline și cache-ui |
| Briefing timp real | Evenimente cu impact ridicat, rare | Da, dar nu la fiecare bar — costisitor |
| Event-driven alerts | Evenimente discrete (FOMC, earnings) | Da — trigger separat de `on_bar` |
| Context per activ | **Recomandat ca default** — exact ce cere `ProposalContext.instrument` | Da — mapare 1:1 cu structura existentă |
| Timeline evenimente | Analiză retrospectivă/backtest | Da, pentru research uman, nu pentru live |
| Research report automat | Analiză periodică profundă | Util pentru om, nu pentru fiecare decizie a agentului |
| RAG query la cerere | Flexibil, dar introduce latență variabilă în bucla de trading | Folosit ca sursă pentru "context per activ" pre-calculat, nu inline la fiecare bar |

Recomandare: **context per activ, pre-calculat și cache-uit** (similar cu `CachingLLMProposalClient` deja existent în `src/engine/proposal_cache.py`), populat din RAG offline, injectat sincron în `external_context` fără a introduce latență de rețea în bucla `on_bar`.

---

## 7. Limita informație → decizie

```
informație brută  → document extras, nesumarizat, cu sursă+timestamp
rezumat           → compresie factuală, fără interpretare adăugată
analiză            → interpretare explicită, cu ipoteze declarate
semnal            → observație cuantificată (ex. sentiment_score=-0.6), fără direcție de acțiune
recomandare        → ⛔ NU produsă de acest pipeline — ar implica sugestie de acțiune
decizie de tranzacționare → exclusiv `RiskEngine` + aprobare umană (Faza 5, per README-ul proiectului)
```

Acest pipeline se oprește la **analiză + semnal**. `direction: long|avoid|exit` din `LLMProposal` rămâne generat exclusiv de LLM-ul de strategie, evaluat de `RiskEngine` — research-ul nu produce niciodată acel câmp direct.

---

## 8. Controale obligatorii pentru agent

Mapate pe testele/pattern-urile deja existente în repo:

1. **Citarea surselor** — orice afirmație din `external_context` include URL/sursă/dată; fără citare = nu intră în context.
2. **Timestamp explicit** — `published_at` vs `event_date` vs `fetched_at`, toate distincte, toate afișate.
3. **Prezentarea contradicțiilor** — dacă `contradicting_sources` nu e gol, ambele versiuni apar în context, nu doar "câștigătorul".
4. **Nivel de încredere explicit** — `confidence_score` afișat, nu ascuns.
5. **Explicitarea necunoscutului** — dacă un activ nu are acoperire de research, contextul spune explicit "no recent verified context available", nu se completează cu presupuneri.
6. **Verificare staleness** — dacă `last_verified_at` e vechi relativ la volatilitatea activului, se marchează explicit "stale".
7. **Fără decizie pe sursă unică** — prag minim de corroborare pentru orice item cu impact estimat "high".
8. **Separare fapt/interpretare** — format text cu secțiuni distincte ("Facts:" / "Interpretation:").
9. **Aprobare umană în fazele inițiale** — consistent cu README (Faza 5 = aprobare umană explicită înainte de execuție reală); research-ul nu schimbă acest gate.

Aceste reguli se implementează ca format de rendering al `external_context` (un template determinist, nu generat liber de un LLM secundar), pentru a păstra proprietatea deja testată "external context is passed as untrusted data" și a nu introduce halucinație într-un strat care ar trebui să fie strict factual.

---

## 9. Trei versiuni

### MVP (1-2 săptămâni)
- **Funcționalități**: RSS aggregator (2-3 feed-uri de presă financiară generalistă) + 1-2 API-uri oficiale gratuite (FRED pentru macro, SEC EDGAR pentru filings pe universul de instrumente deja configurat) → normalizare minimă → stocare SQLite → context per activ generat prin keyword/entity match simplu (fără vector DB încă) → injectat manual în `external_context` pentru teste.
- **Surse**: FRED, SEC EDGAR, 2-3 RSS-uri publice.
- **Tehnologii**: Python (consistent cu restul repo-ului), `httpx` (deja folosit în `src/llm`), `feedparser`, SQLite.
- **Structură date**: subset din schema §4 (fără sentiment/embeddings încă).
- **Cost**: ~0 (toate sursele sunt gratuite).
- **Riscuri**: acoperire redusă, fără deduplicare robustă.
- **Criterii de succes**: context per activ generat determinist, testabil, fără halucinație, cu citare de sursă vizibilă.
- **Ce NU se implementează**: sentiment analysis, vector DB, knowledge graph, browser automation, alerting.

### Intermediar (1-2 luni)
- **Funcționalități**: + surse suplimentare (Alpha Vantage News Sentiment sau Finnhub — plan gratuit, non-comercial), embeddings locale (ex. model mic on-device) + vector DB local (Chroma), deduplicare pe hash+fuzzy, scoring de relevanță (§5) cu ponderi inițiale, verificare multi-sursă de bază, cache pentru context per activ.
- **Surse**: + Finnhub/Alpha Vantage (news+sentiment), ECB/Eurostat/BLS/World Bank pentru macro extins.
- **Tehnologii**: Chroma sau Qdrant local, `sentence-transformers` local, scheduler (`APScheduler` sau cron simplu).
- **Cost**: ~0-50$/lună (dacă se trece la un tier plătit mic pentru un API de news, opțional).
- **Riscuri**: complexitate de întreținere a embeddings/index; nevoie de observabilitate (logging structurat).
- **Criterii de succes**: retrieval relevant demonstrabil pe interogări test, scor de relevanță corelat vizibil cu judecata umană pe un set de validare manual.
- **Ce NU se implementează încă**: knowledge graph, alerting în timp real, browser automation, traducere automată.

### Avansat / producție
- **Funcționalități**: pipeline hibrid complet (§3, toate cele 20 module), knowledge graph pentru relații companie/sector/eveniment, alerting event-driven, audit log complet, verificare cross-sursă avansată, dashboard de observabilitate.
- **Surse**: setul extins din §10, inclusiv eventual surse comerciale plătite dacă volumul o justifică.
- **Tehnologii**: bază de date relațională (Postgres) pentru metadata + graph layer, vector DB dedicat, queue (Redis/RQ) pentru scheduler robust, observabilitate (structured logs + metrics locale).
- **Cost**: variabil, depinde de volumul de surse comerciale adăugate; infra locală rămâne ieftină.
- **Riscuri**: suprafață mare de întreținere; risc de "context overload" dacă scoring-ul nu e calibrat bine.
- **Criterii de succes**: reducere măsurabilă a deciziilor bazate pe informație unică/necorroborată; audit trail complet reproductibil.
- **Ce NU se implementează niciodată în acest feature**: execuție automată bazată pe scor, ocolire de paywall, generare de "recomandări" de tranzacționare — acestea rămân explicit în afara scopului conform cerinței inițiale.

---

## 10. Comparație tehnologii

| Categorie | Opțiuni | Recomandare locală |
|---|---|---|
| Crawling/scraping | `httpx`+`selectolax`/`trafilatura`, Scrapy | `httpx` (deja în repo) + `trafilatura` pentru extracție |
| Browser automation | Playwright, Puppeteer | Playwright, doar pentru surse whitelisted explicit |
| Job scheduling | cron, APScheduler, Celery beat | APScheduler (simplu, in-process, fără infra suplimentară) |
| Queues | Redis+RQ, Celery, SQLite-backed queue | SQLite-backed pentru MVP; Redis+RQ dacă volumul crește |
| Parsing | `trafilatura`, `readability-lxml`, `feedparser` (RSS) | `feedparser` + `trafilatura` |
| Embeddings | `sentence-transformers` local, modele mici pe Ollama | Model mic local, coerent cu Qwen3 deja rulat local |
| Vector search | Chroma, Qdrant, FAISS | Chroma (simplu, embedat, fără server separat) |
| Bază de date relațională | SQLite, Postgres | SQLite pentru MVP → Postgres la scalare |
| Bază de date documente | MongoDB, fișiere plate + index | Fișiere plate (Raw Document Store, imutabil) + SQLite index |
| Observabilitate | logging structurat, Prometheus local, `structlog` | logging structurat simplu, consistent cu restul repo-ului |
| Local deployment | proces Python separat, systemd/launchd timer | Proces separat de `src/engine`, apelat prin fișier/API local, nu import direct |

---

## 11. Surse posibile

**Oficiale (guvernamentale/instituționale, gratuite, verificate azi):**
- SEC EDGAR (filings, full-text search) — [sec.gov/edgar](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) — 10 req/s, User-Agent obligatoriu, fără cheie.
- FRED — Federal Reserve Bank of St. Louis — [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) — gratuit, cheie liberă, 120 req/min.
- BLS (șomaj, CPI) — [bls.gov](https://www.bls.gov/) — gratuit, 25 req/zi fără cheie / 500 cu cheie gratuită.
- ECB Data Portal (SDW) — [data.ecb.europa.eu](https://data.ecb.europa.eu/) — gratuit, fără cheie.
- Eurostat — API SDMX, gratuit, fără cheie.
- World Bank Open Data / IMF DataMapper — gratuite, fără cheie.

**Cu API (comerciale/mixte, verificate azi):**
- Finnhub — plan gratuit ~60 req/min, **doar uz personal/non-comercial**; producție necesită plan plătit.
- Alpha Vantage — plan gratuit 25 req/zi; News Sentiment inclus, dar redistribuirea comercială necesită licențiere separată.
- NewsAPI.org — plan gratuit **interzice explicit uz comercial** și are delay de 24h; producție reală necesită Business ($449/lună).
- CoinGecko — public API 5-15 req/min fără cheie, Demo plan gratuit ~30 req/min cu cheie; uz comercial necesită plan plătit.

**Gratuite, fără cheie:**
- GDELT Project — monitorizare globală de știri, fără cheie, gratuit, index ~3 luni pentru unele API-uri wrapper; datele complete disponibile și via BigQuery.

**Cu RSS:**
- Feed-uri RSS publice ale agențiilor de presă și ale paginilor de Investor Relations ale companiilor listate (fiecare emitent își publică propriul feed pentru comunicate — se verifică individual per companie din universul de instrumente).

**Care NU trebuie crawlite fără permisiune explicită:**
- Bloomberg Terminal/bloomberg.com (conținut cu ToS restrictiv documentat) — se verifică `bloomberg.com/robots.txt` + ToS înainte de orice acces automatizat.
- Reuters.com pentru conținut integral (Reuters a fost în centrul rapoartelor privind respectarea/încălcarea robots.txt de către AI crawlers — [Reuters/TollBit report](https://www.tomshardware.com/tech-industry/artificial-intelligence/several-ai-companies-said-to-be-ignoring-robots-dot-txt-exclusion-scraping-content-without-permission-report)).
- Orice site cu paywall — nu se ocolește tehnic, doar metadate publice (titlu, dată, abstract dacă e public).
- Rețele sociale (X/Twitter, Reddit, Discord de crypto) — au ToS proprii stricte privind scraping-ul automatizat; necesită API oficial cu termeni acceptați explicit, nu scraping direct.

**Notă**: lista de mai sus reflectă politicile verificate la 2026-09-18 via căutare — **fiecare sursă trebuie reverificată direct (robots.txt + pagina de pricing/ToS oficială) înainte de activare în `source_registry`**, deoarece planurile și limitele se schimbă frecvent.

---

## 12. Livrabile (rezumat conform cerinței)

1. **Top 3 idei de implementare**: (a) RSS + API oficiale ca bază legală/cost minim; (b) RAG local (Chroma + embeddings locale) peste corpusul normalizat, injectat în `external_context` existent; (c) scoring de relevanță cu penalizare explicită pentru informație deja "priced in" și pentru surse unice necorroborate.
2. **Recomandare MVP**: RSS (2-3 surse) + FRED + SEC EDGAR → normalizare minimă → SQLite → context per activ generat determinist (keyword/entity match) → injectat manual în `ProposalContext.external_context`, cu citare de sursă obligatorie și fără sentiment/embeddings încă.
3. **Arhitectura propusă**: §3 (pipeline modular de 20 componente, proces separat de `src/engine`).
4. **Schema de date inițială**: §4.
5. **Fluxul complet**: sursă → raw store → extracție → normalizare → dedup → clasificare/entități → sentiment/impact → scoring → verificare multi-sursă → metadata DB + vector DB → retrieval → format determinist → `external_context` → LLM (tratat ca netrusted) → `RiskEngine` (neschimbat) → aprobare umană (Faza 5).
6. **Surse recomandate**: §11.
7. **Riscuri juridice și tehnice**: §1.
8. **Criterii de calitate**: corroborare minimă pe impact "high", citare obligatorie, `confidence_score` vizibil, distincție fapt/interpretare, staleness explicit.
9. **Plan de implementare**: MVP (1-2 săpt.) → Intermediar (1-2 luni) → Avansat (§9).
10. **Întrebări deschise înainte de dezvoltare**:
    - Care e universul exact de instrumente/companii de acoperit (impactează ce feed-uri IR/filings trebuie înregistrate)?
    - Ce buget lunar e acceptabil pentru API-uri comerciale (Finnhub/Alpha Vantage/NewsAPI Business) dacă planurile gratuite devin insuficiente?
    - `external_context` trebuie generat sincron (la fiecare `on_bar`) sau precalculat/cache-uit periodic (recomandat, vezi §6)?
    - Cine calibrează manual `source_credibility` inițial și cu ce cadență se revizuiește?
    - Traducerea automată e necesară acum sau toate sursele țintă sunt deja în engleză?
    - Unde rulează procesul de research — pe aceeași mașină cu Ollama/Qwen3, sau pe o mașină/VM separată, dat fiind consumul de CPU/RAM al embeddings+crawling?

---

## Surse citate (verificate 2026-09-18)

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC EDGAR — Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- [FRED API key & terms](https://fred.stlouisfed.org/docs/api/api_key.html)
- [NewsAPI.org pricing](https://apicostcalc.com/newsapi.html)
- [Alpha Vantage documentation](https://www.alphavantage.co/documentation/)
- [Finnhub pricing](https://finnhub.io/pricing)
- [CoinGecko API rate limit (public plan)](https://support.coingecko.com/hc/en-us/articles/4538771776153-What-is-the-rate-limit-for-CoinGecko-API-public-plan)
- [GDELT Project](https://gdeltproject.org/)
- [ECB Data Portal](https://data.ecb.europa.eu/)
- [World Bank Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)
- [Reuters/TollBit report on AI crawlers ignoring robots.txt](https://www.tomshardware.com/tech-industry/artificial-intelligence/several-ai-companies-said-to-be-ignoring-robots-dot-txt-exclusion-scraping-content-without-permission-report)
- [The Liabilities of Robots.txt (research paper)](https://www.researchgate.net/publication/389402528_The_Liabilities_of_RobotsTxt)
