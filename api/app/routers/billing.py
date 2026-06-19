import uuid
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..billing import construct_event, create_checkout_session, is_enabled
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Subscription, User
from ..schemas import CheckoutOut, SubscriptionOut

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if not is_enabled():
        return SubscriptionOut(billing_enabled=False, status="disabled")
    sub = (
        db.query(Subscription).filter(Subscription.org_id == user.org_id).first()
    )
    if not sub:
        return SubscriptionOut(billing_enabled=True, status="none")
    return SubscriptionOut(
        billing_enabled=True,
        status=sub.status,
        plan=sub.plan,
        current_period_end=sub.current_period_end,
    )


@router.post("/checkout", response_model=CheckoutOut)
def create_checkout(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Crée une session Stripe Checkout d'abonnement pour l'organisation."""
    if not is_enabled() or not settings.stripe_price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Facturation non configurée (STRIPE_SECRET_KEY / STRIPE_PRICE_ID).",
        )
    sub = (
        db.query(Subscription).filter(Subscription.org_id == user.org_id).first()
    )
    customer_id = sub.stripe_customer_id if sub else None
    try:
        url = create_checkout_session(user.org_id, user.email, customer_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe: {exc}"
        )
    return CheckoutOut(url=url)


def _apply_stripe_subscription(sub: Subscription, stripe_sub) -> None:
    sub.status = stripe_sub.get("status", sub.status)
    cpe = stripe_sub.get("current_period_end")
    if cpe:
        sub.current_period_end = datetime.fromtimestamp(cpe, tz=timezone.utc)
    if stripe_sub.get("customer"):
        sub.stripe_customer_id = stripe_sub["customer"]
    sub.stripe_subscription_id = stripe_sub.get("id", sub.stripe_subscription_id)
    try:
        sub.plan = stripe_sub["items"]["data"][0]["price"]["id"]
    except Exception:  # noqa: BLE001
        pass


def _handle_event(event, db: Session) -> None:
    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        org_ref = obj.get("client_reference_id")
        if not org_ref:
            return
        org_id = uuid.UUID(org_ref)
        sub = db.query(Subscription).filter(Subscription.org_id == org_id).first()
        if not sub:
            sub = Subscription(org_id=org_id)
            db.add(sub)
        sub.stripe_customer_id = obj.get("customer")
        sub_id = obj.get("subscription")
        sub.stripe_subscription_id = sub_id
        sub.status = "active"
        if sub_id:
            try:
                _apply_stripe_subscription(sub, stripe.Subscription.retrieve(sub_id))
            except Exception:  # noqa: BLE001
                pass
        db.commit()

    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == obj.get("id"))
            .first()
        )
        if not sub:
            return
        if etype.endswith("deleted"):
            sub.status = "canceled"
        else:
            _apply_stripe_subscription(sub, obj)
        db.commit()


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Endpoint appelé par Stripe (hors auth) : signature vérifiée, statut synchronisé."""
    if not is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Facturation non configurée.",
        )
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = construct_event(payload, sig)
    except Exception as exc:  # noqa: BLE001 — signature invalide / payload corrompu
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Webhook invalide: {exc}"
        )
    _handle_event(event, db)
    return {"received": True}
