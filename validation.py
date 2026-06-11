"""
validation.py
=============
Fiabilité : détection ET correction des incohérences.

Trois lignes de défense :
  1. Validation d'entrée   -> les features extraites par l'IA sont-elles plausibles ?
  2. Cohérence géométrique -> volume ≈ surface × épaisseur, masse ≈ volume × densité
  3. Garde-fous prix       -> le prix de vente ne peut pas être incohérent

Chaque contrôle renvoie un niveau : OK / WARNING / ERROR.
- WARNING : on calcule quand même, mais on signale et on demande validation humaine.
- ERROR   : on bloque ou on corrige automatiquement (recalcul géométrique).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config import SANITY
from models import PartFeatures
from pricing import (
    CostBreakdown, DerivedGeometry, derive_geometry, price_per_kg, density,
)


class Level(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class Check:
    level: Level
    message: str
    field: str = ""


# --------------------------------------------------------------------------- #
#  1. Validation des features extraites                                       #
# --------------------------------------------------------------------------- #
def validate_features(part: PartFeatures) -> list[Check]:
    checks: list[Check] = []
    lo, hi = SANITY["thickness_mm"]
    if not (lo <= part.thickness_mm <= hi):
        checks.append(Check(Level.ERROR,
            f"Épaisseur {part.thickness_mm} mm hors plage [{lo}; {hi}].",
            "thickness_mm"))

    lo, hi = SANITY["dim_mm"]
    for name, val in (("Longueur", part.length_mm), ("Largeur", part.width_mm)):
        if not (lo <= val <= hi):
            checks.append(Check(Level.ERROR,
                f"{name} {val} mm hors plage [{lo}; {hi}].", name.lower()))

    lo, hi = SANITY["hole_diam_mm"]
    for h in part.holes:
        if not (lo <= h.diameter_mm <= hi):
            checks.append(Check(Level.WARNING,
                f"Trou Ø{h.diameter_mm} mm inhabituel (plage [{lo}; {hi}]).", "holes"))
        if h.qty < 1:
            checks.append(Check(Level.ERROR, f"Quantité de trous invalide ({h.qty}).", "holes"))

    if not part.material:
        checks.append(Check(Level.WARNING,
            "Matière non renseignée -> S235 utilisé par défaut, à confirmer.", "material"))

    if part.extraction_confidence < 0.6 and part.source == "claude_vision":
        checks.append(Check(Level.WARNING,
            f"Confiance d'extraction faible ({part.extraction_confidence:.0%}) "
            "-> validation humaine recommandée.", "extraction_confidence"))

    if not checks:
        checks.append(Check(Level.OK, "Caractéristiques cohérentes."))
    return checks


# --------------------------------------------------------------------------- #
#  2. Cohérence géométrique (croise les grandeurs entre elles)                #
# --------------------------------------------------------------------------- #
def check_geometry_coherence(part: PartFeatures,
                             geo: DerivedGeometry) -> list[Check]:
    checks: list[Check] = []

    # surface fournie par l'IA vs géométrie recalculée
    if part.developed_surface_m2 and geo.source_surface == "géométrie":
        checks.append(Check(Level.WARNING,
            f"Surface développée du plan ({part.developed_surface_m2:.4f} m²) "
            f"incohérente avec la géométrie -> recalculée à {geo.developed_surface_m2:.4f} m².",
            "developed_surface_m2"))

    if part.cut_length_mm and geo.source_cut == "géométrie":
        checks.append(Check(Level.WARNING,
            f"Longueur de découpe du plan ({part.cut_length_mm:.0f} mm) "
            f"incohérente -> recalculée à {geo.cut_length_mm:.0f} mm.", "cut_length_mm"))

    # masse fournie vs masse recalculée
    if part.mass_g and geo.mass_g > 0:
        err = abs(part.mass_g - geo.mass_g) / geo.mass_g
        if err > 0.25:
            checks.append(Check(Level.WARNING,
                f"Masse du plan ({part.mass_g:.0f} g) s'écarte de {err:.0%} "
                f"de la masse calculée ({geo.mass_g:.0f} g).", "mass_g"))

    if not checks:
        checks.append(Check(Level.OK, "Grandeurs dérivées cohérentes."))
    return checks


# --------------------------------------------------------------------------- #
#  3. Garde-fous sur le prix                                                  #
# --------------------------------------------------------------------------- #
def check_price_sanity(part: PartFeatures, bd: CostBreakdown,
                       geo: DerivedGeometry) -> list[Check]:
    checks: list[Check] = []

    # le prix de vente ne peut pas être inférieur au coût matière
    if bd.unit_price < bd.material * SANITY["min_margin_over_material"]:
        checks.append(Check(Level.ERROR,
            "Prix de vente unitaire inférieur au coût matière -> calcul à revoir.",
            "unit_price"))

    # prix par kg de pièce finie dans une plage attendue
    if geo.mass_g > 0:
        price_per_kg_part = bd.unit_price / (geo.mass_g / 1000.0)
        lo, hi = SANITY["price_per_kg"]
        if not (lo <= price_per_kg_part <= hi):
            checks.append(Check(Level.WARNING,
                f"Prix au kg de pièce finie {price_per_kg_part:.0f} €/kg hors plage "
                f"usuelle [{lo}; {hi}] -> vérifier quantité / paramètres.", "unit_price"))

    if bd.unit_price <= 0:
        checks.append(Check(Level.ERROR, "Prix unitaire nul ou négatif.", "unit_price"))

    if not checks:
        checks.append(Check(Level.OK, "Prix dans les bornes attendues."))
    return checks


# --------------------------------------------------------------------------- #
#  Synthèse                                                                   #
# --------------------------------------------------------------------------- #
@dataclass
class ValidationReport:
    feature_checks: list[Check]
    geometry_checks: list[Check]
    price_checks: list[Check]

    @property
    def all(self) -> list[Check]:
        return self.feature_checks + self.geometry_checks + self.price_checks

    @property
    def has_error(self) -> bool:
        return any(c.level == Level.ERROR for c in self.all)

    @property
    def has_warning(self) -> bool:
        return any(c.level == Level.WARNING for c in self.all)

    @property
    def status(self) -> Level:
        if self.has_error:
            return Level.ERROR
        if self.has_warning:
            return Level.WARNING
        return Level.OK


def run_full_validation(part: PartFeatures, bd: CostBreakdown,
                        geo: DerivedGeometry) -> ValidationReport:
    return ValidationReport(
        feature_checks=validate_features(part),
        geometry_checks=check_geometry_coherence(part, geo),
        price_checks=check_price_sanity(part, bd, geo),
    )
