"""
extraction.py
=============
Rôle PRÉCIS de l'IA dans l'application : lire un plan technique (PDF ou image)
et en extraire des CARACTÉRISTIQUES STRUCTURÉES (JSON), rien de plus.
L'IA ne calcule aucun prix.

Techno : Claude (modèle Vision) via l'API Anthropic, document PDF ou image
envoyé en base64, réponse contrainte à un schéma JSON strict.

Sans clé API -> mode démo : renvoie les features pré-extraites du plan fourni.
"""
from __future__ import annotations

import base64
import json
import os

from config import CLAUDE_MODEL
from models import PartFeatures, demo_part


# --------------------------------------------------------------------------- #
#  Prompt d'extraction (exemple de prompt attendu par le brief)               #
# --------------------------------------------------------------------------- #
EXTRACTION_SYSTEM = (
    "Tu es un expert en lecture de plans de tôlerie/usinage. "
    "Tu extrais uniquement des caractéristiques mesurables, sans jamais estimer "
    "de prix ni de temps. Si une information est absente du plan, mets null. "
    "Tu réponds STRICTEMENT en JSON valide, sans texte autour, sans balises Markdown."
)

EXTRACTION_PROMPT = """Analyse ce plan technique industriel (il peut comporter PLUSIEURS feuilles : lis-les
toutes, y compris le cartouche et la nomenclature) et renvoie un JSON strict :

{
  "reference": str|null, "designation": str|null,
  "process_type": "tôlerie"|"usinage"|"profilé"|"mixte",
  "material": str|null,         // lue au cartouche (ex: "S235", "5086-H32", "Aluminium")
  "thickness_mm": number|null,  // épaisseur (ex: "15/10" = 1.5 mm, "3.175" = 3.2 mm)
  "length_mm": number|null, "width_mm": number|null,
  "mass_g": number|null,        // MASSE indiquée au cartouche, en grammes (ex: 0,33 kg -> 330)
  "surface_treatment": str|null,// ex: "Zingage" (ZNT), "Anodisation", "Peinture"
  "machined_volume_cm3": number|null,
  "holes": [ {"shape":"rond"|"oblong", "diameter_mm":n, "qty":i,
              "threaded":bool, "countersunk":bool} ],
  "bends": [ {"angle_deg":n, "radius_mm":n, "qty":i} ],
  "welds": [ {"kind":"cordon", "length_mm":n, "qty":i} ],
  "components": [ {"designation":str, "qty":i} ],  // goujons/écrous à sertir, inserts...
  "tolerances": str|null, "notes": str|null,
  "extraction_confidence": number   // 0..1
}

Règles importantes :
- Convertis toutes les dimensions en mm ; les masses en grammes.
- Si la MASSE figure au cartouche, renseigne mass_g (elle est plus fiable que tout calcul).
- Les "goujons à sertir" / "écrous à sertir" de la nomenclature -> components (avec leur qté).
- Un trou oblong -> shape "oblong" (diameter_mm = sa largeur).
- threaded=true si taraudé (ex M6) ; countersunk=true si fraisé/chanfreiné (ex "Ch5").
- process_type "profilé" pour un profilé extrudé (section constante) ; "usinage" si enlèvement
  de matière important ; sinon "tôlerie".
- N'invente aucune valeur (null si absent). Réponds UNIQUEMENT par le JSON."""


# --------------------------------------------------------------------------- #
#  API key                                                                    #
# --------------------------------------------------------------------------- #
def get_api_key(ui_key: str | None = None) -> str | None:
    """Clé API par ordre de priorité : UI > variable d'env > secrets Streamlit."""
    if ui_key:
        return ui_key.strip()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY")  # type: ignore[attr-defined]
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Construction du bloc document (PDF) ou image                               #
# --------------------------------------------------------------------------- #
def _content_block(file_bytes: bytes, mime: str) -> dict:
    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    if mime == "application/pdf":
        return {"type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    return {"type": "image",
            "source": {"type": "base64", "media_type": mime, "data": b64}}


def pdf_to_image_blocks(file_bytes: bytes, max_pages: int = 6,
                        max_px: int = 1600) -> list[dict]:
    """Convertit chaque page du PDF en image haute résolution (meilleure lecture
    Vision sur les plans denses). Repli silencieux si PyMuPDF est absent."""
    try:
        import fitz  # PyMuPDF
    except Exception:
        return []
    blocks = []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    for page in doc[:max_pages]:
        zoom = max_px / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        png = pix.tobytes("png")
        b64 = base64.standard_b64encode(png).decode("utf-8")
        blocks.append({"type": "image",
                       "source": {"type": "base64", "media_type": "image/png", "data": b64}})
    return blocks


def build_content(file_bytes: bytes, mime: str) -> list[dict]:
    """Construit les blocs envoyés au modèle : pages PDF rendues en images
    (multi-pages), ou image unique, avec repli sur le PDF natif."""
    if mime == "application/pdf":
        imgs = pdf_to_image_blocks(file_bytes)
        if imgs:
            return imgs + [{"type": "text", "text": EXTRACTION_PROMPT}]
    return [_content_block(file_bytes, mime),
            {"type": "text", "text": EXTRACTION_PROMPT}]


def _parse_json(text: str) -> dict:
    """Parse robuste : enlève d'éventuelles balises Markdown."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
    # isole le premier objet JSON
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        t = t[start:end + 1]
    return json.loads(t)


# --------------------------------------------------------------------------- #
#  Extraction                                                                 #
# --------------------------------------------------------------------------- #
def extract_from_file(file_bytes: bytes, mime: str,
                      api_key: str | None) -> PartFeatures:
    """Extrait les features via Claude Vision. Lève une exception en cas d'échec."""
    import anthropic  # import paresseux

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2500,
        system=EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": build_content(file_bytes, mime or "application/pdf")}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    data = _parse_json(text)
    data.setdefault("extraction_confidence", 0.8)
    part = PartFeatures.from_dict(data)
    part.source = "claude_vision"
    return part


def extract(file_bytes: bytes | None, mime: str | None,
            api_key: str | None, force_demo: bool = False) -> tuple[PartFeatures, str | None]:
    """Point d'entrée unique.

    Renvoie (features, message). En cas de problème (pas de clé, pas de fichier,
    erreur API), bascule proprement en mode démo et l'indique dans message.
    """
    if force_demo or not file_bytes or not api_key:
        reason = ("Mode démo : " + (
            "forcé." if force_demo else
            "aucun plan importé." if not file_bytes else
            "aucune clé API détectée."))
        return demo_part(), reason
    try:
        return extract_from_file(file_bytes, mime or "application/pdf", api_key), None
    except Exception as e:  # repli sûr : on ne casse jamais l'app
        return demo_part(), f"Extraction IA indisponible ({e}). Repli sur le cas démo."
