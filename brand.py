
from __future__ import annotations

import base64
import os

BRAND = {
    "name": "MAJI",
    "tagline": "MANUFACTURE THE FUTURE",
    "ink":          "#0B3D34",   # teal profond (en-têtes, PDF)
    "primary":      "#0E9C7B",   # vert teal Maji (accent principal, boutons)
    "primary_dark": "#0A6F58",
    "steel":        "#5B6B6B",   # gris (texte secondaire)
    "light":        "#F2F8F6",   # fond clair légèrement teinté teal
    "line":         "#DCE7E3",   # bordures
    "success":      "#0E9C7B",
    "warning":      "#D97706",
    "error":        "#DC2626",
}


def logo_data_uri(path: str = "logo.png") -> str | None:
    """Renvoie le logo en data-URI s'il existe, sinon None (fallback wordmark)."""
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    return None


def inject_css() -> str:
    """Feuille de style globale (couleurs Maji, cartes, étapes, footer)."""
    b = BRAND
    return f"""
<style>
:root {{
  --ink:{b['ink']}; --primary:{b['primary']}; --primary-dark:{b['primary_dark']};
  --steel:{b['steel']}; --light:{b['light']}; --line:{b['line']};
}}
/* compacte le haut de page pour coller l'en-tête */
.block-container {{ padding-top: 1.2rem; max-width: 1200px; }}

/* En-tête de marque */
.maji-header {{
  background: linear-gradient(120deg, var(--ink) 0%, var(--primary-dark) 100%);
  color:#fff; border-radius:16px; padding:22px 26px; margin-bottom:18px;
  display:flex; align-items:center; justify-content:space-between;
  box-shadow:0 6px 20px rgba(14,33,56,.18);
}}
.maji-header .left {{ display:flex; align-items:center; gap:16px; }}
.maji-logo-text {{ font-size:30px; font-weight:800; letter-spacing:.16em; }}
.maji-logo-img {{ height:42px; }}
.maji-tag {{ font-size:11px; letter-spacing:.28em; opacity:.85; margin-top:2px; }}
.maji-header .right {{ text-align:right; }}
.maji-app-name {{ font-size:18px; font-weight:700; }}
.maji-app-sub {{ font-size:12px; opacity:.85; }}

/* puce d'étape */
.maji-step {{ display:flex; align-items:center; gap:12px; margin:6px 0 2px; }}
.maji-step .num {{
  background:var(--primary); color:#fff; width:30px; height:30px; border-radius:50%;
  display:flex; align-items:center; justify-content:center; font-weight:700; flex:0 0 30px;
}}
.maji-step .txt {{ font-size:20px; font-weight:700; color:var(--ink); }}
.maji-step .ai {{ font-size:12px; color:var(--primary); font-weight:600; }}
.maji-step .lock {{ font-size:12px; color:var(--steel); font-weight:600; }}

/* cartes KPI (metrics) */
div[data-testid="stMetric"] {{
  background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:14px 16px; box-shadow:0 1px 2px rgba(14,33,56,.06);
}}
div[data-testid="stMetricValue"] {{ color:var(--ink); }}

/* boutons */
.stButton>button[kind="primary"], .stDownloadButton>button {{
  background:var(--primary); border:0; font-weight:600;
}}

/* footer */
.maji-footer {{
  margin-top:28px; padding-top:14px; border-top:1px solid var(--line);
  color:var(--steel); font-size:12px; text-align:center;
}}
</style>
"""


def header_html() -> str:
    """Bannière d'en-tête (logo image si présent, sinon wordmark)."""
    b = BRAND
    uri = logo_data_uri()
    left_logo = (f'<img class="maji-logo-img" src="{uri}"/>' if uri
                 else f'<div><div class="maji-logo-text">{b["name"]}</div>'
                      f'<div class="maji-tag">{b["tagline"]}</div></div>')
    return f"""
<div class="maji-header">
  <div class="left">{left_logo}</div>
  <div class="right">
    <div class="maji-app-name">Outil de devis assisté par IA</div>
    <div class="maji-app-sub">Plan → extraction IA → calcul déterministe → devis</div>
  </div>
</div>
"""


def step_html(num: int, title: str, ai: bool = False, lock: bool = False) -> str:
    tag = ""
    if ai:
        tag = '<span class="ai">🤖 extraction par l\'IA</span>'
    elif lock:
        tag = '<span class="lock">🔒 calcul déterministe (sans IA)</span>'
    return (f'<div class="maji-step"><div class="num">{num}</div>'
            f'<div class="txt">{title}</div>{tag}</div>')
