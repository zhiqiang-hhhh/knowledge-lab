# Vamana Learning Prototype

This folder is a learning-oriented prototype for the evolution:

1. Linear Scan (exact)
2. Greedy graph search
3. Beam graph search
4. NSG-style pruning intuition (RNG-style)
5. Simplified Vamana build (robust prune with `alpha`)

The goal is not exact reproduction of production implementations.
The goal is to make the algorithmic path easy to understand and runnable.

## Run (from `build` directory)

```bash
cd build
python3 ../vamana_proto/tutorial.py
```

Try parameter sweeps:

```bash
cd build
python3 ../vamana_proto/tutorial.py --beam-width 16 --visit-budget 120
python3 ../vamana_proto/tutorial.py --beam-width 48 --visit-budget 300
python3 ../vamana_proto/tutorial.py --alpha 1.0
python3 ../vamana_proto/tutorial.py --alpha 1.4
```

## How to read the code

- `greedy_search`: local hill-climbing, easy to get trapped.
- `beam_search`: keeps multiple promising frontiers.
- `rng_style_prune`: sparse graph with geometric diversity bias.
- `robust_prune`: core Vamana pruning rule with `alpha`.
- `build_vamana_simplified`: iterative build using search + prune + reverse links.

## Key intuition

- Beam search improves query robustness over pure greedy.
- Good ANN graph quality comes from both search strategy and graph construction.
- Robust prune keeps degree bounded while preserving navigability paths.
- `alpha` controls aggressiveness:
  - smaller `alpha`: stronger pruning, fewer edges, can hurt recall.
  - larger `alpha`: more permissive, better routing, higher graph cost.
