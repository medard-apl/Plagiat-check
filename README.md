# PlagiatCheck

Outil léger de détection de plagiat assisté par IA. L'utilisateur importe un
mémoire (PDF ou DOCX) sur une page web, et reçoit un rapport indiquant les
passages potentiellement copiés ou reformulés depuis une source académique
ou le web ouvert.

Projet développé dans un cadre professionnel, en respectant une contrainte
forte : **aucune dépense financière**. Toutes les briques utilisées sont
gratuites (sources académiques sans clé API, recherche web via DuckDuckGo,
modèle d'embeddings exécuté en local).

## Fonctionnement en un coup d'œil

```
Utilisateur → page web (upload) → backend FastAPI → analyse → rapport JSON → affichage
```

1. **Extraction** du texte du document (PDF/DOCX), nettoyage (en-têtes/pieds
   de page répétés, numéros de page), isolement de la bibliographie.
2. **Segmentation** du texte en paragraphes comparables (~40-60 mots), avec
   détection automatique de la langue.
3. **Recherche de candidats** pour chaque segment assez long : sources
   académiques gratuites (Semantic Scholar, CrossRef, arXiv) et web ouvert
   (DuckDuckGo + extraction du contenu des pages trouvées).
4. **Comparaison** de chaque segment aux candidats trouvés, selon deux
   méthodes complémentaires :
   - **Copie exacte** : empreintes de k-grammes (séquences de mots), détecte
     une citation verbatim même noyée dans un texte plus long.
   - **Similarité sémantique** : embeddings multilingues
     (`multilingual-e5-base`), détecte une reformulation/paraphrase.
5. **Agrégation** en un score global et une liste de passages suspects avec
   leur source.

## Structure du projet

```
plagiat-check/
├── backend/
│   ├── main.py                       # API FastAPI — endpoint POST /analyze
│   ├── services/
│   │   ├── extraction.py             # Lecture PDF/DOCX, nettoyage, bibliographie
│   │   ├── segmentation.py           # Découpage en segments + détection langue
│   │   ├── fingerprint.py            # Détection de copie exacte (k-grammes)
│   │   ├── embeddings.py             # Similarité sémantique (multilingual-e5-base)
│   │   ├── academic_sources.py       # Semantic Scholar, CrossRef, arXiv
│   │   ├── web_search.py             # DuckDuckGo + extraction de contenu web
│   │   └── scoring.py                # Orchestration et calcul du score final
│   ├── tests/
│   │   ├── fixtures/                 # Documents de test (générés localement)
│   │   ├── test_pipeline.py          # Test bout-en-bout local (sans API externes)
│   │   ├── calibration_dataset.py    # Paires étiquetées pour la calibration
│   │   └── test_calibration.py       # Mesure précision/rappel du seuil sémantique
│   └── requirements.txt
│
└── frontend/
    ├── index.html
    ├── style.css
    └── script.js                     # Appelle POST /analyze en FormData
```

## Installation

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

Le premier lancement téléchargera automatiquement le modèle
`multilingual-e5-base` (~1 Go) depuis Hugging Face — une connexion internet
est nécessaire une seule fois, il est ensuite mis en cache localement.

## Lancer le projet

**Backend :**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Frontend :** à servir via un serveur local (pas en `file://`, pour éviter
les blocages de sécurité du navigateur) :
```bash
cd frontend
python3 -m http.server 5500
```
Puis ouvrir `http://127.0.0.1:5500`.

## API

### `POST /analyze`

Requête en `multipart/form-data` :

| Champ | Type | Description |
|---|---|---|
| `file` | fichier | Document à analyser (`.pdf` ou `.docx`, 20 Mo max) |
| `language` | texte | Langue indiquée par l'utilisateur (`auto`, `fr`, `en`...) — actuellement non utilisée activement, la détection est automatique |

Réponse :
```json
{
  "global_score": 12.4,
  "matches": [
    {
      "type": "exact",
      "score": 96.0,
      "text": "...",
      "source_url": "https://...",
      "source_title": "..."
    }
  ],
  "segment_count": 14
}
```

### `GET /health`

Vérification simple que le service tourne (`{"status": "ok"}`).

## Tests

**Pipeline local** (extraction → segmentation → fingerprint → embeddings,
sans appel réseau externe) :
```bash
python3 tests/test_pipeline.py
```

**Calibration des seuils** (précision/rappel sur un jeu de paires
étiquetées) :
```bash
python3 tests/test_calibration.py
```

## Limites connues

- **Détection de langue globale, pas par paragraphe** : un document qui
  mélange plusieurs langues (ex : un mémoire français citant un passage en
  anglais) n'est segmenté qu'avec une seule langue détectée pour tout le
  document, ce qui peut légèrement dégrader la segmentation des paragraphes
  dans la langue minoritaire.
- **Seuil de similarité sémantique en cours de calibration** : des textes
  qui partagent un thème et du vocabulaire académique commun (sans être de
  vraies paraphrases l'un de l'autre) peuvent produire un score sémantique
  élevé. Voir `tests/test_calibration.py` pour l'état actuel de la
  calibration et les cas d'erreur connus.
- **Pas de comparaison contre une base interne** : chaque analyse est
  indépendante, il n'y a pas de mémorisation des documents déjà uploadés
  (choix assumé pour cet outil sans comptes utilisateurs — voir la
  discussion de conception du projet).
- **Recherche web non exhaustive** : seule une poignée de résultats
  DuckDuckGo par segment est vérifiée, ce n'est pas un scan complet du web
  comme le ferait un outil commercial (Turnitin, Copyleaks...).
- **Dépendance à la disponibilité des API externes** : Semantic Scholar,
  CrossRef, arXiv et DuckDuckGo peuvent chacun être temporairement
  indisponibles ou limiter le débit ; le pipeline continue dans ce cas avec
  les sources encore disponibles plutôt que d'échouer entièrement.
- **Blocage DuckDuckGo sous forte charge (constaté, pas juste théorique)** :
  `ddgs` scrape la page de résultats DuckDuckGo (ce n'est pas une API
  officielle avec quota). Une analyse complète d'un document peut
  déclencher un blocage temporaire de l'IP, qui dure ensuite plusieurs
  heures. `scoring.MAX_SEGMENTS_WITH_WEB_SEARCH` (5 par défaut) limite les
  dégâts en plafonnant le nombre de segments vérifiés contre le web par
  analyse — au-delà, ces segments restent quand même vérifiés contre les
  sources académiques, qui n'ont jamais montré ce problème. En pratique :
  espacer les analyses complètes plutôt que les enchaîner, et utiliser
  `tests/debug_pipeline.py` pour vérifier l'état de DuckDuckGo sans
  consommer de budget avant de relancer un vrai test. Ce n'est pas un
  problème résolu, c'est une limite structurelle du choix "gratuit, sans
  clé API" pour cette source précise — à garder en tête si le projet passe
  en usage réel avec plusieurs utilisateurs partageant la même IP serveur.

## Sources et outils utilisés

- [Semantic Scholar API](https://api.semanticscholar.org/) — recherche académique
- [CrossRef API](https://api.crossref.org/) — métadonnées de publications
- [arXiv API](https://arxiv.org/help/api) — preprints scientifiques
- [DuckDuckGo](https://duckduckgo.com/) via `ddgs` — recherche web
- [`multilingual-e5-base`](https://huggingface.co/intfloat/multilingual-e5-base) — embeddings sémantiques multilingues
- [`trafilatura`](https://trafilatura.readthedocs.io/) — extraction de contenu web