# App-Analyse: Premier League und Champions League

Stand: 24. Oktober 2026, Europe/Zurich. Die WM ist auf Wunsch aus dem Bericht ausgeschlossen.

## Ergebnis und Prüfgrenzen

Die App bietet eine gut strukturierte, visuell konsistente Analyseoberfläche. Die größten Schwächen betreffen die Datenzuordnung, die mathematische Ergebnisverteilung, die Absicherung der Prognosegüte und die UCL-Titelsimulation. Eine funktionierende Oberfläche belegt keine zuverlässige Prognose.

Geprüft wurden die veröffentlichte App im vorhandenen Browser, öffentliche API-Antworten und der lokale Quellcode. Der Browser hatte eine schmale Ansicht von ungefähr 560 Pixeln. Desktop, kleinere Handys, Dunkelmodus und Langzeitverfügbarkeit wurden in dieser Untersuchung nicht erneut visuell geprüft. Bestehende Browser-E2E-Tests wurden gelesen, aber nicht ausgeführt. Es wurden keine gemeinsamen Tipps, Bots, Pool-Daten oder Admin-Abrufe gespeichert beziehungsweise ausgelöst.

Die veröffentlichte Oberfläche und der lokale Stand unterscheiden sich: live index-B8oT_LNi.js, lokal index-RjG9w8tn.js. Lokale Tests gelten deshalb nicht automatisch als Beleg für den veröffentlichten Stand. Bewertungen sind fachliche Einschätzungen, keine gemessenen Qualitätsprozente. Skala: 1 sehr schlecht, 5 eingeschränkt brauchbar, 8 gut, 10 ausgezeichnet. F = Funktion/Bedienung, O = Optik in der geprüften Ansicht, Z = Zuverlässigkeit der angezeigten Aussage. Ein Stern bezeichnet fehlende Live-Endprüfung einer Schreibfunktion; ein Strich bedeutet nicht bewertet.

## Funktionstabelle

