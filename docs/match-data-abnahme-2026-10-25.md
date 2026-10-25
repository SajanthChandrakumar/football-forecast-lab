# Abnahme: Spielanalyse und API & Daten

Lokale Abnahme vom 25. Oktober 2026, Branch `codex/match-data-cleanup`, Basis `cd782d8f23a593e7b79314c8e2c2ac1b538414ef`. Alle sieben Browsermarkierungen sind umgesetzt und im finalen Produktionsbuild geprüft.

| Markierung | Ergebnis | Prüfung |
|---|---|---|
| 1 – Tore & Form | Gleich breite Torübersichten nutzen die verfügbare Breite. Modellwerte sind als erwartete Tore erklärt; auf dem Handy stehen lange Teamnamen und Werte ohne gequetschte Textspalte. Überzählige Grid-Spalten und aufaddierte Abstände entfernt. | Geometrie und Bilder bei 375, 788, 1024 und 1440px; alle Themes in der Gesamtrunde. |
| 2 – Sunderland-Form | Gemeinsame Formliste aufgeräumt: passende Anzahl Statistikfelder, Wettbewerb im Untertitel, kein doppeltes „Stand“. Teamnamen, belegte Wappen beziehungsweise neutraler Ersatz, Datum, Gegner, Ergebnis und Ausgang bleiben sichtbar. | Filter, gleiche Statistik-Stichprobe, fünf/zehn Spiele, fehlende Bilder, Heim/Auswärts und lange Namen geprüft. |
| 3 – Leeds-Form | Dieselbe Komponente und Regeln für das zweite Team. Ab 1024px direkter Vergleich nebeneinander; darunter beide Teams untereinander. Spielzeilen richten sich nach der Breite ihrer Karte. | Containergeometrie und sichtbare Ergebnisse; Verlängerung/Elfmeterschießen und zeitlicher Anpfiff-Filter bleiben erhalten. |
| 4 – Buchmacherquoten | Kompakte Heimsieg/Remis/Auswärtssieg-Anzeige: drei Spalten ab 640px, darunter lesbare Zeilen. Marktchancen und Modellwerte bleiben getrennt, Quelle und Zeitpunkt sichtbar. | Handy-/Tablet-Bilder sowie bestehende Quotenverlauf- und Datenstatusfälle. |
| 5 – Spielhinweise | Erklärungen verwenden die angezeigten Modellwahrscheinlichkeiten. Gemischte Quellen, alte Prognosen ohne Quellenkennung und eine bereits fertige Prognose bei noch wartendem Spiellisten-Cache funktionieren. Fehlende Daten bleiben ein kurzer ehrlicher Hinweis. | Neue Modellbasis-Regressionen mit beobachtetem Fehlschlag vor der Korrektur; WM-/Archiv-/Pending-Browserfälle. Kein Rückfall auf aktuelle Buchmacherquoten für historische Modellhinweise. |
| 6 – Pool-Tipp und Rundendaten | Editor, zugehöriger Frontend-Zustand und unnötiges Laden aus der Spielansicht entfernt. | Keine Pool-Abfrage beim Öffnen; gespeicherte Dokumente, Backend-Endpunkte und Tippberechnung unverändert. |
| 7 – API & Daten | Eigene Seite unter Mehr/Analysen und in den Desktop-Einstellungen. Quellen, Datenstand, Abdeckung, Wartung und gemeinsame Kontingente für den ausgewählten Modus. Bestehender geschützter Gesamtabruf für PL/UCL dort verfügbar. | Öffentliches Statuslesen ohne Anbieterabfragen/Schreibvorgänge; Maskierung, falscher Schlüssel, Teilfehler, Kontingent 0/unbekannt, Wiederholung, Wettbewerbswechsel und laufende Abrufe über Seitenwechsel geprüft. |

## Datenanzeigen und Kompatibilität

`GET /api/data-status?competition=...` ergänzt die API kompatibel. Der Endpunkt liest gespeicherte Daten; er reserviert keine Anbieterabfragen und verändert keine Dokumente. Quellen aus gespeicherten Angaben sind von konfigurierten Quellen getrennt. Bereits gespeichertes `espn+fotmob` bleibt als Herkunft sichtbar und aktiviert keinen neuen Fallback.

