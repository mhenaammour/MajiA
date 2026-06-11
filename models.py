"""
models.py
=========
Structures de données partagées entre extraction, pricing, validation et export.

PartFeatures est le contrat pivot de l'application : tout ce qui est nécessaire
pour produire un devis. L'IA (Claude Vision) remplit cet objet à partir du plan ;
le moteur de prix le consomme ; la validation le contrôle.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Hole:
    shape: str                 # "rond", "oblong", "carré"...
    diameter_mm: float
    qty: int = 1
    threaded: bool = False     # trou taraudé
    countersunk: bool = False  # trou fraisé / lamé


@dataclass
class Bend:
    angle_deg: float
    radius_mm: Optional[float] = None
    length_mm: Optional[float] = None
    qty: int = 1


@dataclass
class Weld:
    length_mm: float
    qty: int = 1
    kind: str = "cordon"       # type de soudure (cordon, point...)


@dataclass
class Component:
    """Composant rapporté : écrou à sertir, goujon, insert..."""
    designation: str
    qty: int = 1
    unit_price_eur: Optional[float] = None   # None -> prix par défaut config


@dataclass
class PartFeatures:
    """Caractéristiques d'une pièce de tôlerie, extraites d'un plan."""
    # identification
    reference: str = ""
    designation: str = ""

    # procédé global
    process_type: str = "tôlerie"   # "tôlerie" | "usinage" | "mixte"

    # matière & traitement
    material: Optional[str] = None
    grade: Optional[str] = None
    thickness_mm: float = 0.0
    treatment: Optional[str] = None
    surface_treatment: Optional[str] = None   # clé SURFACE_TREATMENTS

    # dimensions
    length_mm: float = 0.0
    width_mm: float = 0.0
    developed_surface_m2: Optional[float] = None
    cut_length_mm: Optional[float] = None
    volume_mm3: Optional[float] = None
    mass_g: Optional[float] = None
    machined_volume_cm3: Optional[float] = None   # matière enlevée (usinage)

    # features
    holes: list[Hole] = field(default_factory=list)
    bends: list[Bend] = field(default_factory=list)
    welds: list[Weld] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)

    # qualité / divers
    tolerances: str = ""
    notes: str = ""

    # méta extraction
    extraction_confidence: float = 0.0     # 0..1
    source: str = "demo"                   # "claude_vision" | "demo" | "manual"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PartFeatures":
        """Construit un PartFeatures en tolérant les null / champs manquants
        que l'IA peut renvoyer (extraction partielle)."""
        def num(v, default=0.0):
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        def opt_num(v):
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        def integer(v, default=1):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        def boolean(v):
            return bool(v) if isinstance(v, bool) else str(v).lower() in ("true", "1", "oui", "yes")

        holes = [Hole(shape=str(h.get("shape") or "rond"),
                      diameter_mm=num(h.get("diameter_mm")),
                      qty=integer(h.get("qty")),
                      threaded=boolean(h.get("threaded")),
                      countersunk=boolean(h.get("countersunk")))
                 for h in (d.get("holes") or [])]
        bends = [Bend(angle_deg=num(b.get("angle_deg")),
                      radius_mm=opt_num(b.get("radius_mm")),
                      length_mm=opt_num(b.get("length_mm")),
                      qty=integer(b.get("qty")))
                 for b in (d.get("bends") or [])]
        welds = [Weld(length_mm=num(w.get("length_mm")),
                      qty=integer(w.get("qty")),
                      kind=str(w.get("kind") or "cordon"))
                 for w in (d.get("welds") or [])]
        comps = [Component(designation=str(c.get("designation") or ""),
                           qty=integer(c.get("qty")),
                           unit_price_eur=opt_num(c.get("unit_price_eur")))
                 for c in (d.get("components") or [])]

        return cls(
            reference=str(d.get("reference") or ""),
            designation=str(d.get("designation") or ""),
            process_type=str(d.get("process_type") or "tôlerie"),
            material=d.get("material"),
            grade=d.get("grade"),
            thickness_mm=num(d.get("thickness_mm")),
            treatment=d.get("treatment"),
            surface_treatment=d.get("surface_treatment"),
            length_mm=num(d.get("length_mm")),
            width_mm=num(d.get("width_mm")),
            developed_surface_m2=opt_num(d.get("developed_surface_m2")),
            cut_length_mm=opt_num(d.get("cut_length_mm")),
            volume_mm3=opt_num(d.get("volume_mm3")),
            mass_g=opt_num(d.get("mass_g")),
            machined_volume_cm3=opt_num(d.get("machined_volume_cm3")),
            holes=holes, bends=bends, welds=welds, components=comps,
            tolerances=str(d.get("tolerances") or ""),
            notes=str(d.get("notes") or ""),
            extraction_confidence=num(d.get("extraction_confidence"), 0.0),
            source=str(d.get("source") or "demo"),
        )


def demo_part() -> PartFeatures:
    """Cas simulé crédible = la pièce SUPPORT REAR BRAKE du plan fourni.

    Sert de jeu de démonstration : l'application tourne de bout en bout
    SANS clé API ni plan importé.
    """
    return PartFeatures(
        reference="21597494",
        designation="SUPPORT REAR BRAKE",
        material="S235 (acier)",
        grade="S235",
        thickness_mm=2.0,
        treatment="Aucun (épargne peinture sur filetage)",
        length_mm=60.0,
        width_mm=60.0,
        developed_surface_m2=None,   # recalculé géométriquement -> démontre la fiabilité
        cut_length_mm=None,          # recalculé géométriquement
        volume_mm3=None,
        mass_g=None,
        holes=[
            Hole(shape="rond", diameter_mm=4.0, qty=2),
            Hole(shape="rond", diameter_mm=8.0, qty=2),
        ],
        bends=[
            Bend(angle_deg=45.0, radius_mm=2.0, length_mm=60.0, qty=2),
        ],
        components=[
            Component(designation="Écrou à sertir M6 1.00 CL8 S2S", qty=2),
        ],
        tolerances="ISO 2768-m",
        notes="Rayon de pliage 2mm ; rayons non cotés 2mm ; "
              "écrous à sertir norme RT 39.02.409 ; pas de peinture sur filetage.",
        extraction_confidence=1.0,
        source="demo",
    )
