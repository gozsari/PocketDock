# MM-GBSA Rescoring

MM-GBSA-style rescoring adds a second binding-energy estimate to each docked pose, complementary to Vina's score. PocketDock's implementation is **opt-in**, **lightweight**, and **approximate** — it's calibrated for ranking poses within the same job, not for predicting absolute binding free energies.

<!-- TODO: screenshot — Results table with the MM-GBSA score column visible → docs/images/results-mmgbsa-column.png -->

## When to use it

- **Re-rank Vina poses** that look comparable by combined score — MM-GBSA often disagrees with Vina on close calls, and the disagreement is informative.
- **Triage a hit list** from a batch screen — flag ligands where Vina and MM-GBSA agree on the top pose vs. those where they don't.
- **Stress-test ensemble docking** — compare the MM-GBSA scores of the top pose in different conformations to see if any one conformation stands out.

Skip it for first-pass screening: rescoring multiplies per-job runtime, and Vina's combined score is already enough to filter the obvious non-binders.

## Enabling MM-GBSA

On the upload page (single or batch tab), tick **MM-GBSA rescore**. The flag applies to every pose the job produces. Combine freely with pose refinement and ensemble docking — they cascade in this order:

```
... → Vina docking → (refine_poses?) → (rescore_mmgbsa?) → COMPLETED
```

When `rescore_mmgbsa=true`, the job transitions through `running_mmgbsa` after Vina (and after refinement, if enabled). Failures during rescoring are non-fatal — the pose still ships with its Vina score, just without an MM-GBSA value.

## What it actually computes

!!! warning "Read this — it's not strict MM-GBSA"
    PocketDock's "MM-GBSA" is a deliberately lightweight stand-in. It uses RDKit + simple force-field terms rather than the full AMBER MM-GBSA protocol. Treat the score as a **second opinion to Vina**, not as a rigorous ΔG prediction.

The actual calculation per pose:

1. Parse the receptor once: extract heavy-atom coordinates, Gasteiger partial charges (via RDKit), and Lennard-Jones vdW radii.
2. Parse the pose PDB: ligand coordinates, Gasteiger charges, and vdW radii.
3. Compute the **protein–ligand interaction energy** as a sum of:
   - **Coulomb** electrostatic energy between protein and ligand atoms
   - **Lennard-Jones** vdW energy (12-6 form, Lorentz–Berthelot combining rules)
4. Compute the **ligand strain** with MMFF94 (single-point energy of the bound conformer minus the energy of the same connectivity after a local relaxation).
5. Total: `ΔG ≈ E_interaction + E_strain`, in **kJ/mol** (more negative = stronger binding).

There is **no implicit solvent term, no entropy term, and no per-residue decomposition** — this is intentional. The goal is to give a fast, additional ranking signal that's grounded in well-defined physics, not to compete with a proper MD/MM-PBSA workflow.

## Reading the score

The `mmgbsa_score` column appears in the results table next to Vina's affinity. Sort by it to see the MM-GBSA ranking. **More negative is stronger binding.**

| MM-GBSA ΔG (kJ/mol) | Rough interpretation |
|---------------------|----------------------|
| `≤ −150` | Strong (lots of favorable contacts, low strain) |
| `−150 to −80` | Moderate |
| `−80 to −20` | Weak — limited contact area or significant strain |
| `> −20` | Likely non-binder (or a Vina pose with serious geometry problems) |

These ranges depend strongly on system size and pocket polarity — a small hydrophobic pocket simply can't produce ΔG values as negative as a large polar one. **Compare scores within the same job**, not across different proteins.

### What sign / units to expect

- **Sign**: negative = favorable binding. A positive `mmgbsa_score` means the calculated interaction is unfavorable — usually a clash or a high-strain conformer.
- **Units**: kJ/mol (not kcal/mol — that's Vina's convention). Multiply Vina's kcal/mol by ~4.184 if you want to put both on the same scale.
- **Missing values**: `null` in the JSON / blank in the table means rescoring failed for that pose (rare — usually a parsing edge case). The pose's other columns are unaffected.

## When Vina and MM-GBSA disagree

Their disagreement is the point. The two methods see different things:

| Vina favors | MM-GBSA favors |
|-------------|----------------|
| Empirically-trained pose ranking | Explicit electrostatics + vdW |
| Hydrophobic burial via pseudo-shape terms | Specific polar contacts (Coulomb is the loudest term) |
| Native-like geometries from training | Geometrically clean, low-strain conformers |

A pose where Vina and MM-GBSA agree on the top rank is more credible than one where only Vina likes it. Look closer at poses with strong Vina but weak MM-GBSA — often they're hydrophobic-burial poses lacking specific contacts, which is a known Vina failure mode.

## Cost

- Single-pose rescoring is **~1–3 seconds** on a typical CPU.
- A standard job (3 pockets × 9 poses = 27 poses) adds **roughly 30 seconds–1 minute** of `running_mmgbsa` time.
- In an ensemble (N conformations × ~27 poses each), the cost is N× that. Plan accordingly.

There's no GPU acceleration for this path; everything runs on CPU through RDKit.

## API access

Per-pose scores appear in the `results[].mmgbsa_score` field of `/api/jobs/<job_id>/results/` (see the [API reference](../api.md)).

```python
import requests
data = requests.get("http://localhost:8000/api/jobs/42/results/").json()
by_mmgbsa = sorted(
    (r for r in data["results"] if r["mmgbsa_score"] is not None),
    key=lambda r: r["mmgbsa_score"],
)
for r in by_mmgbsa[:5]:
    print(f"pocket {r['pocket_rank']} pose {r['pose_rank']}: "
          f"Vina {r['affinity']} kcal/mol, MM-GBSA {r['mmgbsa_score']:.1f} kJ/mol")
```

## Tips

- **Always pair MM-GBSA with pose refinement** when the goal is the cleanest possible score — refined poses have lower strain and produce more meaningful interaction energies. Raw Vina poses sometimes carry small clashes that inflate the strain term.
- **Don't compare MM-GBSA scores across targets** — the magnitudes are pocket-size-dependent.
- **Use it as a tiebreaker** in batch screening: filter to the top 20% by combined score, then re-rank that subset by MM-GBSA before manual inspection.
- **If you need rigorous ΔG estimates**, export the poses and run a real MM-PBSA / MM-GBSA workflow (`ambertools`, `gmx_MMPBSA`) or FEP. PocketDock's score is not a substitute.

## See also

- [Interpreting Results — MM-GBSA column](../interpreting-results.md#mm-gbsa-score) — how it sits next to Vina in the results table
- [Concepts: MM-GBSA score](../concepts.md#mm-gbsa-score) — short glossary entry
- [API reference](../api.md) — the `mmgbsa_score` field
