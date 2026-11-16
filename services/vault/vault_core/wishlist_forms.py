from django import forms
from django.forms import formset_factory
from django.forms.renderers import DjangoTemplates
from django.forms.utils import flatatt
from django.utils.html import format_html, format_html_join

from .wishlists import euro_cents


class WishlistRenderer(DjangoTemplates):
    """Render only this form's simple widgets without nested template dispatch.

    Widget.get_context and BoundField still supply values, IDs, validation and ARIA.
    flatatt/format_html escape every attribute and value; other widgets use Django.
    """

    def render(self, template_name, context, request=None):
        simple = {
            "django/forms/widgets/" + name + ".html"
            for name in ("text", "date", "checkbox", "textarea", "hidden")
        }
        if template_name not in simple:
            return super().render(template_name, context, request)
        widget = context["widget"]
        if template_name.endswith("/textarea.html"):
            return format_html(
                '<textarea name="{}"{}>\n{}</textarea>',
                widget["name"],
                flatatt(widget["attrs"]),
                widget["value"] or "",
            )
        attrs = {"type": widget["type"], "name": widget["name"], **widget["attrs"]}
        if widget["value"] is not None:
            attrs["value"] = widget["value"]
        return format_html("<input{}>", flatatt(attrs))


class WishForm(forms.Form):
    default_renderer = WishlistRenderer()

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

    def as_p(self):
        # Keep Django widgets/validation/ARIA attributes; avoid repeatedly rendering
        # the generic form/label templates for this fixed, flat eight-field form.
        rows = []
        for field in self:
            label = format_html('<label for="{}">{}</label>', field.id_for_label, field.label)
            rows.append((field.errors if field.errors else "", label, field.as_widget()))
        return format_html(
            "{}{}", self.non_field_errors() or "", format_html_join("", "{}<p>{}{}</p>", rows)
        )

    def clean_price(self):
        value = self.cleaned_data["price"]
        if not value:
            return None
        try:
            return euro_cents(value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None


WishFormSet = formset_factory(
    WishForm,
    extra=0,
    min_num=3,
    max_num=3,
    absolute_max=3,
    validate_min=True,
    validate_max=True,
    renderer=WishForm.default_renderer,
)
