"""
explain.py
==========
Explicabilité : chaque ligne du devis porte déjà sa formule et son calcul
(produits par pricing.py). Ce module expose la traçabilité des ENTRÉES
(d'où viennent les caractéristiques) et un accès simple aux lignes.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import PricingConfig, resolve_material
from models import PartFeatures
from pricing import CostBreakdown, DerivedGeometry


@dataclass
class Line:
    poste: str
    montant: float
    formule: str
    calcul: str


def _src_label(src: str) -> str:
    return "valeur du plan (IA)" if src == "ia" else "recalculé (géométrie)"


def sources(part: PartFeatures, geo: DerivedGeometry) -> list[str]:
    extr = {"claude_vision": "extraction IA (Claude Vision)",
            "demo": "cas démo pré-extrait",
            "manual": "saisie manuelle"}.get(part.source, part.source)
    mat = resolve_material(part.material)
    mat_line = (f"Matière : {mat['label']} — "
                + ("reconnue dans la base." if mat["known"]
                   else f"inconnue, estimée via famille « {mat['family']} »."))
    return [
        f"Caractéristiques : {extr} — confiance {part.extraction_confidence:.0%}.",
        f"Procédé : {part.process_type}.",
        mat_line,
        f"Surface développée : {geo.developed_surface_m2:.4f} m² "
        f"({_src_label(geo.source_surface)}).",
        f"Longueur de découpe : {geo.cut_length_mm:.0f} mm "
        f"({_src_label(geo.source_cut)}).",
        "Volume / masse : recalculés (surface nette × épaisseur × densité).",
    ]


def explain(part: PartFeatures, cfg: PricingConfig, geo: DerivedGeometry,
            bd: CostBreakdown) -> list[Line]:
    """Détail ligne à ligne = les opérations réellement détectées."""
    return [Line(l.poste, l.montant, l.formule, l.calcul) for l in bd.lines]


def totals_explanation(cfg: PricingConfig, bd: CostBreakdown) -> list[Line]:
    return [
        Line("Coût de revient unitaire", bd.unit_cost,
             "somme des opérations détectées", ""),
        Line("Prix de vente unitaire", bd.unit_price,
             "coût_revient × (1 + marge)",
             f"{bd.unit_cost:.3f} € × (1 + {int(cfg.margin_rate*100)} %)"),
        Line(f"Total ({cfg.quantity} pièces)", bd.total_price,
             "prix_unitaire × quantité",
             f"{bd.unit_price:.3f} € × {cfg.quantity}"),
    ]