| Funktion | F / O / Z | Prüfung und Urteil |
|---|---|---|
| Start und Erreichbarkeit | 5 / 7 / 5 | Zunächst nur Render-Ladeseite, später erreichbar. Das ist eine beobachtete Startverzögerung, keine gemessene Ausfallquote. |
| Hauptnavigation und Analysemenü | 8 / 8 / 8 | Spiele, gemeinsame Tipps, Tabellen und vier Analysebereiche erreichbar. Auswahl und Dialogzustand nachvollziehbar. |
| Wettbewerbswechsel PL/UCL | 9 / 8 / 8 | Inhalte und Mannschaftsauswahl wechseln passend; PL hat 20, UCL 36 Teams. |
| Spielübersicht und Karten | 8 / 8 / 6 | Tipps, Anpfiff, 1/X/2 und Quellen gut sichtbar. Die PL-Antwort enthielt 380 Spiele, die UCL-Antwort 144. Langsame Datenantworten schränken die Bedienung ein. |
| Suche, Filter, Runden | 8 / 8 / 7 | Suche nach Arsenal funktioniert. Spielwochen sind Kalendergruppen, keine offiziellen Spieltagsnummern; teils 9, 11 oder 20 Spiele pro Gruppe. |
| Ergebnisse und offene Resultate | 7 / 8 / 6 | PL: 70 abgeschlossene Spiele und 2 ausstehende Ergebnisse im Browser. UCL: 54 abgeschlossene Spiele. Externe Ergebnisrichtigkeit wurde nicht einzeln gegengeprüft. |
| Spieltag-Radar | 7 / 8 / 4 | PL zeigt 2 klare Tipps, 5 offene Spiele und 1 Alarm. Die Kategorien prüfen im lokalen Code keine Datenalterung; vier Tage alte Eingaben können weiterhin klare Tipps erzeugen. Die Tagesüberschrift bezeichnet den ersten Tag eines bis zu 72-stündigen Fensters. |
| Tipp-Assistent | 8 / 7 / 6* | Runde, Vorschläge, Abgabefrist und gemeinsame Sichtbarkeit verständlich. PL-Beispiel: 0 von 8 kommenden Tipps gespeichert. Serien-Speichern nur über Code und Tests bewertet. |
| Direktes Tippen und T−5-Sperre | 7 / 8 / 7* | Zwei Torfelder und sichtbare Frist. Lokale Tests prüfen Validierung und Sperrgrenzen; keine produktiven Tipps zum Test gespeichert. |
| Kopieren von Tipp/Tippkarte | 7 / 8 / 6* | Bedienelemente und Fehlerbehandlung vorhanden. Zwischenablage-Ergebnis in diesem Lauf nicht getestet. |
| Spielanalyse: Überblick | 8 / 8 / 6 | Empfehlung, gemeinsame Eingabe, Ausgangschancen und Datenlage gut gegliedert. Übersichtskarten zeigen teils Marktchancen, Details kombinierte Modellchancen: bei Arsenal 68/21/11 gegenüber 67/21/13. Quellen sind benannt, die Unterschiede sollten prominenter erklärt werden. |
| 1/X/2-Wahrscheinlichkeiten | 7 / 8 / 4 | Werte und Herkunft sichtbar; derzeit keine belastbare nachgewiesene Prognosegüte. Ein Fehler in der zugrunde liegenden Score-Verteilung ist live nachvollziehbar. |
| Ergebnistipps, xG, Score-Matrix, erwartete Punkte | 6 / 8 / 3 | Sehr gute Trennung von erwarteten Punkten und exakter Trefferchance. Dixon-Coles-Faktoren für 1:0/0:1 vertauscht; beeinflusst Ergebniswahrscheinlichkeiten und darauf aufbauende Berechnungen. |
| PL-Teamform im Spiel | 8 / 8 / 7 | Erfasste PL-Spiele mit Gegnern, Ergebnissen und transparenter Beschränkung auf die Liga. In der untersuchten PL-Antwort keine Frauenwettbewerbe in der Form gefunden. |
| UCL-Teamform im Spiel | 3 / 8 / 2 | Bei 15 verschiedenen UCL-Teams enthalten die Live-Formdaten Frauenwettbewerbe. Serien, Tore und Formzusammenfassungen sind dadurch fachlich unzuverlässig. |
| Spielerform | 3 / 7 / 3 | In den geprüften PL- und UCL-Spieldetails 0 von 3 erforderlichen Spielen mit echten Spielerstatistiken. Fehlende Werte werden ehrlich benannt, die Funktion liefert aber noch keinen Nutzen. |
| Aufstellungen und Ausfälle | 4 / 7 / 4 | Im geprüften PL-Spiel nicht erfasst; historische Aufstellung meldet nach Klick ebenfalls fehlendes Archiv. Keine Aussage über die Abdeckung aller Spiele. Leere Ausfalldaten sind kein Beweis für einen vollständigen Kader. |
| Marktquoten | 7 / 8 / 4 | Arsenal-Beispiel liefert Quoten 1.39 / 4.60 / 8.65 mit Stand 20.10., am Prüftag vier Tage alt. Überschrift „Aktuelle Quoten“ passt nicht zur tatsächlichen Aktualität. |
| Quotenverlauf | 7 / 7 / 5 | Arsenal hat zwei reale gespeicherte Punkte vom 13. und 20.10.; Veränderung korrekt dargestellt. Beide Achsenpunkte heißen „Manuell“, dadurch wird der Zeitverlauf im Diagramm schlecht erkennbar. |
| Datenlage und Quellenanzeige | 8 / 7 / 6 | Detailansicht kennzeichnet ältere Eingaben und fehlende Aufstellungen. Die API meldet vier Tage alte ClubElo-Daten weiterhin als fresh; Statussemantik ist zwischen API und Oberfläche uneinheitlich. |
| Tipp-Chancen | 8 / 8 / 4 | Zeitraum und Rangfolge funktionieren; PL-Beispiel 8 Empfehlungen, Arsenal vorne mit 4.72 erwarteten Punkten. Qualität hängt von Datenalter und Score-Modell ab. |
| Modell & Markt: kommende Spiele | 7 / 8 / 5 | PL: 18 kommende Vergleiche. Elo-minus-Markt wird als Anteil ohne Remis korrekt erklärt. Auf den Karten fehlt die prominente Datenalterung. Eine Abweichung ist kein nachgewiesener Vorteil. |
| Modell & Markt: historische Trefferquote | 5 / 8 / 3 | PL zeigt 50 %, konkret 7 Treffer, 7 verfehlt, 6 knapp/Remis. Der lokale Auswertungspfad verlangt keinen belegten Vorab-Capture. Die Quote belegt weder Modellgüte noch eine Überlegenheit gegenüber dem Markt. |
| Gespeicherte gemeinsame Tipps | 8 / 8 / 7* | Für kommende PL-/UCL-Spiele leer, mit sinnvoller Erklärung. UCL-Archiv enthält 36 gemeinsame Tipps; produktives Speichern und erneutes Laden nicht getestet. |
| Punkte und Verlauf | 7 / 7 / 6 | UCL zeigt 54 abgeschlossene Spiele, 36 gemeinsame Tipps und 164 Punkte. Ältere und rekonstruierte Modelltipps sind markiert; Gesamtverlauf und fairer Vergleich nutzen unterschiedliche Stichproben. Viele standardmäßig ausgewählte Kurven erschweren den Überblick. |
| Fairer Modellvergleich / Kalibrierung | 8 / 6 / 4 | UCL 7/54 auswertbare Vorabspiele, PL 0/70. Ehrliche Ausschlüsse, aber für belastbare Gütebewertung zu wenig Daten. Zwei aufeinanderfolgende Vergleichsblöcke wiederholen ähnliche Kennzahlen. |
| Historische Tipps nachtragen | 5* / — / — | Im lokalen Stand implementiert und getestet; in der geprüften veröffentlichten Historie keine Eingabefelder vorhanden. Nicht als live verfügbar gewertet. |
| Bots und Rücktests | 5 / 7 / 4 | Regler und Berechnung reagieren. PL-Rücktest nach Änderung des Risikoreglers: keine auswertbaren Spiele. Bot-Speichern wurde nicht produktiv getestet. |
| Pool-Kontext | 5 / 6 / 4* | Formular für eigene Punkte, Führung und Tippverteilung vorhanden; ohne Daten kein Pool-Tipp. Reales Speichern und Qualität des resultierenden Vorschlags nicht geprüft. |
| PL-/UCL-Tabellen | 8 / 8 / 6 | Vollständige Darstellung von 20 bzw. 36 Teams mit Punkten und Bilanz. Quellenzeitpunkt ist in der Tabelle nicht prominent; keine komplette externe Prüfung aller Resultate und Gleichstände. |
| Teamvergleich und Elo-Rangliste | 7 / 8 / 6 | Teams hinzufügen/entfernen funktioniert. Ranglisten decken 20 bzw. 36 Teams ab. Bei den geprüften Teams nur aktueller Elo-Wert, kein historischer Verlauf; Diagrammnutzen daher eingeschränkt. |
| UCL-Turniersimulation | 5 / 8 / 2 | Liefert nach langer Ladephase Ergebnisse, 100 Durchläufe, fehlende Koeffizienten und offizielle Reihenfolge. Lokaler Code verwendet bei unbekannten Paarungen eine durchschnittliche Score-Matrix, die Mannschaftsstärken nicht paarweise abbildet. |
| PL-Simulation | — / 6 / — | Nicht implementiert. Menü führt auf „Für die Premier League nicht anwendbar“. Besser im Wettbewerb ausblenden oder direkt als nicht verfügbar kennzeichnen. |
| Cache neu laden / Admin-Abruf | 7* / 7 / 6* | Menü unterscheidet gespeicherte Daten neu laden und geschützten Anbieterabruf. Admin-Schlüssel erforderlich, Abrufknopf ohne Schlüssel deaktiviert. Anbieterabruf nicht ausgelöst. |
| Hell/Dunkel und Bildschirmgrößen | — / 8 / — | Die tatsächlich geprüfte schmale helle Ansicht ist konsistent. Tabs werden horizontal abgeschnitten und benötigen Scrollen; Quellcode unterstützt weitere Ansichten, diese wurden nicht visuell abgenommen. |
| Speicherschutz und Bedienung | 7* / 5 / 7* | Lokaler Schutz blockiert Schreibzugriffe ohne Editor-Schlüssel. Browser-Prompt für den Schlüssel ist wenig komfortabel; die Anmeldung wird erst beim Speichern erkennbar. Keine umfassende Sicherheitsprüfung. |

