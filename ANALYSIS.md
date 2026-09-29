# Football Forecast Lab – Rückblickende WM-Analyse

## 1. Einleitung & Zielsetzung
Dieses Projekt wurde als quantitatives Vorhersage- und Analyse-Tool für das **SRF Tippspiel** zur Fußball-Weltmeisterschaft 2026 entwickelt. Das primäre Ziel war nicht nur die Vorhersage des wahrscheinlichsten Ergebnisses, sondern die systematische Maximierung der *Expected Points (xP)* anhand des spezifischen Regelwerks des Tippspiels (10 Punkte für das exakte Resultat, 8 Punkte für die korrekte Tordifferenz, 5-6 Punkte für die Tendenz). 

Zusätzlich diente das Dashboard als "Build-a-Bot"-Sandbox, um verschiedene Tipp-Strategien (Markt-Quoten vs. Elo-Rating) zu vergleichen und systematische Fehleinschätzungen des Marktes aufzudecken ("Model Edge").

---

## 2. Methodik & Mathematisches Modell

Die Architektur des Modells kombinierte etablierte stochastische Verfahren mit echten Marktdaten:

*   **Odds-to-xG Extraction (L-BFGS-B):** Mithilfe des `scipy.optimize.minimize`-Solvers wurden die aggregierten Konsens-Quoten der Buchmacher (bereinigt um die Buchmachermarge) in *Expected Goals (xG)* für Heim- und Auswärtsteam übersetzt.
*   **Bivariate Poisson & Dixon-Coles:** Die berechneten xG-Werte wurden genutzt, um eine Wahrscheinlichkeitsmatrix ($10 \times 10$) aller möglichen Ergebnisse aufzubauen. Dabei kam die **Dixon-Coles-Korrektur ($\rho = -0.15$)** zum Einsatz, um die bei unabhängigen Poisson-Verteilungen typische Unterschätzung von niedrigen Ergebnissen (0:0, 1:0, 0:1, 1:1) auszugleichen.
*   **Elo-Integration (70/30 Blend):** Ein eigens berechnetes, dynamisches Elo-Rating für alle 48 Nationen (inklusive Heimvorteil für USA/CAN/MEX) wurde zu 30% mit den Buchmacherquoten gemischt, um Formschwankungen und systematische Fehlbewertungen im Wettmarkt auszugleichen.

---

## 3. Architektur & Tech-Stack

Das Projekt wurde als moderne, entkoppelte Full-Stack-Applikation umgesetzt:
*   **Backend (Python/FastAPI):** Sorgte für die mathematischen Berechnungen, das Caching (Dynamic TTL zur Schonung des API-Quotas) und die Integration externer Datenquellen (ESPN für Live-Ergebnisse, The Odds API für Buchmacher-Quoten).
*   **Datenhaltung (MongoDB):** Speicherung historischer Ergebnisse, dynamischer Elo-Ratings und der Performance-Metriken der verschiedenen Bot-Strategien.
*   **Frontend (React 19 / Vite / Tailwind):** Ein responsives, im Glassmorphism-Design gehaltenes Dashboard, welches komplexe Datenstrukturen (Wahrscheinlichkeits-Matrizen, Monte-Carlo-Simulationen) für den Endnutzer visuell aufbereitet hat.

---

## 4. Evaluation: Gesamtranking aller Strategien

Nach Abschluss aller **104 Spiele** wurden sämtliche Strategien verglichen – vom manuellen Tipp über den xP-Algorithmus bis hin zu den House-Bots und dem theoretisch besten "Build-a-Bot", ermittelt durch eine **erschöpfende Suche über 859'551 Parameterkombinationen**.

### 4.1 Gesamtranking (104 Spiele, ohne Bonusfragen)

