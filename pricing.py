"""
pricing.py
==========
Moteur de calcul DÉTERMINISTE, AUDITABLE et ADAPTATIF.

Principe : l'IA extrait des caractéristiques ; le prix est calculé ici par des
formules explicites. Le devis est une LISTE D'OPÉRATIONS détectées dynamiquement
selon la pièce : une tôle plate n'a pas de pliage, une pièce usinée a une ligne
usinage, une pièce soudée une ligne soudure, etc. Ajouter une opération = ajouter
une fonction qui produit une CostLine — aucune autre partie du code à toucher.

Chaîne : Σ opérations détectées + composants + réglages amortis = coût de revient ;
× (1 + marge) = prix de vente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import config
from config import PricingConfig, resolve_material, operations
from models import PartFeatures


# --------------------------------------------------------------------------- #
#  Helpers matière / géométrie                                                #
# --------------------------------------------------------------------------- #
def material_family(material: str | None) -> str:
    return resolve_material(material)["family"]


def density(material: str | None) -> float:
    return resolve_material(material)["density"]


def price_per_kg(material: str | None) -> float:
    return resolve_material(material)["price_eur_kg"]


def cutting_speed(material: str | None, thickness_mm: float) -> float:
    """Vitesse de coupe (mm/min) par interpolation linéaire sur l'épaisseur."""
    fam = material_family(material)
    table = config.CUTTING_SPEED_MM_MIN.get(fam, config.CUTTING_SPEED_MM_MIN["acier"])
    thk = sorted(table.keys())
    t = max(min(thickness_mm or thk[0], thk[-1]), thk[0])
    for i in range(len(thk) - 1):
        if thk[i] <= t <= thk[i + 1]:
            x0, x1 = thk[i], thk[i + 1]
            y0, y1 = table[x0], table[x1]
            return y0 + (y1 - y0) * (t - x0) / (x1 - x0)
    return table[thk[-1]]


def holes_area_mm2(part: PartFeatures) -> float:
    return sum(math.pi * (h.diameter_mm / 2) ** 2 * h.qty for h in part.holes)


def holes_perimeter_mm(part: PartFeatures) -> float:
    return sum(math.pi * h.diameter_mm * h.qty for h in part.holes)


def n_pierces(part: PartFeatures) -> int:
    return 1 + sum(h.qty for h in part.holes)


# --------------------------------------------------------------------------- #
#  Géométrie dérivée cohérente                                                #
# --------------------------------------------------------------------------- #
@dataclass
class DerivedGeometry:
    developed_surface_m2: float
    cut_length_mm: float
    volume_mm3: float
    mass_g: float
    treated_surface_m2: float
    source_surface: str
    source_cut: str
    mass_source: str = "géométrie"


def derive_geometry(part: PartFeatures) -> DerivedGeometry:
    rho = density(part.material)
    footprint_mm2 = part.length_mm * part.width_mm
    net_surface_mm2 = max(footprint_mm2 - holes_area_mm2(part), 0.0)
    surf_geo_m2 = net_surface_mm2 / 1_000_000.0
    # On fait CONFIANCE à la surface du plan si elle existe (guard large pour
    # accepter les formes complexes), sinon on recalcule depuis la géométrie.
    if part.developed_surface_m2 and part.developed_surface_m2 > 0:
        ratio = (part.developed_surface_m2 / surf_geo_m2) if surf_geo_m2 > 0 else 1.0
        surface_m2, src_s = ((part.developed_surface_m2, "ia") if 0.2 <= ratio <= 5.0
                             else (surf_geo_m2, "géométrie"))
    else:
        surface_m2, src_s = surf_geo_m2, "géométrie"

    outer_mm = 2 * (part.length_mm + part.width_mm)
    cut_geo_mm = outer_mm + holes_perimeter_mm(part)
    if part.cut_length_mm and part.cut_length_mm > 0:
        ratio = (part.cut_length_mm / cut_geo_mm) if cut_geo_mm > 0 else 1.0
        cut_mm, src_c = ((part.cut_length_mm, "ia") if 0.2 <= ratio <= 5.0
                         else (cut_geo_mm, "géométrie"))
    else:
        cut_mm, src_c = cut_geo_mm, "géométrie"

    # MASSE : on privilégie la masse indiquée au cartouche (fiable, surtout pour
    # les pièces non rectangulaires) ; sinon on l'estime géométriquement.
    geo_mass_g = (net_surface_mm2 * part.thickness_mm / 1000.0) * rho
    if part.mass_g and part.mass_g > 0:
        mass_g, mass_src = part.mass_g, "plan"
    else:
        mass_g, mass_src = geo_mass_g, "géométrie"

    volume_mm3 = net_surface_mm2 * part.thickness_mm
    treated_m2 = surface_m2 * 2.0   # deux faces

    return DerivedGeometry(surface_m2, cut_mm, volume_mm3, mass_g,
                           treated_m2, src_s, src_c, mass_src)


