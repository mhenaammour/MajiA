# Outil de devis assisté par IA — Groupe Maji (V1)

Prototype fonctionnel de bout en bout : **plan technique → extraction IA → calcul déterministe → devis structuré (PDF)**.
Remplace le devis Excel manuel par un process rapide, fiable et **auditable**.

---

## 1. Démarrage

```bash
pip install -r requirements.txt
streamlit run app.py
```

L'application s'ouvre sur `http://localhost:8501`.

- **Sans clé API** → cliquez sur **« Cas démo »** : l'app tourne de bout en bout sur la pièce
  `SUPPORT REAR BRAKE` du plan fourni.
- **Avec clé API Anthropic** → saisissez-la dans la barre latérale (*Connexion IA*), importez un
  plan PDF/image, cliquez **« Extraire »** : Claude Vision lit le plan et remplit les caractéristiques.
  La clé peut aussi venir de la variable d'environnement `ANTHROPIC_API_KEY` ou de `st.secrets`.

> Adaptez `CLAUDE_MODEL` dans `config.py` au modèle auquel votre clé donne accès.

---

## 2. Ce que ça change vs Excel

| Excel manuel | Cet outil |
|---|---|
| Ressaisie manuelle des cotes depuis le plan | **Extraction automatique** par l'IA |
| Formules dispersées, peu traçables | Moteur de prix **centralisé et documenté** |
| Erreurs silencieuses | **Contrôles de fiabilité** (cohérence + bornes) |
| Pas de garde-fou | Prix incohérent **détecté et corrigé** |
| Mise en forme manuelle | Devis PDF **généré automatiquement** |

---

## 3. Rôle PRÉCIS de l'IA

L'IA fait **une seule chose** : lire le plan (PDF/image) et en extraire des **caractéristiques
structurées** (dimensions, trous, plis, matière, tolérances) au format JSON strict.

**L'IA ne calcule aucun prix.** Le prix est produit par un moteur déterministe (`pricing.py`) :
mêmes entrées → même prix, toujours. C'est ce qui rend le devis défendable et reproductible.

