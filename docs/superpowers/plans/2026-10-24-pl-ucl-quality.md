PLEASE IMPLEMENT THIS PLAN:
# PL und UCL vollständig überarbeiten und live prüfen

## Ziel und feste Entscheidungen

Die Fehler aus der Analysetabelle systematisch beheben und die Mannschaftsform wie in einer Fußball-App darstellen.

- **Nur PL/UCL ändern.** WM-Oberfläche, WM-Berechnung und historische WM-Daten bleiben unverändert.
- Bestehenden grünen Stil verbessern; kein vollständiges Redesign.
- Alle Herren-Pflichtspiele berücksichtigen, standardmäßig fünf, auf zehn erweiterbar.
- Form zunächst als nachvollziehbaren Kontext verwenden, ohne zusätzliche Gewichtung der Tipps.
- Vorhandene Anbieter und Kontingente nutzen; keine neuen Kosten.
- Abschluss erst nach Veröffentlichung und Prüfung der echten PL-/UCL-Seiten.

Abnahme bedeutet: keine bekannten offenen Fehler aus dieser Liste, konsistente Berechnungen und ehrliche Datenanzeigen. Fehlerfreiheit externer Anbieter und eine bestimmte Trefferquote sind keine garantierbaren Ziele.

## 1. Mannschaftsdaten und Formlisten bereinigen

**Identitäten und Datenbestand**

- Mannschaften anhand von Anbieter-ID, nachgewiesener Herrenmannschaft und Wettbewerb zuordnen. Gleiche Vereinsnamen allein reichen nicht.
- Frauen-, Nachwuchs-, Freundschafts-, abgesagte und noch nicht abgeschlossene Spiele ausschließen.
- Die PL-Datensammlung um Pokal und Europapokal erweitern. PL und UCL verwenden dieselben Regeln für Formdaten.
- Bereits vermischte Formdaten nach Sicherung kontrolliert neu aufbauen. Ungeprüfte Altbestände bis dahin aus Formstatistiken ausschließen.
- Historische Tipps, Vorabprognosen und deren Punkte nicht überschreiben.
- Fehlgeschlagene Abrufe dürfen weder gültige Daten löschen noch deren Erfolgszeitpunkt erneuern.

**Darstellung**

- Eine gemeinsame Formlisten-Komponente in Spieldetails und Teamvergleich verwenden.
- Jede Spielzeile zeigt Datum, Wettbewerb, Heimteam mit Wappen, Endstand und Auswärtsteam mit Wappen. Das betrachtete Team wird hervorgehoben; Sieg, Remis und Niederlage sind zusätzlich als Text erkennbar.
- Neueste Spiele zuerst; fünf sichtbar, „Weitere Spiele“ erweitert auf zehn. Filter: alle Pflichtspiele, Liga, Pokal, Europapokal.
- Formstatistik und Zusammenfassung verwenden dieselbe gefilterte Stichprobe. Die Stichprobengröße bleibt sichtbar.
- Verlängerung und Elfmeterschießen getrennt kennzeichnen; Elfmetertore niemals als reguläre Spieltore zählen.
- Wappen aus belegten Anbieterdaten übernehmen. Bei fehlendem Bild einen neutralen Ersatz zeigen, kein geratenes Vereinswappen.
- In historischen Spielanalysen ausschließlich Formspiele vor dem jeweiligen Anpfiff berücksichtigen.

## 2. Berechnungen und Analysen korrekt machen

**Eigenständiger PL-/UCL-Modellstand**

- Die Dixon-Coles-Korrektur für Torerwartungsanpassung und Ergebnismatrix gemeinsam reparieren.
- Eine ausdrücklich nach Wettbewerb gewählte Berechnungsvariante einführen: korrigierter Club-Modellstand für PL/UCL, bisheriger Stand für die WM.
- Neue Club-Prognosen mit eigener Modellversion speichern. Alte eingefrorene Prognosen bleiben ihrem damaligen Modellstand zugeordnet.
- Ausgangschancen, Ergebniswahrscheinlichkeiten und erwartete Punkte konsistent ableiten. Marktquoten und Modellwerte eindeutig unterscheiden.
- 90-Minuten-Wahrscheinlichkeiten getrennt von Verlängerung und Weiterkommen behandeln.
- Faire Auswertungen ausschließlich aus belegten Vorabprognosen erstellen; Modellversion und Stichprobengröße anzeigen. Historische „Modellkanten“ ohne Vorabnachweis aus Güteaussagen ausschließen.

**UCL-Simulation**

- Die durchschnittliche Ersatzmatrix für beliebige Paarungen entfernen.
- Für hypothetische Paarungen die belegten ClubElo-Werte beider Mannschaften und den korrigierten Club-Rechenweg verwenden. Keine erfundenen Ratings.
- Hin-/Rückspiel, Gesamtergebnis, Verlängerung, Elfmeterschießen und bekannte Ergebnisse korrekt berücksichtigen.
- Standardmäßig 5.000 Durchläufe berechnen. Verteilungen vorbereiten und Ergebnisse nach Datenstand und Modellversion zwischenspeichern.
- Fehlende Koeffizienten beziehungsweise Rangfolgendaten klar benennen. Fehlende notwendige Eingaben führen zu „nicht verfügbar“.
- Die nicht unterstützte PL-Turniersimulation im PL-Menü ausblenden.

