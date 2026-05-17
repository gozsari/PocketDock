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

## Beyond single-ligand docking

PocketDock v2.0 adds several capabilities on top of the basic pocket+Vina flow. Each has its own user-guide page; the short definitions below are enough to orient yourself.

### Batch job

A **batch job** is a single submission that creates one `DockingJob` per ligand against a shared protein. PocketDock supports up to 100 ligands per batch; multi-molecule SDF files are split automatically. All jobs in a batch share a `batch_id` and appear on a single dashboard at `/batch/<batch_id>/`. See [Batch Docking](user-guide/batch-docking.md).

### Ensemble docking

**Ensemble docking** generates several plausible conformations of the receptor and docks the ligand into all of them. PocketDock supports two methods:

- **NMA (Normal Mode Analysis)** — fast (~30 s for 5 conformations). Builds an anisotropic network model from the Cα atoms, then perturbs the structure along the lowest normal modes. Captures slow, collective backbone motions.
- **MD (short OpenMM molecular dynamics)** — slower (5–15 min). Runs a 20 ps Langevin simulation at 300 K with AMBER14 + OBC2 implicit solvent and saves N evenly-spaced snapshots. Captures local relaxation including side-chain rearrangements.

The number of conformations (`num_conformations`) is configurable from 2 to 10. Each child conformation becomes its own docking job; the ensemble dashboard at `/ensemble/<ensemble_id>/` aggregates them and shows a consensus top-20 pose ranking by combined score. See [Ensemble Docking](user-guide/ensemble-docking.md).

### ADMET, Lipinski, Veber, QED

**ADMET** stands for *Absorption, Distribution, Metabolism, Excretion, Toxicity* — the in-vivo behaviors that determine whether a binder can become an actual drug. PocketDock doesn't predict ADMET directly; it computes a set of fast **drug-likeness descriptors** from RDKit that correlate with good oral-drug behavior.

- **Lipinski's rule of five** — MW ≤ 500, logP ≤ 5, H-bond donors ≤ 5, H-bond acceptors ≤ 10. The count of broken rules is the **Lipinski violation** number.
- **Veber's rules** — TPSA ≤ 140 Å² *and* rotatable bonds ≤ 10.
- **QED** — Quantitative Estimate of Drug-likeness on `[0, 1]`. A single number that blends several Lipinski-style features and structural alerts. Marketed oral drugs typically sit in `0.5–0.8`.

ADMET runs on every job automatically; the panel appears on the results page. See [ADMET Properties](user-guide/admet.md).

### Pose refinement

**Pose refinement** is an optional post-docking step that energy-minimizes each Vina pose with OpenMM (AMBER14-all force field + OBC2 implicit solvent, Langevin dynamics at 300 K, no constraints). The result is a slightly relaxed pose with reduced steric clashes and small geometry adjustments. After refinement, PocketDock re-runs the interaction analysis so the contact list reflects the relaxed geometry. Enabled by ticking **Refine poses** on the upload form.

### MM-GBSA score

A **second, physics-based binding-energy estimate** added to each pose when **MM-GBSA rescore** is enabled. PocketDock's implementation is a lightweight stand-in for the full AMBER MM-GBSA protocol: it uses RDKit MMFF94 + Gasteiger charges to compute a per-pose interaction energy (Coulomb + Lennard-Jones) plus a ligand-strain term, reported in **kJ/mol** (more negative = stronger binding). It is **not** a rigorous ΔG prediction — use it as a second opinion to Vina, not as a replacement for it. See [MM-GBSA Rescoring](user-guide/mmgbsa-rescoring.md).

## What PocketDock is *not*

- Not a molecular dynamics simulator — there's no time evolution or solvation modeling.
- Not a free-energy perturbation tool — the affinities are scoring-function estimates, not rigorous ΔG predictions.
- Not a docking validator — predicted poses still need experimental confirmation for any high-stakes claim.

For most exploratory and ranking work — virtual screening, hypothesis generation, teaching — that's plenty.
