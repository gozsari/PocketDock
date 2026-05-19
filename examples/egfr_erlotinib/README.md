# Example: EGFR kinase domain + Erlotinib

A small, well-known kinase–inhibitor pair you can use to try PocketDock end-to-end in a few minutes.

## Files

| File | Source | Description |
|---|---|---|
| [4HJO.pdb](4HJO.pdb) | [RCSB PDB 4HJO](https://www.rcsb.org/structure/4HJO) | Inactive EGFR tyrosine kinase domain in complex with erlotinib (2.75 Å, 2012) |
| [erlotinib.sdf](erlotinib.sdf) | [PubChem CID 176870](https://pubchem.ncbi.nlm.nih.gov/compound/176870) | Erlotinib (Tarceva), an EGFR tyrosine kinase inhibitor |

Both files are redistributed under the terms of their respective sources: PDB entries are in the public domain (no license required); PubChem records are public-domain US-government works.

## What you'll see

Erlotinib is the **ground-truth ligand** for this structure, so PocketDock should:

- Detect the **ATP-binding cleft** as one of the top P2Rank pockets
- Produce docked poses with binding affinity around **-7 to -9 kcal/mol**
- Recover hydrogen bonds to the hinge region (typically **Met793**) and hydrophobic contacts in the back pocket

This makes the example useful as a sanity check — if you see numbers wildly different from the above, something is misconfigured.

## How to run

### From the web UI

1. Start PocketDock: `docker compose up --build` (from the repo root)
2. Open <http://localhost:8000>
3. On the upload page:
   - **Protein**: upload `4HJO.pdb`
   - **Ligand**: upload `erlotinib.sdf`
   - Leave AutoDock Vina defaults (exhaustiveness 8, 9 modes)
4. Submit and wait for the job to finish (~1–3 min on a typical laptop)
5. Inspect the top pose in the 3D viewer; the ADMET panel will also be populated

### Optional extras

- **Pose refinement** — tick the "OpenMM refinement" box on the upload form to energy-minimize each pose
- **MM-GBSA rescoring** — tick the rescoring option for a per-pose ΔG estimate
- **Ensemble docking** — generate 5 NMA conformations of the receptor to see how the pocket geometry varies

## Citations

If you use this example in published work, please cite the original sources:

- **4HJO**: Park JH, Liu Y, Lemmon MA, Radhakrishnan R. *Erlotinib binds both inactive and active conformations of the EGFR tyrosine kinase domain.* Biochem J. 2012; 448(3):417–423. doi:[10.1042/BJ20121513](https://doi.org/10.1042/BJ20121513)
- **Erlotinib**: National Center for Biotechnology Information. [PubChem Compound Summary for CID 176870, Erlotinib](https://pubchem.ncbi.nlm.nih.gov/compound/176870).