## Wichtigste Einzelbefunde

### 1. UCL-Form vermischt Mannschaften

Die Live-Antwort von /api/matches?competition=ucl2026 enthält bei 15 unterschiedlichen Teams Frauenwettbewerbe in home_form.matches beziehungsweise away_form.matches. Beispiele: Atlético Madrid gegen Madrid CFF (Liga F), Bayern gegen Benfica (UEFA Women's Champions League), Arsenal gegen Manchester City (Women's Super League). Die im Browser angezeigten Serien und Torsummen schließen diese Spiele ein. In der untersuchten PL-Antwort wurde diese Vermischung nicht gefunden.

Lokaler Zuordnungspfad: src/services/team_form.py:493–496 vergleicht im Bulk-Pfad normalisierte Namen. Ein Namensvergleich allein unterscheidet Herren-, Frauen- und Nachwuchsmannschaften nicht. Der bestätigte Befund betrifft zunächst die angezeigte Form; eine Auswirkung dieser Formdaten auf sämtliche Prognosen wurde nicht nachgewiesen.

### 2. Dixon-Coles-Fehler ist auch in der Live-Matrix nachweisbar

src/math_engine.py:247–248 sowie 299–305 verwenden für die Zelle 1:0 die Heimtorerwartung und für 0:1 die Auswärtstorerwartung. Bei Zeilen = Heimtore und Spalten = Auswärtstore gilt umgekehrt: tau(1,0) = 1 + lambda_away*rho und tau(0,1) = 1 + lambda_home*rho.

