FoodPlan – GitHub + Render
==========================

Dateien im Repository (alle vier im Hauptverzeichnis):
- index.html
- server.py
- requirements.txt
- README.txt

Render Web Service:
- Runtime/Language: Python 3
- Build Command: pip install -r requirements.txt
- Start Command: python server.py
- Der Server nutzt automatisch die Render-Umgebungsvariable PORT und bindet an 0.0.0.0.

Funktionen:
- Kalorien, Makros, Budget und Einkaufsliste
- Öffentliche REWE-Angebote für Syke abrufen versuchen
- REWE-Onlineshop-Produktsuche über den undokumentierten Endpunkt /api/suggestions, mit /api/products als Fallback
- Nährwerte werden optional über Open Food Facts gesucht; bei fehlendem oder unsicherem Treffer fragt der Rechner nach den Nährwerten vom Etikett

Wichtige Grenzen:
- Die REWE-Suchendpunkte sind nicht offiziell dokumentiert und können sich ändern oder Abrufe blockieren.
- Preise im REWE-Onlineshop hängen vom Standort/Abhol- bzw. Liefermarkt ab. Wenn keine Preise zurückkommen, fragt der Rechner nach manueller Eingabe, statt einen Preis zu erfinden.
- Die REWE-Seite für den Markt Syke zeigt Wochenangebote, aber nicht das vollständige Sortiment und keine vollständige Liste aller Regalpreise. REWE selbst sagt, dass Marktbestand nicht online angezeigt wird.
- Open Food Facts ist eine Drittquelle; Nährwerte müssen zum ausgewählten Produkt passen. Prüfe im Zweifel die Verpackung.

Recherchequellen:
https://www.rewe.de/angebote/syke/540502/rewe-hauptstr-56-58-suurend/
https://www.rewe.de/marktseite/syke/540502/rewe-markt-hauptstr-56-58-suurend/
https://shop.rewe.de/
https://world.openfoodfacts.org/
