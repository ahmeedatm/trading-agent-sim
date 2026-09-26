# trading-agent-sim

Simulation de gains/pertes **en argent fictif** à partir des décisions de
[TradingAgents](https://github.com/TauricResearch/TradingAgents) (v0.5.1), sur données de marché réelles.

TradingAgents produit une note par ticker et par date (`Buy`, `Overweight`, `Hold`, `Underweight`,
`Sell`). Son backtest intégré mesure la *qualité* de ces notes (alpha moyen par note) mais, par choix,
**ne simule pas de portefeuille**. Ce repo ajoute cette couche :

| Commande | Rôle | Coût LLM |
|---|---|---|
| `tasim signals` | Lance TradingAgents sur une grille tickers × dates, stocke les notes (`runs/<run>/signals.csv`, reprise automatique) | Oui |
| `tasim simulate` | Rejoue les notes comme un portefeuille en cash (frais, exécution J+1) vs buy & hold et SPY | Non |
| `tasim paper` | Note du jour → ordres sur un compte **Alpaca paper** (dry-run par défaut) | Oui |

## Règles de simulation

- Long-only, sans levier. Chaque ticker a un « slot » égal = 1/N du capital.
- Exposition du slot selon la note : Buy 100 % · Overweight 75 % · Underweight 25 % · Sell 0 % ·
  Hold et REVIEW = on ne touche à rien (`tasim/ratings.py`).
- Une note datée J est exécutée à **l'ouverture du premier jour de bourse après J** (pas de look-ahead).
- Frais : 5 bps du notionnel échangé par défaut (`--fee-bps`). Valorisation à la clôture.

## Installation

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[paper,dev]"
cp .env.example .env   # ANTHROPIC_API_KEY (+ clés Alpaca paper pour le live)
pytest
```

## Utilisation

```bash
# 1. Pilote bon marché : 2 tickers, 1 analyse / semaine sur 1 mois (≈ 8 runs LLM)
tasim signals NVDA,AAPL --start 2026-08-01 --end 2026-08-31 --every 7 --run pilote

# 2. Simulation en argent fictif (aucun appel LLM, rejouable à volonté)
tasim simulate --run pilote --capital 10000 --fee-bps 5

# 3. Paper trading : à lancer après la clôture US (~22h30 Paris)
tasim paper NVDA,AAPL              # dry-run : affiche les ordres
tasim paper NVDA,AAPL --execute    # envoie les ordres sur le compte paper
```

Par défaut, seuls les analystes `market` et `news` tournent (coût réduit) ; `--full` ajoute `social`
et `fundamentals`. Modèles par défaut : `claude-sonnet-5` (deep) et `claude-haiku-4-5` (quick),
modifiables via `TRADINGAGENTS_*` dans `.env`.

## Limites à garder en tête

- Les flux texte (news, réseaux sociaux) ne sont pas archivés point-in-time : un backtest sur le
  passé voit parfois des contenus postérieurs → résultats **indicatifs**, à confirmer en paper trading.
- Un LLM n'est pas déterministe : deux runs d'une même cellule peuvent différer.
- Ce projet est un outil de recherche, pas un conseil en investissement. Aucun chemin vers un
  compte réel : le client Alpaca est toujours instancié avec `paper=True`.