- Techno : **Claude (Vision)** via l'API Anthropic, document PDF/image en base64.
- Le prompt d'extraction est dans `extraction.py` (`EXTRACTION_PROMPT`).
- *(Évolution possible : RAG sur l'historique de devis pour caler marges et temps par famille de pièces.)*

---

## 4. Logique métier (calcul du prix)

Coût de revient unitaire =
`matière + découpe laser + pliage + sertissage + finition + contrôle/conditionnement + composants + réglages série amortis`
puis `prix de vente = coût × (1 + marge)`.

- **Matière** : flan brut = surface nette × (1 + taux de chute) ; masse × prix/kg matière.
- **Découpe** : longueur de coupe / vitesse (table par matière+épaisseur) + temps d'amorces.
- **Pliage** : nb de plis × temps/pli × taux plieuse.
- **Réglages série** : programmation + réglages, **amortis sur la quantité** (d'où l'effet série).

Toutes les hypothèses (prix matière, vitesses, taux horaires, temps, marge, quantité) sont
**modifiables** : base dans `config.py`, ajustables en direct dans la barre latérale.

Ordres de grandeur sur la pièce démo (S235) : **≈ 54 € à l'unité, ≈ 3,65 € en série de 100**.

---

## 5. Fiabilité (point clé)

Trois lignes de défense dans `validation.py` :

1. **Validation d'entrée** — les features extraites sont-elles plausibles (épaisseur, dimensions, Ø) ?
2. **Cohérence géométrique** — volume ≈ surface × épaisseur, masse ≈ volume × densité.
   Les grandeurs sont **recalculées** ; une valeur du plan jugée incohérente est ignorée et
   remplacée par la valeur géométrique (signalée dans l'UI).
3. **Garde-fous prix** — le prix de vente ne peut pas passer sous le coût matière ; le prix au kg
   de pièce finie doit rester dans une plage usuelle.

Niveaux : `OK` / `WARNING` (calcul mais validation humaine conseillée) / `ERROR` (export bloqué).
**L'humain reste dans la boucle** : toutes les caractéristiques restent corrigeables avant calcul.

---

## 6. Architecture

```
Plan (PDF/img) ──► extraction.py (Claude Vision)  ──► PartFeatures (JSON)
                                                         │
                          (humain vérifie/corrige) ◄─────┤
                                                         ▼
                          pricing.py (déterministe) ──► CostBreakdown
                                                         │
                          validation.py (fiabilité) ◄────┤
                                                         ▼
                          pdf_export.py ──────────────► Devis PDF
```

| Fichier | Rôle |
|---|---|
| `app.py` | UI Streamlit + orchestration (parcours utilisateur) |
| `extraction.py` | Service d'extraction IA + repli démo |
| `pricing.py` | Moteur de prix déterministe |
| `validation.py` | Contrôles de fiabilité |
| `pdf_export.py` | Génération du devis PDF |
| `config.py` | Paramètres métier (base matière, taux, vitesses) |
| `models.py` | Modèle de données pivot `PartFeatures` |

> Stockage : la V1 est sans base de données (état de session). Évolution naturelle : SQLite/PostgreSQL
> pour historiser devis + features et alimenter un RAG de calage des marges.

---

## 7. Personnalisation aux couleurs Maji

Toute l'identité visuelle est centralisée dans **`brand.py`** (dictionnaire `BRAND`).
Les couleurs actuelles approchent l'univers Maji ; pour la charte exacte :

1. **Couleurs** : remplacez les codes hex dans `BRAND` (`ink`, `primary`, `primary_dark`…).
   Mettez aussi à jour `.streamlit/config.toml` (`primaryColor`, `textColor`).
   Astuce : ouvrez le site Maji, clic droit → *Inspecter*, relevez les codes hex,
   ou récupérez-les depuis la charte graphique.
2. **Logo** : déposez le fichier `logo.png` dans ce dossier → il remplace
   automatiquement le wordmark « MAJI » dans l'en-tête (et le PDF reprend la couleur `ink`).

Aucune couleur n'est codée en dur ailleurs : un seul fichier à modifier.

> `preview.html` donne un aperçu statique du rendu (à ouvrir dans un navigateur).

---

## 8. Déploiement GitHub + Streamlit Cloud (sans exposer la clé)

**Règle d'or : la clé API n'entre jamais dans Git.** L'app lit la clé depuis
`st.secrets`, une variable d'environnement, ou la saisie manuelle — jamais en dur.
Le `.gitignore` exclut déjà `.streamlit/secrets.toml`.

**1. Pousser sur GitHub**
```bash
git init
git add .
git status            # vérifiez qu'AUCUN secrets.toml n'apparaît
git commit -m "Outil de devis assisté IA - Maji (V1)"
git branch -M main
git remote add origin https://github.com/<vous>/<repo>.git
git push -u origin main
```

**2. Déployer sur Streamlit Cloud**
- Allez sur share.streamlit.io → *New app* → choisissez le repo, branche `main`,
  fichier `app.py`.

**3. Injecter la clé en secret (jamais dans le code)**
- Dans l'app déployée : *Settings → Secrets*, collez :
  ```toml
  ANTHROPIC_API_KEY = "sk-ant-..."
  ```
- L'app la lit automatiquement via `st.secrets`. Aucune modification de code.

**Sécurité / coûts**
- Si vous mettez le secret sur une app **publique**, tous les visiteurs consomment
  *votre* crédit API. Deux options sûres : (a) gardez l'app **privée** (restriction
  d'accès Streamlit Cloud), ou (b) **ne mettez pas** de secret et saisissez la clé
  manuellement dans la barre latérale pendant la démo (le mode démo marche sans clé).
- Définissez une **limite de dépense** dans la console Anthropic.
- Si une clé est exposée par erreur, **révoquez-la immédiatement** dans la console et
  régénérez-en une (un commit reste dans l'historique Git même après suppression).

---

## 9. Paramétrage dynamique (rien n'est figé)

Tout le « savoir métier » est dans **`parameters.yaml`** : matières, taux horaires,
vitesses de coupe, traitements, temps opératoires **et la liste des opérations**.
Le moteur lit ce fichier au démarrage ; modifier le fichier (ou l'uploader dans
l'app via *Paramètres dynamiques (YAML)*) suffit à faire évoluer l'outil — **sans
toucher au code**.

- Ajouter une **matière** → une entrée sous `materials:`.
- Changer un **taux** → une valeur sous `rates_eur_h:`.
- Ajouter une **opération** → une entrée sous `operations:` (ex. `kind: time_per_unit`,
  `qty: n_holes`, `time: ...`, `rate: ...`). L'interface, le PDF et l'explicabilité
  l'affichent automatiquement.

Si `parameters.yaml` (ou PyYAML) est absent, l'application retombe sur un jeu de
paramètres par défaut intégré et fonctionne quand même.