# --------------------------------------------------------------------------- #
#  Lignes de coût                                                             #
# --------------------------------------------------------------------------- #
@dataclass
class CostLine:
    poste: str
    montant: float
    formule: str = ""
    calcul: str = ""
    group: str = ""


@dataclass
class CostBreakdown:
    lines: list[CostLine] = field(default_factory=list)
    unit_cost: float = 0.0
    unit_price: float = 0.0
    total_price: float = 0.0
    notes: list[str] = field(default_factory=list)

    def amount(self, group: str) -> float:
        return sum(l.montant for l in self.lines if l.group == group)

    @property
    def material(self) -> float:      # compat validation.py
        return self.amount("matière")


def _h(time_s: float, rate_eur_h: float) -> float:
    return time_s / 3600.0 * rate_eur_h


# --------------------------------------------------------------------------- #
#  Calcul du devis : ÉVALUATEUR PILOTÉ PAR LA LISTE D'OPÉRATIONS (config)      #
#  Aucune opération n'est codée en dur : on parcourt config.operations().      #
# --------------------------------------------------------------------------- #
def compute_quote(part: PartFeatures, cfg: PricingConfig,
                  geo: DerivedGeometry | None = None) -> CostBreakdown:
    if geo is None:
        geo = derive_geometry(part)
    bd = CostBreakdown()
    mat = resolve_material(cfg.material)
    rho, pk = mat["density"], mat["price_eur_kg"]
    if not mat["known"]:
        bd.notes.append(
            f"Matière « {mat['label']} » inconnue : estimée via la famille "
            f"« {mat['family']} » ({pk} €/kg, {rho} g/cm³) — à confirmer.")
    proc = (part.process_type or "tôlerie").lower()
    qty = max(int(cfg.quantity), 1)

    # Taux et temps résolus par NOM logique (les opérations y font référence)
    RATE = {"laser": cfg.laser_rate_eur_h, "plieuse": cfg.press_brake_rate_eur_h,
            "mo": cfg.labor_rate_eur_h, "usinage": cfg.milling_rate_eur_h,
            "soudure": cfg.welding_rate_eur_h}
    TIME = {"bend": cfg.bend_time_s, "insert": cfg.insert_time_s, "tap": cfg.tap_time_s,
            "countersink": cfg.countersink_time_s, "finishing_base": cfg.finishing_base_s,
            "finishing_per_hole": cfg.finishing_per_hole_s, "inspection": cfg.inspection_s,
            "packaging": cfg.packaging_s}
    # Quantités disponibles, calculées une fois
    n_holes = sum(h.qty for h in part.holes)
    QTY = {"n_bends": sum(b.qty for b in part.bends),
           "n_threaded": sum(h.qty for h in part.holes if h.threaded),
           "n_countersunk": sum(h.qty for h in part.holes if h.countersunk),
           "n_inserts": sum(c.qty for c in part.components),
           "n_holes": n_holes,
           "weld_mm": sum(w.length_mm * w.qty for w in part.welds),
           "machined_volume_cm3": part.machined_volume_cm3 or 0.0}

    def rate_of(op):
        return RATE.get(op.get("rate", "mo"), cfg.labor_rate_eur_h)

    # --- Évaluateur : un handler par "kind" -------------------------------- #
    def ev_material(op):
        part_mass_kg = (part.mass_g / 1000.0) if (part.mass_g and part.mass_g > 0) else geo.mass_g / 1000.0
        src = "masse du plan" if (part.mass_g and part.mass_g > 0) else "masse calculée"
        blank = part_mass_kg * (1 + cfg.scrap_rate)
        return CostLine(op["label"], blank * pk,
            "masse_flan × prix_matière ; masse_flan = masse pièce × (1 + chute)",
            f"{blank:.4f} kg × {pk} €/kg [{src}, chute {int(cfg.scrap_rate*100)} %]",
            op["group"])

    def ev_cut(op):
        if proc not in [p.lower() for p in op.get("process", ["tôlerie", "mixte"])]:
            return None
        if geo.cut_length_mm <= 0:
            return None
        v = cutting_speed(cfg.material, part.thickness_mm)
        np_ = n_pierces(part)
        t_s = geo.cut_length_mm / v * 60.0 + np_ * config.PIERCE_TIME_S
        return CostLine(op["label"], _h(t_s, rate_of(op)),
            "(longueur/vitesse + amorces×t_amorce) × taux",
            f"{geo.cut_length_mm:.0f} mm ÷ {v:.0f} mm/min + {np_}×{config.PIERCE_TIME_S}s "
            f"= {t_s:.1f}s → ×{rate_of(op)} €/h", op["group"])

    def ev_time_per_unit(op):
        q = QTY.get(op["qty"], 0)
        if q <= 0:
            return None
        t_s = q * TIME[op["time"]]
        return CostLine(op["label"], _h(t_s, rate_of(op)),
            f"{op['qty']} × temps_unitaire × taux",
            f"{q} × {TIME[op['time']]}s = {t_s:.0f}s → ×{rate_of(op)} €/h", op["group"])

    def ev_volume_rate(op):
        if proc not in [p.lower() for p in op.get("process", ["usinage", "mixte"])]:
            return None
        vol = QTY.get(op["qty"], 0)
        if vol <= 0:
            return None
        mrr = config.MRR_CM3_MIN.get(mat["family"], 8.0)
        t_min = vol / mrr
        return CostLine(op["label"], t_min * rate_of(op) / 60.0,
            "volume_enlevé ÷ débit_copeaux × taux",
            f"{vol:.1f} cm³ ÷ {mrr} cm³/min = {t_min:.1f} min → ×{rate_of(op)} €/h",
            op["group"])

    def ev_length_rate(op):
        q = QTY.get(op["qty"], 0)
        if q <= 0:
            return None
        t_s = q / config.WELD_SPEED_MM_MIN * 60.0
        return CostLine(op["label"], _h(t_s, rate_of(op)),
            "longueur ÷ vitesse × taux",
            f"{q:.0f} mm ÷ {config.WELD_SPEED_MM_MIN:.0f} mm/min = {t_s:.0f}s "
            f"→ ×{rate_of(op)} €/h", op["group"])

    def ev_area_rate(op):
        treat = part.surface_treatment or cfg.surface_treatment or "Aucun"
        rate_m2 = config.SURFACE_TREATMENTS.get(treat, 0.0)
        if rate_m2 <= 0 or geo.treated_surface_m2 <= 0:
            return None
        return CostLine(f"{op['label']} : {treat}", rate_m2 * geo.treated_surface_m2,
            "surface_traitée × coût/m²",
            f"{geo.treated_surface_m2:.4f} m² × {rate_m2} €/m²", op["group"])

    def ev_time_base_per_hole(op):
        t_s = TIME[op["base"]] + n_holes * TIME[op["per_hole"]]
        return CostLine(op["label"], _h(t_s, rate_of(op)),
            "(base + nb_trous × temps_trou) × taux",
            f"{TIME[op['base']]}s + {n_holes}×{TIME[op['per_hole']]}s = {t_s:.0f}s "
            f"→ ×{rate_of(op)} €/h", op["group"])

    def ev_fixed_time(op):
        t_s = sum(TIME[n] for n in op["times"])
        return CostLine(op["label"], _h(t_s, rate_of(op)),
            "temps_fixe × taux", f"{t_s:.0f}s → ×{rate_of(op)} €/h", op["group"])

    def ev_components(op):
        cost = sum((c.unit_price_eur if c.unit_price_eur is not None
                    else cfg.insert_unit_price_eur) * c.qty for c in part.components)
        if cost <= 0:
            return None
        return CostLine(op["label"], cost, "Σ (quantité × prix_unitaire)",
            f"{QTY['n_inserts']} composant(s) → {cost:.3f} €", op["group"])

    def ev_setup(op):
        n_unique_bends = len(part.bends)
        setup_min = (cfg.setup_programming_min + cfg.setup_laser_min
                     + n_unique_bends * cfg.setup_bend_min_per_bend)
        avg = (cfg.laser_rate_eur_h + cfg.press_brake_rate_eur_h + cfg.labor_rate_eur_h) / 3.0
        total = setup_min / 60.0 * avg
        return CostLine(op["label"], total / qty, "coût_réglage_total ÷ quantité",
            f"{total:.2f} € ÷ {qty} pièces ({setup_min:.0f} min)", op["group"])

    HANDLERS = {
        "material": ev_material, "cut": ev_cut, "time_per_unit": ev_time_per_unit,
        "volume_rate": ev_volume_rate, "length_rate": ev_length_rate,
        "area_rate": ev_area_rate, "time_base_per_hole": ev_time_base_per_hole,
        "fixed_time": ev_fixed_time, "components": ev_components, "setup": ev_setup,
    }

    for op in operations():
        handler = HANDLERS.get(op.get("kind"))
        if not handler:
            continue
        try:
            line = handler(op)
        except Exception:
            line = None
        if line is not None:
            bd.lines.append(line)

    bd.unit_cost = sum(l.montant for l in bd.lines)
    bd.unit_price = bd.unit_cost * (1 + cfg.margin_rate)
    bd.total_price = bd.unit_price * qty
    return bd
