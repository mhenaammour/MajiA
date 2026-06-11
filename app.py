
from __future__ import annotations

import pandas as pd
import streamlit as st

import brand
import config
from config import MATERIALS, DEFAULT_MATERIAL, SURFACE_TREATMENTS, PricingConfig
from models import PartFeatures, Hole, Bend, Weld, Component
from extraction import extract, get_api_key
from pricing import derive_geometry, compute_quote
from validation import run_full_validation, Level
from pdf_export import build_pdf
import explain

st.set_page_config(page_title="Devis IA — Maji", page_icon="🛠️", layout="wide")
st.markdown(brand.inject_css(), unsafe_allow_html=True)
st.markdown(brand.header_html(), unsafe_allow_html=True)

LEVEL_STYLE = {
    Level.OK:      ("✅", "success"),
    Level.WARNING: ("⚠️", "warning"),
    Level.ERROR:   ("⛔", "error"),
}


def _eur(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f} €".replace(",", " ")


# --------------------------------------------------------------------------- #
#  Panneau "Comment ça marche" (répond aux points 1 & 3 du cahier des charges) #
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ Comment ça marche / Rôle de l'IA", expanded=False):
    a, b = st.columns(2)
    a.markdown(
        "**Ce que ça change vs Excel**\n\n"
        "- Plus de ressaisie manuelle des cotes : l'IA lit le plan.\n"
        "- Calcul centralisé, documenté et **reproductible**.\n"
        "- Contrôles de fiabilité automatiques.\n"
        "- Devis PDF généré en un clic.")
    b.markdown(
        "**Rôle précis de l'IA**\n\n"
        "- L'IA (**Claude Vision**) **extrait** les caractéristiques du plan "
        "(dimensions, trous, plis, matière) au format JSON.\n"
        "- Elle **ne calcule aucun prix** : le prix vient d'un moteur "
        "déterministe → même pièce, même prix.\n"
        "- L'humain vérifie/corrige avant calcul.")

