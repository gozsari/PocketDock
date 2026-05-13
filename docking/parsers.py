"""Parsers for P2Rank and AutoDock Vina output files."""

import csv
import re
from pathlib import Path
from typing import Optional


def parse_p2rank_predictions(csv_path: str | Path) -> list[dict]:
    """
    Parse P2Rank *_predictions.csv output.

    Expected columns (with possible leading spaces):
        name, rank, score, probability, sas_points, surf_atoms,
        center_x, center_y, center_z, residue_ids, surf_atom_ids

    Returns list of dicts with pocket data.
    """
    pockets = []
    path = Path(csv_path)
    if not path.exists():
        return pockets

    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned = {k.strip(): v.strip() for k, v in row.items()}
            try:
                pocket = {
                    "rank": int(cleaned["rank"]),
                    "score": float(cleaned["score"]),
                    "probability": float(cleaned["probability"]),
                    "center_x": float(cleaned["center_x"]),
                    "center_y": float(cleaned["center_y"]),
                    "center_z": float(cleaned["center_z"]),
                    "residue_ids": cleaned.get("residue_ids", ""),
                    "surf_atom_ids": cleaned.get("surf_atom_ids", ""),
                    "sas_points": int(cleaned.get("sas_points", 0)),
                }
                pockets.append(pocket)
            except (KeyError, ValueError):
                continue

    return pockets


def parse_vina_output(pdbqt_path: str | Path) -> list[dict]:
    """
    Parse a Vina output PDBQT file and extract pose data.

    Each MODEL block in the file corresponds to one pose.
    The REMARK VINA RESULT line contains: affinity, rmsd_lb, rmsd_ub
    """
    poses = []
    path = Path(pdbqt_path)
    if not path.exists():
        return poses

    current_pose = None
    pose_rank = 0

    with open(path, "r") as f:
        for line in f:
            if line.startswith("MODEL"):
                pose_rank += 1
                current_pose = {"pose_rank": pose_rank, "lines": []}
            elif line.startswith("REMARK VINA RESULT"):
                parts = line.split()
                if len(parts) >= 6:
                    current_pose = current_pose or {"pose_rank": pose_rank, "lines": []}
                    current_pose["affinity"] = float(parts[3])
                    current_pose["rmsd_lb"] = float(parts[4])
                    current_pose["rmsd_ub"] = float(parts[5])
            elif line.startswith("ENDMDL"):
                if current_pose and "affinity" in current_pose:
                    poses.append(current_pose)
                current_pose = None
            elif current_pose is not None:
                current_pose["lines"].append(line)

    return poses


def extract_residue_coordinates(pdb_path: str | Path, residue_ids_str: str) -> Optional[dict]:
    """
    Extract min/max coordinates from a PDB file for given residue IDs
    to compute an appropriate grid box size.

    Returns dict with center and size, or None if no coordinates found.
    """
    if not residue_ids_str.strip():
        return None

    residue_tokens = [r.strip() for r in residue_ids_str.split(",") if r.strip()]
    res_numbers = set()
    for token in residue_tokens:
        match = re.search(r"(\d+)", token)
        if match:
            res_numbers.add(int(match.group(1)))

    if not res_numbers:
        return None

    coords = []
    path = Path(pdb_path)
    if not path.exists():
        return None

    with open(path, "r") as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                try:
                    res_seq = int(line[22:26].strip())
                    if res_seq in res_numbers:
                        x = float(line[30:38].strip())
                        y = float(line[38:46].strip())
                        z = float(line[46:54].strip())
                        coords.append((x, y, z))
                except (ValueError, IndexError):
                    continue

    if not coords:
        return None

    xs, ys, zs = zip(*coords)
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
        "min_z": min(zs), "max_z": max(zs),
        "size_x": max(xs) - min(xs),
        "size_y": max(ys) - min(ys),
        "size_z": max(zs) - min(zs),
    }
