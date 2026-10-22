# 🍷 Wine Recollection

Identifier une bouteille de vin à partir de photos d'une étiquette abîmée
(humidité, déchirure, moisissure, décoloration).

Deux façons de l'utiliser :

- **Sans programmer et sans coût supplémentaire** : la page
  [`app/wine-recollection.html`](app/wine-recollection.html), publiée sur claude.ai.
  Elle s'ouvre sur téléphone, prend les photos et utilise votre compte Claude
  (abonnement existant, aucune clé API). Elle n'a pas de recherche web : les
  boutons « Comparer les étiquettes » et « Rechercher » vous laissent vérifier
  chaque candidat.
- **Pour développeurs** : le prototype Python ci-dessous, avec vérification
  automatique par recherche web et mesure de fiabilité. Il passe par l'API
  Anthropic, facturée à l'usage.

## Comment ça marche

L'identification se fait en deux étapes séparées, pour limiter les « inventions » de l'IA :

1. **Observation** (`Clues`) : le modèle relève ce qu'il voit, sans rien identifier.
   Fragments de texte recopiés tels quels (`…ILLAC`, `19?5`), éléments visuels,
   forme de bouteille, capsule, bouchon, mentions légales.
2. **Enquête** (`Identification`) : à partir des indices et des photos, le modèle
   propose 1 à 5 candidats et **vérifie chacun par recherche web**. Pour chaque
   candidat, il donne un score de confiance, les indices qui concordent, ceux qui
   contredisent, les sources consultées, et des questions pour départager les candidats.

```
photos ──► Observation (JSON strict) ──► Enquête + recherche web ──► candidats classés
```

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # https://console.anthropic.com
```

## Identifier une bouteille

```bash
python -m wine_id photo_etiquette.jpg
python -m wine_id face.jpg contre_etiquette.jpg bouchon.jpg --notes "trouvée dans la cave de mon grand-père, région bordelaise"
```

Options utiles :

| Option | Effet |
|---|---|
| `--notes "…"` | Ce que vous savez déjà (origine, époque d'achat…) |
| `--no-web` | Pas de vérification web (plus rapide, moins fiable) |
| `--effort low/medium/high/xhigh/max` | Profondeur de réflexion (défaut : `high`) |
| `--model claude-sonnet-5-5` | Modèle moins cher (défaut : `claude-opus-5-5`, ou la variable `WINE_ID_MODEL`) |
| `--json` | Sortie JSON complète |

**Conseils photo** : lumière rasante (une lampe de côté fait ressortir les encres
pâlies), plusieurs angles en tournant la bouteille, et surtout **le bouchon et la
capsule**, souvent marqués du nom du domaine ou du millésime.

## Mesurer la fiabilité (le plus important)

Sans jeu de test, impossible de savoir si une modification améliore ou dégrade les résultats.

1. **Constituer le jeu de test** : mettez vos photos dans `eval/dataset/photos/`,
   copiez `eval/dataset/answers.example.csv` en `eval/dataset/answers.csv`, et
   indiquez la bonne réponse pour chaque bouteille. Plusieurs photos pour une même
   bouteille sont séparées par `;`.
2. **Compléter avec des étiquettes abîmées artificiellement** : prenez en photo des
   bouteilles en bon état, puis :
   ```bash
   python eval/degrade.py eval/propres/*.jpg --out eval/dataset/photos --variants 3 --damages 2
   ```
   Le script combine au hasard taches d'eau, déchirures, décoloration, moisissure et flou.
3. **Lancer l'évaluation** :
   ```bash
   python eval/run_eval.py --label premier-essai
   python eval/run_eval.py --limit 5 --no-web     # essai rapide et peu coûteux
   ```
   Le script affiche le **top-1** (la bonne bouteille est le 1er candidat), le **top-3**,
   la justesse du millésime et le coût, puis écrit un rapport détaillé dans `eval/results/`.

Objectif suggéré : 30 à 50 bouteilles, dont une bonne part de vraies étiquettes abîmées.
Les données générées par `degrade.py` sont utiles mais moins réalistes.

## Coût

Chaque identification fait deux appels au modèle avec images, plus quelques
recherches web (0,01 $ chacune). Le coût estimé s'affiche à la fin de chaque
résultat. Comptez de l'ordre de quelques centimes à une dizaine de centimes avec
Opus ; `--model claude-sonnet-5-5` divise environ par deux le coût des tokens.

## Structure

```
wine_id/
  schemas.py    formats de sortie (indices, candidats)
  prompts.py    instructions données au modèle
  pipeline.py   les deux étapes + recherche web + suivi du coût
  images.py     redressement EXIF, redimensionnement, encodage
  matching.py   comparaison souple des noms (accents, « Château », « Domaine »…)
  cli.py        ligne de commande
eval/
  degrade.py    abîmer artificiellement des étiquettes
  run_eval.py   mesurer top-1 / top-3 / millésime / coût
  dataset/      vos photos + answers.csv (non versionnés)
tests/          tests hors ligne (aucune clé API nécessaire) : pip install -r requirements-dev.txt && python -m pytest
```

## Prochaines étapes

- [ ] Constituer le jeu de test et mesurer une première base
- [ ] Ajuster les prompts selon les erreurs observées dans `eval/results/`
- [ ] Mode « questions complémentaires » : réinjecter les réponses de l'utilisateur
- [ ] API (FastAPI) pour l'application mobile
- [ ] Application mobile (Expo) : prise de photos guidée, affichage des candidats
- [ ] Base d'étiquettes confirmées + recherche par similarité visuelle
