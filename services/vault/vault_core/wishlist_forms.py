from django import forms
from django.forms import formset_factory

from .wishlists import euro_cents


class WishForm(forms.Form):
    title = forms.CharField(label="Nom et référence de l'article", max_length=160, required=False)
    url = forms.CharField(label="Lien HTTPS de référence", max_length=2048, required=False)
    price = forms.CharField(
        label="Prix indicatif en EUR, strictement inférieur à 50 €", required=False
    )
    currency = forms.CharField(
        label="Devise du prix d'origine (EUR, USD…)", initial="EUR", max_length=3, required=False
    )
    price_date = forms.DateField(
        label="Date du prix déclaré", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    note = forms.CharField(
        label="Taille, couleur, édition ou compatibilité",
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    exact_model = forms.BooleanField(label="Modèle exact requis", required=False)
    equivalent_ok = forms.BooleanField(label="Un article équivalent me convient", required=False)

    def clean_price(self):
        value = self.cleaned_data["price"]
        if not value:
            return None
        try:
            return euro_cents(value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None


WishFormSet = formset_factory(
    WishForm, extra=0, min_num=3, max_num=3, absolute_max=3, validate_min=True, validate_max=True
)
