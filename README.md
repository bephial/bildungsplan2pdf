# bildungsplan2pdf

Die Fachpläne des Bildungsplans Baden-Württemberg (Fassung V3.0) gibt es auf
[bildungsplaene-bw.de](https://www.bildungsplaene-bw.de) nur noch als Webseite
und nicht mehr als PDF zum Herunterladen. Dieses Python-Skript lädt eine
Fachseite herunter, bereitet den Inhalt für den Druck auf und speichert ihn als
übersichtliches PDF.

## Was im PDF steht

- **Titelseite** mit Fach, Schulart, Fassung, Quell-URL und Abrufdatum sowie
  einer Legende zu den Verweisen
- **Inhaltsverzeichnis** mit Seitenzahlen; jeder Eintrag springt im PDF an die
  passende Stelle
- **Alle Kapitel sind aufgeklappt.** Jedes Hauptkapitel beginnt auf einer neuen
  Seite. Kopf- und Fußzeile zeigen Fach, Kapitel, Fassung und Seitenzahl.
- **Teilkompetenzen** erscheinen als nummerierte Liste, so wie auf der Website,
  mit Zwischenüberschriften und Hinweise-Kästen
- **Verweise**, die auf der Website erst nach einem Klick auf die Symbole
  sichtbar werden, stehen klein unter jeder Teilkompetenz:

  | Kürzel | Bedeutung |
  |---|---|
  | **P** | Prozessbezogene Kompetenzen |
  | **I** | Bezüge zu anderen Standards im selben Fach |
  | **F** | Andere Fächer |
  | **L** | Leitperspektiven |
  | **D** | Demokratiebildung |

  Verweise innerhalb des Fachplans sind im PDF anklickbar und springen an die
  richtige Stelle. Verweise auf andere Fächer und auf die Leitperspektiven
  öffnen die passende Seite auf der Website.
- **Tabellen** wie der Operatorenkatalog und **Grafiken** in bestmöglicher
  Auflösung
- **Fachbegriffe** werden hervorgehoben, wie auf der Website. **Formeln** in
  Mathematik und den Naturwissenschaften werden vereinfacht in Unicode-Zeichen
  umgesetzt (siehe unten).

## Installation

Benötigt wird Python 3.9 oder neuer sowie diese Pakete:

```bash
pip install requests beautifulsoup4
```

Bei Anaconda sind beide Pakete normalerweise schon installiert.

Zusätzlich braucht das Skript [WeasyPrint](https://weasyprint.org), um das PDF
zu erzeugen. Es reicht **einer** der folgenden Wege:

| Umgebung | Befehl |
|---|---|
| macOS mit Homebrew | `brew install weasyprint` |
| Anaconda | `conda install -c conda-forge weasyprint` |
| Normales Python (Linux) | `pip install weasyprint` |

Wenn das Python-Modul `weasyprint` fehlt, nimmt das Skript automatisch das
Programm `weasyprint`, zum Beispiel aus Homebrew. Mit Anaconda und
Homebrew-WeasyPrint funktioniert es also ohne weiteren Aufwand.

> Hinweis: `pip install weasyprint` scheitert auf dem Mac oft daran, dass die
> Grafik-Bibliothek Pango fehlt. Homebrew oder conda-forge bringen sie gleich
> mit.

## Benutzung

```bash
python bildungsplan2pdf.py "<URL der Fachseite>"
```

Beispiel (Geographie, Gymnasium):

```bash
python bildungsplan2pdf.py "https://www.bildungsplaene-bw.de/,Lde/DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_GEO(V3.0)"
```

**Die URL muss in Anführungszeichen stehen**, weil sie Klammern und ein Komma
enthält. Ohne Anführungszeichen bricht die Shell mit einer Fehlermeldung ab.

Das PDF landet im aktuellen Ordner. Der Dateiname wird aus Fach und Fassung
gebildet, zum Beispiel
`Bildungsplan_Geographie_Überarbeitete_Fassung_vom_08._April_2026_V3.0.pdf`.

### Optionen

| Option | Wirkung |
|---|---|
| `-o DATEI.pdf` | Legt Namen und Ort der PDF-Datei fest |
| `--ohne-verweise` | Lässt die P/I/F/L/D-Verweise weg, dadurch wird das PDF kürzer |
| `--html DATEI.html` | Speichert zusätzlich das aufbereitete HTML, etwa zur Kontrolle oder für eigene Anpassungen |
| `-h` | Zeigt die Hilfe an |

Statt einer URL kann man auch eine im Browser gespeicherte HTML-Seite angeben:

```bash
python bildungsplan2pdf.py geographie.html -o geographie.pdf
```

### Mehrere Fächer auf einmal

```bash
for fach in GEO BIO CH PH M D E1; do
  python bildungsplan2pdf.py "https://www.bildungsplaene-bw.de/,Lde/DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_${fach}(V3.0)"
done
```

Die Fachkürzel stehen jeweils am Ende der URL der Fachseite.

## Wie es funktioniert

1. Die Seite wird mit `requests` heruntergeladen. Der komplette Inhalt steckt
   schon im HTML der Seite und muss nicht per JavaScript nachgeladen werden.
2. `BeautifulSoup` liest die Struktur aus: Kapitel (Akkordeons),
   Überschriften, Textblöcke, Listen, Grafiken, Kompetenztabellen mit ihren
   Verweis-Boxen und normale Tabellen. Navigation, Buttons und Symbole werden
   verworfen.
3. Daraus entsteht ein schlankes HTML-Dokument mit eigenem Druck-Layout (CSS
   für A4, Kopf- und Fußzeilen, Inhaltsverzeichnis).
4. WeasyPrint setzt dieses HTML als PDF.

Die weichen Trennstriche der Website bleiben erhalten. Deshalb trennt das PDF
lange deutsche Wörter sauber.

## Grenzen

- **Formeln:** WeasyPrint kann kein MathJax. Einfache Formeln werden umgesetzt,
  zum Beispiel ℕ, ℤ, x², a₁, ≤, ·, √ und Brüche als `a/b`. Aufwendig gesetzte
  Formeln sehen dadurch schlichter aus als auf der Website.
- **Aufbau der Website:** Das Skript richtet sich nach den CSS-Klassen der
  aktuellen Website. Ändert das Land die Seitenstruktur, muss das Skript
  angepasst werden. Unbekannte Inhalte werden möglichst als normaler Text
  übernommen und nicht verworfen.
- **Maßgeblich bleibt die Online-Fassung.** Darauf weist auch die Titelseite des
  PDFs hin.

## Fehlerbehebung

| Problem | Lösung |
|---|---|
| `zsh: no matches found` oder Fehler wegen Klammern | URL in Anführungszeichen setzen |
| `WeasyPrint wurde weder als Python-Modul noch als Programm gefunden` | WeasyPrint wie oben beschrieben installieren |
| `OSError: cannot load library 'libgobject…'` / `libpango…` | Pango fehlt; WeasyPrint über Homebrew oder conda-forge installieren |
| Grafiken fehlen im PDF | Keine Verbindung zur Website während der Erzeugung; Skript erneut starten |
| Fehlermeldung mit `Traceback` bei einem bestimmten Fach | Wahrscheinlich nutzt die Fachseite eine neue Struktur; Fehlermeldung und URL notieren und das Skript anpassen |

Entwickelt anhand der Fachpläne Geographie, Biologie und Englisch (Gymnasium,
V3.0). Mathematik und Deutsch nutzen denselben Seitenaufbau.
