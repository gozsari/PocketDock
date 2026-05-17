# Interpreting Results

PocketDock reports six numbers per docked pose. This page explains what each one means, how it's calculated, and how to read it without over-interpreting.

## At a glance

| Metric | Source | Range | What it tells you |
|--------|--------|-------|-------------------|
| **Binding affinity** | AutoDock Vina | typically −15 to 0 kcal/mol | Predicted strength of binding (more negative = stronger) |
| **Pocket probability** | P2Rank | 0–1 | Likelihood the pocket can bind a drug-like ligand |
| **Combined score** | Computed | 0–1 | Blended ranking of pocket quality + binding strength |
| **Ligand efficiency (LE)** | Computed | 0+ kcal/mol per heavy atom | Affinity normalized by ligand size |
| **Binding strength (Kd)** | Computed | nM to mM | Affinity expressed as a dissociation constant |
| **RMSD LB / UB** | AutoDock Vina | Å | Pose-uncertainty range vs. the best pose |
| **MM-GBSA score** *(opt-in)* | RDKit + force field | kJ/mol | Second-opinion binding energy from physics-based rescoring |
| **ADMET descriptors** *(every job)* | RDKit | — | Drug-likeness panel: MW, logP, TPSA, QED, Lipinski / Veber pass |

## Binding affinity

Vina reports each pose's predicted binding free energy in **kcal/mol**. **More negative is stronger binding.**

A useful mental scale:

| Affinity (kcal/mol) | Predicted strength | Approx. Kd at 298 K |
|---|---|---|
| ≤ −12 | Very strong (drug-like) | sub-nM |
| −12 to −10 | Strong | nM |
| −10 to −8 | Moderate | µM |
| −8 to −6 | Weak | mM |
| > −6 | Very weak / non-binder | — |

!!! warning "Don't over-trust Vina's absolute numbers"
    Vina's scoring function is fast, not rigorous. Treat affinities as **rankings within the same study**, not as substitutes for measured ΔG. A pose that scores −10 kcal/mol in PocketDock is *probably* a better binder than one that scores −6 kcal/mol against the same target — but it is **not** evidence that the molecule's experimental Kd is in the nM range.

## Pocket probability

P2Rank assigns each detected pocket a probability in `[0, 1]` indicating how druggable the pocket looks based on its geometry and the chemistry of the lining residues.

Rough interpretation:

| Probability | Druggability label in PocketDock |
|-------------|----------------------------------|
| `> 0.80` | Highly druggable |
| `0.50–0.80` | Moderately druggable |
| `< 0.50` | Low |

Low probability doesn't mean a pocket can't bind — it means it doesn't look like a typical drug-binding pocket. Allosteric sites, cofactor pockets, and shallow surface clefts often score lower than canonical orthosteric sites.

## Combined score

PocketDock blends pocket probability and binding affinity into a single 0–1 ranking metric. A pose ranks well only if it sits in a credible pocket *and* scores well in docking.

### Formula

$$
\text{combined} = 0.4 \times P_\text{pocket} + 0.6 \times \mathrm{norm}(A)
$$

Where:

- $P_\text{pocket}$ is the pocket probability in `[0, 1]`.
- $A$ is the Vina affinity in kcal/mol.
- The affinity is normalized as

  $$
  \mathrm{norm}(A) = \mathrm{clamp}\!\left(\frac{\min(A, 0)}{A_\max},\ 0,\ 1\right)
  $$

  with $A_\max = -15.0$ kcal/mol. So `−15 kcal/mol → 1.0`, `0 kcal/mol → 0.0`, anything stronger than `−15` clamps to `1.0`.

### Worked example

A pose with affinity `−9.6 kcal/mol` in a pocket with probability `0.72`:

```
norm(A)  = min(-9.6, 0) / -15.0 = 0.64
combined = 0.4 × 0.72 + 0.6 × 0.64 = 0.288 + 0.384 = 0.672
```

That's a **green** combined score — strong by both criteria.

### Color thresholds in the UI

| Combined score | Color | Meaning |
|----------------|-------|---------|
| `> 0.6` | Green | Strong on both axes |
| `0.3–0.6` | Yellow | Mixed — strong on one axis, weak on the other |
| `< 0.3` | Gray | Weak overall |

## Ligand efficiency

Ligand efficiency normalizes affinity by ligand size, letting you compare a tight-binding small fragment against a tight-binding large molecule fairly:

