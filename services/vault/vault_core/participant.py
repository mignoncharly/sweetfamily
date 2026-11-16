"""Participant forms; membership and mutations remain scoped to the current account."""

import json

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from noel_ui import COUNTRIES, call_api

from . import draw_views, views, wishlist_views
from .models import Membership


class ProfileForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput, min_value=0)
    display_name = forms.CharField(label="Mon prénom ou nom dans le groupe", max_length=80)
    country = forms.ChoiceField(label="Pays où je commande et reçois le cadeau", choices=COUNTRIES)


class WithdrawForm(forms.Form):
    confirm = forms.BooleanField(label="Je confirme mon retrait et ses conséquences pour le groupe")


class MerchantForm(forms.Form):
    hostname = forms.CharField(
        label="Domaine de la boutique",
        max_length=253,
        help_text=(
            "Par exemple boutique.fr, sans lien produit. Aucun site n’est consulté automatiquement."
        ),
    )


@require_http_methods(["GET"])
def help_page(request):
    return render(request, "vault/help.html")


@require_http_methods(["GET", "POST"])
@views.authenticated
def page(request, kind):
    try:
        member = views.membership(request)
    except (Membership.DoesNotExist, ValidationError, ValueError):
        return views.error(status=404)
    if kind == "profile":
        form = ProfileForm(
            request.POST if request.method == "POST" else None,
            initial={
                "revision": member.revision,
                "display_name": member.display_name,
                "country": member.country,
            },
        )
        if member.event.state == "DRAWN":
            form.fields["display_name"].disabled = True
        title = "Mon profil"
        notice = (
            "Avant le tirage, une modification demande une nouvelle confirmation du"
            " groupe. Après le tirage, le nom reste gelé."
        )
        target = views.profile
        method = "PATCH"
    elif kind == "withdraw":
        form = WithdrawForm(request.POST if request.method == "POST" else None)
        title = "Me retirer du groupe"
        notice = (
            "Avant le tirage, le groupe devra confirmer à nouveau. Dès le lancement"
            " du tirage, ton retrait annule le tirage pour tout le groupe, sans "
            "nouvelle attribution."
        )
        target = draw_views.withdrawal
        method = "POST"
    else:
        form = MerchantForm(request.POST if request.method == "POST" else None)
        title = "Proposer une boutique"
        notice = (
            "Une demande ne vaut pas approbation. Choisis une boutique déjà "
            "autorisée pour valider ta liste en attendant."
        )
        target = wishlist_views.merchant_request
        method = "POST"
    status = 200
    if request.method == "POST" and form.is_valid():
        response = call_api(request, target, request.path, form.cleaned_data, method=method)
        if response.status_code < 300:
            messages.success(
                request,
                "Ta demande est enregistrée."
                if kind == "merchant"
                else "Modification enregistrée.",
            )
            return redirect("/" if kind == "withdraw" else request.get_full_path())
        status = response.status_code
        form.add_error(
            None,
            json.loads(response.content).get(
                "message", "Action non confirmée. Ta saisie est conservée."
            ),
        )
    elif request.method == "POST":
        status = 400
    return render(
        request,
        "vault/form.html",
        {"form": form, "title": title, "notice": notice, "member": member},
        status=status,
    )
