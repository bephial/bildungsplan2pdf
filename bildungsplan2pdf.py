#!/usr/bin/env python3
"""
bildungsplan2pdf.py – Wandelt eine Fachseite von www.bildungsplaene-bw.de
(neue Darstellung, Bildungsplan V3.0) in ein gut lesbares PDF um.

Aufruf:
    python bildungsplan2pdf.py "<URL>"                  -> PDF mit automatischem Namen
    python bildungsplan2pdf.py "<URL>" -o geo.pdf
    python bildungsplan2pdf.py "<URL>" --ohne-verweise   -> ohne P/L/F/I/D-Verweise
    python bildungsplan2pdf.py "<URL>" --html geo.html   -> zusätzlich aufbereitetes HTML speichern
    python bildungsplan2pdf.py seite.html                 -> lokal gespeicherte Seite verarbeiten

Wichtig: Die URL in Anführungszeichen setzen (sie enthält Klammern und Kommas).

Voraussetzungen:
    pip install requests beautifulsoup4
    und WeasyPrint auf EINEM dieser Wege:
      brew install weasyprint                    (Skript nutzt dann das Programm)
      conda install -c conda-forge weasyprint    (als Python-Modul in Anaconda)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

SITE = "https://www.bildungsplaene-bw.de/,Lde/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 bildungsplan2pdf"
)

# Verweis-Boxen unter den Teilkompetenzen (Buchstabe -> Beschriftung)
REF_LABELS = {
    "p": "Prozessbezogene Kompetenzen",
    "i": "Bezüge im Fach",
    "f": "Andere Fächer",
    "l": "Leitperspektiven",
    "d": "Demokratiebildung",
}
REF_ORDER = ["p", "i", "f", "l", "d"]

INLINE_KEEP = {"br", "b", "strong", "i", "em", "sup", "sub", "u", "a", "code"}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"})


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def has_class(el: Tag, *names: str) -> bool:
    classes = el.get("class") or []
    return any(n in classes for n in names)


def class_contains(el: Tag, fragment: str) -> bool:
    return any(fragment in c for c in (el.get("class") or []))


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def plain(el: Tag | str) -> str:
    """Reiner Text ohne weiche Trennstriche."""
    text = el if isinstance(el, str) else el.get_text(" ")
    return norm_ws(text.replace("­", ""))


def anchor_id(raw: str) -> str:
    """'3.1.2.1(4)' -> 'bp-3-1-2-1-4' (sichere ID für PDF-Sprungmarken)."""
    return "bp-" + re.sub(r"[^0-9A-Za-z]+", "-", unquote(raw)).strip("-")


def esc(text: str) -> str:
    return html.escape(text, quote=True)


# --------------------------------------------------------------------------- #
# Einfache Umsetzung von MathJax-Formeln \( … \) in Unicode-Text
# (WeasyPrint kann kein MathJax; für die kurzen Formeln der Bildungspläne reicht das)
# --------------------------------------------------------------------------- #
TEX_SYMBOLS = {
    r"\mathbb{N}": "ℕ", r"\mathbb{Z}": "ℤ", r"\mathbb{Q}": "ℚ", r"\mathbb{R}": "ℝ", r"\mathbb{C}": "ℂ",
    r"\cdot": "·", r"\times": "×", r"\div": "÷", r"\pm": "±", r"\mp": "∓", r"\leq": "≤", r"\le": "≤",
    r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠", r"\approx": "≈", r"\infty": "∞",
    r"\in": "∈", r"\notin": "∉", r"\subseteq": "⊆", r"\subset": "⊂", r"\cup": "∪", r"\cap": "∩",
    r"\setminus": "∖", r"\emptyset": "∅", r"\varnothing": "∅", r"\Rightarrow": "⇒", r"\Leftrightarrow": "⇔",
    r"\rightarrow": "→", r"\to": "→", r"\mapsto": "↦", r"\sqrt": "√", r"\pi": "π", r"\alpha": "α",
    r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\Delta": "Δ", r"\varepsilon": "ε", r"\epsilon": "ε",
    r"\lambda": "λ", r"\mu": "μ", r"\sigma": "σ", r"\varphi": "φ", r"\phi": "φ", r"\omega": "ω",
    r"\Omega": "Ω", r"\sum": "∑", r"\int": "∫", r"\degree": "°", r"\circ": "°", r"\perp": "⊥",
    r"\parallel": "∥", r"\angle": "∠", r"\overline": "", r"\vec": "", r"\left": "", r"\right": "",
    r"\,": " ", r"\;": " ", r"\!": "", r"\quad": "  ", r"\ ": " ", r"\{": "{", r"\}": "}",
}
_TEX_INLINE = re.compile(r"\\\((.+?)\\\)|\\\[(.+?)\\\]", re.S)


def _tex_to_unicode(tex: str) -> str:
    t = tex.strip()
    t = re.sub(r"\\(?:text|mathrm|mathit|mathbf|operatorname)\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = re.sub(r"\(([A-Za-z0-9.,]+)\)/", r"\1/", t)
    t = re.sub(r"/\(([A-Za-z0-9.,]+)\)", r"/\1", t)
    t = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", t)
    for k in sorted(TEX_SYMBOLS, key=len, reverse=True):
        t = t.replace(k, TEX_SYMBOLS[k])
    t = esc(t)
    # Hoch- und Tiefstellungen
    t = re.sub(r"\^\{([^{}]*)\}", r"<sup>\1</sup>", t)
    t = re.sub(r"\^(\S)", r"<sup>\1</sup>", t)
    t = re.sub(r"_\{([^{}]*)\}", r"<sub>\1</sub>", t)
    t = re.sub(r"_(\S)", r"<sub>\1</sub>", t)
    t = t.replace("{", "").replace("}", "")
    return t


def tex_to_html(text: str) -> str:
    """Escaped Text; MathJax-Formeln werden in Unicode umgesetzt."""
    if "\\(" not in text and "\\[" not in text:
        return esc(text)
    out, pos = [], 0
    for m in _TEX_INLINE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        out.append(f'<span class="math">{_tex_to_unicode(m.group(1) or m.group(2))}</span>')
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


# --------------------------------------------------------------------------- #
# Umwandlung
# --------------------------------------------------------------------------- #
class Converter:
    def __init__(self, soup: BeautifulSoup, page_url: str, with_refs: bool = True):
        self.soup = soup
        self.page_url = page_url
        self.with_refs = with_refs
        self.toc: list[tuple[int, str, str]] = []  # (Ebene, Anker, Titel)
        self._auto = 0
        # Alle IDs, die im Dokument vorkommen -> interne Links nur auf diese
        self.known_ids = {anchor_id(t["id"]) for t in soup.find_all(id=True)}

    # ---------- Inline-Inhalte ---------------------------------------------
    def inline(self, el: Tag) -> str:
        """Gibt bereinigtes Inline-HTML des Inhalts von el zurück."""
        out: list[str] = []
        for node in el.children:
            out.append(self._inline_node(node))
        return re.sub(r"\s+", " ", "".join(out)).strip()

    def _inline_node(self, node) -> str:
        if isinstance(node, NavigableString):
            if node.__class__.__name__ in ("Comment", "Doctype", "Declaration"):
                return ""
            return tex_to_html(str(node))
        if not isinstance(node, Tag):
            return ""
        name = node.name
        if name in ("script", "style", "svg", "button", "noscript"):
            return ""
        if name == "br":
            return "<br>"
        inner = "".join(self._inline_node(c) for c in node.children)
        if name == "span" and class_contains(node, "bold"):
            return f"<strong>{inner}</strong>"
        if name == "span" and class_contains(node, "italic") and not class_contains(node, "bold"):
            return f"<em>{inner}</em>"
        if name == "span" and has_class(node, "semantic-bpbw-fachbegriff"):
            return f'<em class="fb">{inner}</em>'
        if name == "span" and has_class(node, "superscript"):
            return f"<sup>{inner}</sup>"
        if name == "span" and has_class(node, "subscript"):
            return f"<sub>{inner}</sub>"
        if name == "a":
            href = self.link(node.get("href", ""))
            return f'<a href="{esc(href)}">{inner}</a>' if href else inner
        if name in INLINE_KEEP:
            return f"<{name}>{inner}</{name}>"
        if name in ("p", "div", "li"):  # verschachtelte Blöcke im Inline-Kontext
            return inner + " "
        return inner

    def link(self, href: str) -> str:
        if not href or href.startswith(("javascript:", "mailto:")):
            return href if href.startswith("mailto:") else ""
        if href.startswith("#"):
            aid = anchor_id(href[1:])
            return "#" + aid if aid in self.known_ids else ""
        return urljoin(self.page_url, href)

    # ---------- Überschriften ----------------------------------------------
    def heading(self, level: int, text_html: str, raw_id: str | None) -> str:
        level = max(1, min(level, 5))
        if raw_id:
            aid = anchor_id(raw_id)
        else:
            self._auto += 1
            aid = f"auto-{self._auto}"
        title = plain(BeautifulSoup(text_html, "html.parser"))
        if level <= 3:
            self.toc.append((level, aid, title))
        return f'<h{level} id="{aid}">{text_html}</h{level}>\n'

    # ---------- Blöcke -------------------------------------------------------
    def blocks(self, container: Tag) -> str:
        out: list[str] = []
        for child in container.children:
            if isinstance(child, NavigableString):
                txt = str(child).strip()
                if txt and child.__class__.__name__ == "NavigableString":
                    out.append(f"<p>{esc(txt)}</p>")
                continue
            if isinstance(child, Tag):
                out.append(self.block(child))
        return "".join(out)

    def block(self, el: Tag) -> str:
        name = el.name
        if name in ("script", "style", "svg", "button", "nav", "noscript", "form", "input"):
            return ""

        # Kapitel (Akkordeon)
        if name == "article" and has_class(el, "accordion__item"):
            return self.chapter(el)
        if name == "h3" and has_class(el, "accordion__header"):
            label = el.select_one(".accordion__toggle-label") or el
            return self.heading(1, self.inline(label), el.get("id"))

        # Überschriften h1–h6 innerhalb des Inhalts: h4->2, h5->3, h6->4
        if re.fullmatch(r"h[1-6]", name):
            lvl = max(2, int(name[1]) - 2)
            return self.heading(lvl, self.inline(el), el.get("id"))

        # Kompetenz-Tabellen & normale Tabellen
        if name == "section" and has_class(el, "table"):
            return self.table_section(el)
        if name == "table":
            if has_class(el, "bp_allg_content_item_table_bpx"):
                return self.competency_table(el)
            return self.generic_table(el)

        # Grafiken
        if name == "figure":
            return self.figure(el)

        if class_contains(el, "nlist_headline"):
            return f'<p class="blockhead">{self.inline(el)}</p>\n'

        # Textblöcke
        if name == "p":
            txt = self.inline(el)
            if not txt:
                return ""
            cls = ' class="blockhead"' if class_contains(el, "block-headline") else ""
            return f"<p{cls}>{txt}</p>\n"
        if name in ("ul", "ol"):
            return self.list_(el)

        # Container: rekursiv
        if name in ("div", "section", "article", "main", "picture", "aside", "header", "footer", "span"):
            if name == "span":
                txt = self.inline(el)
                return f"<p>{txt}</p>\n" if txt else ""
            return self.blocks(el)

        txt = self.inline(el)
        return f"<p>{txt}</p>\n" if txt else ""

    def chapter(self, art: Tag) -> str:
        out = ['<section class="chapter">\n']
        header = art.find(class_="accordion__header")
        if header:
            out.append(self.block(header))
        content = art.find(class_="accordion__content")
        out.append(self.blocks(content if content else art))
        out.append("</section>\n")
        return "".join(out)

    def list_(self, el: Tag) -> str:
        items = []
        for li in el.find_all("li", recursive=False):
            nested = "".join(self.list_(sub) for sub in li.find_all(["ul", "ol"], recursive=False))
            for sub in li.find_all(["ul", "ol"], recursive=False):
                sub.extract()
            items.append(f"<li>{self.inline(li)}{nested}</li>")
        if not items:
            return ""
        return f"<{el.name}>{''.join(items)}</{el.name}>\n"

    def figure(self, fig: Tag) -> str:
        img = fig.find("img")
        src = None
        if img:
            # größte verfügbare Auflösung bevorzugen
            cands: list[tuple[int, str]] = []
            for s in fig.find_all("source"):
                try:
                    cands.append((int(s.get("width", 0)), s.get("srcset", "").split()[0]))
                except (ValueError, IndexError):
                    pass
            for part in (img.get("srcset") or "").split(","):
                bits = part.split()
                if len(bits) == 2 and bits[1].endswith("w"):
                    cands.append((int(bits[1][:-1]), bits[0]))
            cands = [c for c in cands if c[1]]
            src = max(cands)[1] if cands else img.get("src")
        cap = fig.find("figcaption")
        cpr = fig.select_one(".copyright__text")
        out = ['<figure>']
        if src:
            alt = esc(img.get("alt", ""))
            out.append(f'<img src="{esc(urljoin(self.page_url, src))}" alt="{alt}">')
        if cap:
            out.append(f"<figcaption>{self.inline(cap)}</figcaption>")
        if cpr:
            out.append(f'<div class="copyright">© {self.inline(cpr)}</div>')
        out.append("</figure>\n")
        return "".join(out)

    # ---------- Tabellen -----------------------------------------------------
    def table_section(self, sec: Tag) -> str:
        out = []
        head = sec.find(class_="bp_allg_content_table_headline_bpx")
        if head and plain(head):
            out.append(f'<p class="tablecaption">{self.inline(head)}</p>')
        for tbl in sec.find_all("table"):
            out.append(self.block(tbl))
        return "".join(out)

    def competency_table(self, tbl: Tag) -> str:
        """Teilkompetenzen '(1) …' mit Verweisen, Zwischenüberschriften und Hinweisen."""
        out = ['<div class="kt">']
        th = tbl.find("th")
        if th and plain(th):
            out.append(f'<div class="kt-head">{self.inline(th)}</div>')

        entries: list[dict] = []          # in Reihenfolge der Tabelle
        last_item: dict | None = None     # Teilkompetenz, zu der folgende Verweise gehören
        for tr in tbl.find_all("tr"):
            if tr.find_parent("thead") or tr.find_parent("table") is not tbl:
                continue
            cls = " ".join(tr.get("class") or [])
            if "table_item_bpx" in cls:
                nr = tr.select_one(".text-number")
                bullet = tr.select_one(".text-bullet")
                body = tr.select_one(".text-body") or tr
                last_item = {
                    "type": "item",
                    "id": anchor_id(tr["id"]) if tr.get("id") else "",
                    "nr": plain(nr) if nr else ("•" if bullet is not None else ""),
                    "body": self.blocks(body),
                    "refs": "",
                }
                entries.append(last_item)
            elif "table_level_bpx" in cls:
                refs = self.references(tr) if self.with_refs else ""
                if not refs:
                    continue
                if last_item is not None:
                    last_item["refs"] += refs
                else:  # z. B. „Verweise für alle Teilkompetenzen“
                    entries.append({"type": "html", "html": f'<div class="kt-allrefs">{refs}</div>'})
            elif "reference_headline" in cls:
                last_item = None
                if self.with_refs:
                    entries.append({"type": "html",
                                    "html": f'<div class="kt-subhead">{self.inline(tr.find("td") or tr)}</div>'})
            elif "subhead" in cls:
                last_item = None
                entries.append({"type": "html",
                                "html": f'<div class="kt-subhead">{self.inline(tr.find("td") or tr)}</div>'})
            elif "notes_headline" in cls:
                entries.append({"type": "html",
                                "html": f'<div class="kt-notes-head">{self.inline(tr.find("td") or tr)}</div>'})
            elif "notes_text" in cls:
                entries.append({"type": "html",
                                "html": f'<div class="kt-notes">{self.blocks(tr.find("td") or tr)}</div>'})
            elif plain(tr):  # unbekannte Zeilenart: Inhalt trotzdem übernehmen
                entries.append({"type": "html", "html": f'<div class="kt-notes">{self.blocks(tr)}</div>'})

        for e in entries:
            if e["type"] == "item":
                idattr = f' id="{e["id"]}"' if e["id"] else ""
                out.append(
                    f'<div class="kt-item"{idattr}><div class="kt-nr">{esc(e["nr"])}</div>'
                    f'<div class="kt-body">{e["body"]}{e["refs"]}</div></div>'
                )
            else:
                out.append(e["html"])
        out.append("</div>\n")
        return "".join(out)

    def references(self, tr: Tag) -> str:
        boxes = {}
        for box in tr.select(".references_boxes .box"):
            kind = next((c[5:] for c in box.get("class", []) if c.startswith("box--")), "?")
            entries = []
            for li in box.select(".box-content li"):
                entries.append(self.inline(li))
            if entries:
                boxes.setdefault(kind, []).extend(entries)
        if not boxes:
            return ""
        rows = []
        for kind in REF_ORDER + [k for k in boxes if k not in REF_ORDER]:
            if kind not in boxes:
                continue
            label = REF_LABELS.get(kind, kind.upper())
            rows.append(
                f'<div class="ref"><span class="ref-tag ref-{esc(kind)}" title="{esc(label)}">'
                f'{esc(kind.upper())}</span><span class="ref-list">{" · ".join(boxes[kind])}</span></div>'
            )
        return f'<div class="refs">{"".join(rows)}</div>'

    def generic_table(self, tbl: Tag) -> str:
        out = ['<table class="gt">']
        thead = tbl.find("thead")
        if thead:
            out.append("<thead>")
            for tr in thead.find_all("tr"):
                out.append("<tr>" + "".join(
                    f"<th>{self.cell(c)}</th>" for c in tr.find_all(["th", "td"], recursive=False)
                ) + "</tr>")
            out.append("</thead>")
        out.append("<tbody>")
        for tr in tbl.find_all("tr"):
            if tr.find_parent("thead") or tr.find_parent("table") is not tbl:
                continue
            cells = []
            for c in tr.find_all(["th", "td"], recursive=False):
                tag = c.name
                span = ""
                for attr in ("colspan", "rowspan"):
                    if c.get(attr):
                        span += f' {attr}="{esc(c[attr])}"'
                cells.append(f"<{tag}{span}>{self.cell(c)}</{tag}>")
            out.append("<tr>" + "".join(cells) + "</tr>")
        out.append("</tbody></table>\n")
        return "".join(out)

    def cell(self, c: Tag) -> str:
        inner = self.blocks(c)
        # Einzelnen Absatz ohne <p> ausgeben (kompakter)
        m = re.fullmatch(r"\s*<p>(.*)</p>\s*", inner, flags=re.S)
        if m and "<p" not in m.group(1):
            return m.group(1)
        return inner


# --------------------------------------------------------------------------- #
# Dokument zusammenbauen
# --------------------------------------------------------------------------- #
CSS = r"""
@page {
  size: A4;
  margin: 22mm 18mm 20mm 20mm;
  @top-left   { content: string(fach); font-size: 8pt; color: #666; }
  @top-right  { content: string(kapitel); font-size: 8pt; color: #666; }
  @bottom-left  { content: string(fassung); font-size: 7.5pt; color: #888; }
  @bottom-right { content: "Seite " counter(page) " von " counter(pages); font-size: 8pt; color: #666; }
}
@page :first { @top-left { content: none; } @top-right { content: none; } @bottom-left { content: none; } @bottom-right { content: none; } }
@page toc { @top-right { content: "Inhaltsverzeichnis"; font-size: 8pt; color: #666; } }

html { font-family: "Source Sans 3", "Source Sans Pro", "Noto Sans", "DejaVu Sans", Arial, sans-serif;
       font-size: 10pt; line-height: 1.4; color: #1a1a1a; }
body { margin: 0; }
p { margin: 0 0 0.5em; text-align: justify; hyphens: manual; orphans: 3; widows: 3; }
a { color: #0b4f8a; text-decoration: none; }
em.fb { color: #005ea5; }
.math { font-family: "DejaVu Serif", "Cambria Math", "STIX Two Math", serif; white-space: nowrap; }

/* Titelseite */
.titlepage { break-after: page; }
.titlepage .kicker { margin-top: 50mm; font-size: 11pt; letter-spacing: 0.06em; text-transform: uppercase; color: #0b4f8a; }
.titlepage .fach { font-size: 32pt; font-weight: bold; margin: 6mm 0 4mm; line-height: 1.1; string-set: fach content(); }
.titlepage .fassung { font-size: 12pt; color: #333; string-set: fassung content(); }
.titlepage .quelle { margin-top: 60mm; font-size: 8pt; color: #666; line-height: 1.5; }
.titlepage .quelle a { word-break: break-all; }
.titlepage .bar { width: 30mm; height: 2mm; background: #0b4f8a; margin-top: 8mm; }

/* Inhaltsverzeichnis */
nav.toc { page: toc; break-after: page; }
nav.toc h1.tochead { font-size: 18pt; margin: 0 0 6mm; border: 0; }
nav.toc ul { list-style: none; margin: 0; padding: 0; }
nav.toc li { margin: 0; }
nav.toc li.l1 { font-weight: bold; margin-top: 3.5mm; }
nav.toc li.l2 { padding-left: 6mm; margin-top: 1mm; }
nav.toc li.l3 { padding-left: 12mm; font-size: 9pt; color: #333; }
nav.toc a { color: inherit; }
nav.toc a::after { content: leader('.') target-counter(attr(href), page); }

/* Überschriften */
h1, h2, h3, h4, h5 { hyphens: manual; break-after: avoid; line-height: 1.2; }
h1 { font-size: 17pt; color: #0b4f8a; margin: 0 0 5mm; padding-bottom: 2mm; border-bottom: 1.5pt solid #0b4f8a;
     string-set: kapitel content(); }
section.chapter { break-before: page; }
h2 { font-size: 13pt; margin: 7mm 0 2.5mm; color: #0b4f8a; }
h3 { font-size: 11.5pt; margin: 6mm 0 2mm; }
h4 { font-size: 10.5pt; margin: 5mm 0 1.5mm; }
h5 { font-size: 10pt; margin: 4mm 0 1mm; font-style: italic; }
p.blockhead { font-weight: bold; margin-top: 3mm; }
ul, ol { margin: 0 0 0.6em; padding-left: 5mm; }
li { margin-bottom: 0.2em; }

/* Kompetenzlisten */
.kt { margin: 2mm 0 4mm; border-left: 2.5pt solid #0b4f8a; padding-left: 3mm; }
.kt-head { font-weight: bold; color: #0b4f8a; margin-bottom: 1.5mm; break-after: avoid; }
.kt-item { margin: 0 0 2mm; break-inside: avoid; }
.kt-nr { float: left; width: 8mm; font-weight: bold; }
.kt-body { margin-left: 8mm; }
.kt-body p { margin-bottom: 0.25em; text-align: left; }
.kt-subhead { font-weight: bold; margin: 3mm 0 1.5mm; break-after: avoid; }
.kt-allrefs { margin: 0 0 2mm 8mm; }
.kt-allrefs .refs { margin-top: 0; }
.kt-notes-head { font-weight: bold; margin-top: 3mm; break-after: avoid; }
.kt-notes { background: #f3f6f9; padding: 1.5mm 2.5mm; margin-top: 1mm; font-size: 9.5pt; }

/* Verweise */
.refs { margin: 0.8mm 0 0; font-size: 7.8pt; line-height: 1.3; color: #444; }
.ref { margin: 0.4mm 0; padding-left: 5.5mm; text-indent: -5.5mm; }
.ref-tag { display: inline-block; width: 3.4mm; text-indent: 0; text-align: center; font-weight: bold; color: #fff;
           border-radius: 0.6mm; margin-right: 2mm; font-size: 7pt; line-height: 1.35; }
.ref-p { background: #0b4f8a; } .ref-i { background: #5a7d2a; } .ref-f { background: #8a5a0b; }
.ref-l { background: #7a2a6a; } .ref-d { background: #b03030; }
.ref-list a { color: #444; }

/* Legende */
.legend { font-size: 8.5pt; margin-top: 8mm; }
.legend .ref { padding-left: 6mm; }

/* Tabellen */
table.gt { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 9pt; }
table.gt th, table.gt td { border: 0.5pt solid #b8c4cf; padding: 1.2mm 1.8mm; vertical-align: top; text-align: left; }
table.gt th { background: #e6eef5; }
table.gt thead { display: table-header-group; }
table.gt tr { break-inside: avoid; }
table.gt p { margin: 0 0 0.2em; text-align: left; }
p.tablecaption { font-weight: bold; }

/* Grafiken */
figure { margin: 4mm 0; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 150mm; }
figcaption { font-size: 9pt; font-style: italic; margin-top: 1.5mm; }
.copyright { font-size: 7pt; color: #888; }
"""


def build_html(soup: BeautifulSoup, page_url: str, with_refs: bool) -> tuple[str, str]:
    root = soup.select_one(".composedcontent-ls_bp_allg_bildungsplan_bpx") or soup.select_one("main") or soup.body
    if root is None:
        raise SystemExit("Fehler: Kein Inhalt auf der Seite gefunden.")

    # Kopf: Fach und Fassung
    header = root.select_one(".bp_allg-header h1") or soup.find("h1")
    fach, fassung = "", ""
    if header:
        parts = [plain(d) for d in header.find_all("div", recursive=False)] or [plain(header)]
        fach = parts[0] if parts else ""
        fassung = " ".join(parts[1:])
    if not fach:
        fach = plain(soup.title or "") or "Bildungsplan"

    # Schulart aus der Brotkrumen-Navigation, z. B. „Bildungsplan des Gymnasiums“
    kicker = ""
    crumbs = [plain(li) for li in soup.select("ol.breadcrumb__list li")]
    for c in reversed(crumbs):
        if c.lower().startswith("bildungsplan"):
            kicker = c
            break
    if not kicker:
        kicker = "Bildungsplan Baden-Württemberg"

    conv = Converter(soup, page_url, with_refs=with_refs)
    body_root = root.select_one("#textcontent") or root
    if header:
        hdr = header.find_parent(class_="bp_allg-header")
        if hdr and body_root is root:
            hdr.extract()
    body = conv.blocks(body_root)

    # Inhaltsverzeichnis
    toc_items = "".join(
        f'<li class="l{lvl}"><a href="#{aid}">{esc(title)}</a></li>' for lvl, aid, title in conv.toc
    )
    legend = ""
    if with_refs:
        legend = '<div class="legend"><p><strong>Verweise unter den Teilkompetenzen:</strong></p>' + "".join(
            f'<div class="ref"><span class="ref-tag ref-{k}">{k.upper()}</span>{esc(REF_LABELS[k])}</div>'
            for k in REF_ORDER
        ) + "</div>"

    today = _dt.date.today().strftime("%d.%m.%Y")
    doc = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>{esc(fach)} – {esc(fassung)}</title>
<style>{CSS}</style></head>
<body>
<div class="titlepage">
  <div class="kicker">{esc(kicker)}</div>
  <div class="fach">{esc(fach)}</div>
  <div class="fassung">{esc(fassung)}</div>
  <div class="bar"></div>
  {legend}
  <div class="quelle">Quelle: <a href="{esc(page_url)}">{esc(page_url)}</a><br>
  Abgerufen und in PDF umgewandelt am {today}. Maßgeblich ist die Online-Fassung.</div>
</div>
<nav class="toc"><h1 class="tochead">Inhalt</h1><ul>{toc_items}</ul></nav>
{body}
</body></html>"""
    safe = re.sub(r"[^\w\-]+", "_", f"Bildungsplan_{fach}_{fassung}").strip("_")
    return doc, safe


def make_url_fetcher():
    """URL-Fetcher für Bilder mit Browser-User-Agent (WeasyPrint alt und neu)."""
    try:  # WeasyPrint >= 66: klassenbasierter Fetcher
        from weasyprint.urls import URLFetcher
        return URLFetcher(timeout=30, http_headers={"User-Agent": USER_AGENT})
    except ImportError:
        from weasyprint import default_url_fetcher

        def fetch(url, timeout=30, ssl_context=None):
            if url.startswith(("http://", "https://")):
                r = SESSION.get(url, timeout=timeout)
                r.raise_for_status()
                return {
                    "string": r.content,
                    "mime_type": r.headers.get("Content-Type", "").split(";")[0] or None,
                    "redirected_url": r.url,
                }
            return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)
        return fetch


def find_weasyprint_cli() -> str | None:
    import shutil
    exe = shutil.which("weasyprint")
    if exe:
        return exe
    for cand in ("/opt/homebrew/bin/weasyprint", "/usr/local/bin/weasyprint"):
        if Path(cand).exists():
            return cand
    return None


def render_with_cli(doc: str, out: Path) -> bool:
    """Erzeugt das PDF mit dem weasyprint-Programm statt mit dem Python-Modul."""
    import subprocess
    import tempfile
    exe = find_weasyprint_cli()
    if not exe:
        return False
    print(f"Python-Modul fehlt – nutze {exe}", file=sys.stderr)
    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as tmp:
        tmp.write(doc)
        tmp_path = tmp.name
    try:
        import os
        # Anaconda-Variablen nicht an das Homebrew-Programm weitergeben
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
        res = subprocess.run([exe, "--encoding", "utf-8", tmp_path, str(out)], env=env)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if res.returncode != 0:
        raise SystemExit(f"weasyprint meldet Fehler (Code {res.returncode}).")
    return True


def load(source: str) -> tuple[str, str]:
    """Gibt (HTML, Basis-URL) zurück – aus dem Netz oder aus einer lokalen Datei."""
    p = Path(source)
    if not source.startswith(("http://", "https://")) and p.exists():
        return p.read_text(encoding="utf-8", errors="replace"), SITE
    if not source.startswith(("http://", "https://")):
        source = "https://" + source
    r = SESSION.get(source, timeout=60)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text, r.url


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Fachseite von bildungsplaene-bw.de als PDF speichern.",
        epilog='Beispiel: python bildungsplan2pdf.py "https://www.bildungsplaene-bw.de/,Lde/'
               'DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_GEO(V3.0)"',
    )
    ap.add_argument("quelle", help="URL der Bildungsplan-Seite (in Anführungszeichen) oder gespeicherte HTML-Datei")
    ap.add_argument("-o", "--output", help="Name der PDF-Datei (Standard: automatisch aus Fach und Fassung)")
    ap.add_argument("--ohne-verweise", action="store_true",
                    help="Verweise (P, I, F, L, D) unter den Teilkompetenzen weglassen")
    ap.add_argument("--html", metavar="DATEI", help="Aufbereitetes HTML zusätzlich speichern")
    args = ap.parse_args(argv)

    print("Lade Seite …", file=sys.stderr)
    try:
        raw, base = load(args.quelle)
    except requests.RequestException as e:
        print(f"Fehler beim Laden: {e}", file=sys.stderr)
        return 1

    soup = BeautifulSoup(raw, "html.parser")
    doc, safe_name = build_html(soup, base, with_refs=not args.ohne_verweise)

    if args.html:
        Path(args.html).write_text(doc, encoding="utf-8")
        print(f"HTML gespeichert: {args.html}", file=sys.stderr)

    out = Path(args.output or f"{safe_name}.pdf")
    print("Erzeuge PDF (kann bei großen Fächern eine Minute dauern) …", file=sys.stderr)
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as e:
        # Fallback: WeasyPrint als Programm (z. B. per Homebrew installiert)
        if not render_with_cli(doc, out):
            print("WeasyPrint wurde weder als Python-Modul noch als Programm gefunden.\n  " + str(e) +
                  "\nLösungen:\n  brew install weasyprint            (Homebrew)\n"
                  "  conda install -c conda-forge weasyprint   (Anaconda)", file=sys.stderr)
            return 2
    else:
        HTML(string=doc, base_url=base, url_fetcher=make_url_fetcher()).write_pdf(out)
    print(f"Fertig: {out.resolve()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
