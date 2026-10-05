# Live-Check und Datenlage – 4. Oktober 2026

## Verifizierter öffentlicher Betrieb

Geprüft am 4. Oktober 2026, API-Stichprobe 18:39:11–18:39:22 UTC (20:39 Uhr Zürich).
Öffentliche Anwendung: https://wc2026-predictor-8skd.onrender.com/

- GitHub Actions für `main`, Commit `1398d5a950b7cac100f74e9ed073129ba8b5dac2`, ist erfolgreich: [Run 37208222185](https://github.com/SajanthChandrakumar/football-forecast-lab/actions/runs/37208222185). Backend, Typecheck, Lint, Build und Browser-Prüfungen sind grün.
- Der öffentliche HTML-Einstieg verweist auf `index-Dv8ju8Fj.js`. Dieses Bundle, React, Rolldown-Runtime und Einstiegs-CSS stimmen per SHA-256 mit den Dateien dieses Commits überein. Das bestätigt den Frontend-Einstieg; die genaue Backend-Revision ist öffentlich nicht separat belegt.
- Die erste Anfrage lieferte HTTP 503 und die Render-Ladeseite. Bei der späteren Prüfung antworteten Anwendung, Wettbewerbsregister und die unten genannten APIs mit HTTP 200. Ein Startverzug ist plausibel; seine Ursache wurde nicht durch private Logs belegt.
- Im Browser wurden die UCL-Übersicht, ein UCL-Spiel und die Premier-League-Übersicht mit echten öffentlichen Antworten geöffnet. Es wurde kein Live-Tipp gespeichert und keine Wartung ausgelöst.

## Datenstand und Vorab-Erfassung

| Wettbewerb | Spiele laut `/api/matches` | Abgeschlossene Spiele im Modellvergleich | Verifizierte Vorab-Prognosen | Elo-Beobachtung | Elo-Abdeckung |
| --- | ---: | ---: | ---: | --- | --- |
| UCL | 144, davon 126 bevorstehend | 18 | 0 | 24. September 2026, 08:26 UTC | 36/36 Teams |
| Premier League | 380, davon 330 bevorstehend | 50 | 0 | 1. Oktober 2026, 19:56 UTC | 20/20 Teams |
| WM | 111, keine bevorstehend | 104 | 0 | In der Stichprobe nicht datiert | Nicht Gegenstand der ClubElo-Statusprüfung |

Quellen sind die öffentlichen Endpunkte `/api/matches`, `/api/archive`, `/api/model-comparison` sowie für die Club-Wettbewerbe `/api/elo_ratings_status`, jeweils mit dem passenden `competition`-Parameter. Das Archiv enthielt 36 UCL-, 50 PL- und 172 WM-Einträge; kein Eintrag enthielt `prediction.evaluation_forecast`. Archiv- und Spielzahlen haben unterschiedliche Filter und teils Alias-Einträge und sind daher keine gemeinsame Grundgesamtheit.

Gespeicherte Buchmacherquoten tragen ebenfalls Beobachtungen vom 24. September (UCL) bzw. 1. Oktober (PL). Die Elo-API bezeichnet beide Bestände als `fresh`, obwohl die Zeitpunkte mehr als 24 Stunden zurückliegen. Die neue UI berücksichtigt deshalb sowohl den Quellenstatus als auch den tatsächlichen Zeitpunkt.

Null verifizierte Vorab-Prognosen bedeutet: Der faire Modellvergleich hat derzeit keine verwertbaren Erfassungen. Es beweist keinen Scheduler-Ausfall; die abgeschlossenen Spiele können vor Einführung der Erfassung liegen. Der externe Wartungszeitplan, erfolgreiche geschützte Aufrufe und eine echte Erfassung im Fenster T−15 bis vor T−5 sind weiterhin nicht verifiziert.

Die automatische Freigabeprüfung hat das Öffnen des privaten Render-Dashboards abgelehnt, weil die bisherige Autorisierung als öffentlicher Live-Check gewertet wurde. Die gesonderte Frage nach lesendem Dashboard-Zugriff blieb zum Abschluss unbeantwortet. Es wurden weder private Deploymentdaten noch Scheduler-Einstellungen geöffnet oder verändert.

## Lokale Umsetzung

Branch `codex/live-data-status` im bestehenden UI-Worktree, ausgehend von `1398d5a`.

- Übersicht: aufklappbare Datenlage direkt an jedem bevorstehenden Spiel, einschließlich kompakter Spielkarten.
- Detail: Quelle, eigener Beobachtungszeitpunkt und Alter von Buchmacherquoten und Elo; Aufstellungsstatus separat daneben. Fehlende Eingaben, veraltete Bestände, Fehler und unbekannte Zeitpunkte werden benannt.
- Die Datenlage gehört zur tatsächlich angezeigten Empfehlung. Eine neue `/api/predict`-Antwort übernimmt nicht die Metadaten einer älteren Empfehlung aus der Spielliste. Bleibt der gespeicherte Vorschlag sichtbar, bleiben auch dessen Metadaten maßgeblich.
- Fehlende Aufstellungen werden als „Nicht erfasst“ bezeichnet. „Noch nicht veröffentlicht“ erscheint nur mit entsprechendem Anbieterhinweis. Teilweise erfasste Aufstellungen und Abruffehler bleiben unterscheidbar.
- Undatiertes Elo erhält keinen erfundenen Quotenzeitpunkt und keine unbelegte ClubElo-Zuordnung. Eigene, auch verschachtelt gespeicherte Quellenzeitpunkte bleiben erhalten.
- Modellrechnung und sichtbare beziehungsweise gespeicherte Tipps werden durch diese Metadatenkorrektur nicht geändert.

Die Änderungen sind lokal und noch nicht veröffentlicht. Der gespeicherte Frontend-Build ist aktualisiert. Die Vorschau unter http://127.0.0.1:8003/#/match/401915418 verwendet Kopien der öffentlichen Live-Antworten; ihr Predict-Endpunkt zeigt die kopierte Cache-Empfehlung. Sie speichert keine Tipps und ist kein vollständiger Backend-Livetest.

## Validierung

- Python: `python -m pytest -q` – 376 bestanden.
- Frontend: `node --test tests/*.test.mjs` – 113 bestanden.
- TypeScript und Release-Build: `npm run build` – erfolgreich.
- Lint: `npm run lint` – keine Fehler; fünf bestehende Fast-Refresh-Warnungen.
- Playwright: `npm run test:e2e` – 73 bestanden, drei für das jeweilige Gerät nicht anwendbare Tests übersprungen. Ansichten in hellem/dunklem Modus sowie 375/390 px, Tablet und Desktop; neue Datenlagefälle auf allen vier Größen.
- Die zwei zusätzlichen Quellenfehler wurden zuerst mit fehlschlagenden Tests reproduziert und danach unabhängig nachgeprüft.
