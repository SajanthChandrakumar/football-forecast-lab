# Appweite UI-Überarbeitung – lokale Abnahme

Stand: 25. Oktober 2026. Branch `codex/competition-themes-ui`, Ausgangsrevision `dbdaa5da04b4a0c0e0d72b27fe9ccacd3557dd49`. Alle nachfolgend genannten UI-Prüfungen betreffen den finalen Produktionsbuild im isolierten Arbeitsstand.

## Gestaltung und Funktionsprüfung

Gemeinsame Navigation und Bedienung; WM mit Grün/Gold, UCL mit Nachtblau/Silber, PL mit Violett/Türkis. Alle Wettbewerbe unterstützen Hell/Dunkel. Kompakte Spiele mit klar beschriftetem Ergebnis beziehungsweise Modelltipp stehen im Vordergrund. Weitere Chancen und Details lassen sich gezielt öffnen.

| Bereich | Stand | Nachweis und Ergebnis |
|---|---|---|
| Wettbewerb-Auswahl und Themes | Geprüft | Drei direkte Schalter mit Tastaturbedienung, ausgeschriebenen Beschreibungen und gespeichertem Zustand. Hell/Dunkel bleibt unabhängig vom Wettbewerb. Kein zusätzlicher Anbieterabruf beim Umschalten. |
| Spielelisten | Geprüft | Kompakte Zeilen, lange Teamnamen, vorhandene Wappen beziehungsweise neutraler Ersatz, Ergebnis/Modelltipp und Datenstatus. Bedienflächen mindestens 44px hoch. Einzelne mobile Aktionen und Offenlegungen füllen die verfügbare Breite. |
| Spielanalyse und Datenstatus | Geprüft | Lesbare Tabs, zusätzliche Details aufklappbar, fehlende/veraltete Eingaben sichtbar. Auch kompakte Zeilen behalten ihre Warnmarkierung. PL-Empfehlungen übergeben den aktiven Wettbewerb an die vorhandene Statusanzeige. |
| Tabellen und Teamvergleich | Geprüft | Gemeinsame visuelle Hierarchie, rechtsbündige numerische Werte und begrenztes Scrollen breiter Tabellen. Formdaten und deren Stichprobe bleiben inhaltlich unverändert. |
| Gemeinsame Tipps und Auswertung | Geprüft | Speichern, Ablehnung, erneutes Laden, Wettbewerbstrennung, Serienabgabe und T−5-Sperre mit isolierten Testdaten. Bestehende historische Zuordnungen bleiben erhalten. |
| Diagramme | Geprüft | Elo-, Punkte- und Prozent-Einheiten sowie benannte Serien. Aufgeklappter Quotenverlauf mit zwei gespeicherten Testbeobachtungen in beiden Darstellungen bei allen fünf Breiten; Einheit und 100%-Wert liegen vollständig innerhalb der Grafik. |
| Radar, Assistent und Simulation | Geprüft / datenabhängig | Gemeinsame Theme-Akzente, unveränderte Funktionen und ehrliche Lade-/Nichtverfügbarkeitsanzeigen. Die nicht unterstützte PL-Simulation bleibt ausgeblendet. Fehlende Anbietereingaben werden durch die Gestaltung nicht ergänzt. |
| WM-Regressionsschutz | Geprüft | Auch WM erhält das neue Erscheinungsbild. Backend, Modell, Berechnungen, APIs und historische Daten werden von diesem Branch nicht geändert. Vorhandene Backend- und WM-Browserprüfungen bestehen. |

## Endgültige lokale Prüfungen

- **523 Backendtests bestanden**, 22,24 Sekunden; dotenv-Zugangsdaten deaktiviert und keine Produktionsdatenbank verwendet.
- **125 Frontendtests bestanden**, keine Fehler.
- **368 Browserprüfungen bestanden**, 17 bewusst gerätespezifische Fälle übersprungen, 385 Fälle insgesamt; Laufzeit 2,7 Minuten.
- Browsermatrix: **375, 390, 768, 1024 und 1440 Pixel**, WM/UCL/PL, Hell/Dunkel, sämtliche Hauptseiten und vorhandene Analysetabs. Zusätzlich Tastatur, Speichern/Fehlerfälle, langsame Antworten und Wettbewerbswechsel.
- App- und E2E-Typprüfung, Lint und Produktionsbuild bestanden. Lint meldet weiterhin fünf bereits vorhandene Fast-Refresh-Hinweise, keine Fehler.
- Unabhängige Luna-xhigh-Prüfungen für die Teilaufgaben und den Gesamtstand. Gefundene Layoutfehler wurden korrigiert und gezielt nachgeprüft; abschließendes Review bestanden.

Die zuletzt gefundenen Fehler wurden zuerst reproduziert: Ein einzelnes mobiles Bedienelement ließ 159,5px ungenutzt; die vertikale Quoten-Einheit lag außerhalb der Grafik. Die entsprechenden geometrischen Browserprüfungen scheiterten vor der Korrektur und bestehen danach. Lokale Screenshots wurden zusätzlich visuell kontrolliert. Ein früherer Lauf während eines parallelen Builds hatte einen JavaScript-Ladeabbruch; der unveränderte Fall bestand isoliert. Die endgültige Gesamtrunde nutzte einen unveränderten Build und hatte keine Fehler.

## Erhaltung, Veröffentlichung und Grenzen

Die 39 bereits vorhandenen geänderten Dateien im ursprünglichen Checkout wurden nicht verändert. Ihr Patch-Hash wurde vor und nach der Umsetzung bestätigt: `bcb6e89334f8868b71e58dc3f286188625be752b1cce5bb517c0a97ebe348a50`.

Dieser Branch verändert Darstellung und Bedienung. Keine neuen Abhängigkeiten, keine Migration, keine Änderung an Anbieterzugriffen, Modellformeln, APIs oder gespeicherten Tipps. Datenfarben für Ergebnisse, Warnungen und Diagrammserien behalten ihre Bedeutung unabhängig vom Theme. Der vorige veröffentlichte Stand `dbdaa5d` bleibt über Git wiederherstellbar.

Der bereits genehmigte Release erfolgt nach dieser lokalen Abnahme über PR, CI und Zusammenführung des geprüften Standes. Der Nachweis der tatsächlich ausgelieferten Revision und Dateien wird gesondert im Abschluss festgehalten; lokale Tests allein gelten nicht als Veröffentlichung. Die öffentliche Seite antwortete vor dem Release nach einem anfänglichen Timeout mit HTTP 200 und der erwarteten Ausgangsrevision.

**Die Live-Sichtprüfung bleibt auf Wunsch des Nutzers zurückgestellt.** Screenshots und Browserprüfungen verwenden ausschließlich isolierte Beispieldaten. Es erfolgen keine produktiven Schreibtests. Anbieterabdeckung, Trefferquote, externe Wartungszeitpläne und Aufwachzeiten des kostenlosen Hostings werden durch diese UI-Überarbeitung nicht als behoben ausgegeben.
