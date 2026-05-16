# Troubleshooting

Common failure modes mapped to causes and fixes. The error message shown on the status page is the same one stored in the `DockingJob.error_message` field and surfaced via the [status API](api.md#get-job-status).

## Upload-time errors

### "Protein file must be PDB (.pdb), gzipped PDB (.pdb.gz), or mmCIF (.cif)."

The file extension didn't match the whitelist. Convert to one of the supported formats — PyMOL, ChimeraX, or Open Babel can all do this. If your file is already in the right format, check the extension is lowercase.

### "Protein file must be under 50 MB."

Your structure exceeds the form-level size limit. Options:

- Strip waters, ions, alternate conformations, and any non-essential chains.
- Submit a single biological-assembly chain instead of the full crystal asymmetric unit.
- Raise the limit in [Configuration](configuration.md#file-upload-limits) if you control the deployment.

### "Ligand file must be SDF (.sdf), MOL2 (.mol2), or MOL (.mol)."

Same as above for the ligand. Convert with RDKit (`rdkit.Chem.MolToMolFile`), Open Babel (`obabel input.smi -O ligand.sdf --gen3d`), or your editor of choice.

### "Ligand file must be under 10 MB."

Most drug-like ligands are well under 10 KB — if your file is over 10 MB, you probably uploaded a multi-molecule SDF library by mistake. Split it and submit one ligand at a time.

## Pipeline errors

### "P2Rank found no pockets in the protein structure."

P2Rank ran but identified zero druggable pockets. Possible causes:

- The protein has no obvious cavity — try a different structure (a bound state from PDB rather than an `apo` form often helps).
- The structure has the wrong chain selection — single-chain inputs sometimes work where the full assembly didn't.
- The structure is too small (e.g., a peptide < 20 residues).

If you *know* the binding site exists, try a different PDB entry of the same protein, ideally one already crystallized with a bound ligand.

### "P2Rank failed (exit code N): &lt;stderr&gt;"

P2Rank crashed. The stderr in the message usually pinpoints the cause — most often an unparseable PDB entry (non-standard residues, broken HETATM records, malformed CRYST1). Re-save the file from PyMOL/ChimeraX with default options to normalize it.

### "Failed to prepare receptor PDBQT file."

Meeko couldn't convert the receptor to PDBQT. Usually caused by:

- Modified or non-standard amino acids that Meeko's force field doesn't recognize.
- Missing heavy atoms in the structure (e.g., a residue truncated at C-α).

Fix by removing the offending residues or replacing them with their standard counterparts.

### "Failed to prepare ligand PDBQT file." { #ligand-preparation-failures }

Meeko couldn't process the ligand. Common causes and fixes:

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `RDKit failed to read ligand file` | Malformed SDF/MOL2/MOL — wrong atom block, missing END line | Re-export from your source tool with default settings |
| Crashes on a metal-containing ligand | Meeko doesn't handle exotic metals | Remove the metal and dock the organic fragment alone |
| Crashes on a charged ligand | Protonation state ambiguity | Pre-protonate at pH 7.4 with `obabel -p 7.4` |
| `Unsupported ligand format` | Extension matched but content wasn't recognized | Convert with Open Babel: `obabel ligand.mol2 -O ligand.sdf` |

### "Vina failed on a pocket"

This is logged as a warning, not a fatal error — the pipeline continues with the remaining pockets. The job will still complete; the affected pocket simply won't appear in the results table.

If *every* pocket fails this way, suspect a problem with the prepared receptor or ligand PDBQT files (download them from `/api/jobs/<id>/files/receptor.pdbqt` and inspect manually). A common cause is a ligand with too many rotatable bonds for Vina's default settings — try lowering `VINA_NUM_MODES` or simplifying the ligand.

## Performance issues

### Job runs much longer than expected

- **Lower exhaustiveness** to `4` to roughly halve the docking time. Useful for screening passes.
- **Reduce the number of pockets** — docking against 1 pocket is 3× faster than against 3.
- **Profile the protein size** — large structures (> 1000 residues) increase P2Rank time noticeably.

### Hits the Celery task time limit (3600s)

The `CELERY_TASK_TIME_LIMIT` in [settings.py](https://github.com/gozsari/PocketDock/blob/main/pocketdock/settings.py) kills tasks running over an hour. Either raise the limit (see [Configuration](configuration.md)) or reduce the workload (lower exhaustiveness / fewer pockets).

## UI issues

### 3D viewer shows a blank canvas

Open the browser console — most "blank viewer" issues are 404s for the pose file. Check the pose URL `/api/jobs/<id>/files/results/pocket_<R>_pose_<P>.pdb` returns a real PDB and not an HTML 404 page.

If WebGL isn't available (older browsers, hardened sandboxes), 3Dmol.js can't render. Try a recent Firefox or Chromium build.

### Interaction lines don't appear

The interaction detector runs separately from docking and is wrapped in a `try/except` — if it crashes for a particular pose, the pose still appears in the results but with no interactions. Check the Celery worker logs for `interaction detection failed` warnings.

You can also try **toggling Near-miss on** — the interaction may be just outside the default cutoff.

## Container / deployment issues

### `docker compose up` fails downloading P2Rank or Vina

The Dockerfile fetches both binaries from GitHub Releases at build time. If you're behind a corporate proxy or your network blocks GitHub Releases, the build fails on the `wget` step. Set `HTTP_PROXY` / `HTTPS_PROXY` build args, or pre-download the binaries and `COPY` them into the image.

### "Permission denied" writing to `media/`

The container runs as a non-root user by default (depending on your image base). On Linux hosts, ensure the bind-mounted `./media` directory is writable by UID 1000 (or whatever the container user maps to).

### Celery worker doesn't pick up jobs

Three things to check:

1. Redis is reachable from the worker container — `redis-cli -h redis ping` from inside the worker.
2. `CELERY_BROKER_URL` in the web container matches the worker's broker URL.
3. The worker actually started — `docker compose logs celery` should show `celery@... ready`.

## Where to get more detail

- **Celery worker logs**: `docker compose logs celery` — most pipeline failures dump tracebacks here.
- **Web logs**: `docker compose logs web` — for upload validation, request errors.
- **Job artifacts**: every job's working directory is at `media/jobs/<job_dir>/`. Inspect P2Rank output (`p2rank_output/`), prepared structures (`receptor.pdbqt`, `ligand.pdbqt`), and per-pose PDBs (`results/`) directly.
- **Open an issue**: <https://github.com/gozsari/PocketDock/issues> — include the error message, the input files (or a redacted version), and the Celery log excerpt.