## 3. Aktualisierung, Bedienung und Geschwindigkeit verbessern

- Quellenstatus in API und Oberfläche vereinheitlichen. Für Quoten und Elo zunächst die vorhandene 24-Stunden-Grenze verwenden; fehlende oder zukünftige Zeitstempel gelten nicht als bestätigte Aktualität.
- Alte, eindeutig zugeordnete Daten mit Datum und Warnung lesbar halten. Radar, Assistent und Empfehlungen dürfen daraus keine starken Sicherheitssignale erzeugen.
- Fehlende Spielerstatistiken und Aufstellungen ausdrücklich benennen; eine leere Ausfallliste nicht als vollständigen Kader darstellen.
- Vorhandene Wartung und Vorab-Erfassung für PL/UCL verbinden, gegen parallele Doppelläufe absichern und letzten Erfolg, nächste Fälligkeit sowie Fehler sichtbar machen.
- Den vorhandenen externen Wartungszeitplan prüfen und PL/UCL innerhalb der bestehenden Kontingente zuverlässig einbinden. Kostenloses Hosting darf weiterhin Aufwachzeiten haben; diese werden nicht als behoben ausgegeben.
- Teure Prognoseberechnungen je Eingabestand wiederverwenden. Eine vollständige Liste nicht bei jedem Aufruf erneut durchrechnen.
- Die UCL-Simulation im Hintergrund berechnen. Ohne fertiges Ergebnis einen begrenzten Berechnungsstatus mit automatischer Nachprüfung zeigen.
- Netzwerkaufrufe mit Abbruchgrenze und verständlicher Wiederholungsmöglichkeit versehen.
- Abgeschnittene Tabs, doppelte Vergleichsblöcke und unklare Diagrammachsen korrigieren.
- Gemeinsame Tipps überall einheitlich benennen. Schlüssel-Eingabe als maskiertes Formular statt Browser-Prompt gestalten; Schlüssel nur vorübergehend im Speicher halten.
- Speichern, Fehlerfälle, Teilfehler bei Serienabgabe, erneutes Laden und T−5-Sperre vollständig prüfen.

## 4. Schnittstellen und Prüfung

**Schnittstellen**

- Bestehende APIs kompatibel erweitern: Formspiele erhalten belegte Mannschaftsidentitäten, beide Teams und Wappen, Wettbewerb, Ergebnisart und Herkunft.
- Abdeckungsstatus zusätzlich zur Aktualität führen: zehn erfasste Spiele bedeuten nicht automatisch zehn vollständig belegte Spiele.
- Modellversion und Eingabestand auch für Simulation und Prognosecache verwenden.
- Der Simulationsendpunkt darf während der Berechnung HTTP 202 mit einem maschinenlesbaren Berechnungsstatus liefern; die Oberfläche behandelt diesen ausdrücklich.
- Öffentliche Seiten lösen keine kostenpflichtigen Anbieterabrufe aus.

**Pflichtprüfungen**

- Gleichnamige Herren-, Frauen- und Nachwuchsteams; unterschiedliche Anbieter-IDs; unklare Zuordnung; doppelte Spiele.
- Heim-/Auswärtsdarstellung, Torsummen, Wettbewerbsfilter, Sortierung, Zeitzone sowie Verlängerung und Elfmeterschießen.
- Asymmetrische Dixon-Coles-Beispiele, normalisierte Wahrscheinlichkeiten und konsistente erwartete Punkte.
- Unveränderte WM-Ergebnisse und unveränderte historische Prognosen.
- UCL-Paarungen mit vertauschten Mannschaftsstärken, Gesamtergebnis und fehlenden Ratings.
- Alte Daten, Anbieterausfälle, Kontingentgrenzen, Wiederholungen und parallele Wartung.
- Erfolgreiches und abgelehntes Speichern mit kontrollierten Testdaten.
- Gesamte Backend- und Frontend-Suite, Typprüfung, Lint und Build. Tests vom lokalen Zugangsdatenbestand isolieren und den veralteten Navigationstest ersetzen.
- Browserprüfung bei 375, 390, 768, 1024 und 1440 Pixeln, hell/dunkel und per Tastatur. Bestehende Komponenten wiederverwenden und die WM auf Regressionen prüfen.

## 5. Veröffentlichung und Live-Abnahme

- Vorhandene lokale Änderungen erfassen und erhalten; nur geprüfte, zu dieser Überarbeitung gehörende Änderungen veröffentlichen.
- Vor der produktiven Formbereinigung die betroffenen Dokumente sichern, den Reparaturlauf zunächst lesend auswerten und eine Wiederherstellung ermöglichen.
- PL/UCL veröffentlichen, abgeleitete Caches gezielt erneuern und die bereinigten Daten kontrollieren. Historische Tipp- und Bewertungsdaten bleiben erhalten.
- Auf der echten Seite Formlisten, Wappen, Analysen, Tabellen, Simulation, Ladeverhalten und Wartungsstatus prüfen. Schreibtests erfolgen mit isolierten Testdaten.
- Jede Zeile der ursprünglichen Analysetabelle abschließend als **behoben**, **geprüft** oder **durch Anbieter/Hosting begrenzt** dokumentieren. Offene Einschränkungen nicht als Erfolg ausgeben.