Beim live gelesenen Arsenal–Everton-Spiel 401878768 betragen die xG 2.079266147951612 und 0.7060561000304509. Die gesamte gelieferte 11×11-Matrix stimmt exakt mit der lokalen Implementierung überein (maximale absolute Differenz 0). Bei unveränderten xG liegt P(1:0) live bei 8.9861 %, mit korrigierter Korrektur bei 11.4722 %. P(0:1) liegt live bei 3.9648 %, korrigiert bei 2.9981 %. Das isoliert den Fehler; nach einer Reparatur der xG-Anpassung könnten sich zusätzlich die geschätzten xG ändern.

Fachlicher Abgleich: Király und Qian, „Modelling Competitive Sports: Bradley-Terry-Élo Models for Supervised and On-Line Learning of Paired Competition Outcomes“, Darstellung der Dixon-Coles-Korrektur: https://discovery.ucl.ac.uk/1545162/1/1701.08055v1.pdf .

### 3. UCL-Titelchancen haben eine zu schwache Grundlage

Live bestätigt: 100 Durchläufe, fehlende UEFA-Koeffizienten, keine offizielle Tabellenreihenfolge, lange erste Ladephase. Lokaler Codebefund: build_cached_ucl_inputs mittelt offene Score-Matrizen zu einem default (src/services/ucl_simulation.py:550–561). _matrix_lookup wählt diesen default, wenn keine passende Paarung existiert (Zeile 490). Künftige K.-o.-Paarungen werden ohne eigene Match-ID berechnet.

Ein isolierter Nachweis mit einer vorhandenen Matrix ergab für „Strong gegen Weak“ und „Weak gegen Strong“ exakt dieselbe Verteilung. Die Prüfung belegt das Verhalten des lokalen Fallbacks; welche Matrix jede einzelne veröffentlichte K.-o.-Paarung verwendet hat, ist aus der sichtbaren Ausgabe nicht nachvollziehbar. Die UCL-Titelrangliste ist deshalb derzeit nur ein schwaches Experiment, keine belastbare Titelprognose.

### 4. Prognosegüte ist noch nicht hinreichend belegt

| Wettbewerb | Abgeschlossene Spiele | Gemeinsame belegte Vorab-Stichprobe | Anteil | Brier Modell / Markt / Elo |
|---|---:|---:|---:|---|
| UCL | 54 | 7 | 13.0 % | 0.634 / 0.617 / 0.696 |
| PL | 70 | 0 | 0 % | nicht berechenbar |

Kleiner ist bei Brier und Log Loss besser. In den sieben UCL-Spielen ist der Markt numerisch etwas besser als das Modell (Log Loss 1.063 gegenüber 1.092). Die Stichprobe ist zu klein für ein belastbares Ranking. Fehlende Vorab-Erfassungen sind fehlende Evidenz und keine nachgewiesenen Fehlprognosen. Ein Grund für die Lücken, etwa ein fehlender Scheduler, ist durch diese Untersuchung nicht bewiesen.