# --------------------------------------------------------------------------- #
#  Barre latérale : IA + paramètres modifiables                               #
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Configuration")

    with st.expander("🧩 Paramètres dynamiques (YAML)", expanded=False):
        st.caption("Rien n'est figé : matières, taux, opérations… tout vit ici. "
                   "Téléchargez, modifiez, ré-importez (valable pour la session).")
        try:
            import yaml as _yaml
            _cur = _yaml.safe_dump(config.SETTINGS, allow_unicode=True, sort_keys=False)
            st.download_button("⬇️ Télécharger les paramètres", _cur,
                               file_name="parameters.yaml", mime="text/yaml")
            _up = st.file_uploader("Ré-importer des paramètres", type=["yaml", "yml"], key="cfg_up")
            if _up is not None:
                try:
                    config.apply_settings(_yaml.safe_load(_up.read()))
                    st.success("Paramètres mis à jour pour la session.")
                except Exception as e:
                    st.error(f"YAML invalide : {e}")
        except Exception:
            st.info("PyYAML indisponible : éditez parameters.yaml directement.")

    with st.expander("🤖 Connexion IA", expanded=False):
        ui_key = st.text_input("Clé API Anthropic", type="password",
                               help="Vide = mode démo.")
        force_demo = st.checkbox("Forcer le mode démo", value=False)
    api_key = get_api_key(ui_key)
    (st.success if (api_key and not force_demo) else st.info)(
        "IA connectée — extraction Vision active." if (api_key and not force_demo)
        else "Mode démo actif (sans clé API).")

    st.divider()
    st.subheader("Paramètres de calcul")
    st.caption("Toutes les hypothèses du prix sont modifiables ici.")

    _existing = st.session_state.get("part")
    _detected = _existing.material if _existing else None
    _opts = list(MATERIALS.keys())
    if _detected and _detected not in _opts:
        _opts = [_detected] + _opts            # matière détectée hors base
    _def = _detected if _detected in _opts else DEFAULT_MATERIAL
    material = st.selectbox("Matière", _opts, index=_opts.index(_def))
    custom_mat = st.text_input("…ou matière libre",
                               help="Prioritaire. Matière inconnue → estimée par famille.")
    if custom_mat.strip():
        material = custom_mat.strip()

    _procs = ["tôlerie", "usinage", "mixte"]
    _pdef = _existing.process_type if (_existing and _existing.process_type in _procs) else "tôlerie"
    process = st.selectbox("Procédé", _procs, index=_procs.index(_pdef))

    _tkeys = list(SURFACE_TREATMENTS.keys())
    _tdef = _existing.surface_treatment if (_existing and _existing.surface_treatment in _tkeys) else "Aucun"
    treatment = st.selectbox("Traitement de surface", _tkeys, index=_tkeys.index(_tdef))

    quantity = st.number_input("Quantité (série)", min_value=1,
                               value=int(config.SETTINGS["defaults"]["quantity"]), step=1)
    margin = st.slider("Marge (%)", 0, 80,
                       int(config.SETTINGS["defaults"]["margin_rate"] * 100)) / 100.0
    scrap = st.slider("Taux de chute / nesting (%)", 0, 50,
                      int(config.SETTINGS["defaults"]["scrap_rate"] * 100)) / 100.0
    _R = config.SETTINGS["rates_eur_h"]
    _T = config.SETTINGS["times_s"]
    with st.expander("Taux horaires (€/h)"):
        laser_rate = st.number_input("Laser", value=float(_R["laser"]), step=5.0)
        bend_rate = st.number_input("Plieuse", value=float(_R["plieuse"]), step=5.0)
        labor_rate = st.number_input("Main d'œuvre", value=float(_R["mo"]), step=5.0)
        milling_rate = st.number_input("Usinage", value=float(_R["usinage"]), step=5.0)
        welding_rate = st.number_input("Soudure", value=float(_R["soudure"]), step=5.0)
    with st.expander("Temps & composants"):
        bend_time = st.number_input("Temps par pli (s)", value=float(_T["bend"]), step=1.0)
        insert_time = st.number_input("Temps par insert (s)", value=float(_T["insert"]), step=1.0)
        insert_price = st.number_input("Prix insert (€)",
            value=float(config.SETTINGS["components"]["insert_unit_price_eur"]),
            step=0.05, format="%.2f")
        tap_time = st.number_input("Temps taraudage (s)", value=float(_T["tap"]), step=1.0)
        csk_time = st.number_input("Temps fraisurage (s)", value=float(_T["countersink"]), step=1.0)

cfg = PricingConfig(
    laser_rate_eur_h=laser_rate, press_brake_rate_eur_h=bend_rate,
    labor_rate_eur_h=labor_rate, milling_rate_eur_h=milling_rate,
    welding_rate_eur_h=welding_rate, material=material, scrap_rate=scrap,
    bend_time_s=bend_time, insert_time_s=insert_time, insert_unit_price_eur=insert_price,
    tap_time_s=tap_time, countersink_time_s=csk_time,
    surface_treatment=treatment, margin_rate=margin, quantity=int(quantity),
)

# --------------------------------------------------------------------------- #
#  Étape 1 — Import & extraction                                              #
# --------------------------------------------------------------------------- #
st.markdown(brand.step_html(1, "Import du plan", ai=True), unsafe_allow_html=True)
c1, c2 = st.columns([3, 1])
with c1:
    up = st.file_uploader("Plan technique (PDF, PNG, JPG)",
                          type=["pdf", "png", "jpg", "jpeg"], label_visibility="collapsed")
with c2:
    go = st.button("🚀 Extraire le plan", use_container_width=True, type="primary")
    demo_btn = st.button("📄 Charger le cas démo", use_container_width=True)

if go or demo_btn:
    file_bytes = up.read() if (up and not demo_btn) else None
    mime = up.type if up else None
    with st.spinner("Lecture du plan par l'IA…"):
        part, msg = extract(file_bytes, mime, api_key, force_demo=force_demo or demo_btn)
    st.session_state.part = part
    (st.info if msg else st.success)(msg or "Extraction IA réussie.")