Anbieter-Restkontingente und interne App-Reservierungen sind getrennte globale Zähler. The Odds API zählt Credits, API-Football Abfragen. Unbekannte, undatierte, ungültige oder zukünftige Kontingentbeobachtungen liefern keinen erfundenen Restwert. Echte Nullwerte und datierte ältere Zähler bleiben unterscheidbar. Für ESPN/ClubElo/FotMob wird kein unendliches oder erfundenes Kontingent angezeigt. Bestehende Limits und Schutzreserven sowie `GET /api/quota` bleiben unverändert.

Tabellenstatus folgt den tatsächlich verfügbaren Tabellen: WM aus dem gespeicherten Tabellenbestand, UCL über die bestehenden Validierungs-/Ableitungsregeln. Abrufversuche sind keine bestätigten Erfolge. Der neue Status berücksichtigt fehlende Zeitpunkte, Teilabdeckung und laufende Wartungssperren.

Der Admin-Schlüssel bleibt vorübergehend im Eingabefeld und wird vor dem Abruf gelöscht. Nur Wettbewerbskennung und numerische Wartezeit-Grenzen gelangen in den App-Zustand. Wartezeit und laufende Abrufsperre bleiben beim Seitenwechsel erhalten. WM erhält die Datenübersicht; der vorhandene Sofortabruf bleibt auf PL/UCL beschränkt.

## Endgültige lokale Prüfungen

- **544 Backendtests bestanden**, 15,15 Sekunden, ohne lokale dotenv-Zugangsdaten und ohne Produktionszugriff.
- **130 Frontendtests bestanden**; App-/E2E-Typprüfung und Produktionsbuild bestanden.
- **429 Browserprüfungen bestanden**, 21 bewusst eingegrenzte Fälle übersprungen, 450 insgesamt; 2,7 Minuten.
- Bildschirmbreiten 375/390/768/1024/1440px, alle sechs Wettbewerb-/Hell-Dunkel-Kombinationen; zusätzlich die gemeldeten 788px. Aufnahmen für Form, Markt und API-Seite visuell kontrolliert.
- Lint ohne Fehler; fünf bereits vorhandene Fast-Refresh-Hinweise. Alle eingesetzten Subagenten: Luna xhigh. Unabhängige Frontend-, Backend- und Gesamtprüfung nach Korrekturen freigegeben.

Die erste Gesamtrunde hatte 15 Fehler in veralteten Testannahmen: ein alter Selektor/Viewport-Breakpoint sowie ein WM-Test, dessen Antwort noch eine bekannte Quellenkennung erzeugte. Die Auswahl und Testantwort wurden an die tatsächlichen neuen Abläufe angepasst; keine fachlichen Aussagen wurden entfernt. Die komplette Runde wurde danach erneut erfolgreich ausgeführt. Geometrie wird beim Größenwechsel zusammenhängend erfasst, statt unterschiedliche Renderzeitpunkte miteinander zu vergleichen.

## Erhaltung und Veröffentlichung

Berechnungen, Modellversionen, gespeicherte Prognosen und historische Tipps werden nicht geändert. Es gibt keine Migration und keine neuen Abhängigkeiten oder Anbieter. Die 39 vorhandenen Änderungen im ursprünglichen Projektordner entsprechen weiterhin dem vor dieser Überarbeitung bestätigten Patch-Hash `bcb6e89334f8868b71e58dc3f286188625be752b1cce5bb517c0a97ebe348a50`. Der bereits vorhandene andere Abnahmebericht wird nicht mit veröffentlicht.

Der geprüfte Stand wird über PR, grüne CI und Zusammenführung veröffentlicht; die tatsächliche Auslieferung wird danach anhand Revision, Dateien und öffentlichen Status-Leseabrufen gesondert bestätigt. Die Quellen- und Modelländerungen sind über Git zur Basisrevision rücksetzbar; keine Datenwiederherstellung ist nötig.

Die **Live-Sichtprüfung bleibt auf Wunsch zurückgestellt**. Browserbilder und Schreibtests nutzen isolierte Beispieldaten. Es erfolgen keine produktiven Schreibtests oder manuellen Anbieterabrufe zur Abnahme. Anbieterabdeckung, fehlende Verletzungs-/Spielerwerte, externe Zeitpläne und Aufwachzeiten des kostenlosen Hostings bleiben erkennbare Grenzen.
