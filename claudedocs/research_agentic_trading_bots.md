# Research tehnic: proiecte open-source de AI agentic trading bots (GitHub/Hugging Face)

*Data research-ului: 18 septembrie 2026. Obiectiv: identificarea unei baze tehnice solide pentru un agent local de trading (stocks/forex/crypto/eventual Robinhood), pornind de la 6 proiecte indicate + descoperire suplimentară.*

## Notă metodologică

Raportul separă explicit patru niveluri de certitudine:

- **[FAPT VERIFICAT]** — confirmat direct din README/pagina oficială a proiectului sau din documentația oficială a unui broker.
- **[SURSĂ SECUNDARĂ]** — confirmat din agregatoare/bloguri tehnice independente (de regulă concordante între ele), dar nu am putut deschide eu însumi fișierul sursă (de ex. codul intern, nu doar README-ul).
- **[INFERENȚĂ]** — concluzie logică trasă din ce e documentat, dar netestată de mine (nu am rulat codul).
- **[OPINIE/RECOMANDARE]** — evaluarea sau recomandarea mea, nu un fapt din sursă.

Nu am rulat niciun cod, nu am plasat niciun ordin și nu am validat performanța istorică a niciunei strategii. Acest document nu este consultanță financiară.

---

## 1. Rezumat executiv

- Niciunul dintre cele 6 proiecte indicate de tine nu este, singur, o bază suficientă pentru scopul tău (agent local, real, multi-asset, cu risc controlat). Fiecare are un punct forte îngust:
 - **fsaavedra0003/Agentic-AI-Trading-Bot** — schelet didactic ok ca inspirație pentru layout (ingestion → LLM → decizie → execuție), dar nedovedit ca robustețe (8 stele, README trunchiat, fără dovadă de teste reale).
 - **FriesTrader** — cel mai bun exemplu de **filozofie de siguranță** găsit în tot research-ul (reguli de risc mecanice, separate de raționamentul LLM), dar e un *template* mic (25 commit-uri), nu un framework, și e gândit pentru rulare **cloud programată**, nu local.
 - **Topicul GitHub `quant-trading-bot`** — nu e un proiect, ci un motor de descoperire dominat de repo-uri de marketing/scam de tip „arbitraj 100% automat" — nerecomandat ca sursă de căutare.
 - **Krexibd/quant-trading** — fork al binecunoscutului `je-suis-tm/quant-trading`: colecție educațională de strategii tehnice **fără nicio componentă agentică/LLM și fără execuție live**. Util doar ca bibliotecă de referință pentru indicatori/backtesting clasic.
 - **kweinmeister/agentic-trading (Google)** — demo tehnic foarte curat (Google ADK + protocol A2A), dar rulează pe **date sintetice**, fără broker real, cu avertisment explicit „doar informativ". Util pentru **tiparul arhitectural** (agent de risc separat de agentul de tranzacționare).
 - **HKUDS/AI-Trader** — cele mai multe stele (21,6k) din tot setul, dar e o **potrivire greșită de categorie**: e o platformă socială găzduită (ai4trade.ai) de „copy trading" între agenți, nu un bot local pe care îl rulezi tu, cu risc controlat de tine. Exact tipul de caz în care stelele induc în eroare.