# --------------------------------------------------------------------------- #
#  Étapes 2 & 3                                                               #
# --------------------------------------------------------------------------- #
if "part" in st.session_state:
    part: PartFeatures = st.session_state.part

    st.markdown(brand.step_html(2, "Caractéristiques extraites — vérifiables"),
                unsafe_allow_html=True)
    src = {"claude_vision": "🤖 IA (Claude Vision)", "demo": "📄 Cas démo",
           "manual": "✏️ Saisie manuelle"}.get(part.source, part.source)
    st.caption(f"Source : {src} · Confiance : {part.extraction_confidence:.0%}")

    a, b, c = st.columns(3)
    part.reference = a.text_input("Référence", part.reference or "")
    part.designation = b.text_input("Désignation", part.designation or "")
    part.thickness_mm = c.number_input("Épaisseur (mm)",
                                       value=float(part.thickness_mm or 0.0),
                                       min_value=0.0, step=0.1)
    a, b, c = st.columns(3)
    part.length_mm = a.number_input("Longueur (mm)",
                                    value=float(part.length_mm or 0.0),
                                    min_value=0.0, step=1.0)
    part.width_mm = b.number_input("Largeur (mm)",
                                   value=float(part.width_mm or 0.0),
                                   min_value=0.0, step=1.0)
    part.tolerances = c.text_input("Tolérances", part.tolerances or "")

    st.markdown("**Trous / découpes**")
    holes_df = st.data_editor(
        pd.DataFrame([{"Forme": h.shape, "Ø (mm)": h.diameter_mm, "Qté": h.qty,
                       "Taraudé": h.threaded, "Fraisé": h.countersunk}
                      for h in part.holes] or
                     [{"Forme": "rond", "Ø (mm)": 0.0, "Qté": 1,
                       "Taraudé": False, "Fraisé": False}]),
        num_rows="dynamic", key="holes_ed", use_container_width=True)
    st.markdown("**Plis**")
    bends_df = st.data_editor(
        pd.DataFrame([{"Angle (°)": b.angle_deg, "Rayon (mm)": b.radius_mm or 0.0,
                       "Long. (mm)": b.length_mm or 0.0, "Qté": b.qty}
                      for b in part.bends] or
                     [{"Angle (°)": 90.0, "Rayon (mm)": 0.0, "Long. (mm)": 0.0, "Qté": 1}]),
        num_rows="dynamic", key="bends_ed", use_container_width=True)
    st.markdown("**Soudures** (longueur de cordon, mm)")
    welds_df = st.data_editor(
        pd.DataFrame([{"Type": w.kind, "Long. (mm)": w.length_mm, "Qté": w.qty}
                      for w in part.welds] or
                     [{"Type": "cordon", "Long. (mm)": 0.0, "Qté": 1}]),
        num_rows="dynamic", key="welds_ed", use_container_width=True)
    st.markdown("**Composants (écrous à sertir, inserts…)**")
    comp_df = st.data_editor(
        pd.DataFrame([{"Désignation": c.designation, "Qté": c.qty}
                      for c in part.components] or [{"Désignation": "", "Qté": 1}]),
        num_rows="dynamic", key="comp_ed", use_container_width=True)
    machined_vol = st.number_input(
        "Volume usiné / matière enlevée (cm³) — pour procédé usinage",
        value=float(part.machined_volume_cm3 or 0.0), min_value=0.0, step=1.0)

    def _f(v, d=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d

    def _i(v, d=1):
        try:
            return int(v)
        except (TypeError, ValueError):
            return d

    def _b(v):
        return bool(v)

    part.holes = [Hole(str(r["Forme"]), _f(r["Ø (mm)"]), _i(r["Qté"]),
                       _b(r.get("Taraudé", False)), _b(r.get("Fraisé", False)))
                  for _, r in holes_df.iterrows() if _f(r["Ø (mm)"]) > 0]
    part.bends = [Bend(_f(r["Angle (°)"]), _f(r["Rayon (mm)"]) or None,
                       _f(r["Long. (mm)"]) or None, _i(r["Qté"]))
                  for _, r in bends_df.iterrows() if _i(r["Qté"]) > 0]
    part.welds = [Weld(_f(r["Long. (mm)"]), _i(r["Qté"]), str(r["Type"]))
                  for _, r in welds_df.iterrows() if _f(r["Long. (mm)"]) > 0]
    part.components = [Component(str(r["Désignation"]), _i(r["Qté"]))
                       for _, r in comp_df.iterrows() if str(r["Désignation"]).strip()]
    part.material = material
    part.process_type = process
    part.surface_treatment = treatment
    part.machined_volume_cm3 = machined_vol or None
    st.session_state.part = part

    # --- Étape 3 : calcul déterministe ------------------------------------- #
    st.markdown(brand.step_html(3, "Devis généré", lock=True), unsafe_allow_html=True)
    geo = derive_geometry(part)
    bd = compute_quote(part, cfg, geo)
    report = run_full_validation(part, bd, geo)

    icon, kind = LEVEL_STYLE[report.status]
    getattr(st, kind)(f"{icon} Fiabilité : {report.status.value}")
    for n in bd.notes:
        st.warning("ℹ️ " + n)
    with st.expander("Détail des contrôles de fiabilité",
                     expanded=report.status != Level.OK):
        for chk in report.all:
            ico, _ = LEVEL_STYLE[chk.level]
            st.write(f"{ico} {chk.message}")

    m1, m2, m3 = st.columns(3)
    m1.metric("Prix unitaire", _eur(bd.unit_price))
    m2.metric(f"Total ({cfg.quantity} pièces)", _eur(bd.total_price))
    m3.metric("Coût de revient unitaire", _eur(bd.unit_cost))

    with st.expander("Grandeurs dérivées (recalculées pour fiabilité)"):
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Surface dév.", f"{geo.developed_surface_m2:.4f} m²", geo.source_surface)
        g2.metric("Longueur découpe", f"{geo.cut_length_mm:.0f} mm", geo.source_cut)
        g3.metric("Volume", f"{geo.volume_mm3:.0f} mm³")
        g4.metric("Masse", f"{geo.mass_g:.0f} g")

    st.subheader("Décomposition du coût (unitaire)")
    df = pd.DataFrame([(l.poste, l.montant) for l in bd.lines],
                      columns=["Poste", "Coût (€)"])
    df["Part (%)"] = (df["Coût (€)"] / bd.unit_cost * 100).round(1) if bd.unit_cost else 0
    cc1, cc2 = st.columns([2, 1])
    cc1.dataframe(df.style.format({"Coût (€)": "{:.3f}", "Part (%)": "{:.1f}"}),
                  use_container_width=True, hide_index=True)
    cc2.bar_chart(df.set_index("Poste")["Coût (€)"], color=brand.BRAND["primary"])

    # --- Explicabilité : d'où vient chaque chiffre ------------------------- #
    st.subheader("🔍 Explicabilité — d'où viennent les résultats")
    with st.expander("Traçabilité des données d'entrée", expanded=False):
        for s in explain.sources(part, geo):
            st.write(f"• {s}")
    st.caption("Détail du calcul de chaque poste (formule + valeurs utilisées) :")
    exp_rows = [{"Poste": l.poste, "Montant (€)": round(l.montant, 3),
                 "Formule": l.formule, "Calcul": l.calcul}
                for l in explain.explain(part, cfg, geo, bd)]
    st.dataframe(pd.DataFrame(exp_rows), use_container_width=True, hide_index=True)
    with st.expander("Synthèse coût → prix"):
        for l in explain.totals_explanation(cfg, bd):
            calc = f" = {l.calcul}" if l.calcul else ""
            st.write(f"**{l.poste}** : {_eur(l.montant)}  ·  *{l.formule}*{calc}")

    st.subheader("Export")
    if report.has_error:
        st.warning("Devis bloqué : corrigez les erreurs de fiabilité avant export.")
    else:
        pdf = build_pdf(part, bd, geo, cfg)
        st.download_button("⬇️ Télécharger le devis (PDF)", data=pdf,
                           file_name=f"devis_{part.reference or 'piece'}.pdf",
                           mime="application/pdf", type="primary")
else:
    st.info("👆 Importez un plan puis **Extraire**, ou testez avec **Charger le cas démo**.")

st.markdown(
    f'<div class="maji-footer">{brand.BRAND["name"]} · Outil interne de devis assisté IA — '
    "extraction par IA, calcul déterministe et auditable.</div>",
    unsafe_allow_html=True)
