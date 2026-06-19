"""Facturation Stripe : Checkout d'abonnement + vérification des webhooks.

Opt-in : tout repose sur `settings.stripe_secret_key`. Vide => facturation
désactivée (le gating laisse passer, cf. deps.require_active_subscription).
"""
import stripe

from .config import settings


def is_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def _init() -> None:
    stripe.api_key = settings.stripe_secret_key


def create_checkout_session(org_id, email: str, customer_id: str | None = None) -> str:
    """Crée une session Checkout d'abonnement et renvoie son URL."""
    _init()
    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": settings.stripe_price_id, "quantity": 1}],
        "success_url": settings.billing_success_url,
        "cancel_url": settings.billing_cancel_url,
        "client_reference_id": str(org_id),
    }
    if customer_id:
        params["customer"] = customer_id
    elif email:
        params["customer_email"] = email
    session = stripe.checkout.Session.create(**params)
    return session.url


def construct_event(payload: bytes, sig_header: str):
    """Vérifie la signature Stripe et renvoie l'événement."""
    _init()
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )
