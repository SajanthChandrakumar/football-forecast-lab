# Startseite und Datenübersicht schneller laden

## Diagnose vom 25. Oktober 2026

Die Nutzerklärung priorisiert die Startseite. Alle Messungen sind öffentliche, ausschließlich lesende HTTP-Aufrufe an die veröffentlichte Anwendung; keine Anbieteraktualisierung wurde ausgelöst.

| Abruf | Beobachtete Dauer | Befund |
| --- | ---: | --- |
| Serverstatus | 0,42 s | Server bereits erreichbar |
| PL-Spiele, vollständige Antwort | 41,29 s | 8,65 MB JSON, 1,41 MB komprimiert |
| UCL-Spiele, vollständige Antwort | Abbruch nach 45 s | Keine Antwort im Messfenster |
| PL-Archiv | 17,48 s | 1,97 MB JSON, zusätzlich beim Start geladen |
| PL-Tabelle | 0,12 s | Kein wesentlicher Engpass |
| API-Datenübersicht | 10,88 s; wiederholt 6,80 s | Viele aufeinanderfolgende Datenbankabfragen |

Server-Timing der PL-Spiele: 26,05 s Cache lesen, 7,00 s Formdaten ergänzen, 5,40 s Spielinformationen ergänzen, 0,70 s Archivabgleich, 1,29 s serialisieren. Die Startseite benötigt die umfangreichen Analysedaten nicht. Detailansicht und Teamvergleich benötigen sie weiterhin.

## Umsetzung

1. Nur für PL/UCL eine optionale `overview=true`-Antwort ergänzen. Die Datenbankprojektion lässt Form, Aufstellungen und umfangreiche Buchmacherdaten aus. Matrizen bleiben für die vorhandene Prüfung der gespeicherten Modellberechnung erhalten und werden erst danach aus der Übersicht entfernt. Keine neue Berechnung, keine Anbieteraufrufe, keine Schreibvorgänge.
2. Den vorhandenen Archivabgleich für eingefrorene Tipps und die Quellendatierung erhalten. Ohne Cache bleibt die Antwort ehrlich nicht verfügbar. Der bisherige vollständige Endpunkt und die WM bleiben unverändert.
3. Die Startseite und ihre Wappenverwaltung verwenden dieselbe Übersicht. Vollständige Analysedaten erhalten einen getrennten Abfrageschlüssel; bestehende Invalidierungen bleiben wirksam. Nach „Gespeicherte Daten neu laden“ die Übersicht ausdrücklich ebenfalls aktualisieren.
4. Das PL-/UCL-Archiv erst für offene gemeinsame Tipps oder den aktiven Assistenten laden. Unbekannte Tippanzahl bis dahin nicht als null ausgeben. Bereits besuchte, ausgeblendete Assistenten stoppen ihren Archivabruf.
5. Übersichtsantworten als `detail_level: overview` kennzeichnen. Die Oberfläche verweist für Aufstellungen auf die Spieldetails und behauptet keinen fehlenden Datenbestand.
6. Auf der API-Seite keine unbenutzten Saisonlisten für Wappen laden. Die Statusabfragen mit schmalen Projektionen bündeln: ein Metadatenabruf, ein begrenzter Aufstellungsstatusabruf, ein globaler Kontingentabruf. Anbieterrestkontingente und App-Verbrauch weiterhin getrennt behandeln; Priorität von scoped IDs, Altdaten und Fehleranzeigen erhalten.

## Prüfung und Veröffentlichung

- Reproduzierbare fehlgeschlagene Prüfungen für unnötige Startabrufe, Übersichtsinvalidation, unveränderte Eingaben und Metadatenabfragezahl; danach erfolgreiche Wiederholung.
- Gesamte Backend- und Frontendsuite, Typprüfung, Lint, Build und Browserfälle bei 375, 390, 768, 1024 und 1440 Pixeln. Unabhängige Reviews mit Luna xhigh.
- Nur diese Änderungen und den geprüften Build veröffentlichen; ursprünglichen schmutzigen Checkout und den vorhandenen fremden Abnahmebericht unverändert erhalten.
- Nach Veröffentlichung Revision und ausgelieferte Dateien prüfen und öffentliche Startseitenabrufe erneut messen. Lokale Fixture-Browsertests und echte HTTP-Messungen getrennt ausweisen; Live-Sichtprüfung bleibt auf Nutzerwunsch ausgesetzt.
- Keine produktiven Schreibtests, Formbereinigung oder Anbieteraktualisierung. Keine neue Abhängigkeit, Kosten, längeren Zeitgrenzen oder zusätzliche Modellgewichtung. Aufwachzeiten des kostenlosen Hostings bleiben möglich.

## Lokaler Abnahmestand

551 Backendtests und 131 Frontendtests bestanden. Typprüfung und Produktionsbuild bestanden. Lint ohne Fehler, mit fünf bereits vorhandenen Fast-Refresh-Warnungen. Die gesamte Browser-Suite bestand mit 459 erfolgreichen und 21 gezielt übersprungenen Fällen über fünf Bildschirmgrößen. Unabhängige Luna-xhigh-Reviews für Statusabfragen, Backend-Übersicht und Frontend sind freigegeben. Produktive Antwortzeiten werden erst nach Veröffentlichung erneut gemessen; die lokalen Tests sind keine Live-Sichtprüfung.
