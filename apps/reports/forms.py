from django import forms


class ReportCreateForm(forms.Form):
    description = forms.CharField(required=True)
    latitude = forms.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = forms.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    image = forms.ImageField(required=False)

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if not description:
            raise forms.ValidationError("Description cannot be empty.")
        return description
