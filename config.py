"""
config.py
=========
Chargement DYNAMIQUE des paramètres métier depuis parameters.yaml.
Rien n'est figé dans le code : matières, taux, vitesses, traitements et la
LISTE DES OPÉRATIONS sont des données. On peut éditer le fichier (ou en
uploader un autre dans l'app) pour faire évoluer l'outil sans le reprogrammer.

Si parameters.yaml (ou PyYAML) est absent, on retombe sur un jeu par défaut
intégré, identique, pour que l'application tourne quand même.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict

CURRENCY = "€"
ROUND_UNIT = 2
ROUND_TOTAL = 2
CLAUDE_MODEL = "claude-sonnet-4-6"

_DIR = os.path.dirname(os.path.abspath(__file__))
_PARAM_FILE = os.path.join(_DIR, "parameters.yaml")

# --- Repli minimal si le YAML est introuvable (l'app tourne quand même) ----- #
_FALLBACK = {
    "defaults": {"material": "S235 (acier)", "quantity": 100,
                 "margin_rate": 0.20, "scrap_rate": 0.20},
    "rates_eur_h": {"laser": 120, "plieuse": 75, "mo": 45, "usinage": 90, "soudure": 65},
    "times_s": {"bend": 20, "insert": 10, "tap": 12, "countersink": 8, "pierce": 0.6,
                "finishing_base": 30, "finishing_per_hole": 4, "inspection": 20, "packaging": 8},
    "setup": {"programming_min": 15, "laser_min": 10, "bend_min_per_bend": 7},
    "components": {"insert_unit_price_eur": 0.15},
    "machining": {"mrr_cm3_min": {"acier": 8, "inox": 4, "alu": 25, "laiton": 18,
                                  "cuivre": 12, "titane": 2}},
    "weld_speed_mm_min": 300,
    "materials": {"S235 (acier)": {"price_eur_kg": 1.20, "density": 7.85, "family": "acier"},
                  "Inox 304": {"price_eur_kg": 4.50, "density": 7.90, "family": "inox"},
                  "Aluminium 6061": {"price_eur_kg": 4.20, "density": 2.70, "family": "alu"}},
    "family_defaults": {"acier": {"price_eur_kg": 1.30, "density": 7.85},
                        "inox": {"price_eur_kg": 5.00, "density": 7.90},
                        "alu": {"price_eur_kg": 4.00, "density": 2.70},
                        "laiton": {"price_eur_kg": 7.50, "density": 8.40},
                        "cuivre": {"price_eur_kg": 9.50, "density": 8.96},
                        "titane": {"price_eur_kg": 35.0, "density": 4.51}},
    "material_keywords": {"inox": "inox", "alu": "alu", "aluminium": "alu",
                          "laiton": "laiton", "cuivre": "cuivre", "titane": "titane",
                          "acier": "acier", "steel": "acier", "s235": "acier"},
    "cutting_speed_mm_min": {"acier": {1: 8000, 2: 5000, 3: 3200, 5: 1900, 8: 1000},
                             "inox": {1: 6000, 2: 3500, 3: 2200, 5: 1200, 8: 600},
                             "alu": {1: 9000, 2: 6500, 3: 4500, 5: 2600, 8: 1400}},
    "treatments_eur_m2": {"Aucun": 0, "Zingage": 12, "Peinture poudre (époxy)": 18,
                          "Anodisation": 25, "Passivation inox": 8},
    "sanity": {"thickness_mm": [0.3, 20.0], "dim_mm": [1.0, 3000.0],
               "hole_diam_mm": [0.5, 200.0], "price_per_kg": [3.0, 400.0]},
    "operations": [
        {"id": "matiere", "label": "Matière", "group": "matière", "kind": "material"},
        {"id": "decoupe", "label": "Découpe laser", "group": "découpe", "kind": "cut",
         "rate": "laser", "process": ["tôlerie", "mixte", "profilé"]},
        {"id": "pliage", "label": "Pliage", "group": "pliage", "kind": "time_per_unit",
         "qty": "n_bends", "time": "bend", "rate": "plieuse"},
        {"id": "taraudage", "label": "Taraudage", "group": "taraudage", "kind": "time_per_unit",
         "qty": "n_threaded", "time": "tap", "rate": "mo"},
        {"id": "fraisurage", "label": "Fraisurage / lamage", "group": "fraisurage",
         "kind": "time_per_unit", "qty": "n_countersunk", "time": "countersink", "rate": "usinage"},
        {"id": "usinage", "label": "Usinage", "group": "usinage", "kind": "volume_rate",
         "qty": "machined_volume_cm3", "rate": "usinage", "process": ["usinage", "mixte"]},
        {"id": "soudure", "label": "Soudure", "group": "soudure", "kind": "length_rate",
         "qty": "weld_mm", "rate": "soudure"},
        {"id": "sertissage", "label": "Sertissage inserts", "group": "sertissage",
         "kind": "time_per_unit", "qty": "n_inserts", "time": "insert", "rate": "mo"},
        {"id": "traitement", "label": "Traitement de surface", "group": "traitement",
         "kind": "area_rate", "rate": "mo"},
        {"id": "finition", "label": "Finition / ébavurage", "group": "finition",
         "kind": "time_base_per_hole", "base": "finishing_base",
         "per_hole": "finishing_per_hole", "rate": "mo"},
        {"id": "controle", "label": "Contrôle + conditionnement", "group": "contrôle",
         "kind": "fixed_time", "times": ["inspection", "packaging"], "rate": "mo"},
        {"id": "composants", "label": "Composants", "group": "composants", "kind": "components"},
        {"id": "reglages", "label": "Réglages série (amortis)", "group": "réglages", "kind": "setup"},
    ],
}


def _load_settings() -> dict:
    try:
        import yaml
        with open(_PARAM_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and data.get("materials") and data.get("operations"):
            return data
    except Exception:
        pass
    return _FALLBACK


SETTINGS: dict = _load_settings()

# --- Globals "miroir" (mutés en place par apply_settings) ------------------- #
MATERIALS: dict = {}
FAMILY_DEFAULTS: dict = {}
MATERIAL_KEYWORDS: dict = {}
SURFACE_TREATMENTS: dict = {}
CUTTING_SPEED_MM_MIN: dict = {}
MRR_CM3_MIN: dict = {}
SANITY: dict = {}
DEFAULT_MATERIAL = "S235 (acier)"
PIERCE_TIME_S = 0.6
WELD_SPEED_MM_MIN = 300.0


def _refresh_globals() -> None:
    global DEFAULT_MATERIAL, PIERCE_TIME_S, WELD_SPEED_MM_MIN
    MATERIALS.clear(); MATERIALS.update(SETTINGS["materials"])
    FAMILY_DEFAULTS.clear(); FAMILY_DEFAULTS.update(SETTINGS["family_defaults"])
    MATERIAL_KEYWORDS.clear()
    MATERIAL_KEYWORDS.update({str(k).lower(): v for k, v in SETTINGS["material_keywords"].items()})
    SURFACE_TREATMENTS.clear(); SURFACE_TREATMENTS.update(SETTINGS["treatments_eur_m2"])
    CUTTING_SPEED_MM_MIN.clear()
    for fam, tbl in SETTINGS["cutting_speed_mm_min"].items():
        CUTTING_SPEED_MM_MIN[fam] = {float(k): float(v) for k, v in tbl.items()}
    MRR_CM3_MIN.clear(); MRR_CM3_MIN.update(SETTINGS["machining"]["mrr_cm3_min"])
    SANITY.clear()
    SANITY.update({k: tuple(v) for k, v in SETTINGS["sanity"].items()})
    SANITY["min_margin_over_material"] = 1.0
    DEFAULT_MATERIAL = SETTINGS["defaults"]["material"]
    PIERCE_TIME_S = float(SETTINGS["times_s"]["pierce"])
    WELD_SPEED_MM_MIN = float(SETTINGS["weld_speed_mm_min"])


_refresh_globals()


def apply_settings(new_settings: dict) -> None:
    """Remplace les paramètres pour la session (ex. YAML uploadé dans l'app)."""
    global SETTINGS
    SETTINGS = new_settings
    _refresh_globals()


def operations() -> list:
    return SETTINGS.get("operations", [])


def rates() -> dict:
    return SETTINGS.get("rates_eur_h", {})


# --------------------------------------------------------------------------- #
#  Résolution matière ADAPTATIVE                                              #
# --------------------------------------------------------------------------- #
def infer_family(material: str | None) -> str:
    m = (material or "").lower()
    # famille explicite dans la base
    if material in MATERIALS and MATERIALS[material].get("family"):
        return MATERIALS[material]["family"]
    for kw, fam in MATERIAL_KEYWORDS.items():
        if kw in m:
            return fam
    return "acier"


def resolve_material(material: str | None) -> dict:
    if not material or not str(material).strip():
        material = DEFAULT_MATERIAL
    if material in MATERIALS:
        d = MATERIALS[material]
        return {"price_eur_kg": d["price_eur_kg"], "density": d["density"],
                "family": d.get("family", infer_family(material)),
                "known": True, "label": material}
    fam = infer_family(material)
    d = FAMILY_DEFAULTS.get(fam, FAMILY_DEFAULTS["acier"])
    return {"price_eur_kg": d["price_eur_kg"], "density": d["density"],
            "family": fam, "known": False, "label": material}


# --------------------------------------------------------------------------- #
#  Paramètres tarifaires (valeurs par défaut tirées des SETTINGS)             #
# --------------------------------------------------------------------------- #
_R = SETTINGS["rates_eur_h"]; _T = SETTINGS["times_s"]
_S = SETTINGS["setup"]; _D = SETTINGS["defaults"]; _C = SETTINGS["components"]


@dataclass
class PricingConfig:
    laser_rate_eur_h: float = float(_R["laser"])
    press_brake_rate_eur_h: float = float(_R["plieuse"])
    labor_rate_eur_h: float = float(_R["mo"])
    milling_rate_eur_h: float = float(_R["usinage"])
    welding_rate_eur_h: float = float(_R["soudure"])

    material: str = _D["material"]
    scrap_rate: float = float(_D["scrap_rate"])

    bend_time_s: float = float(_T["bend"])
    tap_time_s: float = float(_T["tap"])
    countersink_time_s: float = float(_T["countersink"])
    insert_time_s: float = float(_T["insert"])
    insert_unit_price_eur: float = float(_C["insert_unit_price_eur"])

    finishing_base_s: float = float(_T["finishing_base"])
    finishing_per_hole_s: float = float(_T["finishing_per_hole"])
    inspection_s: float = float(_T["inspection"])
    packaging_s: float = float(_T["packaging"])

    setup_programming_min: float = float(_S["programming_min"])
    setup_laser_min: float = float(_S["laser_min"])
    setup_bend_min_per_bend: float = float(_S["bend_min_per_bend"])

    surface_treatment: str = "Aucun"
    margin_rate: float = float(_D["margin_rate"])
    quantity: int = int(_D["quantity"])

    def to_dict(self) -> dict:
        return asdict(self)
