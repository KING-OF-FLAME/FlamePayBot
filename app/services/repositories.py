import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import AccessCode, AuditLog, BalanceLedger, CallbackEvent, GatewayConfig, GatewayPackage, Order, PayoutRequest, User


ORDER_LABELS = {
    '0': 'created',
    '1': 'in payment',
    '2': 'success',
    '3': 'failure',
    '4': 'revoked',
    '5': 'refunded',
    '6': 'closed',
}


def get_or_create_user(db: Session, tg_user_id: int, username: str | None, full_name: str | None) -> User:
    user = db.scalar(select(User).where(User.tg_user_id == tg_user_id))
    if not user:
        user = User(tg_user_id=tg_user_id, username=username, full_name=full_name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def create_access_code(db: Session, created_by: int, max_uses: int = 1, expires_at: datetime | None = None) -> AccessCode:
    code = secrets.token_urlsafe(8).replace('-', '').replace('_', '').upper()[:10]
    rec = AccessCode(code=code, max_uses=max_uses, expires_at=expires_at, created_by=created_by)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def activate_with_code(db: Session, user: User, code: str) -> tuple[bool, str]:
    record = db.scalar(select(AccessCode).where(AccessCode.code == code, AccessCode.is_active.is_(True)))
    if not record:
        return False, 'Invalid code.'
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if record.expires_at and record.expires_at < now:
        return False, 'Code expired.'
    if record.used_count >= record.max_uses:
        return False, 'Code max uses reached.'
    user.is_active = True
    user.activated_at = now
    record.used_count += 1
    db.commit()
    return True, 'Activation successful.'


def audit(db: Session, actor_tg_user_id: int | None, action: str, target_type: str | None = None, target_id: str | None = None, detail: dict | None = None) -> None:
    row = AuditLog(
        actor_tg_user_id=actor_tg_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
    )
    db.add(row)
    db.commit()


def get_enabled_gateways(db: Session) -> list[GatewayConfig]:
    return list(db.scalars(select(GatewayConfig).where(GatewayConfig.enabled.is_(True)).order_by(GatewayConfig.title)))


def get_gateway_packages(db: Session, gateway_id: int) -> list[GatewayPackage]:
    return list(
        db.scalars(
            select(GatewayPackage)
            .where(GatewayPackage.gateway_id == gateway_id, GatewayPackage.enabled.is_(True))
            .order_by(GatewayPackage.sort_order, GatewayPackage.amount_cents)
        )
    )


def create_order(db: Session, user: User, way_code: str, package_label: str, amount_cents: int, fee_percent: Decimal, final_amount_cents: int) -> Order:
    mch_order_no = f'FP{user.tg_user_id}{int(datetime.utcnow().timestamp())}{secrets.randbelow(900)+100}'
    order = Order(
        user_id=user.id,
        mch_no='N/A',
        mch_order_no=mch_order_no,
        way_code=way_code,
        package_label=package_label,
        amount_cents=amount_cents,
        fee_percent=fee_percent,
        final_amount_cents=final_amount_cents,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def update_order_status(db: Session, order: Order, new_status: str, pay_order_no: str | None = None, provider_payload: dict | None = None) -> None:
    order.status = new_status
    if pay_order_no:
        order.pay_order_no = pay_order_no
    if provider_payload:
        order.provider_raw_notify = json.dumps(provider_payload, ensure_ascii=False)
    db.commit()


def credit_order_success(db: Session, order: Order) -> None:
    user = db.get(User, order.user_id)
    amount = Decimal(order.amount_cents) / Decimal(100)
    existing = db.scalar(select(BalanceLedger).where(BalanceLedger.ref_order_id == order.id, BalanceLedger.entry_type == 'deposit_credit'))
    if existing:
        return
    user.balance_available = Decimal(user.balance_available) + amount
    db.add(BalanceLedger(user_id=user.id, entry_type='deposit_credit', amount=amount, ref_order_id=order.id, note='Order success'))
    db.commit()


def create_payout_request(db: Session, user: User, amount: Decimal, network: str, address: str) -> PayoutRequest:
    user.balance_available = Decimal(user.balance_available) - amount
    user.balance_hold = Decimal(user.balance_hold) + amount
    payout = PayoutRequest(user_id=user.id, amount=amount, network=network, address=address)
    db.add(payout)
    db.flush()
    db.add(BalanceLedger(user_id=user.id, entry_type='payout_hold', amount=amount, ref_payout_id=payout.id, note='Payout request hold'))
    db.commit()
    db.refresh(payout)
    return payout


def approve_payout(db: Session, payout: PayoutRequest, note: str | None, txid: str | None) -> None:
    if payout.status != 'pending':
        return
    user = db.get(User, payout.user_id)
    user.balance_hold = Decimal(user.balance_hold) - Decimal(payout.amount)
    payout.status = 'approved'
    payout.admin_note = note
    payout.txid = txid
    db.add(BalanceLedger(user_id=user.id, entry_type='payout_approve', amount=Decimal(payout.amount), ref_payout_id=payout.id, note=note or 'Approved'))
    db.commit()


def reject_payout(db: Session, payout: PayoutRequest, reason: str) -> None:
    if payout.status != 'pending':
        return
    user = db.get(User, payout.user_id)
    user.balance_hold = Decimal(user.balance_hold) - Decimal(payout.amount)
    user.balance_available = Decimal(user.balance_available) + Decimal(payout.amount)
    payout.status = 'rejected'
    payout.admin_note = reason
    db.add(BalanceLedger(user_id=user.id, entry_type='payout_reject_return', amount=Decimal(payout.amount), ref_payout_id=payout.id, note=reason))
    db.commit()


def register_callback_event(db: Session, event_key: str, payload: dict) -> bool:
    exists = db.scalar(select(CallbackEvent).where(CallbackEvent.event_key == event_key))
    if exists:
        return False
    db.add(CallbackEvent(event_key=event_key, payload_json=json.dumps(payload, ensure_ascii=False), processed=True))
    db.commit()
    return True


def recent_orders(db: Session, user_id: int, limit: int = 10) -> list[Order]:
    return list(db.scalars(select(Order).where(Order.user_id == user_id).order_by(desc(Order.created_at)).limit(limit)))
