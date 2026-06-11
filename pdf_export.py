"""
pdf_export.py
=============
Génère un devis PDF clair et structuré, reprenant le format de la fiche attendue
(Identification / Matière / Dimensions / Trous / Plis) et ajoutant le détail
chiffré (coûts décomposés + prix de vente).
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)

from config import CURRENCY
from models import PartFeatures
from pricing import CostBreakdown, DerivedGeometry
from brand import BRAND
import explain as _explain

NAVY = colors.HexColor(BRAND["ink"])
LIGHT = colors.HexColor(BRAND["light"])


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H", parent=ss["Heading2"], textColor=NAVY,
                          fontSize=12, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Title2", parent=ss["Title"], textColor=NAVY, fontSize=18))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8,
                          textColor=colors.grey))
    ss.add(ParagraphStyle("Cell", parent=ss["Normal"], fontSize=7, leading=9))
    return ss


def _kv_table(rows, col_widths=(55 * mm, 110 * mm)):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _header_table(rows, widths):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _fmt(x, dec=2):
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def build_pdf(part: PartFeatures, bd: CostBreakdown, geo: DerivedGeometry,
              cfg, quote_number: str | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    ss = _styles()
    el = []
    qn = quote_number or datetime.now().strftime("DV%Y%m%d-%H%M")

    el.append(Paragraph("DEVIS — TÔLERIE / USINAGE", ss["Title2"]))
    el.append(Paragraph(
        f"N° {qn} · Généré le {datetime.now():%d/%m/%Y à %H:%M} · "
        f"Source extraction : {part.source}", ss["Small"]))
    el.append(Spacer(1, 6))

    # Identification
    el.append(Paragraph("Identification", ss["H"]))
    el.append(_kv_table([
        ["Référence", part.reference or "—"],
        ["Désignation", part.designation or "—"],
        ["Procédé", part.process_type or "tôlerie"],
        ["Quantité (série)", str(cfg.quantity)],
    ]))

    # Matière
    el.append(Paragraph("Matière & traitement", ss["H"]))
    el.append(_kv_table([
        ["Matière", cfg.material],
        ["Épaisseur", f"{_fmt(part.thickness_mm,1)} mm"],
        ["Traitement surface", part.surface_treatment or cfg.surface_treatment or "Aucun"],
        ["Note", part.treatment or "—"],
    ]))

    # Dimensions
    el.append(Paragraph("Dimensions & masse", ss["H"]))
    el.append(_kv_table([
        ["Longueur", f"{_fmt(part.length_mm,1)} mm"],
        ["Largeur", f"{_fmt(part.width_mm,1)} mm"],
        ["Surface dév.", f"{_fmt(geo.developed_surface_m2,4)} m² ({geo.source_surface})"],
        ["Longueur découpe", f"{_fmt(geo.cut_length_mm,0)} mm ({geo.source_cut})"],
        ["Volume", f"{_fmt(geo.volume_mm3,0)} mm³"],
        ["Masse estimée", f"{_fmt(geo.mass_g,0)} g ({_fmt(geo.mass_g/1000,3)} kg)"],
    ]))

    # Trous
    if part.holes:
        el.append(Paragraph("Trous / découpes", ss["H"]))
        rows = [["Forme", "Ø (mm)", "Quantité"]]
        rows += [[h.shape, _fmt(h.diameter_mm, 1), str(h.qty)] for h in part.holes]
        el.append(_header_table(rows, [55 * mm, 55 * mm, 55 * mm]))

    # Plis
    if part.bends:
        el.append(Paragraph("Plis", ss["H"]))
        rows = [["Angle", "Rayon (mm)", "Longueur (mm)", "Quantité"]]
        rows += [[f"{_fmt(b.angle_deg,0)}°",
                  _fmt(b.radius_mm, 1) if b.radius_mm else "—",
                  _fmt(b.length_mm, 0) if b.length_mm else "—",
                  str(b.qty)] for b in part.bends]
        el.append(_header_table(rows, [40 * mm, 42 * mm, 42 * mm, 41 * mm]))

    # Décomposition des coûts (opérations détectées dynamiquement)
    el.append(Paragraph("Décomposition du coût (unitaire)", ss["H"]))
    rows = [["Poste", f"Coût ({CURRENCY})"]]
    for ln in bd.lines:
        rows.append([ln.poste, _fmt(ln.montant, 3)])
    rows.append(["Coût de revient unitaire", _fmt(bd.unit_cost, 3)])
    rows.append([f"Marge ({_fmt(cfg.margin_rate*100,0)} %)",
                 _fmt(bd.unit_price - bd.unit_cost, 3)])
    t = _header_table(rows, [110 * mm, 55 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -2), (-1, -2), 0.8, NAVY),
    ]))
    el.append(t)

    # Totaux
    el.append(Spacer(1, 8))
    tot = Table([
        ["PRIX DE VENTE UNITAIRE", f"{_fmt(bd.unit_price,2)} {CURRENCY}"],
        [f"TOTAL ({cfg.quantity} pièces)", f"{_fmt(bd.total_price,2)} {CURRENCY}"],
    ], colWidths=[110 * mm, 55 * mm])
    tot.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    el.append(tot)

    # Explicabilité du calcul
    el.append(Paragraph("Explicabilité du calcul", ss["H"]))
    rows = [["Poste", "Formule", "Calcul"]]
    for ln in _explain.explain(part, cfg, geo, bd):
        rows.append([Paragraph(ln.poste, ss["Cell"]),
                     Paragraph(ln.formule, ss["Cell"]),
                     Paragraph(ln.calcul, ss["Cell"])])
    exp_t = Table(rows, colWidths=[38 * mm, 62 * mm, 65 * mm])
    exp_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    el.append(exp_t)

    el.append(Spacer(1, 10))
    el.append(Paragraph(
        f"Tolérances : {part.tolerances or '—'} · Notes : {part.notes or '—'}",
        ss["Small"]))
    el.append(Paragraph(
        "Devis indicatif généré par outil interne assisté IA. "
        "Extraction des caractéristiques par IA ; calcul de prix déterministe et explicable.",
        ss["Small"]))

    doc.build(el)
    return buf.getvalue()