### 5. Datenalter und Reaktionszeit

PL-Quoten und ClubElo-Daten der Beispiele stammen vom 20.10., vier Tage vor der Prüfung. Für die nächste UCL-Runde sind in der sichtbaren Übersicht überwiegend reine Elo-Tipps vorhanden. Das ist als Ersatzmodus gekennzeichnet, sollte aber nicht wie eine vollständige Marktanalyse wirken.

Einzelne öffentliche Match-Antworten dauerten beim direkten Abruf 8.73 Sekunden (UCL, 144 Spiele) und 13.62 Sekunden (PL, 380 Spiele). Weitere API-Antworten lagen im selben Durchlauf überwiegend unter 1.2 Sekunden; das PL-Archiv benötigte 5.75 Sekunden. Das sind Einzelmessungen, keine Lasttests oder Perzentile. Im lokalen matches-Pfad werden zahlreiche Prognosen beim Lesen neu berechnet; ein Beitrag zur Laufzeit ist plausibel, aber nicht profiliert. Die UCL-Simulation lieferte nach längerer Wartephase schließlich Ergebnisse, war also nicht dauerhaft defekt.

## Aktuelle technische Prüfungen

- Frontend-Modultests: 112 bestanden, 0 fehlgeschlagen.
- TypeScript-Prüfung: bestanden.
- Produktionsbuild: bestanden; Ausgabe in ein separates temporäres Verzeichnis, vorhandener Release-Ordner nicht überschrieben.
- Python-Suite mit deaktiviertem dotenv-Laden: 419 bestanden, 1 fehlgeschlagen. Der Test test_public_ui_does_not_expose_protected_elo_sync_control liest die nicht mehr existierende Sidebar.tsx. Er prüft dadurch die aktuelle Navigation nicht.
- Normaler Python-Lauf: 416 bestanden, 4 fehlgeschlagen. Drei zusätzliche Fehler hängen mit dem Einlesen der vorhandenen lokalen Konfiguration und dem dadurch ausgelösten Netzwerk-/Credential-Pfad zusammen; dies sind keine drei zusätzlich bestätigten Produktfehler. Tests sollten vom lokalen Konfigurationsbestand isoliert sein.
- Bestehende Browser-E2E-Suite nicht erneut ausgeführt. Lokale Tests beweisen weder die veröffentlichte Schreibfunktion noch die langfristige Datenaktualisierung.

Die bestandenen Tests erkennen den Dixon-Coles-Fehler nicht: Die vorhandenen Matrix-Tests prüfen unter anderem Form, Wertebereich und qualitative Änderung der niedrigen Ergebnisse, aber nicht die korrekten asymmetrischen Faktoren. Auch die falsche Mannschaftskategorie wird durch die bestehende Suite nicht verhindert.

## Empfohlene Reihenfolge

1. UCL-Mannschaftszuordnung anhand stabiler Identitäten und Wettbewerb/Kategorie korrigieren; betroffene Formdaten danach kontrolliert neu aufbauen.
2. Dixon-Coles an beiden Stellen korrigieren und mit asymmetrischen Beispielen absichern; gespeicherte Vorab-Prognosen als historischen Modellstand erhalten.
3. Paarungsspezifische K.-o.-Wahrscheinlichkeiten für UCL statt eines allgemeinen Durchschnitts verwenden; Titelchancen bis dahin entsprechend begrenzen.
4. Aktualisierung und Vorab-Erfassung nachweisbar überwachen; alte Eingaben auch in Radar, Assistent und Modell-Markt-Ansicht sichtbar machen.
5. Langsame Listen und Simulation messen und optimieren; klare Warte-/Fehlergrenzen für Anfragen ergänzen.
6. Lokalen und veröffentlichten Stand angleichen, veralteten Navigationstest ersetzen und die relevanten Bedienwege mit kontrollierten Testdaten prüfen.
7. Danach Tabs, wiederholte Vergleichsblöcke und Diagrammachsen vereinfachen.

Diese Untersuchung ändert keine App-Funktion und veröffentlicht keine Änderungen.
