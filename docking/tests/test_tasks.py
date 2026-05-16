from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class TestPdbToPdbqtSimple:
    def test_basic_conversion(self, tmp_path):
        from docking.tasks import _pdb_to_pdbqt_simple

        pdb_path = FIXTURES / "mini_protein.pdb"
        out = tmp_path / "receptor.pdbqt"
        _pdb_to_pdbqt_simple(pdb_path, out)

        assert out.exists()
        content = out.read_text()
        assert "ATOM" in content or "HETATM" in content

    def test_empty_pdb(self, tmp_path):
        from docking.tasks import _pdb_to_pdbqt_simple

        empty_pdb = tmp_path / "empty.pdb"
        empty_pdb.write_text("END\n")
        out = tmp_path / "receptor.pdbqt"
        _pdb_to_pdbqt_simple(empty_pdb, out)

        assert out.exists()
        assert "ATOM" not in out.read_text()


class TestPdbqtToPdb:
    def test_extract_model(self, tmp_path):
        from docking.tasks import _pdbqt_to_pdb

        pdbqt = FIXTURES / "vina_output.pdbqt"
        out = tmp_path / "pose.pdb"
        _pdbqt_to_pdb(pdbqt, out, model_num=1)

        assert out.exists()
        content = out.read_text()
        assert "END" in content

    def test_extract_second_model(self, tmp_path):
        from docking.tasks import _pdbqt_to_pdb

        pdbqt = FIXTURES / "vina_output.pdbqt"
        out = tmp_path / "pose2.pdb"
        _pdbqt_to_pdb(pdbqt, out, model_num=2)

        assert out.exists()


class TestClassifyPocketResidues:
    def test_basic_classification(self):
        from docking.tasks import _classify_pocket_residues

        result = _classify_pocket_residues("A_42_ALA,A_43_VAL,B_10_GLY")
        assert result["total"] == 3
        assert result["hydrophobic"] > 0
        assert result["special"] > 0

    def test_empty_string(self):
        from docking.tasks import _classify_pocket_residues

        result = _classify_pocket_residues("")
        assert result["total"] == 0


class TestDetectInteractionsGeometry:
    def test_basic_detection(self):
        from docking.tasks import _detect_interactions_geometry

        result = _detect_interactions_geometry(
            FIXTURES / "mini_protein.pdb",
            FIXTURES / "mini_ligand.pdb",
        )
        assert isinstance(result, dict)
        assert "hydrogen_bonds" in result
        assert "hydrophobic" in result
        assert "nearby_residues" in result

    def test_missing_ligand(self, tmp_path):
        from docking.tasks import _detect_interactions_geometry

        result = _detect_interactions_geometry(
            FIXTURES / "mini_protein.pdb",
            tmp_path / "missing.pdb",
        )
        assert result["hydrogen_bonds"] == []
