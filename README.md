# Football Forecast Lab

**Statistische Fussballprognosen und transparente Modellanalyse.**

Persönliches Analyse- und Portfolio-Projekt: Das Dashboard verbindet Spieldaten, Quoten und Elo-Ratings zu nachvollziehbaren Wahrscheinlichkeiten und Ergebnistipps. Es unterstützt die **FIFA-Weltmeisterschaft 2026**, die **UEFA Champions League 2026/27** und die **Premier League 2026/27** als getrennte Wettbewerbe.

[Live-Demo](https://wc2026-predictor-8skd.onrender.com/) · [GitHub-Repository](https://github.com/SajanthChandrakumar/football-forecast-lab)

## Ziel

Fussballprognosen hängen von vielen Informationen ab, die sich nicht leicht direkt vergleichen lassen. Football Forecast Lab bündelt die verfügbaren Eingaben in einer Web-App und zeigt, wie daraus Wahrscheinlichkeiten, Ergebnistipps und Turniersimulationen entstehen. Das Projekt dient der persönlichen Analyse und dem technischen Portfolio.

## Funktionen

- **Spiele und Datenlage:** kommende und gespielte Partien, Ergebnisse, Tabellen, Teamform und – soweit verfügbar – Quoten. Datenquellen und Aktualität werden kenntlich gemacht; fehlende Daten werden nicht als echte Anbieterquoten ausgegeben.
- **Spielanalyse:** 1/X/2-Wahrscheinlichkeiten, erwartete Tore, wahrscheinliche Resultate, Score-Matrix und verständliche Teamvergleiche.
- **Ergebnistipps:** Auswahl eines Tipps anhand der erwarteten Punkte nach dem SRF-Tippspiel-Regelwerk. Für Nutzer-Tipps können Punkte im Archiv gespeichert und nach bekannten Ergebnissen ausgewertet werden.
- **Spieltag-Assistent:** Ergebnistipps einer Spielwoche bearbeiten, gemeinsam speichern oder als Tippkarte kopieren. Gespeicherte Tipps sind derzeit für alle Nutzer sichtbar; die Eingabe schliesst fünf Minuten vor Anpfiff.
- **Quotenverlauf:** vorhandene Buchmacher-Snapshots vor Anpfiff mit bereinigten 1/X/2-Wahrscheinlichkeiten und deren Veränderung. Ohne gespeicherte Beobachtungen wird kein Verlauf erfunden.
- **Modellvergleich:** Modell, Buchmacher und reines Elo anhand derselben belegbaren Vorabspiele vergleichen: Brier-Score, Log Loss und Kalibrierung. Altbestand und Rekonstruktionen zählen nicht zu dieser Stichprobe.
- **Leistungsverlauf:** vergleicht gespeicherte, vor dem Anpfiff erfasste Prognosen mit Ergebnissen. Nachträglich aus Elo-Werten rekonstruierte Tipps werden separat ausgewiesen.
- **Strategie- und Turnierexperimente:** Build-a-Bot kann Parameter gegen archivierte Spiele rücktesten. Für die WM gibt es eine Elo-basierte K.-o.-Simulation; für die Champions League eine Simulation der Ligaphase und der anschliessenden K.-o.-Runden auf Basis der gespeicherten Spieldaten.
- **Datenpflege:** Provider-Abrufe erfolgen über einen authentifizierten Wartungsendpunkt. Öffentliche App-Aufrufe lesen gespeicherte Daten; sie rufen nicht direkt die Sportdatenanbieter ab.

## Datenquellen und Abdeckung

| Daten | Quellen im Projekt |
|---|---|
| Spielplan, Resultate und Tabellen | ESPN; WM-/CL-Tabellen zusätzlich aus gespeicherten Ergebnissen, PL-Tabelle aus gespeichertem ESPN-Tabellenabruf |
| 1/X/2- und Torlinienquoten | The Odds API; optional API-Football als konfigurierbare Quotenquelle |
| Club-Ratings | ClubElo für CL- und Premier-League-Teams; Elo-Ratings und Verlauf für die WM-Teams |
| Teamform, Aufstellungen und Spieldetails | gespeicherte ESPN-Daten; API-Football und FotMob ergänzen einzelne Datenpfade, sofern konfiguriert bzw. verfügbar |
| Archiv und Cache | MongoDB |

Die Abdeckung hängt von Wettbewerb, Anbieter, Tarif und Wartungslauf ab. ESPN- und FotMob-Fallbacks verwenden teilweise nicht offiziell dokumentierte öffentliche Endpunkte. Verfügbarkeit, Vollständigkeit und Aktualität sind daher nicht garantiert.

### Premier-League-Modus

Der Wettbewerbsumschalter bietet `epl2026` neben `ucl2026` und `wc2026`. Cache, Archiv und Tipps werden in eigenen MongoDB-Collections gespeichert (`cache_epl2026`, `archive_epl2026`, `custom_bot_epl2026`). Der Modus verwendet ESPN `eng.1`, The Odds API `soccer_epl` und echte ClubElo-Ratings. Die optionale API-Football-Quotenquelle verwendet Liga 39; die Saisonverfügbarkeit hängt vom Tarif ab.

Der Saisonplan umfasst gespeicherte gespielte und kommende Partien. Die Teamform nutzt zunächst ausschliesslich erfasste Premier-League-Ergebnisse (bis zu zehn Spiele), nicht zusätzlich Pokal-/Europapokalspiele. ESPN-Spielzusammenfassungen ergänzen Aufstellungen, übermittelte Formationen und Spielerbeiträge, soweit vorhanden. Alte Spiele werden schrittweise mit höchstens fünf ESPN-Abrufen pro UTC-Tag archiviert (einschliesslich Fehlversuchen); aktuelle Anpfifffenster haben Vorrang. Historische Detailseiten lesen ausschliesslich dieses Archiv. Spielerform braucht mindestens drei Spiele mit echten Spielerstatistiken; fehlende Daten bleiben ausdrücklich unverfügbar. Verletzungsdaten und eine Ligatitel-Simulation sind nicht implementiert. Spielwochen sind Datumsgruppen, keine zugesicherten offiziellen Spieltagsnummern.

Schon gespielte Partien werden als Ergebnisse importiert, ohne nachträglich eine damalige Vorabprognose zu erfinden. Neue Prognosen und Quotenverläufe entstehen erst mit rechtzeitigen Wartungsläufen. Die Punkteoptimierung verwendet das vorhandene SRF-Schema als Modellvergleich; sie ist kein offizielles Premier-League-Tippspiel-Regelwerk.

Für den neuen Modus muss der bestehende externe Scheduler zusätzlich `POST /api/internal/maintenance?competition=epl2026` mit `Authorization: Bearer <CRON_SECRET>` aufrufen, beispielsweise alle 15 Minuten. PL-Quotenfenster sind T−75 und T−15; tägliche Discovery-Abrufe finden nur statt, wenn ein Spiel in den kommenden sieben Tagen ansteht. Ein Lauf bündelt diese Aufgaben zu höchstens einem The-Odds-API-Bulkabruf (`h2h,totals`, Region `eu`: maximal zwei Credits). Bei geeigneten Wartungsläufen prüft ESPN Aufstellungen etwa T−35 und T−15 und archiviert nach Spielende Statistiken; bestätigte Aufstellungen werden vor Anpfiff nicht erneut abgerufen. Der PL-Modus verwendet hierfür bewusst keinen API-Football-Fallback, solange die aktuelle Saisonabdeckung des Tarifs nicht bestätigt ist. ESPN ist eine inoffizielle, nicht garantiert verfügbare Schnittstelle.

Alle bezahlten Anbieterpfade teilen einen MongoDB-Reservierungszähler, unabhängig vom Wettbewerb und Prozess: höchstens 400 reservierte Odds-Credits in rollierenden 31 Tagen sowie 80 API-Football-Abfragen in rollierenden 24 Stunden. API-Football wird zusätzlich global auf mindestens sieben Sekunden Abstand und höchstens neun reservierte Anfragen pro Minute begrenzt. Reservierung erfolgt atomar vor HTTP; auch Fehler und leere Antworten zählen konservativ. Bekannte aktuelle Anbieter-Restkontingente schützen zusätzlich eine Reserve von 100 Odds-Credits bzw. 20 API-Football-Abfragen. Ist die Reservierungsdatenbank nicht verfügbar, werden bezahlte Abrufe blockiert, nicht ungeschützt fortgesetzt. Das ist bewusst strenger als ein Kalendertag/-monat und kann nach einem Tarif-Reset weiter begrenzen. Andere Anwendungen mit denselben Keys können Kontingente ebenfalls verbrauchen; der Schutz ist keine Garantie für deren Nutzung.

ESPN-Saisonplan, ClubElo und die PL-Tabelle werden gecacht; Nutzeraufrufe und Teamform aus Ergebnissen verursachen keine zusätzlichen Anbieterabrufe. Ein externer Zeitplan wird durch das Einbauen des Modus nicht automatisch aktiviert. Bei fehlendem Budget bleibt der vorhandene Cache nutzbar; Quellen und Datenstände werden nicht als frisch erfunden.

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

Der authentifizierte Wartungslauf friert verfügbare Prognosen im Fenster zwischen T−15 und Anpfiff ein und speichert belegbare Markt- und Elo-Vergleichswerte. Ohne rechtzeitigen Wartungslauf oder geeignete gespeicherte Eingaben bleibt die Vergleichsstichprobe unvollständig. Der Vergleich bewertet 90-Minuten-Ausgänge; bei verlängerungsfähigen Spielen ist dafür ein separat erfasstes 90-Minuten-Resultat nötig.

Weichen Archiv- und Provider-Spiel-ID voneinander ab, funktionieren Tippabgabe und Quotenverlauf über die gespeicherte Team-/Datumszuordnung. Das automatische Einfrieren überspringt solche ID-Aliase derzeit, statt doppelte Archivspiele anzulegen.

Quotenverlauf und Modellvergleich lesen ausschliesslich gespeicherte Daten. Der Spieltag-Assistent nutzt den vorhandenen Tipp-Endpunkt: maximal 18 Speicheranfragen pro Schritt, höchstens drei gleichzeitig. Diese Nutzeraktionen lösen keine Sportanbieter-Abfragen aus.

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