$$
\mathrm{LE} = \frac{-\text{affinity}}{\text{heavy atom count}}
$$

Units are kcal/mol per heavy atom. PocketDock annotates the value:

| LE (kcal/mol/atom) | Label |
|--------------------|-------|
| `> 0.3` | Good |
| `0.2–0.3` | Moderate |
| `< 0.2` | Poor |

Heavy-atom count is the number of non-hydrogen atoms in the ligand. The convention comes from fragment-based drug discovery: an LE near `0.3` is the rule-of-thumb threshold for an efficient fragment.

## Binding strength (Kd)

PocketDock estimates the dissociation constant Kd from the docking affinity using the Boltzmann relation:

$$
K_d = \exp\!\left(\frac{A \times 1000}{R \times T}\right)
$$

with $R = 1.987$ cal/(mol·K) and $T = 298.15$ K. The factor of `1000` converts kcal to cal so the units match.

The resulting Kd is binned into a label:

| Affinity (kcal/mol) | Strength label | Approx. Kd |
|---------------------|----------------|------------|
| ≤ −10 | Very Strong | ≤ ~50 nM |
| −10 to −8 | Strong | ~50 nM – 1 µM |
| −8 to −6 | Moderate | ~1 µM – 50 µM |
| −6 to −4 | Weak | ~50 µM – 1 mM |
| > −4 | Very Weak | > 1 mM |

!!! warning "Kd is a derived number, not a measurement"
    The Kd shown in the UI inherits all of Vina's scoring uncertainty. It's useful as an intuitive sense of scale but should never be reported as a predicted experimental Kd. For a rigorous estimate, use a dedicated free-energy method (FEP, MM/PBSA, or wet-lab measurement).

## RMSD lower / upper bound

For each pose, Vina reports two RMSD values relative to the best pose in the same pocket:

- **RMSD LB** — RMSD computed by matching each atom in the pose to the closest atom of the same type in the reference (best) pose. Insensitive to atom-naming order.
- **RMSD UB** — RMSD computed with the original atom-name correspondence. Sensitive to atom ordering, so generally larger.

Both are in Ångströms. Together they bracket how different a pose is from the top-ranked one in the same pocket. The first pose always has RMSD = 0 by definition.

A small spread (`UB − LB < 0.5 Å`) means the pose is geometrically similar to the best pose. A large spread suggests the pose is structurally distinct (a different orientation or conformation).

## ADMET panel

Every job ships with a drug-likeness panel computed by RDKit. The panel sits alongside the docking poses on the results page; the same data is available as the `admet` field in the API response.

The panel reports physicochemical descriptors (MW, logP, HBA, HBD, TPSA, rotatable bonds, aromatic rings, heavy atoms, ring count, Fsp3) plus two derived scores and two pass/fail flags.

### Lipinski

Lipinski's rule of five flags molecules unlikely to be orally bioavailable. PocketDock counts violations of four conditions:

| Rule | Threshold |
|------|-----------|
| Molecular weight | ≤ 500 Da |
| logP | ≤ 5 |
| H-bond donors | ≤ 5 |
| H-bond acceptors | ≤ 10 |

The **Lipinski pass** badge is green when violations = 0. One violation is traditionally still tolerated; two or more is a clear signal that the molecule sits outside classical oral-drug space — which may be fine for tool compounds, PROTACs, peptidomimetics, or non-oral routes, but is worth knowing.

### Veber

Veber's complementary filter targets oral bioavailability from a flexibility / polarity angle. **Veber pass** requires:

- TPSA ≤ 140 Å²
- Rotatable bonds ≤ 10

Veber tends to catch flexible molecules and overly polar ones that Lipinski misses. Together with Lipinski it's a reasonable two-filter check; passing both is not a guarantee, failing both is a strong steer to go back to the drawing board.

### QED

