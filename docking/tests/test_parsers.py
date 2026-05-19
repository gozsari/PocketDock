from pathlib import Path

import pytest

from docking.parsers import (
    extract_residue_coordinates,
    parse_p2rank_predictions,
    parse_vina_output,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseP2RankPredictions:
    def test_valid_csv(self):
        pockets = parse_p2rank_predictions(FIXTURES / "predictions_valid.csv")
        assert len(pockets) == 2
        assert pockets[0]["rank"] == 1
        assert pockets[0]["probability"] == pytest.approx(0.85)
        assert pockets[0]["center_x"] == pytest.approx(10.0)
        assert pockets[1]["rank"] == 2

    def test_empty_csv(self):
        pockets = parse_p2rank_predictions(FIXTURES / "predictions_empty.csv")
        assert pockets == []

    def test_missing_file(self):
        pockets = parse_p2rank_predictions(FIXTURES / "nonexistent.csv")
        assert pockets == []

    def test_malformed_rows_skipped(self):
        pockets = parse_p2rank_predictions(FIXTURES / "predictions_malformed.csv")
        assert len(pockets) == 1
        assert pockets[0]["rank"] == 1


class TestParseVinaOutput:
    def test_valid_pdbqt(self):
        poses = parse_vina_output(FIXTURES / "vina_output.pdbqt")
        assert len(poses) == 2
        assert poses[0]["affinity"] == pytest.approx(-7.5)
        assert poses[0]["rmsd_lb"] == pytest.approx(0.0)
        assert poses[1]["affinity"] == pytest.approx(-6.2)
        assert poses[1]["rmsd_ub"] == pytest.approx(2.345)

    def test_missing_file(self):
        poses = parse_vina_output(FIXTURES / "nonexistent.pdbqt")
        assert poses == []


class TestExtractResidueCoordinates:
    def test_valid_extraction(self):
        result = extract_residue_coordinates(FIXTURES / "mini_protein.pdb", "A_42_ALA,A_43_VAL")
        assert result is not None
        assert "size_x" in result
        assert result["size_x"] >= 0
        assert result["min_x"] <= result["max_x"]

    def test_empty_residue_string(self):
        assert extract_residue_coordinates(FIXTURES / "mini_protein.pdb", "") is None

    def test_missing_file(self):
        assert extract_residue_coordinates("/tmp/nope.pdb", "A_42_ALA") is None

    def test_no_matching_residues(self):
        result = extract_residue_coordinates(FIXTURES / "mini_protein.pdb", "A_999_ALA")
        assert result is None
