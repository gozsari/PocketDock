# Concepts

A short primer on what PocketDock does and the terminology it uses. Skip this page if you're already comfortable with structure-based virtual screening.

## Molecular docking, in one paragraph

**Docking** predicts how a small molecule (the *ligand*) binds to a protein (the *receptor*). The output is a set of candidate **poses** — each pose is a 3D arrangement of the ligand within a binding site, scored by an estimated **binding affinity**. Better-scoring poses are more likely to represent the true bound state. Docking does **not** simulate molecular dynamics; it samples plausible orientations and ranks them with a fast scoring function.

## Binding pockets

Most drug-like ligands bind in **cavities** on the protein surface — clefts deep enough to accommodate a small molecule and lined with the right mix of hydrophobic and polar residues. These cavities are *binding pockets*.

PocketDock uses **[P2Rank](https://github.com/rdk/p2rank)** to predict pockets directly from the 3D structure. P2Rank is a machine-learning model that scores patches of the protein surface by how *druggable* they look. For each predicted pocket you get:

- **Probability** (0–1) — likelihood the pocket can bind a drug-like molecule.
- **P2Rank score** — an internal pocket-quality metric (higher is better).
- **Center coordinates** — used by Vina to position the docking grid.
- **Lining residues** — the amino acids forming the pocket wall.

You don't need to specify a binding site in advance. PocketDock docks into the **top *N* pockets** (you set *N* — default is 3).

## Docking poses

For each pocket, AutoDock Vina searches for ligand conformations and orientations that minimize the predicted binding free energy inside the docking box. It returns up to **9 ranked poses per pocket** by default, ordered from best (lowest energy) to worst.

Each pose has:

- **Affinity** in **kcal/mol** (more negative = stronger predicted binding).
- **RMSD lower bound** and **upper bound** vs. the best pose — measures of pose uncertainty in Ångströms.

## Binding affinity, in numbers

Vina's affinity is an estimate of the binding free energy ΔG. As a rough guide:

| Affinity (kcal/mol) | Predicted strength |
|---|---|
| ≤ −10 | Very strong |
| −10 to −8 | Strong |
| −8 to −6 | Moderate |
| −6 to −4 | Weak |
| > −4 | Very weak |

These ranges are heuristics — Vina's scoring function is fast but approximate, so treat affinities as *rankings* rather than absolute predictions. Confidence is highest when comparing similar ligands against the same target.

## Exhaustiveness

Vina's **exhaustiveness** parameter controls how many independent search runs are performed inside the docking box. Default is `8`. Doubling it roughly doubles runtime but reduces the chance of missing a low-energy pose. Use `16` or `32` for tricky systems (flexible ligands, large pockets); use the default for screening.

## What the "combined score" is

PocketDock reports a **combined score** in the results table that blends pocket probability with binding affinity:

```
combined = 0.4 × pocket_probability + 0.6 × normalize(affinity, max = -15.0)
```

- `pocket_probability` is in `[0, 1]` from P2Rank.
- `normalize(affinity, max=-15.0)` maps affinity to `[0, 1]` such that −15 kcal/mol = 1.0 and 0 kcal/mol = 0.0.

The intent: a pose ranks well only if it sits in a credible pocket *and* binds tightly. See [Interpreting Results](interpreting-results.md#combined-score) for a worked example.

## Useful related concepts

- **Ligand efficiency (LE)** — affinity normalized by ligand size; lets you compare a tight-binding small molecule against a tight-binding large molecule. PocketDock displays it in the pose info panel.
- **Dissociation constant (Kd)** — affinity expressed as a concentration; PocketDock estimates it from the docking score using the Boltzmann relation. Useful as an intuitive number, but inherits all the uncertainty of the docking score.
- **Interactions** — specific contacts between ligand and pocket residues (H-bonds, hydrophobic, salt bridges, π-stacking, π-cation, halogen). PocketDock detects six types geometrically and visualizes them in the 3D viewer. See [Interaction Analysis](user-guide/interactions.md).

## What PocketDock is *not*

- Not a molecular dynamics simulator — there's no time evolution or solvation modeling.
- Not a free-energy perturbation tool — the affinities are scoring-function estimates, not rigorous ΔG predictions.
- Not a docking validator — predicted poses still need experimental confirmation for any high-stakes claim.

For most exploratory and ranking work — virtual screening, hypothesis generation, teaching — that's plenty.
