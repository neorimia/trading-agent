Implementează integrarea **Alpaca Paper Trading** în proiectul local:

`/Users/gabrielcruceanu/WebstormProjects/trading-agent`

Obiectivul este ca agentul existent să poată trimite ordine simulate către Alpaca și să urmărească execuțiile, folosind controalele actuale de risc, aprobare și audit.

**Context și arhitectură**

În inspecția anterioară au fost identificate:

- NautilusTrader `1.231.0`, folosit pentru backtesting. Instalarea locală inspectată nu includea adaptor Alpaca.
- Bucla paper folosește propriul `OrderGateway` și `SimulatedBroker`.
- `BrokerClient` din `src/execution/broker.py` definește `submit`, `cancel_all` și `snapshot`.
- `scripts/paper_trading/run_paper_session.py` construiește explicit `SimulatedBroker`.
- `src/engine/paper_config.py` acceptă doar `venue: KRAKEN` și impune `dry_run: true`.
- Configurația existentă este ETHUSD, bare de o oră, EMA 10/20.
- Există verificări de risc, aprobări, kill switch, prevenirea duplicatelor, reconciliere și persistență.

Verifică starea actuală a codului înainte de implementare: proiectul poate fi modificat între timp. Citește instrucțiunile locale și păstrează modificările existente ale utilizatorului.

**Decizia de implementare**

Construiește `AlpacaPaperBroker` pentru interfața de broker a aplicației:

Strategie/propunere → risc → aprobare → OrderGateway → AlpacaPaperBroker → Alpaca Paper → actualizare ordine și portofoliu.

Păstrează NautilusTrader pentru backtesting. Nu migra execuția la un adaptor Nautilus în această etapă.

LLM-ul continuă să producă propuneri; nu primește acces direct la chei sau autoritate de a ocoli controalele.

**1. Configurație și conectare**

- Adaugă alegerea explicită între simulatorul local și Alpaca Paper, păstrând comportamentul existent ca implicit.
- Separă clar simularea locală de simularea la broker. Nu reutiliza ambiguu `dry_run`.
- Acceptă exclusiv endpointul de tranzacționare paper. Configurațiile live trebuie respinse.
- Citește cheile din variabile de mediu și documentează-le într-un fișier exemplu.
- Nu include chei în cod, loguri, mesaje de eroare, teste sau rezultate.
- Folosește documentația oficială curentă pentru alegerea API-ului/SDK-ului și compatibilitatea dependențelor.

**2. Broker și ciclul ordinelor**

Implementează trimiterea ordinelor, citirea contului, pozițiilor și ordinelor, precum și anularea ordinelor administrate de agent.

Inspectează limitele interfețelor actuale și extinde-le unde este necesar:

- Trimiterea acceptată de broker nu înseamnă execuție.
- Urmărește execuții parțiale și complete, respingeri, anulări și expirări.
- Procesează actualizările Alpaca `trade_updates`, cu recuperare prin API după reconectare.
- Nu contabiliza de două ori execuțiile repetate sau cantitățile cumulative.
- Persistă identificatorii locali și cei ai brokerului.
- După timeout, caută ordinul folosind `client_order_id` înainte de orice retransmitere.
- Nu genera automat un identificator nou pentru aceeași intenție de tranzacționare.
- Previne procesarea simultană a aceleiași intenții de către două instanțe.
- La anulare, așteaptă confirmarea și tratează posibilitatea unei execuții între timp.

Pentru prima versiune sunt suficiente ordine market cu cantitate explicită. Respinge explicit tipurile neimplementate.

**3. Portofoliu, risc și recuperare**

- Actualizează pozițiile, numerarul și rezultatele din execuții confirmate.
- Verifică numerarul disponibil și ordinele în așteptare înainte de trimitere.
- Nu permite levier, vânzare în lipsă sau cumpărări peste limitele configurate.
- Reconciliază contul la pornire, după reconectare și periodic.
- La diferențe neexplicate sau stare incertă, blochează ordinele noi și înregistrează motivul.
- Definește comportamentul kill switch-ului: oprirea ordinelor noi și anularea celor proprii. Nu adăuga lichidarea automată a pozițiilor.
- Păstrează aprobările și mecanismele de persistență existente.
- Detectează pozițiile sau ordinele externe fără a le prelua ori anula automat.

**4. Acțiuni și date de piață**

Creează o configurație separată pentru AAPL, cont paper, maximum o acțiune deținută.

Elimină din acest flux presupunerile fixe despre crypto/Kraken: clasa activului, comisioanele, spreadul, precizia cantității și programul pieței.

Folosește calendarul bursier și fusul `America/New_York`. Calculează semnalele numai din bare zilnice încheiate. Documentează sursa datelor, drepturile necesare și tratarea spliturilor/dividendelor. La date lipsă sau învechite, nu tranzacționa.

**5. Strategie demonstrativă**

Adaugă separat SMA 20/50, fără a modifica implicit strategia EMA existentă:

- Cumpărare: SMA20 anterioară ≤ SMA50 anterioară, iar SMA20 curentă > SMA50 curentă.
- Vânzare: intersecția inversă, numai dacă există poziție.
- Fără intersecție: nicio acțiune.
- La prima pornire, nu cumpăra doar pentru că SMA20 este deja peste SMA50.
- Execută după semnal, în următoarea ședință eligibilă.
- Previne repetarea ordinului pentru același semnal.
- Definește explicit comportamentul pentru semnale ratate în timpul opririi.

Păstrează aceeași definiție a semnalelor în testele istorice și în paper. Dacă backtesterul necesită adaptări pentru acțiuni, implementează-le sau raportează clar limita.

**6. Testare și criterii de acceptare**

Testează cu răspunsuri controlate: ordin acceptat și executat ulterior, execuții parțiale, evenimente duplicate, respingere, anulare, timeout după acceptare, restart, reconectare, numerar insuficient, piață închisă, date învechite și kill switch.

Integrarea este acceptată când:

- Simulatorul existent continuă să funcționeze.
- Endpointurile live sunt respinse.
- Același semnal nu produce ordine duplicate.
- Pozițiile și numerarul reflectă execuțiile confirmate.
- Restartul recuperează starea fără retransmiteri nejustificate.
- Configurația și logurile nu expun secrete.
- Verificările relevante ale proiectului trec.

Nu cere chei pentru dezvoltare sau teste automate. Nu porni automatizări persistente și nu trimite ordine către Alpaca în această sarcină. Pregătește separat o verificare manuală paper, activată explicit de operator.

**Livrabile**

Livrează codul, configurația exemplu, testele și un ghid pentru configurare, pornire, oprire, reconciliere și revenire la simulator.

În raportul final precizează ce ai schimbat, ce ai verificat efectiv, ce necesită cont Alpaca și ce limite rămân. Nu prezenta teste simulate drept validare cu brokerul și nu afirma profitabilitatea strategiei.

Începe prin inspectarea codului și un plan scurt, apoi continuă implementarea. Cere clarificări numai pentru blocaje reale.