- Am găsit patru proiecte din ecosistemul mai larg net superioare tehnic pentru scopul tău: **TauricResearch/TradingAgents** (arhitectură multi-agent LLM cea mai matură), **AI4Finance-Foundation/FinRL + FinRL-X/FinRL-Trading** (singurul cu integrare **reală, documentată** de broker — Alpaca — pentru paper/live trading și risc pre-tranzacție), **freqtrade** (cel mai matur motor de execuție/risc/backtesting open-source, dar fără LLM, doar crypto) și **virattt/ai-hedge-fund** (bun pentru tiparul de „personas" LLM, dar zero execuție reală).
- **Robinhood s-a schimbat fundamental între ianuarie și mai 2026**: pe lângă API-ul oficial de crypto (existent de mai mult timp), Robinhood a lansat pe 27 mai 2026 **Agentic Trading** — un server MCP oficial prin care un agent AI conectat poate plasa ordine reale de acțiuni (extins ulterior la opțiuni și crypto) într-un cont dedicat, cu limite de buget și deconectare instant. Acest lucru nu exista în datele mele de antrenament și schimbă complet analiza „Robinhood are API sau nu" — vezi secțiunea 6.
- Recomandarea mea nu este „pornește de la un singur repo", ci o **compoziție**: infrastructură de execuție/risc/backtesting dovedită (freqtrade pentru crypto, FinRL-X/Alpaca pentru stocks) + tipar de raționament multi-agent (inspirat din TradingAgents) + filozofie de siguranță mecanică (FriesTrader). Detalii în secțiunea 4 și 7.

---

## 2. Tabel comparativ (scoruri 1–10)

Scala: 1 = absent/foarte slab, 10 = excelent/dovedit în producție. **Scorurile NU sunt corelate cu numărul de stele** — vezi coloana „Activitate" separat de restul.

| Proiect | Maturitate tehnică | Calitate cod | Caracter agentic | Suport multi-asset | Suport broker/exchange | Backtesting | Paper trading | Risk mgmt | Securitate | Observabilitate | Documentație | Extensibilitate | Activitate/mentenanță | Adecvare rulare locală |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fsaavedra0003/Agentic-AI-Trading-Bot | 3 | 3 | 5 | 3 | 4 | 4 | 5 | 3 | 3 | 4 | 5 | 4 | 3 | 6 |
| FriesTrader | 5 | 5 | 7 | 3 | 4 | 1 | 6 | 7 | 5 | 6 | 7 | 5 | 3 | 4 |
| Krexibd/quant-trading (fork je-suis-tm) | 6 | 6 | 1 | 5 | 1 | 6 | 1 | 2 | 5 | 3 | 7 | 4 | 3 | 7 |
| kweinmeister/agentic-trading (Google) | 5 | 7 | 6 | 1 | 1 | 3 | 1 | 6 | 6 | 6 | 8 | 6 | 6 | 7 |
| HKUDS/AI-Trader | 4 | 5 | 4 | 7 | 3 | 2 | 6 | 2 | 3 | 5 | 6 | 4 | 9 | 3 |
| TauricResearch/TradingAgents | 8 | 7 | 9 | 5 | 2 | 7 | 6 | 6 | 5 | 7 | 8 | 8 | 9 | 7 |
| AI4Finance-Foundation/FinRL + FinRL-X | 8 | 7 | 4 | 6 | 7 | 8 | 8 | 6 | 5 | 6 | 7 | 7 | 7 | 6 |
| freqtrade | 9 | 8 | 1 | 3 | 9 | 9 | 9 | 8 | 7 | 8 | 9 | 8 | 9 | 8 |
| virattt/ai-hedge-fund | 5 | 6 | 7 | 2 | 1 | 5 | 3 | 5 | 5 | 5 | 7 | 7 | 8 | 8 |

*Topicul GitHub `quant-trading-bot` nu apare în tabel — nu e un proiect unic, ci un canal de descoperire; l-am tratat separat în secțiunea 5.3.*

---

## 3. Top 3 opțiuni (pentru scopul tău specific)

1. **freqtrade** — cea mai matură infrastructură open-source de execuție + risc + backtesting pentru **crypto**. Nu e agentic, dar e exact tipul de „motor determinist" pe care orice strat LLM ar trebui să-l respecte, nu să-l înlocuiască.
2. **AI4Finance-Foundation/FinRL-Trading (FinRL-X)** — singurul din tot setul cu integrare **documentată și reală** de broker (Alpaca) pentru paper ȘI live trading la nivel de acțiuni, cu control de risc pre-tranzacție explicit.
3. **TauricResearch/TradingAgents** — cea mai matură arhitectură multi-agent LLM (analiști, dezbatere bull/bear, risc, portofoliu), utilă ca **tipar de raționament**, cu mențiunea că execuția lui implicită merge într-un exchange simulat, nu la un broker real.

*(FriesTrader nu intră în top 3 ca "bază", pentru că e prea mic ca framework — dar principiile lui de siguranță ar trebui copiate literal, indiferent ce bază alegi.)*

---

## 4. Recomandare finală argumentată [OPINIE]

Nu recomand adoptarea unui singur repo „ca atare". Motivul e structural: proiectele cu adevărat **agentice** (TradingAgents, ai-hedge-fund, fsaavedra0003, FriesTrader) execută fie în simulare, fie prin conectori minimali, netestați la scară; proiectele cu **execuție reală dovedită** (freqtrade, FinRL-X) nu au raționament LLM agentic nativ. A alege unul singur înseamnă fie (a) un „creier" bun fără „mâini" de încredere, fie (b) „mâini" bune fără judecată contextuală.

**Recomandare: arhitectură compusă din 3 straturi, fiecare provenind din proiectul cel mai dovedit pe acea funcție:**

- **Strat de execuție + risc determinist + backtesting** → pornește de la **freqtrade** (dacă prima clasă de active pe care o pornești e crypto) și/sau **FinRL-X + Alpaca** (dacă pornești cu acțiuni). Ambele au: gestionare reală de poziții, stop-loss/ROI, backtesting cu comisioane/slippage, mod dry-run/paper matur. **Nu rescrie asta de la zero.**
- **Strat de raționament LLM** → inspiră-te din arhitectura **TradingAgents** (roluri specializate: analist fundamental/sentiment/tehnic, cercetători bull/bear care dezbat, „trader" care propune, manager de risc, manager de portofoliu). Nu-i folosi execuția implicită (merge spre un exchange simulat) — conectează output-ul „propunere de tranzacție" la stratul determinist de mai sus.
- **Strat de siguranță/guvernanță** → copiază literal filozofia **FriesTrader**: fișier de reguli mecanice (poziție maximă, stop-loss, limită de pierdere zilnică) pe care LLM-ul nu-l poate suprascrie, separarea „generare teză" de „execuție cu date proaspete", un număr minim de cicluri în dry-run înainte de live, log JSONL auditabil al fiecărei decizii (inclusiv cele respinse). Adaugă și tiparul **RiskGuard** din kweinmeister/agentic-trading: un agent/modul de risc *separat*, apelat obligatoriu înainte de orice execuție, care poate doar aproba/respinge, niciodată propune.

De ce nu HKUDS/AI-Trader în ciuda celor 21,6k stele: pentru că produsul lor e o platformă găzduită de „copy trading" între agenți (ai4trade.ai) — controlul tău asupra riscului, datelor și execuției e mult mai mic decât dacă rulezi propriul stack local. E util eventual mai târziu ca loc de publicare/urmărire a semnalelor, nu ca fundație.

De ce nu ai-hedge-fund ca bază: recunoaște explicit că **nu execută tranzacții reale** — e o simulare de „dezbatere între personaje" (Buffett, Munger, Burry etc.), foarte bună ca sursă de inspirație pentru prompt-uri de agenți, zero valoare pentru execuție.

De ce nu Krexibd/quant-trading ca bază: zero componentă agentică — e literalmente colecția clasică de strategii tehnice `je-suis-tm/quant-trading`, republicată. Bibliotecă utilă de strategii/indicatori pentru backtesting, nimic mai mult.

---

## 5. Analiza detaliată pe proiect

### 5.1 fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis
**[FAPT VERIFICAT din README, fetch direct]**
- **Sursă**: github.com/fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis
- **Activitate**: 8 stele, 4 fork-uri, 205 commit-uri; data exactă a ultimului commit nu a fost vizibilă în pagina randată (limitare tehnică a fetch-ului, nu neapărat inactivitate). **Nivel de încredere: mediu** — README detaliat, dar quickstart-ul e trunchiat în pagină și nu există dovezi vizibile de CI/teste rulate.
- **Scop/arhitectură**: pipeline ingestion (Twitter/X, Reddit, News API, PDF-uri de earnings) → LLM pentru sentiment/reasoning → agent de decizie (tipar LangChain) → execuție prin adaptoare Alpaca/Binance → dashboard Streamlit.
- **Agentic sau script cu LLM?** Undeva la mijloc — folosește orchestrare de tip agent cu tool-calling, dar structura repo-ului (module separate `ingestion/`, `sentiment/`, `models/`, `execution/`) sugerează mai degrabă un **pipeline determinist cu pași LLM**, nu o buclă agentică autonomă completă. **[INFERENȚĂ]**
- **Multi-asset/broker**: menționează adaptoare Alpaca (acțiuni) și Binance (crypto) — fără forex.
- **Backtesting/paper trading**: README menționează ambele module, dar nu am putut verifica profunzimea implementării (fetch-ul README s-a oprit la secțiunea Quickstart).
- **Risk management**: listat generic („max position size, configurable limits, circuit breakers") — fără detalii de implementare vizibile.
- **Securitate**: fără `SECURITY.md` vizibil; are `.gitignore` — presupun (nu confirmat) gestionare de chei prin `.env`.
- **Licență**: **nu a fost vizibilă în pagina fetch-ată** — verifică explicit înainte de reutilizare comercială/personală serioasă.
- **Verdict**: proiect de tip „portofoliu" (chiar așa se auto-descrie — „portfolio/research project"), util ca **inspirație de layout**, nu ca bază de producție.

### 5.2 FriesTrader
**[FAPT VERIFICAT din README, fetch direct]**
- **Sursă**: github.com/YizhiSong/FriesTrader
- **Activitate**: 14 stele, 3 fork-uri, 25 commit-uri, licență MIT. Repo tânăr și mic. **Nivel de încredere: ridicat pentru ce descrie** (README-ul e neobișnuit de onest și de precis tehnic), **dar dimensiune mică = puțină bătaie testată în producție**.
- **Scop/arhitectură**: „template extras dintr-o implementare reală, live" — Claude Code + un conector MCP de brokeraj, rulat ca **două sesiuni cloud programate**: Faza A (~16:30 CT) generează teze pe simboluri candidate din datele de închidere, fără ordine; Faza B (~08:35 CT) reverifică tezele cu date proaspete de deschidere, aplică mecanic `risk_rules.json`, și execută (sau doar simulează) ordinele.
- **Agentic sau script?** Genuin agentic — LLM-ul (Claude Code) face raționamentul de screening/teză, dar **execuția e condiționată de reguli mecanice pe care LLM-ul nu le controlează**. Cel mai bun exemplu din tot setul de separare corectă „judecată LLM" vs. „control determinist".
- **Multi-asset/broker**: un singur cont de brokeraj (numărul de cont e placeholder de completat) — nu specifică explicit ce broker, presupun (dat fiind contextul „US equities" implicit) că e un broker cu API programabil de tip Alpaca/similar. **[INFERENȚĂ]** Fără forex; crypto nemenționat.
- **Backtesting**: **explicit absent și declarat imposibil de făcut onest** — README-ul spune clar că pasul de raționament bazat pe știri nu poate fi backtestat contra datelor istorice pe care modelul le poate deja „ști".
- **Paper trading**: `execution.mode: "dry_run"` obligatoriu un număr minim de cicluri înainte de live — bine gândit.
- **Risk management**: cel mai serios din tot setul mic — `risk_rules.json` conține poziționare, stop-loss, limite de pierdere, filtre de universal, plus un guard explicit de **wash-sale** (regulă fiscală IRS) care verifică conturi legate. Autorul spune explicit: „regulile de risc sunt mecanismul real de siguranță aici, nu calitatea raționamentului."
- **Adecvare rulare locală**: **de fapt, opusul** — e proiectat să ruleze **fără mașină locală**, ca sesiuni cloud programate care clonează repo-ul și fac push la rezultate; repo-ul însuși devine starea persistentă. Dacă vrei rulare pe propriul calculator, trebuie adaptat.
- **Verdict**: nu-l adopta ca framework (e prea mic), dar **copiază-i literal filozofia de siguranță**.

### 5.3 Topicul GitHub `quant-trading-bot`
**[FAPT VERIFICAT din fetch al paginii de topic]**
- Nu e un singur proiect. Rezultatele de top includ repo-uri cu titluri de tipul „Cortex AI: #1 sistem cantitativ inteligent — motor de arbitraj crypto 100% automat v3.4... cel mai bun bot de trading cantitativ de mare frecvență din 2026" — limbaj tipic de marketing agresiv/spam, imposibil de verificat tehnic din README și cu semnale clasice de risc de scam (promisiuni de „cel mai bun", fără dovezi de audit sau track record verificabil).
- **Recomandare**: nu folosi acest topic ca sursă de descoperire pentru un proiect de bază. Topicuri mai fiabile pe GitHub pentru acest domeniu: `quantitative-trading` (conține proiecte serioase precum Microsoft Qlib), `algorithmic-trading`, `llm-agents` + `finance` combinate în căutare.

### 5.4 Krexibd/quant-trading
**[FAPT VERIFICAT din README, fetch direct]**
- **Sursă**: github.com/Krexibd/quant-trading — acesta e un fork/republicare a proiectului foarte cunoscut **je-suis-tm/quant-trading**.
- **Activitate**: 10 stele, 1 fork, 1075 commit-uri (istoric moștenit), ultimul „Release" datat 29 aprilie 2026, licență MIT, are `SECURITY.md`.
- **Scop**: colecție de 17 strategii clasice de trading cantitativ (MACD, pair trading/cointegrare, Heikin-Ashi, London Breakout, Bollinger, RSI, Monte Carlo, VIX calculator, options straddle etc.), fiecare cu script de backtest separat.
- **Agentic sau script?** **Zero componentă agentică sau LLM.** README-ul afirmă explicit că toate scripturile presupun piețe „frictionless" (fără slippage, fără comisioane, fără iliciditate) — deci nici măcar backtesting-ul nu e realist pentru tranzacționare reală.
- **Multi-asset**: acoperă conceptual acțiuni, forex (London Breakout), mărfuri/opțiuni — dar fiecare ca script independent, nu ca motor unificat.
- **Broker/execuție/paper trading**: inexistente — e strict pentru cercetare istorică offline.
- **Verdict**: bibliotecă de referință utilă pentru a înțelege indicatori tehnici clasici și pentru teste de backtesting educaționale, **fără nicio legătură cu cerința ta de „agentic"**.

### 5.5 kweinmeister/agentic-trading (Google)
**[FAPT VERIFICAT din README, fetch direct]**
- **Sursă**: github.com/kweinmeister/agentic-trading — descriere oficială: „Sample application to demonstrate Google ADK and A2A interoperability. For informational purposes only."
- **Activitate**: 251 stele, 58 fork-uri, 156 commit-uri, licență Apache-2.0, are folder `tests/`.
- **Arhitectură**: trei servicii — **AlphaBot** (strategie SMA crossover, construit cu Google Agent Development Kit), **RiskGuard** (evaluează propuneri de tranzacție contra unor reguli de risc configurabile: mărime maximă poziție, concentrare maximă portofoliu) și un **Simulator UI** (FastAPI + Plotly). Comunicare prin protocolul **Agent-to-Agent (A2A)**.
- **Agentic sau script?** Genuin „agent-to-agent" ca protocol/arhitectură, dar strategia de tranzacționare propriu-zisă (SMA crossover) e o regulă simplă, nu raționament LLM liber — nu e clar din README dacă AlphaBot invocă efectiv un LLM pentru decizie sau doar folosește scaffolding-ul ADK peste o regulă determinată. **[INFERENȚĂ: probabil regulă determinată încapsulată în ADK, nu apel LLM la fiecare decizie]**
- **Date/execuție**: piață **complet sintetică** (preț inițial, volatilitate, trend configurabile) — fără conector la date reale sau broker real. Avertisment explicit: „nu folosi pentru decizii de tranzacționare reale sau cu bani reali."
- **Risk management**: RiskGuard e un tipar arhitectural excelent — un serviciu separat, apelabil independent, care poate doar aproba/respinge.
- **Verdict**: nu adăuga acest cod ca bază funcțională (nu are date/broker reale), dar **adoptă tiparul RiskGuard ca serviciu de veto separat** în arhitectura ta.

### 5.6 HKUDS/AI-Trader
**[FAPT VERIFICAT din README, fetch direct]**
- **Sursă**: github.com/HKUDS/AI-Trader — „100% Fully-Automated Agent-Native Trading"
- **Activitate**: **21,6k stele, 3,3k fork-uri, 388 commit-uri**, changelog cu intrări datate până la 11 iunie 2026 — de departe cel mai activ/popular proiect din întregul set analizat.
- **Ce este de fapt**: **nu e un bot pe care îl rulezi local împotriva propriului broker.** E o **platformă socială găzduită** (ai4trade.ai) unde orice agent AI „se înregistrează" citind un `SKILL.md`, publică semnale/strategii, face „copy trading" de la alți agenți, și are acces la $100k „paper trading" **pe platforma lor**. Codul open-source de pe GitHub e în mare parte **backend-ul platformei** (FastAPI + frontend React), nu creierul de tranzacționare al unui agent individual.
- **Multi-asset/broker**: pretinde acces universal (Stocks, Crypto, Forex, Options, Futures) și compatibilitate cu „Binance, Coinbase, Interactive Brokers și altele" — dar aceasta e prin **sincronizare de semnale/copy trading**, nu execuție directă controlată de tine cu propriul tău motor de risc.
- **Risk management**: nu există în repo un strat de risc configurabil per-utilizator, în sensul cerut de tine (limite proprii, pe capitalul tău) — riscul e gestionat la nivel de platformă/social.
- **Observație despre stele**: README-ul conține insistent apeluri de tip „dați-ne o stea ⭐" repetate de multiple ori — un semnal (nu o dovadă) tipic de proiecte optimizate agresiv pentru vizibilitate virală, exact motivul pentru care cerința ta de a separa popularitatea de calitatea tehnică e justificată aici.
- **Verdict**: **potrivire greșită de categorie** pentru cerința ta explicită de agent local care tranzacționează pe contul tău. Poate fi interesant mai târziu ca loc unde publici/verifici performanța strategiei tale față de comunitate, nu ca fundație tehnică.

### 5.7 TauricResearch/TradingAgents
**[SURSĂ SECUNDARĂ, corroborată din mai multe agregatoare independente + un mirror parțial al README-ului oficial]**
- **Sursă**: github.com/TauricResearch/TradingAgents; lucrare arXiv:2412.20138 (Xiao, Sun, Luo, Wang) + follow-up Trading-R1 (arXiv:2509.11420).
- **Activitate**: ~91,7k stele, ~17,7k fork-uri, licență **Apache-2.0**, ultima versiune raportată v0.3.1 (5 iulie 2026), ~20 contribuitori activi, comunitate pe Discord/WeChat. **Nivel de încredere: mediu-ridicat** — date corroborate din multiple surse independente, dar nu am deschis eu însumi codul sursă complet.
- **Arhitectură**: construit pe **LangGraph**, cu roluri specializate — analiști (fundamental, sentiment, știri, tehnic) → cercetători bull/bear care **dezbat** → un agent „trader" → o echipă de management al riscului → un „Portfolio Manager" care aprobă/respinge final. Log de decizii persistent (Portfolio Manager „învață" din runde anterioare).
- **Agentic sau script?** Cel mai genuin agentic dintre toate cele analizate — dezbatere reală între roluri, nu doar pipeline liniar.
- **Multi-asset/date**: acțiuni (via Alpha Vantage cu fallback yfinance), plus date macro (FRED) și piețe de predicție (Polymarket paper trading). Nu am găsit dovezi de suport nativ pentru forex sau conectori dedicați de crypto exchange.
- **Broker/execuție**: **important** — conform documentației, ordinul aprobat de Portfolio Manager „este trimis la exchange-ul simulat și executat" — adică, implicit, **nu există execuție reală la un broker**; ar trebui construit tu însuți un adaptor de execuție reală.
- **Backtesting/paper trading**: da, cu fidelitate de dată în backtesting și checkpoint/resume; efectiv funcționează ca paper trading intern.
- **Risk management**: există un rol dedicat de management al riscului, dar **decizia de risc e ea însăși generată prin dezbatere LLM**, nu prin reguli mecanice fixe — o diferență importantă față de cerința ta explicită ca LLM-ul să nu poată plasa ordine fără limite dure.
- **Securitate**: suportă multipli furnizori LLM (OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen, GLM, Ollama local) — flexibil, dar crește suprafața de atac legată de chei API; nu am găsit o politică de securitate dedicată.
- **Verdict**: cea mai bună sursă de **tipar arhitectural de raționament**, dar execuția implicită nu e utilizabilă direct pentru bani reali fără o rescriere a stratului de execuție + adăugarea unor limite mecanice (gen FriesTrader) peste decizia „Portfolio Manager".

### 5.8 AI4Finance-Foundation/FinRL și FinRL-X (FinRL-Trading)
**[SURSĂ SECUNDARĂ, corroborată din README oficial (mirror), lucrare arXiv:2603.21330, șabloane de deploy]**
- **Sursă**: github.com/AI4Finance-Foundation/FinRL (originalul) și github.com/AI4Finance-Foundation/FinRL-Trading (succesorul, „FinRL-X").
- **Activitate**: FinRL original ~15,2k stele, fundație activă de 5+ ani, bază academică solidă (NeurIPS 2020, ICAIF 2020); FinRL-X mai nou (~2,9k stele), poziționat explicit ca succesor „AI-native, orientat spre producție".
- **Ce este**: **deep reinforcement learning** pentru trading (PPO, DDPG, A2C, SAC, TD3), nu raționament LLM prin natura sa — FinRL-X adaugă însă suport pentru **semnale de sentiment bazate pe LLM** ca modul opțional, deci e „LLM-ready", nu „LLM-native".
- **Broker/execuție — cel mai puternic punct al proiectului**: integrare **reală și documentată** cu **Alpaca**, atât pentru paper trading cât și pentru live trading, cu conturi multiple și **controale de risc pre-tranzacție** explicite (ordin/portofoliu/strategie) în FinRL-X — singurul din tot setul analizat unde am găsit confirmare independentă de execuție live reală la un broker, nu doar simulare.
- **Backtesting**: FinRL-X folosește motorul profesional `bt`; comparație multi-benchmark, costuri de tranzacție incluse.
- **Verdict**: cea mai bună bază **non-agentică** pentru stratul de execuție/risc/backtesting pentru acțiuni via Alpaca; combină-l cu un strat LLM separat pentru raționament (nu folosi partea DRL ca înlocuitor de raționament LLM — sunt paradigme diferite).

### 5.9 freqtrade
**[SURSĂ SECUNDARĂ, corroborată din README oficial (mirror), ecosyste.ms, recenzie independentă Gainium]**
- **Sursă**: github.com/freqtrade/freqtrade. Licență **GPL-3.0**. Creat 2017.
- **Activitate**: ~46k stele, ~9,7k fork-uri, ultimul push confirmat 29 ianuarie 2026, versiune curentă schemă anuală **2026.3** (martie 2026) cu **release-uri lunare** — printre cele mai bine întreținute proiecte din tot spațiul open-source de trading.
- **Ce este**: bot de trading **crypto** cu suport pentru majoritatea exchange-urilor mari (via ccxt), control prin Telegram/webUI, backtesting + **Hyperopt** (optimizare de strategie), modul ML opțional **FreqAI** (adaptare/re-antrenare pe date noi), mod **dry-run** ca cetățean de rangul întâi.
- **Agentic sau script?** **Nu e agentic/LLM** — e determinist, bazat pe strategii Python definite de utilizator (plus FreqAI pentru ML clasic). Exact genul de „mâini de încredere" peste care ai putea pune un „creier" LLM separat.
- **Risk management**: extrem de matur — stoploss, tabele ROI, dimensionare poziție, „pairlocks"/protecții, toate deterministe.
- **Observabilitate/testare**: CI, coverage, badge de mentenabilitate, documentație oficială extinsă cu note per exchange.
- **Verdict**: cea mai solidă bază de **execuție + risc + backtesting pentru crypto** din tot setul analizat, cu condiția să accepți că nu are (și nu ar trebui să capete) autonomie de „gândire" LLM în interior — LLM-ul stă deasupra, ca generator de semnal, nu în motorul de execuție.

### 5.10 virattt/ai-hedge-fund
**[SURSĂ SECUNDARĂ, corroborată din multiple fork-uri/mirror-uri ale README-ului]**
- **Sursă**: github.com/virattt/ai-hedge-fund — „proof of concept pentru un hedge fund AI... doar în scop educațional."
- **Arhitectură**: 12-14+ agenți-personaj bazați pe stiluri de investitori celebri (Warren Buffett, Charlie Munger, Michael Burry, Cathie Wood, Ben Graham etc.) + agenți analitici (valoare, sentiment, fundamentale, tehnic) + un Risk Manager + un Portfolio Manager care ia decizia finală.
- **Execuție**: declarat explicit și repetat în README: **„sistemul nu face de fapt nicio tranzacție"** / „simulează decizii de tranzacționare, nu tranzacționează efectiv." Zero valoare de execuție reală.
- **Activitate**: număr mare de fork-uri active identificate independent (freshlife001, jasonhejna, alexzhang76, simonator1001, pwrvs) — semn de popularitate reală în comunitate, dar nu am putut confirma direct din sursă primară numărul exact de stele al repo-ului canonic (o sursă secundară menționează ~59k, tratează ca aproximativ, neconfirmat de mine direct). **[SURSĂ SECUNDARĂ, cifră neconfirmată direct]**
- **Verdict**: excelentă sursă de **inspirație pentru design de prompt-uri/persoane de agent** și pentru structura „Risk Manager + Portfolio Manager", zero utilitate pentru execuție.

### 5.11 Ce am găsit pe Hugging Face
**[FAPT VERIFICAT din căutări directe pe huggingface.co]**
Ecosistemul Hugging Face pentru acest domeniu constă aproape exclusiv din **Spaces demo** (aplicații Gradio mici, adesea proiecte de hackathon sau portofolii personale) construite deasupra acelorași framework-uri de pe GitHub (TradingAgents, FinRL), nu framework-uri de sine stătătoare de nivel producție. Exemple identificate: „Demo MultiAgents Trading" (Gradio, demo), „Agentic Financial Document Analyst", „Stochastic RL Trading Research Lab", „AI-trade-bot-demo". Nu am găsit pe Hugging Face niciun proiect cu integrare de broker real, backtesting matur sau management de risc documentat — Hugging Face e util aici pentru modele de sentiment/NLP financiar sau demo-uri rapide, nu ca sursă de bază pentru agentul tău.

Alte proiecte identificate incidental, **neevaluate în profunzime** (menționate pentru completitudine, nivel de încredere scăzut, doar din snippet-uri de căutare): `Open-Finance-Lab/AgenticTrading` („Agentic Trading Lab" — platformă experimentală open-source pentru agenți de trading LLM, cu backtesting/paper trading și loguri de decizie), `endless-sky-team/ai-trading-agent` (bot LLM pentru crypto perpetuale, stack TypeScript/Bun, folosește OpenRouter). Nu le recomand fără verificare suplimentară directă.

---

## 6. Compatibilitate Robinhood — analiză separată

Aceasta e secțiunea cu cele mai mari schimbări față de ce ai putea găsi în surse mai vechi (inclusiv cunoștințele mele antrenate, care se opresc la ianuarie 2026).

### 6.1 API de crypto (existent de mai mult timp)
**[FAPT VERIFICAT, docs.robinhood.com]** Robinhood are un **API oficial de Crypto Trading**, cu date de piață, informații de cont și plasare programatică de ordine crypto, în două versiuni (v1/v2, diferă prin nivelurile de comision). **Disponibil doar pentru clienți din SUA** pentru această entitate specifică (Robinhood Crypto, LLC).

### 6.2 API de acțiuni „clasic" — istoric inexistent public
**[FAPT VERIFICAT, confirmat din Robinhood Help Center]** Până la începutul lui 2026, Robinhood **nu oferea un API public pentru tranzacționare programatică de acțiuni** — accesul era limitat la aplicația proprie; orice „API" folosit pentru acțiuni în comunitate era neoficial (reverse-engineered), cu risc de blocare a contului.

### 6.3 Schimbarea majoră: Robinhood Agentic Trading (lansat 27 mai 2026)
**[FAPT VERIFICAT, robinhood.com/newsroom + TechCrunch + pagina oficială de suport]**
Pe 27 mai 2026, Robinhood a lansat oficial **Agentic Trading** — un server **Model Context Protocol (MCP)** oficial prin care un agent AI extern (Claude, ChatGPT, Cursor, Codex etc.) se poate conecta la un **cont Agentic dedicat** și:
- poate analiza riscul de concentrare/expunere pe sector, poate căuta idei de tranzacționare, poate face rebalansare de portofoliu, poate face backtesting pe o strategie de tip „mean reversion" și o poate implementa;
- lansat inițial **doar cu acțiuni**, în beta;
- extins ulterior (confirmat prin postări oficiale Robinhood pe X, iunie–iulie 2026) la **opțiuni** și apoi la **crypto** — la data acestui research (18 septembrie 2026), pagina oficială robinhood.com/us/en/agentic-trading afirmă acces pentru **„equities, options, and crypto"** prin serverul MCP;
- contul Agentic are un **buget dedicat** setat de tine, notificare pe fiecare tranzacție, tracker de PnL în timp real, și posibilitatea de **deconectare instantanee dintr-un tap**;
- conform Robinhood: „agenții pot face erori, pot interpreta greșit instrucțiuni, pot acționa pe informații incomplete sau învechite și se pot comporta în moduri neașteptate" — avertisment oficial de risc, direct din documentația lor.
- **[SURSĂ SECUNDARĂ]** o relatare independentă (Virtuals, prin runtimewire.com) menționează aproximativ 100.000 de conturi Agentic deschise până la finalul lunii iunie 2026 și confirmă că produsul a ajuns la „toți utilizatorii eligibili" — dar nu clarifică exact ce înseamnă „eligibil" din punct de vedere geografic.

### 6.4 Disponibilitate geografică — atenție, incertitudine reală
**[FAPT VERIFICAT parțial + INFERENȚĂ]** Robinhood operează prin entități legale separate: brokerajul „clasic" american (SUA) și **Robinhood Europe, UAB** (licențiat în Lituania din aprilie 2025), care oferă clienților din **UE — inclusiv România** — crypto și **acțiuni/ETF-uri tokenizate** (nu acțiuni native). Toate sursele consultate despre lansarea Agentic Trading (Robinhood Newsroom, TechCrunch, presa financiară) vorbesc explicit despre „US customers" / brokerajul american. **Nu am găsit nicio confirmare directă că Agentic Trading (serverul MCP oficial) e disponibil și pentru conturile Robinhood Europe (deci pentru un utilizator din România) — tratez asta ca necunoscut, nu ca „da" sau „nu".** Recomand verificare directă în aplicație/cu suportul Robinhood înainte de a construi orice pe această presupunere.

### 6.5 Limitări pentru automatizare
- Contul Agentic cu margine limitată permite tranzacționare cu fonduri nedecontate; contul cash Agentic clasic impune 1 zi lucrătoare de decontare.
- Împrumutul pe marjă („margin borrowing") **nu e încă activat** pentru conturile Agentic.
- Agentul poate tranzacționa crypto, dar **nu poate transfera, stake-ui sau împrumuta** crypto.
- Onboarding-ul contului Agentic se poate face **doar de pe desktop** (nu mobil).

### 6.6 Riscuri juridice/operaționale
- Produsul e explicit descris de Robinhood ca implicând „risc semnificativ, inclusiv pierderea întregii investiții" și ca „putând fi dificil de monitorizat sau oprit în timp real" — formulare direct din documentația lor de risc, nu exagerare mea.
- Răspunderea pentru o eroare a agentului (Robinhood vs. furnizorul de AI vs. tine) nu pare complet clarificată public — semnalat și de presa independentă (runtimewire.com) ca „risc nerezolvat".
- Fără API dedicat de **forex** la Robinhood — pentru forex ai nevoie oricum de un broker separat (ex. OANDA, Interactive Brokers).

### 6.7 Alternative mai potrivite pentru fiecare clasă de active [OPINIE]
- **Acțiuni (SUA)**: **Alpaca** rămâne opțiunea cu cea mai bună documentație pentru tranzacționare algoritmică (paper + live), integrare directă confirmată cu FinRL-X, TradingAgents (parțial) și proiectul fsaavedra0003. Mai matură ca ecosistem decât Robinhood Agentic Trading, care e la câteva luni de la lansare.
- **Forex**: OANDA REST API sau Interactive Brokers — niciunul din proiectele analizate nu are integrare forex nativă; ai nevoie de un adaptor dedicat.
- **Crypto**: exchange susținut de **freqtrade** (Binance, Kraken etc. via ccxt) — infrastructură de risc/execuție mult mai matură decât orice găsit la nivel de „agentic trading".
- **Recomandare generală**: **da**, folosește broker/exchange separat per clasă de active, cel puțin în fazele 0–4 din planul de mai jos. Consolidarea (eventual prin Robinhood Agentic Trading dacă rezultă eligibil pentru contul tău) poate veni ulterior, ca optimizare, nu ca fundație.

---

## 7. Arhitectura propusă pentru agentul local

```
[Surse de date]        [Layer 1: Market Data]         [Layer 2: Validare date]
 Alpaca / ccxt   ───▶   normalizare OHLCV,      ───▶   verificare gap-uri, prețuri
 (broker/exch.)         știri, sentiment                aberante, stale data

                              │
                              ▼
                    [Layer 3: Feature Engineering]
                    indicatori tehnici, features
                    fundamentale/sentiment
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │   [Layer 4: Strategy Engine — DETERMINIST]   │
        │   reguli clasice (freqtrade-style) SAU        │
        │   semnal RL (FinRL-X)                         │
        └─────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │  [Layer 5: LLM Reasoning — inspirat           │
        │   TradingAgents]                              │
        │  analiști → dezbatere bull/bear → propunere   │
        │  de tranzacție (NU decizie finală)            │
        └─────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │ [Layer 6: Portfolio & Risk Manager —          │
        │  DETERMINIST, gen risk_rules.json din          │
        │  FriesTrader + RiskGuard din kweinmeister]    │
        │  poate DOAR aproba/respinge/reduce mărimea    │
        └─────────────────────────────────────────────┘
                              │
                       [aprobat?]──NO──▶ [Audit DB: motiv respingere]
                              │YES
                              ▼
        ┌─────────────────────────────────────────────┐
        │ [Layer 7: Broker/Exchange Adapter]            │
        │ Alpaca / ccxt / OANDA / (eventual Robinhood   │
        │ MCP, dacă eligibil)                           │
        └─────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │ [Layer 8: Order Execution]                    │
        │ validare finală: preț/lichiditate,            │
        │ anti-duplicare, dry-run vs. live gate          │
        └─────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
   [Backtesting Engine]              [Paper-Trading Engine]
   (bt / freqtrade backtest)         (dry-run, date live, fără bani)
              │                               │
              └───────────────┬───────────────┘
                              ▼
              [Layer 9: Monitoring & Alerting]
              Telegram/webUI (stil freqtrade), kill switch
                              │
                              ▼
              [Layer 10: Audit Database]
              JSONL/SQL — fiecare decizie, aprobată sau nu,
              cu teza LLM + motivul determinist
                              │
                              ▼
              [Layer 11: Human Approval Interface]
              obligatoriu în Fazele 0-4, opțional ulterior
```

### 7.1 Ce decide codul determinist vs. ce poate delega LLM-ului [OPINIE]

**Cod determinist — NEGOCIABIL NICIODATĂ de LLM:**
- Capital maxim per tranzacție, expunere maximă per activ/per clasă de active, pierdere maximă zilnică, drawdown maxim, număr maxim de ordine/zi.
- Circuit breaker (oprire automată la X pierderi consecutive sau la depășirea drawdown-ului).
- Validarea ordinului (preț rezonabil față de piață, lichiditate suficientă), prevenirea ordinelor duplicate.
- Kill switch (oprire imediată, manuală sau automată).
- Trecerea din dry-run în live — **întotdeauna manuală**, niciodată automatizată de agent (exact ca în FriesTrader).

**Poate fi delegat LLM-ului:**
- Interpretarea știrilor/sentimentului, generarea unei teze de investiție.
- Selecția candidaților dintr-un univers predefinit (nu definirea universului însuși).
- Propunerea direcției (long/avoid/exit) și a convingerii (low/medium/high) — niciodată mărimea poziției în bani.
- Explicarea/justificarea deciziei pentru audit ulterior.

### 7.2 Controale tehnice concrete de risc [OPINIE, sintetizat din FriesTrader + freqtrade + FinRL-X]
- **Capital maxim per tranzacție**: procent fix din capital (ex. 2-5% în fazele incipiente cu 500 EUR).
- **Expunere maximă**: per simbol și per clasă de active (nu 100% crypto simultan, de exemplu).
- **Pierdere maximă zilnică**: oprire automată a tranzacționării pentru ziua respectivă la atingerea pragului.
- **Drawdown maxim**: oprire completă (kill switch) dacă portofoliul scade sub un prag de la vârf.
- **Număr maxim de ordine/zi**: previne „overtrading" indus de un LLM prea încrezător.
- **Circuit breaker**: N pierderi consecutive → pauză obligatorie + notificare umană.
- **Validare ordin**: preț curent vs. preț de referință (deviație maximă acceptată), verificare spread/lichiditate minimă.
- **Anti-duplicare**: hash/ID unic per intenție de tranzacție, cu expirare.
- **Kill switch**: comandă unică (CLI/Telegram) care oprește toate operațiunile și anulează ordinele deschise.
- **Aprobare manuală**: obligatorie pentru fiecare tranzacție live în Fazele 0-4 (vezi planul etapizat); trecerea la aprobare automată doar după criterii cuantificate îndeplinite.

---

## 8. Despre obiectivul „multiplicare a capitalului" cu 500 EUR [OPINIE]

Ai cerut o analiză critică a acestei idei — iat-o, direct:

- **„Multiplicarea banilor" nu e o specificație tehnică** pentru că nu spune: în cât timp, cu ce risc acceptat, măsurat cum, comparat cu ce. Fără aceste patru elemente, nu poți construi teste de acceptare, deci nu poți ști niciodată dacă sistemul „funcționează".
- **Obiective măsurabile mai bune**: Sharpe ratio > un prag definit pe o fereastră de minim 3-6 luni de paper trading; drawdown maxim sub un plafon fix (ex. 10-15% din capital); rată de câștig (win rate) și expectancy per tranzacție documentate; comparație directă cu un benchmark pasiv (ex. un ETF S&P 500 sau un coș simplu de buy-and-hold), nu cu „a face bani" în absolut.
- **Limitarea riscului de pierdere**: capital alocat exclusiv pentru acest experiment (cei 500 EUR trebuie tratați ca bani pe care ești pregătit să-i pierzi integral — asta e literalmente riscul cu tranzacționare algoritmică experimentală), plus toate controalele din secțiunea 7.2.
- **De ce backtesting + paper trading înainte de live**: pentru că orice strategie, inclusiv una generată de LLM, poate părea bună retrospectiv din întâmplare (overfitting) sau din cauza unor bias-uri de „look-ahead" (LLM-ul „știe" deja ce s-a întâmplat istoric, deci raționamentul pe știri vechi nu poate fi validat corect — exact avertismentul din FriesTrader).
- **Criterii înainte de live**: minimum N cicluri de dry-run fără eroare, performanță în paper trading care nu contrazice grav backtesting-ul, toate controalele de risc testate manual (inclusiv simularea unui kill switch), aprobare umană explicită.
- **Împărțirea capitalului**: în fazele incipiente, majoritatea celor 500 EUR ar trebui să rămână **cash neexpus**, cu doar o fracțiune mică (ex. 10-20%) alocată primelor tranzacții live reale, crescută treptat doar dacă criteriile de trecere de fază sunt îndeplinite.
- **Metrici de urmărit dincolo de profit**: Sharpe ratio, max drawdown, win rate, expectancy per tranzacție, turnover (frecvența tranzacționării — relevantă pentru costuri), slippage realizat vs. estimat, costuri totale (comisioane + spread).

Nu ofer nicio promisiune de profit și nu prezint acest sistem ca fiind sigur sau capabil să funcționeze fără supraveghere.

---

## 9. Plan etapizat (Faza 0 – Faza 6)

### Faza 0 — Cercetare și selectarea proiectului
- **Obiectiv**: decizie finală asupra arhitecturii de bază (acest document e input, nu decizia finală).
- **Livrabile**: document de decizie arhitecturală, listă de dependențe alese (freqtrade și/sau FinRL-X, broker(i) aleși).
- **Teste**: niciunul de cod — validare că toate componentele alese au licențe compatibile cu scopul tău.
- **Criterii de trecere**: decizie scrisă, cu argumentare, asupra fiecărei clase de active (ce broker/exchange pentru fiecare).
- **Riscuri**: subestimarea efortului de integrare între componente eterogene (freqtrade + FinRL-X + strat LLM propriu).
- **Condiții de oprire**: dacă niciun broker fezabil nu e găsit pentru o clasă de active dorită (ex. Robinhood Agentic Trading confirmat indisponibil din România și fără alternativă acceptabilă), reduci scopul inițial la clasele de active fezabile.

### Faza 1 — Instalare și audit de securitate
- **Obiectiv**: mediu local funcțional, fără chei API reale conectate încă la conturi live.
- **Livrabile**: instalare freqtrade/FinRL-X în mod dry-run, gestionare de secrete (variabile de mediu, niciodată în cod/logs), `.gitignore` verificat.
- **Teste**: pornire completă a stack-ului fără erori, folosind chei de test/paper.
- **Criterii de trecere**: niciun secret în istoricul git, toate dependențele instalate cu versiuni fixate.
- **Riscuri**: chei API scurse accidental în commit-uri sau loguri.
- **Condiții de oprire**: orice scurgere de secret detectată → rotire imediată a cheilor înainte de a continua.

### Faza 2 — Reproducerea rezultatelor existente
- **Obiectiv**: verificare că freqtrade/FinRL-X/TradingAgents funcționează exact cum descrie documentația, pe exemplele lor proprii.
- **Livrabile**: rulare cu succes a tutorialelor oficiale (ex. FinRL_PaperTrading_Demo, exemplul de strategie freqtrade).
- **Teste**: output-urile obținute se potrivesc cu ce descrie documentația (ordine de mărime, nu cifre exacte).
- **Criterii de trecere**: reproducere reușită fără modificări majore de cod.
- **Riscuri**: dependențe învechite/breaking changes între versiunea documentată și cea instalată.
- **Condiții de oprire**: dacă exemplele oficiale nu pot fi reproduse deloc, reconsideră alegerea de bază (Faza 0).

### Faza 3 — Backtesting realist cu comisioane și slippage
- **Obiectiv**: strategie proprie (inițial simplă, determinist, fără LLM) testată istoric cu costuri reale incluse.
- **Livrabile**: rapoarte de backtest cu Sharpe, drawdown, win rate, costuri incluse explicit.
- **Teste**: comparație cu benchmark pasiv pe aceeași perioadă.
- **Criterii de trecere**: performanța ajustată la risc nu e semnificativ inferioară benchmark-ului (nu neapărat superioară — doar informată).
- **Riscuri**: overfitting pe perioada de test.
- **Condiții de oprire**: dacă strategia de bază are drawdown-uri incompatibile cu toleranța ta la risc, revizuiește strategia înainte de a adăuga stratul LLM.

### Faza 4 — Paper trading
- **Obiectiv**: adăugarea stratului LLM de raționament (propuneri), rulat integral în dry-run/paper, pe date live.
- **Livrabile**: log JSONL complet al fiecărei decizii (propuse, aprobate, respinse), inclusiv cele respinse de stratul determinist.
- **Teste**: citirea manuală, sistematică, a log-ului — în special a tranzacțiilor respinse și a declanșărilor de stop-loss (nu doar a celor „câștigătoare").
- **Criterii de trecere**: minimum N cicluri fără eroare tehnică, comportament de risc consistent cu regulile setate, nicio depășire a limitelor mecanice.
- **Riscuri**: LLM-ul generează propuneri incoerente sau încearcă (prin prompt) să sugereze creșterea limitelor de risc — motiv suplimentar ca aceste limite să fie complet în afara controlului LLM-ului.
- **Condiții de oprire**: orice încercare a stratului LLM de a ocoli limitele mecanice → oprire și revizuire de design înainte de a continua.

### Faza 5 — Live trading cu capital minim și aprobare manuală
- **Obiectiv**: primele tranzacții reale, cu fracțiune mică din cei 500 EUR, fiecare aprobată manual de tine.
- **Livrabile**: jurnal de tranzacții reale, comparație explicită paper vs. live (slippage real observat).
- **Teste**: fiecare tranzacție verificată manual înainte de execuție în această fază.
- **Criterii de trecere**: comportament live consistent cu paper trading pe o perioadă suficientă (nu o singură tranzacție norocoasă).
- **Riscuri**: diferență semnificativă între paper și live (slippage, latență, lichiditate reală).
- **Condiții de oprire**: divergență mare paper vs. live → revenire la Faza 4 pentru recalibrare.

### Faza 6 — Automatizare graduală
- **Obiectiv**: reducerea aprobării manuale, DOAR dacă rezultatele anterioare justifică.
- **Livrabile**: criterii explicite, scrise înainte, pentru ce înseamnă „suficient de bine testat pentru mai puțină supraveghere".
- **Teste**: monitorizare continuă a acelorași metrici (Sharpe, drawdown, expectancy) pentru a detecta degradare.
- **Criterii de trecere**: N.A. (fază finală, dar reversibilă oricând).
- **Riscuri**: automatizarea completă elimină ultima plasă de siguranță umană.
- **Condiții de oprire**: orice degradare a metricilor sub pragurile Fazei 3 → revenire imediată la aprobare manuală (Faza 5).

---

## 10. Plan de implementare pe 30/60/90 de zile [OPINIE, orientativ]

- **Zilele 1-30 (≈ Faze 0-2)**: decizie arhitecturală finală; instalare locală freqtrade (crypto) și/sau FinRL-X + Alpaca paper (acțiuni); verificare eligibilitate Robinhood Agentic Trading din România (contactează suportul Robinhood direct — nu presupune); reproducerea tutorialelor oficiale.
- **Zilele 31-60 (≈ Faza 3 + început Faza 4)**: backtesting realist cu comisioane/slippage pe strategie determinist simplă; construirea stratului de reguli mecanice (`risk_rules.json`-style); prototip al stratului LLM de raționament (inspirat TradingAgents), fără conectare încă la execuție.
- **Zilele 61-90 (≈ Faza 4 completă + început Faza 5)**: paper trading complet, cu LLM + validare determinist; audit manual sistematic al log-urilor; dacă criteriile sunt îndeplinite, primele tranzacții live cu capital minim și aprobare manuală strictă.

Notă: acest calendar e orientativ, nu o promisiune — criteriile de trecere din secțiunea 9 au prioritate față de dată calendaristică.

---

## 11. Lista de riscuri critice

1. **Suprascrierea limitelor de risc de către LLM** — dacă arhitectura nu separă strict „propunere" de „aprobare", un LLM „convingător" poate justifica depășirea limitelor.
2. **Backtesting înșelător pe raționament bazat pe știri** — LLM-ul poate „ști" deja rezultatul istoric, făcând backtesting-ul artificial de bun (avertisment explicit din FriesTrader).
3. **Divergență paper vs. live** — slippage, latență și lichiditate reală diferă de simulare.
4. **Chei API compromise** — expunerea cheilor de broker/exchange ar permite pierderi directe de capital.
5. **Confuzie de categorie de proiect** — adoptarea unui produs de tip „platformă" (ex. HKUDS/AI-Trader) crezând că e un „bot local" ar duce la o arhitectură complet greșită pentru scopul tău.
6. **Eligibilitate geografică Robinhood necunoscută** — construirea unei dependențe pe Robinhood Agentic Trading fără confirmare că funcționează din România.
7. **Overtrading indus de LLM** — fără o limită dură de număr de ordine/zi, un agent „prea entuziast" poate genera costuri de tranzacționare care erodează orice câștig.
8. **Wash-sale și implicații fiscale** (relevant mai ales dacă tranzacționezi și printr-un cont neagentic în paralel) — FriesTrader tratează explicit acest risc pentru conturi din SUA; verifică echivalentul fiscal românesc/UE dacă e cazul.
9. **Dependență de furnizori LLM externi** — indisponibilitate API sau cost neașteptat de token-uri poate opri agentul la momente critice de piață.
10. **Lipsa unui kill switch testat** — un sistem „automat" fără o metodă dovedită, testată manual, de oprire imediată e un risc operațional major.

---

## 12. Întrebări la care trebuie să răspunzi înainte de implementare

1. Cu ce clasă de active pornești efectiv primul: acțiuni, forex sau crypto? (Determină ce broker/exchange integrezi primul.)
2. Ești eligibil pentru Robinhood Agentic Trading din România, sau construiești oricum pe Alpaca/alt broker de la început?
3. Care e pragul tău personal de drawdown maxim acceptabil, în procente din cei 500 EUR, înainte de oprire automată?
4. Cât timp (zile/săptămâni) ești dispus să aloci exclusiv pentru dry-run/paper trading înainte de a considera trecerea la live?
5. Ce furnizor(i) LLM ești dispus să folosești (cost, latență, disponibilitate locală/Ollama pentru confidențialitate)?
6. Vrei un singur agent unificat pentru toate clasele de active, sau agenți separați per clasă (mai simplu de securizat și de limitat, dar mai mult de întreținut)?
7. Cine aprobă manual tranzacțiile în Fazele 0-4 — doar tu, sau ai nevoie de un flux de aprobare mai formal (relevant dacă implici Neorimia/clienți)?
8. Ce nivel de auditabilitate ai nevoie (doar log tehnic, sau și rapoarte explicabile pentru un context de conformitate/fiscalitate)?

---

## 13. Surse verificate

- github.com/fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis (fetch direct)
- github.com/YizhiSong/FriesTrader (fetch direct)
- github.com/topics/quant-trading-bot (fetch direct)
- github.com/Krexibd/quant-trading (fetch direct) — fork al github.com/je-suis-tm/quant-trading
- github.com/kweinmeister/agentic-trading (fetch direct)
- github.com/HKUDS/AI-Trader (fetch direct)
- github.com/TauricResearch/TradingAgents — corroborat via dev.co, x-cmd.com, gittrend.io, oosmetrics.com, beamforai.com, arXiv:2412.20138, arXiv:2509.11420
- github.com/AI4Finance-Foundation/FinRL și github.com/AI4Finance-Foundation/FinRL-Trading — corroborat via sourcepulse.org, gitee.com mirrors, arXiv:2603.21330, Railway template
- github.com/freqtrade/freqtrade — corroborat via ecosyste.ms, gainium.io (recenzie independentă), mirror-uri README
- github.com/virattt/ai-hedge-fund — corroborat via multiple fork-uri (freshlife001, jasonhejna, alexzhang76, simonator1001, pwrvs)
- huggingface.co (căutări directe pentru Spaces relevante)
- docs.robinhood.com (documentație oficială API crypto)
- robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/ (anunț oficial, 27 mai 2026)
- robinhood.com/us/en/agentic-trading/ și robinhood.com/us/en/support/articles/ (pagini oficiale curente)
- techcrunch.com — „Robinhood now lets your AI agents trade stocks" (27 mai 2026)
- investingintheweb.com — disponibilitate geografică Robinhood în UE (actualizat 2026, verificat pentru România)
- pinggy.io — „Best AI Trading Agents in 2026" (context comparativ, cifre de stele tratate ca aproximative/neconfirmate direct)

---

## 14. Concluzie

**Aș porni de la o bază compusă, nu de la un singur proiect** — pentru că research-ul arată clar că, în acest moment (septembrie 2026), niciun proiect open-source nu combină simultan raționament LLM matur, execuție reală multi-broker și management de risc determinist dovedit. Concret:

- **Pentru fundația de execuție/risc/backtesting**: **freqtrade** dacă prima clasă de active e crypto (cel mai matur motor open-source din tot setul analizat — 9/10 la backtesting, paper trading și risc), sau **FinRL-X (AI4Finance-Foundation/FinRL-Trading)** dacă pornești cu acțiuni via Alpaca (singurul cu execuție live reală documentată și controale de risc pre-tranzacție).
- **Pentru raționamentul LLM**: adoptă tiparul arhitectural de la **TauricResearch/TradingAgents** (analiști → dezbatere → propunere), rescriind execuția să meargă spre motorul determinist de mai sus, nu spre exchange-ul lor simulat.
- **Pentru siguranță, obligatoriu**: copiază literal filozofia **FriesTrader** — reguli mecanice pe care LLM-ul nu le poate atinge, separare teză/execuție, minim de cicluri dry-run, audit trail complet — plus tiparul de agent de risc separat din **kweinmeister/agentic-trading**.
- **Evită ca bază** HKUDS/AI-Trader (platformă, nu bot local, în ciuda popularității), Krexibd/quant-trading (zero agentic), și tratează Robinhood Agentic Trading ca pe o **opțiune promițătoare dar foarte tânără** (lansată acum 4 luni) și **cu eligibilitate geografică neconfirmată pentru România** — nu construi întreaga arhitectură pe presupunerea că funcționează pentru tine, verifică direct întâi.
