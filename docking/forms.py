from django import forms

from .models import DockingJob

TAILWIND_INPUT = "w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
TAILWIND_CHECKBOX = "h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"


class DockingJobForm(forms.ModelForm):
    ensemble_enabled = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": TAILWIND_CHECKBOX,
                "id": "id_ensemble_enabled",
            }
        ),
    )

    class Meta:
        model = DockingJob
        fields = [
            "name",
            "protein_file",
            "ligand_file",
            "num_pockets",
            "exhaustiveness",
            "scoring_function",
            "refine_poses",
            "rescore_mmgbsa",
            "ensemble_method",
            "num_conformations",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": TAILWIND_INPUT,
                    "placeholder": "e.g. EGFR + Erlotinib",
                }
            ),
            "protein_file": forms.ClearableFileInput(
                attrs={
                    "class": "hidden",
                    "accept": ".pdb,.pdb.gz,.cif",
                    "id": "protein-file-input",
                }
            ),
            "ligand_file": forms.ClearableFileInput(
                attrs={
                    "class": "hidden",
                    "accept": ".sdf,.mol2,.mol",
                    "id": "ligand-file-input",
                }
            ),
            "num_pockets": forms.NumberInput(attrs={"class": TAILWIND_INPUT, "min": 1, "max": 20}),
            "exhaustiveness": forms.NumberInput(
                attrs={"class": TAILWIND_INPUT, "min": 1, "max": 64}
            ),
            "scoring_function": forms.Select(attrs={"class": TAILWIND_INPUT}),
            "refine_poses": forms.CheckboxInput(
                attrs={"class": TAILWIND_CHECKBOX, "id": "id_refine_poses"}
            ),
            "rescore_mmgbsa": forms.CheckboxInput(
                attrs={"class": TAILWIND_CHECKBOX, "id": "id_rescore_mmgbsa"}
            ),
            "ensemble_method": forms.Select(
                attrs={"class": TAILWIND_INPUT, "id": "id_ensemble_method"}
            ),
            "num_conformations": forms.NumberInput(
                attrs={"class": TAILWIND_INPUT, "min": 2, "max": 10, "id": "id_num_conformations"}
            ),
        }

    def clean_protein_file(self):
        f = self.cleaned_data.get("protein_file")
        if f:
            name = f.name.lower()
            if not any(name.endswith(ext) for ext in [".pdb", ".pdb.gz", ".cif"]):
                raise forms.ValidationError(
                    "Protein file must be PDB (.pdb), gzipped PDB (.pdb.gz), or mmCIF (.cif)."
                )
            if f.size > 50 * 1024 * 1024:
                raise forms.ValidationError("Protein file must be under 50 MB.")
        return f

    def clean_ligand_file(self):
        f = self.cleaned_data.get("ligand_file")
        if f:
            name = f.name.lower()
            if not any(name.endswith(ext) for ext in [".sdf", ".mol2", ".mol"]):
                raise forms.ValidationError(
                    "Ligand file must be SDF (.sdf), MOL2 (.mol2), or MOL (.mol)."
                )
            if f.size > 10 * 1024 * 1024:
                raise forms.ValidationError("Ligand file must be under 10 MB.")
        return f

    def clean_num_pockets(self):
        value = self.cleaned_data.get("num_pockets")
        if value is not None and not (1 <= value <= 20):
            raise forms.ValidationError("Number of pockets must be between 1 and 20.")
        return value

    def clean_exhaustiveness(self):
        value = self.cleaned_data.get("exhaustiveness")
        if value is not None and not (1 <= value <= 64):
            raise forms.ValidationError("Exhaustiveness must be between 1 and 64.")
        return value


MAX_BATCH_LIGANDS = 100


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            return [super(MultipleFileField, self).clean(d, initial) for d in data]
        return [super().clean(data, initial)]


class BatchDockingForm(forms.Form):
    """Form for batch docking: one protein + multiple ligands."""

    name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": TAILWIND_INPUT,
                "placeholder": "e.g. EGFR library screen",
            }
        ),
    )
    protein_file = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                "class": "hidden",
                "accept": ".pdb,.pdb.gz,.cif",
                "id": "protein-file-input",
            }
        ),
    )
    ligand_files = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "class": "hidden",
                "accept": ".sdf,.mol2,.mol",
                "id": "ligand-file-input",
            }
        ),
    )
    num_pockets = forms.IntegerField(
        initial=3,
        min_value=1,
        max_value=20,
        widget=forms.NumberInput(attrs={"class": TAILWIND_INPUT, "min": 1, "max": 20}),
    )
    exhaustiveness = forms.IntegerField(
        initial=8,
        min_value=1,
        max_value=64,
        widget=forms.NumberInput(attrs={"class": TAILWIND_INPUT, "min": 1, "max": 64}),
    )
    scoring_function = forms.ChoiceField(
        choices=DockingJob.ScoringFunction.choices,
        initial=DockingJob.ScoringFunction.VINA,
        widget=forms.Select(attrs={"class": TAILWIND_INPUT}),
    )
    refine_poses = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": TAILWIND_CHECKBOX, "id": "id_refine_poses"}),
    )
    rescore_mmgbsa = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": TAILWIND_CHECKBOX, "id": "id_rescore_mmgbsa"}),
    )
    ensemble_enabled = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": TAILWIND_CHECKBOX, "id": "id_ensemble_enabled"}),
    )
    ensemble_method = forms.ChoiceField(
        choices=DockingJob.EnsembleMethod.choices,
        initial=DockingJob.EnsembleMethod.NONE,
        required=False,
        widget=forms.Select(attrs={"class": TAILWIND_INPUT, "id": "id_ensemble_method"}),
    )
    num_conformations = forms.IntegerField(
        initial=5,
        min_value=2,
        max_value=10,
        required=False,
        widget=forms.NumberInput(
            attrs={"class": TAILWIND_INPUT, "min": 2, "max": 10, "id": "id_num_conformations"}
        ),
    )

    def clean_protein_file(self):
        f = self.cleaned_data.get("protein_file")
        if f:
            name = f.name.lower()
            if not any(name.endswith(ext) for ext in [".pdb", ".pdb.gz", ".cif"]):
                raise forms.ValidationError(
                    "Protein file must be PDB (.pdb), gzipped PDB (.pdb.gz), or mmCIF (.cif)."
                )
            if f.size > 50 * 1024 * 1024:
                raise forms.ValidationError("Protein file must be under 50 MB.")
        return f

    def clean(self):
        cleaned = super().clean()
        ligand_files = self.files.getlist("ligand_files")
        if not ligand_files:
            raise forms.ValidationError("At least one ligand file is required.")
        if len(ligand_files) > MAX_BATCH_LIGANDS:
            raise forms.ValidationError(f"Maximum {MAX_BATCH_LIGANDS} ligand files per batch.")
        valid_exts = (".sdf", ".mol2", ".mol")
        for f in ligand_files:
            if not any(f.name.lower().endswith(ext) for ext in valid_exts):
                raise forms.ValidationError(
                    f"'{f.name}' is not a supported ligand format (.sdf, .mol2, .mol)."
                )
            if f.size > 10 * 1024 * 1024:
                raise forms.ValidationError(f"'{f.name}' exceeds the 10 MB limit.")
        return cleaned
