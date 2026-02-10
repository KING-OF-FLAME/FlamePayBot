from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import desc, select

from app.core.config import get_settings
from app.db.models import AccessCode, GatewayConfig, GatewayPackage, Order, PayoutRequest, User
from app.db.session import SessionLocal
from app.services.provider_client import ProviderClient
from app.services.repositories import ORDER_LABELS, approve_payout, audit, create_access_code, get_or_create_user, reject_payout

router = Router()
settings = get_settings()
provider = ProviderClient()


def is_admin(tg_user_id: int) -> bool:
    return tg_user_id in settings.admin_ids


def parse_expiry(date_str: str | None):
    if not date_str:
        return None
    return datetime.fromisoformat(date_str)


@router.message(Command('admin'))
async def admin_menu(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer('/gencode [max_uses] [YYYY-MM-DD]\n/codes\n/ban <tg_id>\n/unban <tg_id>\n/setfee <percent>\n/payouts\n/payout_approve <id> [txid] [note]\n/payout_reject <id> <reason>\n/orders_search <term>\n/reconcile <mchOrderNo>')


@router.message(Command('gencode'))
async def gencode(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split()
    max_uses = int(args[1]) if len(args) > 1 else 1
    expires_at = parse_expiry(args[2]) if len(args) > 2 else None
    with SessionLocal() as db:
        rec = create_access_code(db, message.from_user.id, max_uses=max_uses, expires_at=expires_at)
    await message.answer(f'Code: `{rec.code}` uses={rec.max_uses}', parse_mode='Markdown')


@router.message(Command('codes'))
async def codes(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    with SessionLocal() as db:
        rows = db.scalars(select(AccessCode).order_by(desc(AccessCode.created_at)).limit(20)).all()
    txt = '\n'.join([f'{r.code} used {r.used_count}/{r.max_uses} active={r.is_active}' for r in rows]) or 'None'
    await message.answer(txt)


@router.message(Command('ban'))
async def ban(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split()
    if len(args) < 2:
        await message.answer('Usage: /ban <tg_user_id>')
        return
    tid = int(args[1])
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.tg_user_id == tid))
        if not user:
            await message.answer('user not found')
            return
        user.is_banned = True
        db.commit()
        audit(db, message.from_user.id, 'ban', 'user', str(tid))
    await message.answer('banned')


@router.message(Command('unban'))
async def unban(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split()
    if len(args) < 2:
        await message.answer('Usage: /unban <tg_user_id>')
        return
    tid = int(args[1])
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.tg_user_id == tid))
        if not user:
            await message.answer('user not found')
            return
        user.is_banned = False
        db.commit()
        audit(db, message.from_user.id, 'unban', 'user', str(tid))
    await message.answer('unbanned')


@router.message(Command('setfee'))
async def setfee(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer('Set GLOBAL_FEE_PERCENT in .env and restart (runtime config is static).')


@router.message(Command('payouts'))
async def payouts(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    with SessionLocal() as db:
        rows = db.scalars(select(PayoutRequest).order_by(desc(PayoutRequest.created_at)).limit(20)).all()
    txt = '\n'.join([f'#{r.id} user={r.user_id} amount={r.amount} {r.network} {r.status}' for r in rows]) or 'No payouts.'
    await message.answer(txt)


@router.message(Command('payout_approve'))
async def payout_approve(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split(maxsplit=3)
    if len(args) < 2:
        await message.answer('Usage: /payout_approve <id> [txid] [note]')
        return
    pid = int(args[1])
    txid = args[2] if len(args) > 2 else None
    note = args[3] if len(args) > 3 else None
    with SessionLocal() as db:
        row = db.get(PayoutRequest, pid)
        if not row:
            await message.answer('not found')
            return
        approve_payout(db, row, note, txid)
    await message.answer('approved')


@router.message(Command('payout_reject'))
async def payout_reject(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split(maxsplit=2)
    if len(args) < 3:
        await message.answer('Usage: /payout_reject <id> <reason>')
        return
    pid = int(args[1])
    reason = args[2]
    with SessionLocal() as db:
        row = db.get(PayoutRequest, pid)
        if not row:
            await message.answer('not found')
            return
        reject_payout(db, row, reason)
    await message.answer('rejected')


@router.message(Command('orders_search'))
async def orders_search(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split(maxsplit=1)
    if len(args) < 2:
        await message.answer('Usage: /orders_search <term>')
        return
    term = args[1].strip()
    with SessionLocal() as db:
        rows = db.scalars(select(Order).where((Order.mch_order_no == term) | (Order.pay_order_no == term)).limit(10)).all()
    txt = '\n'.join([f'{r.mch_order_no}/{r.pay_order_no} {ORDER_LABELS.get(r.status, r.status)}' for r in rows]) or 'None'
    await message.answer(txt)


@router.message(Command('reconcile'))
async def reconcile(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split(maxsplit=1)
    if len(args) < 2:
        await message.answer('Usage: /reconcile <mchOrderNo>')
        return
    mch_order_no = args[1].strip()
    resp = provider.query(mch_order_no=mch_order_no)
    data = resp.get('data', {}) if isinstance(resp, dict) else {}
    state = str(data.get('state', '?'))
    with SessionLocal() as db:
        order = db.scalar(select(Order).where(Order.mch_order_no == mch_order_no))
        if order and state in {'0', '1', '2', '3', '4', '5', '6'}:
            order.status = state
            db.commit()
    await message.answer(f'Reconcile result: {resp}')

@router.message(Command('gateway'))
async def gateway_toggle(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split()
    if len(args) < 4:
        await message.answer('Usage: /gateway <way_code> <title> <on|off>')
        return
    way_code, title, mode = args[1], args[2], args[3].lower()
    with SessionLocal() as db:
        row = db.scalar(select(GatewayConfig).where(GatewayConfig.way_code == way_code))
        if not row:
            row = GatewayConfig(way_code=way_code, title=title, enabled=mode == 'on')
            db.add(row)
        else:
            row.title = title
            row.enabled = mode == 'on'
        db.commit()
    await message.answer('Gateway updated.')


@router.message(Command('package_add'))
async def package_add(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    args = (message.text or '').split(maxsplit=4)
    if len(args) < 5:
        await message.answer('Usage: /package_add <way_code> <label> <amount_cents> <sort_order>')
        return
    way_code, label, amount_cents, sort_order = args[1], args[2], int(args[3]), int(args[4])
    with SessionLocal() as db:
        gw = db.scalar(select(GatewayConfig).where(GatewayConfig.way_code == way_code))
        if not gw:
            await message.answer('Gateway not found.')
            return
        p = GatewayPackage(gateway_id=gw.id, label=label, amount_cents=amount_cents, sort_order=sort_order, enabled=True)
        db.add(p)
        db.commit()
    await message.answer('Package added.')
