# Football Forecast Lab

**Statistische Fussballprognosen und transparente Modellanalyse.**

Persönliches Analyse- und Portfolio-Projekt: Das Dashboard verbindet Spieldaten, Quoten und Elo-Ratings zu nachvollziehbaren Wahrscheinlichkeiten und Ergebnistipps. Es unterstützt derzeit die **FIFA-Weltmeisterschaft 2026** und die **UEFA Champions League 2026/27**.

[Live-Demo](https://wc2026-predictor-8skd.onrender.com/) · [GitHub-Repository](https://github.com/SajanthChandrakumar/football-forecast-lab)

## Ziel

Fussballprognosen hängen von vielen Informationen ab, die sich nicht leicht direkt vergleichen lassen. Football Forecast Lab bündelt die verfügbaren Eingaben in einer Web-App und zeigt, wie daraus Wahrscheinlichkeiten, Ergebnistipps und Turniersimulationen entstehen. Das Projekt dient der persönlichen Analyse und dem technischen Portfolio.

## Funktionen

- **Spiele und Datenlage:** kommende und gespielte Partien, Ergebnisse, Tabellen, Teamform und – soweit verfügbar – Quoten. Datenquellen und Aktualität werden kenntlich gemacht; fehlende Daten werden nicht als echte Anbieterquoten ausgegeben.
- **Spielanalyse:** 1/X/2-Wahrscheinlichkeiten, erwartete Tore, wahrscheinliche Resultate, Score-Matrix und verständliche Teamvergleiche.
- **Ergebnistipps:** Auswahl eines Tipps anhand der erwarteten Punkte nach dem SRF-Tippspiel-Regelwerk. Für Nutzer-Tipps können Punkte im Archiv gespeichert und nach bekannten Ergebnissen ausgewertet werden.
- **Leistungsverlauf:** vergleicht gespeicherte, vor dem Anpfiff erfasste Prognosen mit Ergebnissen. Nachträglich aus Elo-Werten rekonstruierte Tipps werden separat ausgewiesen.
- **Strategie- und Turnierexperimente:** Build-a-Bot kann Parameter gegen archivierte Spiele rücktesten. Für die WM gibt es eine Elo-basierte K.-o.-Simulation; für die Champions League eine Simulation der Ligaphase und der anschliessenden K.-o.-Runden auf Basis der gespeicherten Spieldaten.
- **Datenpflege:** Provider-Abrufe erfolgen über einen authentifizierten Wartungsendpunkt. Öffentliche App-Aufrufe lesen gespeicherte Daten; sie rufen nicht direkt die Sportdatenanbieter ab.

## Datenquellen und Abdeckung

| Daten | Quellen im Projekt |
|---|---|
| Spielplan, Resultate und Tabellen | ESPN; Tabellen werden aus gespeicherten Ergebnissen berechnet |
| 1/X/2- und Torlinienquoten | The Odds API; optional API-Football als konfigurierbare Quotenquelle |
| Club-Ratings | ClubElo für die Champions-League-Teams; Elo-Ratings und Verlauf für die WM-Teams |
| Teamform, Aufstellungen und Spieldetails | gespeicherte ESPN-Daten; API-Football und FotMob ergänzen einzelne Datenpfade, sofern konfiguriert bzw. verfügbar |
| Archiv und Cache | MongoDB |

Die Abdeckung hängt von Wettbewerb, Anbieter, Tarif und Wartungslauf ab. ESPN- und FotMob-Fallbacks verwenden teilweise nicht offiziell dokumentierte öffentliche Endpunkte. Verfügbarkeit, Vollständigkeit und Aktualität sind daher nicht garantiert.

## Prognoseansatz

Für ein Spiel werden verfügbare 1/X/2-Wahrscheinlichkeiten um den Buchmacheraufschlag bereinigt. Ein beschränktes L-BFGS-B-Verfahren sucht Tor-Erwartungswerte, die zu diesen Wahrscheinlichkeiten und, falls vorhanden, zur Über/Unter-2,5-Torlinie passen. Daraus entsteht eine Poisson-Ergebnisverteilung mit Dixon-Coles-Korrektur für niedrige Resultate. Elo-Ratings ergänzen die Einschätzung der Teamstärke; fehlen Marktquoten, kann die App einen ausdrücklich als Elo-Modell gekennzeichneten Tipp berechnen.

Für jedes mögliche Ergebnis von 0:0 bis 5:5 berechnet der Tippoptimierer die erwarteten Punkte nach den SRF-Regeln. In K.-o.-Spielen werden die geltenden Punktegewichte berücksichtigt. Die Turniersimulationen verwenden die jeweils verfügbaren Ergebnisverteilungen bzw. Elo-Werte und sind Szenarien, keine sicheren Vorhersagen.

### Vorab-Prognosen und Rücktests

Wenn ein Wartungslauf vor dem Anpfiff Quoten und Elo speichert, kann die Leistungsauswertung diesen Vorab-Snapshot verwenden. Nicht jedes Spiel hat zwingend einen vollständigen Snapshot. Fehlt er, kann ein Ergebnis später aus historischen Elo-Daten rekonstruiert werden; diese Näherung wird in der App getrennt von der regulären Prognose ausgewiesen.

Das Build-a-Bot-Rücktesten und die Parameteroptimierungen in [ANALYSIS.md](ANALYSIS.md) verwenden bereits abgeschlossene Spiele. Sie sind nachträgliche Experimente und kein Beleg dafür, dass dieselben Einstellungen vor einem Spieltag besser prognostiziert hätten. Ergebnisse aus Rücktests oder optimierten Parametern sind nicht mit eingefrorenen Vorab-Prognosen gleichzusetzen.

## Technologie

- **Backend:** Python 3.12, FastAPI, Uvicorn, SlowAPI
- **Modell und Datenverarbeitung:** NumPy, SciPy, Pandas
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, TanStack Query, React Router, Recharts
- **Speicherung:** MongoDB; JSON/CSV-Dateien für lokale Elo-Daten
- **Prüfungen:** pytest, Node.js-Test-Runner, TypeScript-Typecheck, oxlint und Vite-Produktionsbuild; CI-Konfiguration in `.github/workflows/test.yml`

## Lokal starten

Voraussetzungen: Python 3.12, Node.js/npm und eine erreichbare MongoDB-Instanz. Die App benötigt `MONGO_URI` und – bei der Standard-Quotenquelle – `ODDS_API_KEY`.

```bash
git clone https://github.com/SajanthChandrakumar/football-forecast-lab.git
cd football-forecast-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend-v2 ci
```

Lege im Projektverzeichnis eine `.env` mit den benötigten Zugangsdaten an:

```dotenv
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>/<database>
ODDS_API_KEY=<the-odds-api-key>
# Optional: API-Football statt The Odds API als Quoten-Engine
# USE_API_FOOTBALL=true
# API_FOOTBALL_KEY=<api-football-key>
# Für authentifizierte Wartungsläufe
# CRON_SECRET=<secret>
```

Dann das Frontend bauen und den Backend-Server starten:

```bash
npm --prefix frontend-v2 run build
uvicorn src.api:app --reload
```

Die App ist anschliessend unter <http://127.0.0.1:8000> erreichbar. Für Frontend-Entwicklung mit Vite-Hot-Reload starte zusätzlich `npm --prefix frontend-v2 run dev`; der Vite-Server leitet `/api` an `http://localhost:8000` weiter.

## Tests und Auswertung

Die im Repository vorhandenen Backend- und Frontend-Prüfungen lassen sich so starten:

```bash
python -m pytest -q
cd frontend-v2
node --test tests/*.test.mjs
npm run typecheck
npm run lint
npm run build
```

Die App zeigt archivierte Resultate und Prognosepunkte, trennt dabei rekonstruierte Tipps von Vorab-Snapshots und bietet historische Rücktests. [ANALYSIS.md](ANALYSIS.md) dokumentiert zusätzliche rückblickende Untersuchungen. Kennzahlen daraus beschreiben den jeweils untersuchten historischen Datensatz und sind keine garantierte Prognosequalität.

## Einschränkungen und Status

- Wahrscheinlichkeiten sind unsicher und hängen von den verfügbaren sowie gespeicherten Eingabedaten ab.
- Quoten, Teamform, Aufstellungen und Spielerstatistiken können fehlen oder veraltet sein. Die App kennzeichnet solche Zustände, soweit sie aus den gespeicherten Provider-Antworten bekannt sind.
- Ein externer, mit `CRON_SECRET` authentifizierter Wartungsaufruf ist nötig, um Provider-Daten zu aktualisieren. Ein Zeitplan ist nicht Bestandteil des lokalen App-Starts.
- Rücktests und Tippspielpunkt-Optimierung belegen keine finanziellen Gewinne und keine allgemeine Überlegenheit des Modells. Es gibt keine garantierte Trefferquote und keine Wettberatung.
- Das Projekt wird persönlich als Analyse- und Portfolio-Projekt gepflegt; regelmässige Updates sind nicht zugesagt.

Prognosen sind keine Gewissheit. Football Forecast Lab ist ein technisches Analyseprojekt und keine Wett- oder Finanzberatung.

## Weiterführende Dokumente

- [ARCHITECTURE.md](ARCHITECTURE.md) – Modell- und Systemdetails
- [ANALYSIS.md](ANALYSIS.md) – rückblickende Auswertung und Experimente
- [SECURITY_AUDIT.md](SECURITY_AUDIT.md) – dokumentierte Sicherheitsprüfung
