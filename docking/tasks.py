"""Celery tasks for the docking pipeline: P2Rank, Meeko, and AutoDock Vina."""

import logging
import subprocess
from pathlib import Path

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def run_docking_pipeline(self, job_id: int):
    """
    Main pipeline task that orchestrates the full docking workflow:
    1. P2Rank pocket detection
    2. Structure preparation (Meeko)
    3. AutoDock Vina docking for each pocket
    """
    from .models import DockingJob

    job = DockingJob.objects.get(id=job_id)

    try:
        _run_p2rank(job)
        _run_structure_prep(job)
        _compute_admet_properties(job)
        _run_vina_docking(job)
        _run_interaction_analysis(job)

        if job.refine_poses:
            _run_energy_minimization(job)
            _run_interaction_analysis(job)

        job.status = DockingJob.Status.COMPLETED
        job.save(update_fields=["status", "updated_at"])
        logger.info("Job %s completed successfully", job_id)

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        job.status = DockingJob.Status.FAILED
        job.error_message = str(exc)[:2000]
        job.save(update_fields=["status", "error_message", "updated_at"])
        raise


def _run_p2rank(job):
    """Step 1: Run P2Rank pocket prediction."""
    from .models import DockingJob, Pocket
    from .parsers import parse_p2rank_predictions

    job.status = DockingJob.Status.RUNNING_P2RANK
    job.save(update_fields=["status", "updated_at"])

    job_path = job.job_path
    protein_path = Path(job.protein_file.path)
    p2rank_output = job_path / "p2rank_output"
    p2rank_output.mkdir(parents=True, exist_ok=True)

    p2rank_bin = settings.P2RANK_BIN
    cmd = [
        p2rank_bin, "predict",
        "-f", str(protein_path),
        "-o", str(p2rank_output),
    ]
    logger.info("Running P2Rank: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )

    if result.returncode != 0:
        raise RuntimeError(f"P2Rank failed (exit {result.returncode}): {result.stderr[:500]}")

    predictions_files = list(p2rank_output.rglob("*_predictions.csv"))
    if not predictions_files:
        raise RuntimeError(
            f"P2Rank did not produce predictions CSV. "
            f"stdout: {result.stdout[:300]} stderr: {result.stderr[:300]}"
        )

    csv_path = predictions_files[0]
    pockets_data = parse_p2rank_predictions(csv_path)

    if not pockets_data:
        raise RuntimeError("P2Rank found no pockets in the protein structure.")

    for pocket_data in pockets_data:
        comp = _classify_pocket_residues(pocket_data["residue_ids"])
        Pocket.objects.create(
            job=job,
            rank=pocket_data["rank"],
            score=pocket_data["score"],
            probability=pocket_data["probability"],
            center_x=pocket_data["center_x"],
            center_y=pocket_data["center_y"],
            center_z=pocket_data["center_z"],
            residue_ids=pocket_data["residue_ids"],
            surf_atom_ids=pocket_data.get("surf_atom_ids", ""),
            sas_points=pocket_data.get("sas_points", 0),
            composition=comp,
        )

    logger.info("P2Rank found %d pockets for job %s", len(pockets_data), job.id)


_RES_CLASSES = {
    'polar': {'SER', 'THR', 'ASN', 'GLN', 'CYS', 'TYR'},
    'hydrophobic': {'ALA', 'VAL', 'LEU', 'ILE', 'MET', 'PHE', 'TRP', 'PRO'},
    'positive': {'ARG', 'LYS', 'HIS'},
    'negative': {'ASP', 'GLU'},
    'special': {'GLY'},
}
_RES_TO_CLASS = {}
for cls, names in _RES_CLASSES.items():
    for n in names:
        _RES_TO_CLASS[n] = cls


def _classify_pocket_residues(residue_ids_str: str) -> dict:
    """Classify pocket residues into polar/hydrophobic/positive/negative/special."""
    import re
    counts = {k: 0 for k in _RES_CLASSES}
    total = 0
    for token in residue_ids_str.split(","):
        token = token.strip()
        match = re.match(r"[A-Za-z]_\d+_([A-Z]{3})", token)
        if not match:
            match = re.match(r"([A-Z]{3})\d+", token)
        if match:
            resn = match.group(1)
            cls = _RES_TO_CLASS.get(resn, 'special')
            counts[cls] += 1
            total += 1
    pcts = {}
    for k, v in counts.items():
        pcts[k] = round(v / total * 100, 1) if total > 0 else 0
    pcts['total'] = total
    return pcts


def _run_structure_prep(job):
    """Step 2: Prepare receptor and ligand PDBQT files."""
    from .models import DockingJob

    job.status = DockingJob.Status.RUNNING_PREP
    job.save(update_fields=["status", "updated_at"])

    job_path = job.job_path
    protein_path = Path(job.protein_file.path)
    ligand_path = Path(job.ligand_file.path)
    receptor_pdbqt = job_path / "receptor.pdbqt"
    ligand_pdbqt = job_path / "ligand.pdbqt"

    # Prepare receptor using built-in converter
    logger.info("Preparing receptor PDBQT from %s", protein_path.name)
    _pdb_to_pdbqt_simple(protein_path, receptor_pdbqt)

    if not receptor_pdbqt.exists():
        raise RuntimeError("Failed to prepare receptor PDBQT file.")

    # Prepare ligand using RDKit + Meeko Python API
    logger.info("Preparing ligand PDBQT from %s", ligand_path.name)
    _prepare_ligand_pdbqt(ligand_path, ligand_pdbqt)

    if not ligand_pdbqt.exists():
        raise RuntimeError("Failed to prepare ligand PDBQT file.")

    logger.info("Structure preparation complete for job %s", job.id)


def _prepare_ligand_pdbqt(ligand_path: Path, pdbqt_path: Path):
    """Convert SDF/MOL2 ligand to PDBQT using RDKit + Meeko Python API."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from meeko import MoleculePreparation, PDBQTWriterLegacy

    suffix = ligand_path.suffix.lower()

    if suffix == ".sdf":
        supplier = Chem.SDMolSupplier(str(ligand_path), removeHs=False)
        mol = next(iter(supplier), None)
    elif suffix in (".mol2",):
        mol = Chem.MolFromMol2File(str(ligand_path), removeHs=False)
    elif suffix == ".mol":
        mol = Chem.MolFromMolFile(str(ligand_path), removeHs=False)
    else:
        raise RuntimeError(f"Unsupported ligand format: {suffix}")

    if mol is None:
        raise RuntimeError(f"RDKit failed to read ligand file: {ligand_path.name}")

    # Add hydrogens if missing
    if mol.GetNumAtoms() > 0:
        mol = Chem.AddHs(mol)
        if mol.GetNumConformers() == 0:
            AllChem.EmbedMolecule(mol, randomSeed=42)
            AllChem.MMFFOptimizeMolecule(mol)

    preparator = MoleculePreparation()
    mol_setups = preparator.prepare(mol)

    if not mol_setups:
        raise RuntimeError("Meeko failed to prepare the ligand molecule.")

    pdbqt_string = PDBQTWriterLegacy.write_string(mol_setups[0])

    with open(pdbqt_path, "w") as f:
        f.write(pdbqt_string[0] if isinstance(pdbqt_string, tuple) else pdbqt_string)


def _pdb_to_pdbqt_simple(pdb_path: Path, pdbqt_path: Path):
    """Minimal PDB->PDBQT conversion for receptors when other tools aren't available."""
    with open(pdb_path, "r") as fin, open(pdbqt_path, "w") as fout:
        for line in fin:
            if line.startswith(("ATOM", "HETATM")):
                atom_name = line[12:16].strip()
                element = line[76:78].strip() if len(line) >= 78 else atom_name[0]
                # Assign Autodock atom type based on element
                ad_type = element.upper()
                if ad_type == "":
                    ad_type = "C"
                padded = f"{ad_type:<2s}"
                pdbqt_line = line[:70].ljust(70) + f"  0.000 {padded}\n"
                fout.write(pdbqt_line)
            elif line.startswith(("TER", "END", "REMARK", "MODEL", "ENDMDL")):
                fout.write(line)


def _compute_admet_properties(job):
    """Compute ADMET / drug-likeness descriptors from the ligand using RDKit."""
    from rdkit import Chem
    from rdkit.Chem import Descriptors, QED, rdMolDescriptors

    ligand_path = Path(job.ligand_file.path)
    suffix = ligand_path.suffix.lower()

    try:
        if suffix == ".sdf":
            supplier = Chem.SDMolSupplier(str(ligand_path), removeHs=False)
            mol = next(iter(supplier), None)
        elif suffix == ".mol2":
            mol = Chem.MolFromMol2File(str(ligand_path), removeHs=False)
        elif suffix == ".mol":
            mol = Chem.MolFromMolFile(str(ligand_path), removeHs=False)
        else:
            logger.warning("ADMET: unsupported ligand format %s", suffix)
            return
    except Exception as exc:
        logger.warning("ADMET: could not read ligand for job %s: %s", job.id, exc)
        return

    if mol is None:
        logger.warning("ADMET: RDKit returned None for ligand in job %s", job.id)
        return

    mol_no_h = Chem.RemoveHs(mol)

    mw = Descriptors.MolWt(mol_no_h)
    logp = Descriptors.MolLogP(mol_no_h)
    hba = Descriptors.NumHAcceptors(mol_no_h)
    hbd = Descriptors.NumHDonors(mol_no_h)
    tpsa = Descriptors.TPSA(mol_no_h)
    rot_bonds = Descriptors.NumRotatableBonds(mol_no_h)
    aromatic_rings = Descriptors.NumAromaticRings(mol_no_h)
    heavy_atoms = mol_no_h.GetNumHeavyAtoms()
    fsp3 = rdMolDescriptors.CalcFractionCSP3(mol_no_h)
    rings = Descriptors.RingCount(mol_no_h)

    try:
        qed_score = QED.qed(mol_no_h)
    except Exception:
        qed_score = None

    lipinski_violations = sum([
        mw > 500,
        logp > 5,
        hba > 10,
        hbd > 5,
    ])

    veber_pass = tpsa <= 140 and rot_bonds <= 10

    props = {
        "molecular_weight": round(mw, 2),
        "logp": round(logp, 2),
        "hba": hba,
        "hbd": hbd,
        "tpsa": round(tpsa, 2),
        "rotatable_bonds": rot_bonds,
        "aromatic_rings": aromatic_rings,
        "heavy_atoms": heavy_atoms,
        "rings": rings,
        "fsp3": round(fsp3, 3),
        "qed": round(qed_score, 3) if qed_score is not None else None,
        "lipinski_violations": lipinski_violations,
        "lipinski_pass": lipinski_violations == 0,
        "veber_pass": veber_pass,
    }

    job.admet_properties = props
    job.save(update_fields=["admet_properties"])
    logger.info("ADMET properties computed for job %s: MW=%.1f, QED=%s", job.id, mw, qed_score)


def _run_vina_docking(job):
    """Step 3: Dock ligand into each selected pocket using AutoDock Vina."""
    from .models import DockingJob, DockingResult
    from .parsers import extract_residue_coordinates, parse_vina_output

    job.status = DockingJob.Status.RUNNING_VINA
    job.save(update_fields=["status", "updated_at"])

    job_path = job.job_path
    receptor_pdbqt = job_path / "receptor.pdbqt"
    ligand_pdbqt = job_path / "ligand.pdbqt"
    results_dir = job_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    pockets = list(job.pockets.order_by("rank")[: job.num_pockets])
    if not pockets:
        raise RuntimeError("No pockets available for docking.")

    protein_path = Path(job.protein_file.path)
    default_box = settings.VINA_DEFAULT_BOX_SIZE
    padding = settings.VINA_BOX_PADDING

    # Count ligand heavy atoms for ligand efficiency
    ligand_heavy_atoms = 0
    ligand_path = Path(job.ligand_file.path)
    try:
        with open(ligand_path, "r") as f:
            for line in f:
                if line.startswith(("ATOM", "HETATM")):
                    elem = line[76:78].strip() if len(line) > 76 else ""
                    if elem != "H":
                        ligand_heavy_atoms += 1
        if ligand_heavy_atoms == 0 and ligand_path.suffix.lower() == ".sdf":
            with open(ligand_path, "r") as f:
                lines = f.readlines()
                if len(lines) >= 4:
                    counts_line = lines[3].strip().split()
                    if len(counts_line) >= 1:
                        ligand_heavy_atoms = int(counts_line[0])
    except (ValueError, IndexError, IOError) as exc:
        logger.warning("Could not count ligand heavy atoms for job %s: %s", job.id, exc)

    for pocket in pockets:
        logger.info("Docking pocket %d (p=%.2f) for job %s", pocket.rank, pocket.probability, job.id)

        # Compute grid box size from residue spread
        box_size_x = box_size_y = box_size_z = default_box
        coords = extract_residue_coordinates(protein_path, pocket.residue_ids)
        if coords:
            box_size_x = coords["size_x"] + padding
            box_size_y = coords["size_y"] + padding
            box_size_z = coords["size_z"] + padding

        output_pdbqt = results_dir / f"pocket_{pocket.rank}_out.pdbqt"

        vina_cmd = [
            "vina",
            "--receptor", str(receptor_pdbqt),
            "--ligand", str(ligand_pdbqt),
            "--center_x", str(pocket.center_x),
            "--center_y", str(pocket.center_y),
            "--center_z", str(pocket.center_z),
            "--size_x", str(round(box_size_x, 1)),
            "--size_y", str(round(box_size_y, 1)),
            "--size_z", str(round(box_size_z, 1)),
            "--exhaustiveness", str(job.exhaustiveness),
            "--scoring", job.scoring_function,
            "--num_modes", str(settings.VINA_NUM_MODES),
            "--out", str(output_pdbqt),
        ]
        logger.info("Running Vina: %s", " ".join(vina_cmd))

        result = subprocess.run(vina_cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            logger.error(
                "Vina failed for pocket %d: %s", pocket.rank, result.stderr[:500]
            )
            continue

        # Parse results and convert each pose to its own PDB file
        poses = parse_vina_output(output_pdbqt)

        for pose in poses:
            pose_pdb = results_dir / f"pocket_{pocket.rank}_pose_{pose['pose_rank']}.pdb"
            _pdbqt_to_pdb(output_pdbqt, pose_pdb, model_num=pose["pose_rank"])
            pose_pdb_path = f"results/pocket_{pocket.rank}_pose_{pose['pose_rank']}.pdb"

            le = (-pose["affinity"] / ligand_heavy_atoms) if ligand_heavy_atoms > 0 else 0.0
            dr = DockingResult.objects.create(
                pocket=pocket,
                pose_rank=pose["pose_rank"],
                affinity=pose["affinity"],
                rmsd_lb=pose.get("rmsd_lb", 0.0),
                rmsd_ub=pose.get("rmsd_ub", 0.0),
                pose_file=pose_pdb_path,
                ligand_efficiency=round(le, 3),
            )
            dr.compute_combined_score()
            dr.save(update_fields=["combined_score"])

        logger.info(
            "Docked pocket %d: %d poses, best affinity = %.1f",
            pocket.rank,
            len(poses),
            min((p["affinity"] for p in poses), default=0),
        )

    total_results = DockingResult.objects.filter(pocket__job=job).count()
    if total_results == 0:
        raise RuntimeError(
            "Vina produced zero docking results across all pockets. "
            "Check that the ligand and receptor files are valid."
        )


def _run_energy_minimization(job):
    """Step 5 (optional): Refine docked poses via OpenMM energy minimization."""
    from .models import DockingJob, DockingResult

    job.status = DockingJob.Status.RUNNING_REFINEMENT
    job.save(update_fields=["status", "updated_at"])

    job_path = job.job_path
    protein_path = Path(job.protein_file.path)
    results_dir = job_path / "results"

    try:
        from pdbfixer import PDBFixer
        from openmm import LangevinMiddleIntegrator, Platform
        from openmm.app import ForceField, Modeller, PDBFile, Simulation
        import openmm.unit as unit
    except ImportError as exc:
        logger.warning("OpenMM not available, skipping refinement: %s", exc)
        return

    all_results = DockingResult.objects.filter(
        pocket__job=job
    ).select_related("pocket")

    refined_count = 0
    for dr in all_results:
        pose_pdb = results_dir / f"pocket_{dr.pocket.rank}_pose_{dr.pose_rank}.pdb"
        if not pose_pdb.exists():
            continue

        try:
            _minimize_single_pose(
                protein_path, pose_pdb, dr,
                PDBFixer=PDBFixer,
                ForceField=ForceField,
                Modeller=Modeller,
                PDBFile=PDBFile,
                Simulation=Simulation,
                LangevinMiddleIntegrator=LangevinMiddleIntegrator,
                Platform=Platform,
                unit=unit,
            )
            refined_count += 1
        except Exception as exc:
            logger.warning(
                "Refinement failed for pocket %d pose %d: %s",
                dr.pocket.rank, dr.pose_rank, exc,
            )

    logger.info("Energy minimization: refined %d/%d poses for job %s",
                refined_count, all_results.count(), job.id)


def _minimize_single_pose(
    protein_path, pose_pdb_path, docking_result,
    *, PDBFixer, ForceField, Modeller, PDBFile, Simulation,
    LangevinMiddleIntegrator, Platform, unit,
):
    """Minimize a single protein-ligand complex in implicit solvent."""
    import io
    import tempfile

    # Read and combine protein + ligand into a single PDB
    protein_lines = []
    with open(protein_path) as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM", "TER")):
                protein_lines.append(line)

    ligand_lines = []
    with open(pose_pdb_path) as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                # Ensure ligand is marked as HETATM for force field assignment
                ligand_lines.append("HETATM" + line[6:] if line.startswith("ATOM") else line)

    combined_pdb = "".join(protein_lines) + "TER\n" + "".join(ligand_lines) + "END\n"

    # Use PDBFixer to add missing heavy atoms and hydrogens to the protein
    fixer = PDBFixer(pdbfile=io.StringIO(combined_pdb))
    fixer.findMissingResidues()
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(7.0)

    # Build the system with implicit solvent (OBC2)
    forcefield = ForceField("amber14-all.xml", "implicit/obc2.xml")

    try:
        system = forcefield.createSystem(
            fixer.topology,
            nonbondedCutoff=1.0 * unit.nanometers,
            constraints=None,
        )
    except Exception as exc:
        raise RuntimeError(f"Force field parameterization failed: {exc}") from exc

    integrator = LangevinMiddleIntegrator(
        300 * unit.kelvin,
        1.0 / unit.picosecond,
        0.002 * unit.picoseconds,
    )

    try:
        platform = Platform.getPlatformByName("CPU")
    except Exception:
        platform = None

    if platform:
        simulation = Simulation(fixer.topology, system, integrator, platform)
    else:
        simulation = Simulation(fixer.topology, system, integrator)

    simulation.context.setPositions(fixer.positions)

    # Get initial energy
    state_before = simulation.context.getState(getEnergy=True)
    energy_before = state_before.getPotentialEnergy().value_in_unit(unit.kilojoules_per_mole)

    # Minimize
    simulation.minimizeEnergy(maxIterations=500)

    # Get final energy
    state_after = simulation.context.getState(getEnergy=True, getPositions=True)
    energy_after = state_after.getPotentialEnergy().value_in_unit(unit.kilojoules_per_mole)

    logger.info(
        "Pose pocket %d pose %d: energy %.1f -> %.1f kJ/mol (delta %.1f)",
        docking_result.pocket.rank, docking_result.pose_rank,
        energy_before, energy_after, energy_after - energy_before,
    )

    # Extract refined ligand coordinates and overwrite the pose PDB
    positions = state_after.getPositions(asNumpy=True).value_in_unit(unit.angstroms)

    # Count protein atoms to find where ligand starts
    n_protein_atoms = len(protein_lines) - protein_lines.count("TER\n") if "TER\n" in protein_lines else 0
    # More reliable: count ATOM/HETATM lines in protein
    n_prot = sum(1 for l in protein_lines if l.startswith(("ATOM", "HETATM")))

    # We need to figure out how many atoms PDBFixer added (hydrogens etc.)
    # Instead, write the full minimized ligand portion back
    # Re-read original ligand to get the atom count
    orig_lig_atoms = sum(1 for l in ligand_lines if l.startswith(("ATOM", "HETATM")))

    # Write refined ligand PDB from the minimized positions
    # The topology has all atoms; we extract only the last orig_lig_atoms worth
    all_atoms = list(fixer.topology.atoms())
    total_atoms = len(all_atoms)

    # Find ligand atoms by looking for HETATM residues at the end
    lig_atom_indices = []
    for i, atom in enumerate(all_atoms):
        if atom.residue.name not in (
            "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
            "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER",
            "THR", "TRP", "TYR", "VAL", "HOH", "WAT",
        ):
            lig_atom_indices.append(i)

    if not lig_atom_indices:
        return

    # Write only the non-hydrogen ligand atoms with updated coordinates
    out_lines = []
    serial = 1
    for idx in lig_atom_indices:
        atom = all_atoms[idx]
        if atom.element.symbol == "H":
            continue
        x, y, z = positions[idx]
        name = atom.name
        resname = atom.residue.name[:3]
        chain = atom.residue.chain.id or "A"
        resseq = atom.residue.index + 1
        out_lines.append(
            f"HETATM{serial:5d} {name:<4s} {resname:>3s} {chain}{resseq:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00\n"
        )
        serial += 1

    out_lines.append("END\n")
    with open(pose_pdb_path, "w") as f:
        f.writelines(out_lines)


def _run_interaction_analysis(job):
    """Step 4: Analyze protein-ligand interactions using coordinate geometry."""
    import json

    logger.info("Running interaction analysis for job %s", job.id)

    job_path = job.job_path
    protein_path = Path(job.protein_file.path)
    results_dir = job_path / "results"

    results = list(
        job.pockets.values_list("rank", flat=True)
        .order_by("rank")[: job.num_pockets]
    )

    for pocket_rank in results:
        from .models import DockingResult, Pocket

        pocket = Pocket.objects.get(job=job, rank=pocket_rank)
        pose_results = DockingResult.objects.filter(pocket=pocket)

        for dr in pose_results:
            pose_pdb = results_dir / f"pocket_{pocket_rank}_pose_{dr.pose_rank}.pdb"
            if not pose_pdb.exists():
                continue

            # Detect interactions using coordinate geometry
            interactions = _detect_interactions_geometry(protein_path, pose_pdb)

            interaction_json = results_dir / f"pocket_{pocket_rank}_pose_{dr.pose_rank}_interactions.json"
            with open(interaction_json, "w") as f:
                json.dump(interactions, f, indent=2)

            logger.info(
                "Interaction analysis done: pocket %d pose %d - %d H-bonds, %d hydrophobic, %d salt bridges",
                pocket_rank, dr.pose_rank,
                len(interactions.get("hydrogen_bonds", [])),
                len(interactions.get("hydrophobic", [])),
                len(interactions.get("salt_bridges", [])),
            )


def _detect_interactions_geometry(protein_path: Path, ligand_pdb_path: Path) -> dict:
    """Detect protein-ligand interactions using coordinate geometry analysis."""
    import math

    HBOND_DIST = 6.0
    HYDROPHOBIC_DIST = 7.2
    SALT_BRIDGE_DIST = 7.2
    PI_STACK_DIST = 9.0

    HBOND_ELEMENTS = {"N", "O", "S"}
    HYDROPHOBIC_ELEMENTS = {"C"}
    HYDROPHOBIC_RES = {"ALA", "VAL", "LEU", "ILE", "PHE", "TRP", "PRO", "MET"}
    BACKBONE_ATOMS = {"N", "CA", "C", "O"}
    POSITIVE_RES = {"ARG", "LYS", "HIS"}
    NEGATIVE_RES = {"ASP", "GLU"}
    SALT_BRIDGE_ATOMS = {
        "LYS": {"NZ"}, "ARG": {"NH1", "NH2", "NE"}, "HIS": {"ND1", "NE2"},
        "ASP": {"OD1", "OD2"}, "GLU": {"OE1", "OE2"},
    }
    AROMATIC_RES = {"PHE", "TYR", "TRP", "HIS"}

    HBOND_DONORS = {
        "ARG": {"NE", "NH1", "NH2"}, "LYS": {"NZ"},
        "HIS": {"ND1", "NE2"}, "ASN": {"ND2"}, "GLN": {"NE2"},
        "TRP": {"NE1"}, "SER": {"OG"}, "THR": {"OG1"},
        "TYR": {"OH"}, "CYS": {"SG"},
    }
    HBOND_ACCEPTORS = {
        "ASP": {"OD1", "OD2"}, "GLU": {"OE1", "OE2"},
        "ASN": {"OD1"}, "GLN": {"OE1"},
        "SER": {"OG"}, "THR": {"OG1"}, "TYR": {"OH"},
        "HIS": {"ND1", "NE2"}, "CYS": {"SG"}, "MET": {"SD"},
    }
    AROMATIC_RING_ATOMS = {
        "PHE": [["CG", "CD1", "CD2", "CE1", "CE2", "CZ"]],
        "TYR": [["CG", "CD1", "CD2", "CE1", "CE2", "CZ"]],
        "TRP": [["CG", "CD1", "CD2", "NE1", "CE2"],
                ["CD2", "CE2", "CE3", "CZ2", "CZ3", "CH2"]],
        "HIS": [["CG", "ND1", "CD2", "CE1", "NE2"]],
    }
    PI_CATION_DIST = 9.0
    HALOGEN_ELEMENTS = {"CL", "BR", "I"}
    HALOGEN_DIST = 6.0
    HALOGEN_ANGLE_MIN = 140

    interactions = {
        "hydrogen_bonds": [],
        "hydrophobic": [],
        "salt_bridges": [],
        "pi_stacking": [],
        "pi_cation": [],
        "halogen_bonds": [],
        "water_bridges": [],
    }

    def parse_pdb_atoms(path):
        atoms = []
        with open(path, "r") as f:
            for line in f:
                if line.startswith(("ATOM", "HETATM")):
                    try:
                        atoms.append({
                            "serial": int(line[6:11]),
                            "name": line[12:16].strip(),
                            "resn": line[17:20].strip(),
                            "resi": line[22:26].strip(),
                            "chain": line[21:22].strip(),
                            "x": float(line[30:38]),
                            "y": float(line[38:46]),
                            "z": float(line[46:54]),
                            "element": line[76:78].strip() if len(line) >= 78 else line[12:16].strip()[0],
                        })
                    except (ValueError, IndexError):
                        continue
        return atoms

    def dist(a, b):
        return math.sqrt((a["x"]-b["x"])**2 + (a["y"]-b["y"])**2 + (a["z"]-b["z"])**2)

    def centroid(atoms_list):
        n = len(atoms_list)
        cx = sum(a["x"] for a in atoms_list) / n
        cy = sum(a["y"] for a in atoms_list) / n
        cz = sum(a["z"] for a in atoms_list) / n
        return {"x": cx, "y": cy, "z": cz}

    def normal(atoms_list):
        if len(atoms_list) < 3:
            return (0, 0, 1)
        a, b, c = atoms_list[0], atoms_list[1], atoms_list[2]
        v1 = (b["x"]-a["x"], b["y"]-a["y"], b["z"]-a["z"])
        v2 = (c["x"]-a["x"], c["y"]-a["y"], c["z"]-a["z"])
        nx = v1[1]*v2[2] - v1[2]*v2[1]
        ny = v1[2]*v2[0] - v1[0]*v2[2]
        nz = v1[0]*v2[1] - v1[1]*v2[0]
        mag = math.sqrt(nx*nx + ny*ny + nz*nz)
        if mag < 1e-9:
            return (0, 0, 1)
        return (nx/mag, ny/mag, nz/mag)

    def angle_between_normals(n1, n2):
        dot = abs(n1[0]*n2[0] + n1[1]*n2[1] + n1[2]*n2[2])
        dot = min(1.0, dot)
        return math.degrees(math.acos(dot))

    def angle_normal_to_vector(ring_normal, ring_centroid, point):
        """Angle between ring normal and vector from centroid to point (degrees)."""
        v = (point["x"] - ring_centroid["x"],
             point["y"] - ring_centroid["y"],
             point["z"] - ring_centroid["z"])
        mag_v = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
        if mag_v < 1e-9:
            return 0.0
        dot = abs(ring_normal[0]*v[0] + ring_normal[1]*v[1] + ring_normal[2]*v[2])
        cos_a = min(1.0, dot / mag_v)
        return math.degrees(math.acos(cos_a))

    def classify_pi_cation_geometry(angle_deg):
        if angle_deg <= 30:
            return "face_on"
        elif angle_deg >= 60:
            return "edge_on"
        else:
            return "tilted"

    def angle_three_points(a, b, c):
        """Angle at point b formed by a-b-c, in degrees."""
        v1 = (a["x"]-b["x"], a["y"]-b["y"], a["z"]-b["z"])
        v2 = (c["x"]-b["x"], c["y"]-b["y"], c["z"]-b["z"])
        dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
        m1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
        m2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
        if m1 < 1e-9 or m2 < 1e-9:
            return 0
        cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
        return math.degrees(math.acos(cos_a))

    try:
        prot_atoms = parse_pdb_atoms(protein_path)
        lig_atoms = parse_pdb_atoms(ligand_pdb_path)

        if not prot_atoms or not lig_atoms:
            return interactions

        elem_counter = {}
        lig_atom_id_map = {}
        for la in lig_atoms:
            el = la["element"]
            elem_counter[el] = elem_counter.get(el, 0) + 1
            la["atom_id"] = f"{el}{elem_counter[el]}"
            lig_atom_id_map[(la["x"], la["y"], la["z"])] = la["atom_id"]

        best_hbonds = {}
        best_hydro = {}

        for la in lig_atoms:
            for pa in prot_atoms:
                d = dist(la, pa)
                res_label = f"{pa['resn']}{pa['resi']}:{pa['chain']}"

                # H-bonds: N/O/S donor-acceptor pairs with complementarity check,
                # deduplicated to closest contact per (residue, ligand_atom)
                if d <= HBOND_DIST and pa["element"] in HBOND_ELEMENTS and la["element"] in HBOND_ELEMENTS:
                    prot_is_donor = (pa["name"] in HBOND_DONORS.get(pa["resn"], set())
                                     or (pa["name"] == "N" and pa["name"] in BACKBONE_ATOMS))
                    prot_is_acceptor = (pa["name"] in HBOND_ACCEPTORS.get(pa["resn"], set())
                                        or (pa["name"] == "O" and pa["name"] in BACKBONE_ATOMS))
                    if not prot_is_donor and not prot_is_acceptor:
                        prot_is_donor = pa["element"] == "N"
                        prot_is_acceptor = pa["element"] in {"O", "S"}
                    lig_is_donor = la["element"] in {"N", "O"}
                    lig_is_acceptor = la["element"] in {"O", "N", "S"}
                    complementary = (prot_is_donor and lig_is_acceptor) or (prot_is_acceptor and lig_is_donor)
                    if complementary:
                        key = (res_label, la["name"])
                        if key not in best_hbonds or d < best_hbonds[key]["distance"]:
                            if prot_is_donor and prot_is_acceptor:
                                hb_type = "both"
                            elif prot_is_donor:
                                hb_type = "donor"
                            else:
                                hb_type = "acceptor"
                            best_hbonds[key] = {
                                "protein_res": res_label,
                                "protein_atom": pa["name"],
                                "ligand_atom": la["name"],
                                "ligand_atom_id": la["atom_id"],
                                "distance": round(d, 2),
                                "angle": None,
                                "type": hb_type,
                                "protein_coords": [pa["x"], pa["y"], pa["z"]],
                                "ligand_coords": [la["x"], la["y"], la["z"]],
                            }

                # Hydrophobic: sidechain C of hydrophobic residues only,
                # deduplicated to closest contact per (residue, ligand_atom)
                if (d <= HYDROPHOBIC_DIST
                        and pa["element"] in HYDROPHOBIC_ELEMENTS
                        and la["element"] in HYDROPHOBIC_ELEMENTS
                        and pa["resn"] in HYDROPHOBIC_RES
                        and pa["name"] not in BACKBONE_ATOMS):
                    key = (res_label, la["name"])
                    if key not in best_hydro or d < best_hydro[key]["distance"]:
                        best_hydro[key] = {
                            "protein_res": res_label,
                            "protein_atom": pa["name"],
                            "ligand_atom": la["name"],
                            "ligand_atom_id": la["atom_id"],
                            "distance": round(d, 2),
                            "protein_coords": [pa["x"], pa["y"], pa["z"]],
                            "ligand_coords": [la["x"], la["y"], la["z"]],
                        }

                # Salt bridges: charged functional-group atoms near ligand N/O,
                # deduplicated per (residue, ligand_atom)
                if d <= SALT_BRIDGE_DIST:
                    allowed = SALT_BRIDGE_ATOMS.get(pa["resn"])
                    if allowed and pa["name"] in allowed and la["element"] in {"N", "O"}:
                        existing = [sb for sb in interactions["salt_bridges"]
                                    if sb["protein_res"] == res_label and sb["ligand_atom_id"] == la["atom_id"]]
                        if not existing:
                            interactions["salt_bridges"].append({
                                "protein_res": res_label,
                                "protein_atom": pa["name"],
                                "ligand_atom_id": la["atom_id"],
                                "distance": round(d, 2),
                                "type": "negative" if pa["resn"] in NEGATIVE_RES else "positive",
                                "protein_coords": [pa["x"], pa["y"], pa["z"]],
                                "ligand_coords": [la["x"], la["y"], la["z"]],
                            })

        interactions["hydrogen_bonds"] = list(best_hbonds.values())
        interactions["hydrophobic"] = list(best_hydro.values())

        # ── Build protein aromatic ring centroids & normals ──
        prot_by_res = {}
        for a in prot_atoms:
            key = (a["resn"], a["resi"], a["chain"])
            prot_by_res.setdefault(key, {})[a["name"]] = a

        prot_rings = []
        for (resn, resi, chain), atom_map in prot_by_res.items():
            ring_defs = AROMATIC_RING_ATOMS.get(resn, [])
            for ring_names in ring_defs:
                ring_atoms = [atom_map[n] for n in ring_names if n in atom_map]
                if len(ring_atoms) >= 3:
                    c = centroid(ring_atoms)
                    n = normal(ring_atoms)
                    prot_rings.append({
                        "resn": resn, "resi": resi, "chain": chain,
                        "centroid": c, "normal": n, "atoms": ring_atoms,
                    })

        # ── Build ligand ring centroids & normals ──
        lig_ring_eligible = [a for a in lig_atoms if a["element"] in {"C", "N", "O", "S"}]
        adj = {i: set() for i in range(len(lig_ring_eligible))}
        for i in range(len(lig_ring_eligible)):
            for j in range(i + 1, len(lig_ring_eligible)):
                if dist(lig_ring_eligible[i], lig_ring_eligible[j]) <= 1.8:
                    adj[i].add(j)
                    adj[j].add(i)

        def _find_small_rings(adj, max_size=6):
            """Find all simple cycles of size 5 or 6 using DFS."""
            found = set()
            rings = []
            nodes = [i for i in adj if len(adj[i]) >= 2]
            for start in nodes:
                _dfs_ring(adj, start, start, [start], {start}, found, rings, max_size)
            return rings

        def _dfs_ring(adj, start, current, path, visited, found, rings, max_size):
            if len(path) > max_size:
                return
            for neighbor in adj[current]:
                if neighbor == start and len(path) >= 5:
                    canon = frozenset(path)
                    if canon not in found:
                        found.add(canon)
                        rings.append(list(path))
                    continue
                if neighbor in visited:
                    continue
                if neighbor < start:
                    continue
                visited.add(neighbor)
                path.append(neighbor)
                _dfs_ring(adj, start, neighbor, path, visited, found, rings, max_size)
                path.pop()
                visited.discard(neighbor)

        lig_rings = []
        for ring_indices in _find_small_rings(adj):
            ring_atoms = [lig_ring_eligible[i] for i in ring_indices]
            c = centroid(ring_atoms)
            n = normal(ring_atoms)
            lig_rings.append({"centroid": c, "normal": n, "atoms": ring_atoms})

        # ── Pi-stacking: ring centroid-centroid distance + plane angle ──
        seen_pi = set()
        for pr in prot_rings:
            res_label = f"{pr['resn']}{pr['resi']}:{pr['chain']}"
            if res_label in seen_pi:
                continue
            for lr in lig_rings:
                d = dist(pr["centroid"], lr["centroid"])
                if d <= PI_STACK_DIST:
                    ang = angle_between_normals(pr["normal"], lr["normal"])
                    if ang <= 30:
                        stack_type = "parallel"
                    elif ang >= 60:
                        stack_type = "t_shaped"
                    else:
                        stack_type = "tilted"
                    seen_pi.add(res_label)
                    interactions["pi_stacking"].append({
                        "protein_res": res_label,
                        "ligand_atom_id": "ring",
                        "distance": round(d, 2),
                        "angle": round(ang, 1),
                        "type": stack_type,
                        "protein_coords": [pr["centroid"]["x"], pr["centroid"]["y"], pr["centroid"]["z"]],
                        "ligand_coords": [lr["centroid"]["x"], lr["centroid"]["y"], lr["centroid"]["z"]],
                    })
                    break

        # ── Pi-cation detection ──
        prot_cations = []
        for (resn, resi, chain), atom_map in prot_by_res.items():
            if resn == "LYS" and "NZ" in atom_map:
                prot_cations.append({"resn": resn, "resi": resi, "chain": chain, "atom": atom_map["NZ"]})
            elif resn == "ARG" and "CZ" in atom_map:
                prot_cations.append({"resn": resn, "resi": resi, "chain": chain, "atom": atom_map["CZ"]})

        seen_pi_cation = set()
        for cat in prot_cations:
            res_label = f"{cat['resn']}{cat['resi']}:{cat['chain']}"
            if res_label in seen_pi_cation:
                continue
            for lr in lig_rings:
                d = dist(cat["atom"], lr["centroid"])
                if d <= PI_CATION_DIST:
                    ang = angle_normal_to_vector(lr["normal"], lr["centroid"], cat["atom"])
                    geometry = classify_pi_cation_geometry(ang)
                    seen_pi_cation.add(res_label)
                    interactions["pi_cation"].append({
                        "protein_res": res_label,
                        "ligand_atom_id": "ring",
                        "distance": round(d, 2),
                        "angle": round(ang, 1),
                        "type": "protein_cation",
                        "geometry": geometry,
                        "protein_coords": [cat["atom"]["x"], cat["atom"]["y"], cat["atom"]["z"]],
                        "ligand_coords": [lr["centroid"]["x"], lr["centroid"]["y"], lr["centroid"]["z"]],
                        "ligand_ring_normal": list(lr["normal"]),
                    })
                    break

        lig_nitrogens = [a for a in lig_atoms if a["element"] == "N"]
        for pr in prot_rings:
            res_label = f"{pr['resn']}{pr['resi']}:{pr['chain']}"
            if res_label in seen_pi_cation:
                continue
            for ln in lig_nitrogens:
                d = dist(pr["centroid"], ln)
                if d <= PI_CATION_DIST:
                    ang = angle_normal_to_vector(pr["normal"], pr["centroid"], ln)
                    geometry = classify_pi_cation_geometry(ang)
                    seen_pi_cation.add(res_label)
                    interactions["pi_cation"].append({
                        "protein_res": res_label,
                        "ligand_atom_id": ln["atom_id"],
                        "distance": round(d, 2),
                        "angle": round(ang, 1),
                        "type": "protein_ring",
                        "geometry": geometry,
                        "protein_coords": [pr["centroid"]["x"], pr["centroid"]["y"], pr["centroid"]["z"]],
                        "ligand_coords": [ln["x"], ln["y"], ln["z"]],
                        "protein_ring_normal": list(pr["normal"]),
                    })
                    break

        # ── Halogen bond detection ──
        lig_halogens = [a for a in lig_atoms if a["element"].upper() in HALOGEN_ELEMENTS]
        for lh in lig_halogens:
            bonded_c = None
            min_cd = 2.0
            for la2 in lig_atoms:
                if la2["element"] == "C":
                    cd = dist(lh, la2)
                    if cd < min_cd:
                        min_cd = cd
                        bonded_c = la2
            if bonded_c is None:
                continue

            best_hal = {}
            for pa in prot_atoms:
                if pa["element"] not in HBOND_ELEMENTS:
                    continue
                d = dist(lh, pa)
                if d > HALOGEN_DIST or d < 2.5:
                    continue
                ang = angle_three_points(bonded_c, lh, pa)
                if ang < HALOGEN_ANGLE_MIN:
                    continue
                res_label = f"{pa['resn']}{pa['resi']}:{pa['chain']}"
                hal_key = (res_label, lh["name"])
                if hal_key not in best_hal or d < best_hal[hal_key]["distance"]:
                    best_hal[hal_key] = {
                        "protein_res": res_label,
                        "protein_atom": pa["name"],
                        "ligand_atom": lh["name"],
                        "ligand_atom_id": lh["atom_id"],
                        "distance": round(d, 2),
                        "angle": round(ang, 1),
                        "type": "halogen",
                        "protein_coords": [pa["x"], pa["y"], pa["z"]],
                        "ligand_coords": [lh["x"], lh["y"], lh["z"]],
                    }
            interactions["halogen_bonds"].extend(best_hal.values())

        NEARBY_DIST = 5.5
        nearby = []
        for la in lig_atoms:
            contacts = []
            for pa in prot_atoms:
                d = dist(la, pa)
                if d <= NEARBY_DIST:
                    contacts.append({
                        "protein_res": f"{pa['resn']}{pa['resi']}:{pa['chain']}",
                        "protein_atom": pa["name"],
                        "distance": round(d, 2),
                        "element": pa["element"],
                    })
            if contacts:
                contacts.sort(key=lambda c: c["distance"])
                seen_res = set()
                deduped = []
                for c in contacts:
                    if c["protein_res"] not in seen_res:
                        seen_res.add(c["protein_res"])
                        deduped.append(c)
                nearby.append({
                    "ligand_atom_id": la["atom_id"],
                    "ligand_element": la["element"],
                    "ligand_coords": [la["x"], la["y"], la["z"]],
                    "contacts": deduped,
                })
        interactions["nearby_residues"] = nearby

    except Exception as exc:
        logger.warning("Interaction detection failed: %s", exc)

    return interactions


def _pdbqt_to_pdb(pdbqt_path: Path, pdb_path: Path, model_num: int = 1):
    """Extract a specific model from PDBQT and convert to minimal PDB."""
    current_model = 0
    lines = []
    in_target = False

    with open(pdbqt_path, "r") as f:
        for line in f:
            if line.startswith("MODEL"):
                current_model += 1
                if current_model == model_num:
                    in_target = True
                continue
            if line.startswith("ENDMDL"):
                if in_target:
                    break
                continue
            if in_target or current_model == 0:
                if line.startswith(("ATOM", "HETATM")):
                    # Convert PDBQT -> PDB: strip last 2 columns (charge + type)
                    pdb_line = line[:66].rstrip() + "\n"
                    lines.append(pdb_line)

    with open(pdb_path, "w") as f:
        f.writelines(lines)
        f.write("END\n")
