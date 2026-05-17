from django import forms

from .models import DockingJob


class DockingJobForm(forms.ModelForm):
    class Meta:
        model = DockingJob
        fields = ["name", "protein_file", "ligand_file", "num_pockets", "exhaustiveness", "scoring_function", "refine_poses", "rescore_mmgbsa"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent",
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
            "num_pockets": forms.NumberInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                    "min": 1,
                    "max": 20,
                }
            ),
            "exhaustiveness": forms.NumberInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                    "min": 1,
                    "max": 64,
                }
            ),
            "scoring_function": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                }
            ),
            "refine_poses": forms.CheckboxInput(
                attrs={
                    "class": "h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500",
                    "id": "id_refine_poses",
                }
            ),
            "rescore_mmgbsa": forms.CheckboxInput(
                attrs={
                    "class": "h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500",
                    "id": "id_rescore_mmgbsa",
                }
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