QED ([Bickerton et al., 2012](https://doi.org/10.1038/nchem.1243)) collapses several drug-likeness features into a single value on `[0, 1]`. Useful when you need one number to rank analogues:

| QED | Read |
|-----|------|
| `≥ 0.8` | Highly drug-like |
| `0.5–0.8` | Drug-like — typical for marketed oral drugs |
| `0.3–0.5` | Borderline |
| `< 0.3` | Outside typical oral-drug space |

!!! note "What ADMET *isn't* doing"
    These are descriptor-based filters, not predictions of permeability, clearance, or toxicity. Passing Lipinski does not predict in-vivo bioavailability — it just says the molecule isn't disqualified by the most common physicochemical red flags. For real ADME predictions, plug the ligand into a dedicated model.

See the [ADMET Properties page](user-guide/admet.md) for the full descriptor list and Python examples for filtering batch results by drug-likeness.

## MM-GBSA score

When **MM-GBSA rescore** is enabled, each pose gets an extra column: a second binding-energy estimate in **kJ/mol** (note: kJ, not kcal — Vina's units differ).

### Sign convention

More **negative** is stronger binding, matching Vina. A positive value means the calculated interaction is *unfavorable*, almost always a sign of geometric clashes or a high-strain conformer.

### Rough magnitude guide

| MM-GBSA ΔG (kJ/mol) | Read |
|---------------------|------|
| `≤ −150` | Strong — lots of favorable contacts, low strain |
| `−150 to −80` | Moderate |
| `−80 to −20` | Weak — small contact area or significant strain |
| `> −20` | Likely non-binder (or a Vina pose with serious geometry problems) |

These ranges are pocket-size dependent — **compare within the same job**, not across different proteins.

### The methodology caveat

!!! warning "It's not strict MM-GBSA"
    PocketDock's implementation is a lightweight stand-in: RDKit MMFF94 force field + Gasteiger partial charges + Lennard-Jones for the protein–ligand interaction energy, plus a ligand-strain term. There's **no implicit-solvent term, no entropy term, and no per-residue decomposition**. Use it as a second opinion to Vina, not as a replacement for a rigorous MM-PBSA or FEP calculation.

### How to use it

- **Tiebreaker** — when two poses have nearly identical combined scores, the one with the more negative MM-GBSA is usually the better bet.
- **Agreement signal** — when Vina and MM-GBSA agree on the top pose, that pose is more credible than when only one method ranks it well.
- **Hydrophobic-burial detector** — Vina sometimes scores hydrophobic-burial poses too well; MM-GBSA, dominated by Coulomb terms, often disagrees, which is informative.

See the [MM-GBSA Rescoring](user-guide/mmgbsa-rescoring.md) page for the full method description and runtime cost.

## Refined vs. raw poses

When **Refine poses** is enabled, every Vina pose is energy-minimized with OpenMM (AMBER14-all + OBC2 implicit solvent, Langevin dynamics) before the results page is rendered. The PDB files served by the viewer are the **refined** poses; the original Vina output is overwritten on disk.

What changes after refinement:

- **Small geometric adjustments** — clashes are removed, bond lengths and angles relax toward force-field equilibrium values.
- **Updated interaction list** — PocketDock re-runs the geometric interaction analysis after refinement, so H-bonds at borderline distances may appear or disappear depending on whether the relaxation pulled them inside or outside the cutoff.
- **Cleaner MM-GBSA scores** — refined poses have lower strain, so their MM-GBSA value tends to be more meaningful. Pairing **Refine poses + MM-GBSA rescore** is the most robust setup PocketDock offers.

What does **not** change:

- **Vina's affinity number** — that's still the original Vina score; refinement does not recompute it.
- **The pose ranking** — refinement is per-pose; PocketDock does not re-sort the table by post-refinement energy.

For most jobs the changes are small (< 1 Å pose RMSD). When refinement makes a big visual difference, treat it as a signal that the original Vina pose had clashes worth investigating.

## Putting it all together

A pose worth following up on usually has:

1. **Strong affinity** — at least −7 kcal/mol, ideally below −9.
2. **Decent pocket probability** — `> 0.5` so the pocket is plausibly druggable.
3. **Reasonable ligand efficiency** — `> 0.2 kcal/mol/atom` to rule out "good score because the ligand is huge".
4. **Specific interactions** — at least a couple of H-bonds or salt bridges with conserved residues, not just hydrophobic contact (see [Interaction Analysis](user-guide/interactions.md)).
5. **Drug-like properties** — Lipinski pass and QED `≥ 0.5`, unless you're deliberately exploring non-oral chemical space.
6. *(If enabled)* **MM-GBSA agreement** — the same pose is also top-ranked by MM-GBSA, or at least scores strongly negative.

A high combined score with no specific interactions is a red flag — likely a non-specific hydrophobic burial that won't translate to selectivity. A pose that wins on Vina but loses on MM-GBSA is the same red flag with a second sensor.