| Rang | Strategie | Punkte | Pkt/Spiel | Beschreibung |
|------|-----------|--------|-----------|--------------|
| 🥇 | **Best Build-a-Bot** | **751** | **7.22** | mw=0.2, risk=1.0, draw=0.5, underdog=1.2 |
| 🥈 | xP-Optimiser (Algo) | 694 | 6.67 | Standard-Algorithmus (mw=0.7, risk=0) |
| 🥉 | Gambler | 693 | 6.66 | Zufälliger Tipp aus Top-10 xP-Tipps |
| 4 | Broker | 665 | 6.39 | Reiner Buchmacher-Konsens |
| 5 | Professor | 652 | 6.27 | 100% Elo-basiert |
| 6 | User (manuelle Tipps) | 649 | 6.24 | Handgetippte Ergebnisse |
| 7 | Rebel | 339 | 3.26 | Konträr zum Markt |
| 8 | X-Sniper | 315 | 3.03 | Nur Unentschieden |

### 4.2 Analyse: Warum war der Build-a-Bot so stark?

Der "Build-a-Bot" mit **751 Punkten** hätte jeden House-Bot und den Algorithmus geschlagen. Die Gewinner-Parameter verraten, was bei dieser WM entscheidend war:

- **80% Elo, 20% Markt** (`market_weight=0.2`): Die Buchmacher lagen bei diesem Turnier systematisch falsch – grosse Namen wie Portugal oder Brasilien wurden überschätzt, während Elo die wahre Stärke besser abbildete.
- **Maximales Risiko** (`risk=1.0`): Aggressive Exakt-Tipps (z.B. 3:1 statt 1:0) statt sicherer Tendenzen. Bei einem Regelwerk, das exakte Ergebnisse mit 10 Punkten belohnt, zahlt sich Risikobereitschaft überproportional aus.
- **Leichter Draw-Bias** (`draw_bias=0.5`): Das Turnier hatte mehr Unentschieden als reine Modelle erwarteten.
- **Moderater Underdog-Bias** (`underdog_bias=1.2`): Aussenseiter-Siege wurden leicht bevorzugt – und tatsächlich gab es bei dieser WM überdurchschnittlich viele Überraschungen.

> [!NOTE]
> Der Best Build-a-Bot ist ein **retrospektives Optimum** – er wurde nach dem Turnier durch Brute-Force über alle Parameterkombinationen ermittelt. Im Echtzeit-Betrieb war der xP-Optimiser mit 694 Punkten die bestmögliche Strategie ohne Rückblick-Vorteil.

### 4.3 Vergleich mit dem SRF-Tippspiel Leaderboard

