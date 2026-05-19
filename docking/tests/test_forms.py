from django.core.files.uploadedfile import SimpleUploadedFile

from docking.forms import DockingJobForm


def _make_file(name, content=b"data", size=None):
    f = SimpleUploadedFile(name, content)
    if size:
        f.size = size
    return f


class TestDockingJobForm:
    def test_valid_form(self):
        form = DockingJobForm(
            data={
                "name": "test",
                "num_pockets": 3,
                "exhaustiveness": 8,
                "scoring_function": "vina",
            },
            files={
                "protein_file": _make_file("protein.pdb"),
                "ligand_file": _make_file("ligand.sdf"),
            },
        )
        assert form.is_valid(), form.errors

    def test_invalid_protein_extension(self):
        form = DockingJobForm(
            data={"num_pockets": 3, "exhaustiveness": 8},
            files={
                "protein_file": _make_file("protein.xyz"),
                "ligand_file": _make_file("ligand.sdf"),
            },
        )
        assert not form.is_valid()
        assert "protein_file" in form.errors

    def test_invalid_ligand_extension(self):
        form = DockingJobForm(
            data={"num_pockets": 3, "exhaustiveness": 8},
            files={
                "protein_file": _make_file("protein.pdb"),
                "ligand_file": _make_file("ligand.txt"),
            },
        )
        assert not form.is_valid()
        assert "ligand_file" in form.errors

    def test_protein_too_large(self):
        f = _make_file("protein.pdb")
        f.size = 60 * 1024 * 1024
        form = DockingJobForm(
            data={"num_pockets": 3, "exhaustiveness": 8},
            files={"protein_file": f, "ligand_file": _make_file("ligand.sdf")},
        )
        assert not form.is_valid()
        assert "protein_file" in form.errors

    def test_num_pockets_too_high(self):
        form = DockingJobForm(
            data={"num_pockets": 50, "exhaustiveness": 8},
            files={
                "protein_file": _make_file("protein.pdb"),
                "ligand_file": _make_file("ligand.sdf"),
            },
        )
        assert not form.is_valid()
        assert "num_pockets" in form.errors

    def test_num_pockets_zero(self):
        form = DockingJobForm(
            data={"num_pockets": 0, "exhaustiveness": 8},
            files={
                "protein_file": _make_file("protein.pdb"),
                "ligand_file": _make_file("ligand.sdf"),
            },
        )
        assert not form.is_valid()
        assert "num_pockets" in form.errors

    def test_exhaustiveness_too_high(self):
        form = DockingJobForm(
            data={"num_pockets": 3, "exhaustiveness": 100},
            files={
                "protein_file": _make_file("protein.pdb"),
                "ligand_file": _make_file("ligand.sdf"),
            },
        )
        assert not form.is_valid()
        assert "exhaustiveness" in form.errors

    def test_scoring_function_vina(self):
        form = DockingJobForm(
            data={
                "name": "test",
                "num_pockets": 3,
                "exhaustiveness": 8,
                "scoring_function": "vina",
            },
            files={
                "protein_file": _make_file("protein.pdb"),
                "ligand_file": _make_file("ligand.sdf"),
            },
        )
        assert form.is_valid(), form.errors

    def test_scoring_function_vinardo(self):
        form = DockingJobForm(
            data={
                "name": "test",
                "num_pockets": 3,
                "exhaustiveness": 8,
                "scoring_function": "vinardo",
            },
            files={
                "protein_file": _make_file("protein.pdb"),
                "ligand_file": _make_file("ligand.sdf"),
            },
        )
        assert form.is_valid(), form.errors

    def test_scoring_function_invalid(self):
        form = DockingJobForm(
            data={
                "name": "test",
                "num_pockets": 3,
                "exhaustiveness": 8,
                "scoring_function": "invalid",
            },
            files={
                "protein_file": _make_file("protein.pdb"),
                "ligand_file": _make_file("ligand.sdf"),
            },
        )
        assert not form.is_valid()
        assert "scoring_function" in form.errors