Ein direkter Vergleich mit dem [offiziellen SRF-Leaderboard](https://wmtippspiel.srf.ch/ranking/players) ist stark verzerrt: Das SRF-Tippspiel vergab bis zu **~130 Bonus-Punkte** für Zusatzfragen vor Turnierbeginn (Weltmeister, Torschützenkönig, etc.), die der Algorithmus nicht beantwortete.

**Bereinigtes Ranking (Top-Spieler vs. Algorithmus):**

| Rang | Spieler | Punkte |
|------|---------|--------|
| 1 | Sam Haab | 822 |
| 2 | Monika W | 799 |
| 3 | Dominik Stöckli | 798 |
| ... | ... | ... |
| – | **xP-Optimiser** | **694** |

**Fazit:** Selbst mit 0 Bonuspunkten landete der Algorithmus auf **Platz ~74'863 von ~500'000 Teilnehmern** – das entspricht den **Top 15%** weltweit. Der retrospektiv beste Build-a-Bot (751 Punkte) hätte sogar in die **Top 5%** gereicht.

### 4.4 Deep Dive: Woher kommen die 57 Punkte Unterschied?

Der Best Build-a-Bot (751) schlug den xP-Optimiser (694) um exakt **57 Punkte**. Die Match-by-Match-Analyse zeigt, dass der Unterschied fast ausschliesslich aus der **KO-Phase** stammt:

| Phase | Spiele | Algo | Bot | Differenz | Algo/Spiel | Bot/Spiel |
|-------|--------|------|-----|-----------|------------|-----------|
| Gruppenphase | 72 | 346 | 339 | **−7** | 4.81 | 4.71 |
| KO-Phase | 32 | 348 | 412 | **+64** | 10.88 | 12.88 |
| **Total** | **104** | **694** | **751** | **+57** | | |

In der Gruppenphase war der Algo sogar 7 Punkte besser! Doch in der KO-Phase, wo **jeder Punkt doppelt zählt**, explodierte der Vorteil des Build-a-Bot auf +64. Die Gründe:

**1. Draw-Bias × Doppelpunkte = 20 statt 2**
Der `draw_bias=0.5` liess den Bot häufiger `1:1` tippen. Wenn das dann in der KO-Phase eintrat, gab es satte **20 Punkte** (10 × 2) statt der 2 Punkte, die der Algo für einen falschen Nicht-Unentschieden-Tipp kassierte. Allein die Spiele Australien–Ägypten (1:1) und Schweiz–Kolumbien (0:0) brachten dem Bot **+32 Punkte Vorsprung**.

**2. Risiko zahlt sich in der KO-Phase doppelt aus**
`risk=1.0` sorgte dafür, dass der Bot häufiger exakte Ergebnisse traf (18 vs. 15 Exakt-Treffer). In der KO-Phase ist ein Exakt-Treffer **20 Punkte** wert. England–Argentinien (1:2 exakt) allein brachte dem Bot +18 Punkte Vorsprung.

**3. Der Algo war konservativer – und das kostete**
In 56 von 104 Spielen tippten beide identisch. In den 48 Spielen mit unterschiedlichem Tipp gewann der Bot in 26 Spielen (+171 Pkt), der Algo in 22 (+114 Pkt). Der Bot ging also öfter das Risiko ein, und die KO-Doppelpunkte verstärkten seine Gewinne überproportional.

> [!TIP]
> **Kern-Erkenntnis:** Der xP-Optimiser war in der Gruppenphase die bessere Strategie. Für ein Tippspiel mit Doppelpunkten in der KO-Phase lohnt es sich jedoch, ab dem Achtelfinale auf aggressivere Parameter umzuschalten – mehr Risiko, mehr Draw-Bias.

---

## 5. Learnings & Ausblick

> [!TIP]
> **Erkenntnisse aus dem Betrieb**
> *   **Cold-Starts bei Render:** Das Hosting auf dem Render Free-Tier führte zu spürbaren Verzögerungen beim ersten Aufruf. Ein Ping-Endpunkt linderte das Problem.
> *   **Expected Points vs. Wahrscheinlichkeit:** Die Optimierung auf xP nach SRF-Regeln führte oftmals zu anderen Tipps (z.B. eher "2:1" statt "1:0"), als es die reine Ergebniswahrscheinlichkeit vorgegeben hätte.
> *   **Dixon-Coles war entscheidend:** Ohne die Korrektur der niedrigen Resultate wäre die Trefferquote bei "knappen" Ergebnissen spürbar geringer ausgefallen.
> *   **Phase-adaptives Tipping:** Die grösste Erkenntnis der Post-Tournament-Analyse: Ein statischer Parametersatz ist suboptimal. Der Algo sollte in der KO-Phase automatisch auf aggressivere Parameter wechseln (`risk ↑`, `draw_bias ↑`), da Doppelpunkte die Varianz-Prämie verdoppeln.

Insgesamt hat das Projekt erfolgreich demonstriert, wie sich Echtzeit-Sportdaten, stochastische Mathematik und modernes Web-Engineering zu einer robusten Analyse-Plattform kombinieren lassen. Die erschöpfende Post-Tournament-Analyse über 859'551 Parameterkombinationen liefert zudem eine klare Blaupause für die Optimierung zukünftiger Tippspiel-Algorithmen.
