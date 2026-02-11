from decimal import Decimal
import logging

import httpx

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.bot.keyboards.common import main_menu, payout_networks
from app.core.config import get_settings
from app.db.models import GatewayConfig, GatewayPackage, Order, User
from app.db.session import SessionLocal
from app.services.provider_client import ProviderClient
from app.services.repositories import (
    ORDER_LABELS,
    activate_with_code,
    create_order,
    create_payout_request,
    get_or_create_user,
    list_enabled_gateway_codes,
    recent_orders,
)

router = Router()
settings = get_settings()
provider = ProviderClient()
logger = logging.getLogger(__name__)



USER_HELP_TEXT = """User Commands:
/start - Open main menu
/help - Show this help
/activate <code> - Activate account
/pay - Start recharge flow
/status <mchOrderNo|payOrderNo> - Check order
/orders - Recent orders
/payoutrequest - Create payout request
/bal - Check balance
"""

ADMIN_HELP_TEXT = USER_HELP_TEXT + """
Admin Commands:
/admin - Admin menu
/gencode [max_uses] [YYYY-MM-DD] - Create access code
/codes - List access codes
/ban <tg_id> /unban <tg_id> - Manage bans
/setfee <percent> - Fee instruction
/gateway - List gateway allowlist
/gateway_add <code> - Enable gateway
/gateway_remove <code> - Disable gateway
/gateway_config <way_code> <title> <on|off> - Gateway package config
/package_add <way_code> <label> <amount_cents> <sort_order> - Add package
/payouts - List payouts
/payout_approve <id> [txid] [note] - Approve payout
/payout_reject <id> <reason> - Reject payout
/orders_search <term> - Search orders
/reconcile <mchOrderNo> - Query provider status
"""


@router.message(Command('help'))
async def help_cmd(message: Message) -> None:
    is_admin = message.from_user.id in settings.admin_ids
    await message.answer(ADMIN_HELP_TEXT if is_admin else USER_HELP_TEXT)


class PayoutFSM(StatesGroup):
    waiting_amount = State()
    waiting_network = State()
    waiting_address = State()


@router.message(Command('start'))
async def start(message: Message) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
    txt = 'Welcome. Use /activate <code> first. Send /help for commands.' if not user.is_active else 'Welcome back. Send /help for commands.'
    await message.answer(txt, reply_markup=main_menu())


@router.message(Command('activate'))
async def activate(message: Message) -> None:
    args = (message.text or '').split(maxsplit=1)
    if len(args) < 2:
        await message.answer('Usage: /activate <code>')
        return
    code = args[1].strip().upper()
    with SessionLocal() as db:
        user = get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
        _, msg = activate_with_code(db, user, code)
    await message.answer(msg)




async def _safe_cb_answer(cb: CallbackQuery, text: str | None = None) -> None:
    try:
        await cb.answer(text or '')
    except TelegramBadRequest:
        logger.warning('Callback answer skipped: query too old/invalid')

def _check_access(user: User) -> str | None:
    if user.is_banned:
        return 'You are banned.'
    if not user.is_active:
        return 'Activate first with /activate <code>.'
    return None


@router.message(Command('pay'))
async def pay(message: Message) -> None:
    await send_gateways(message, message.from_user.id, message.from_user.username, message.from_user.full_name)


@router.callback_query(F.data == 'menu:pay')
async def menu_pay(cb: CallbackQuery) -> None:
    await send_gateways(cb.message, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await _safe_cb_answer(cb)


async def send_gateways(message: Message, tg_user_id: int, username: str | None, full_name: str | None) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, tg_user_id, username, full_name)
        denied = _check_access(user)
        if denied:
            await message.answer(denied)
            return
        enabled_codes = list_enabled_gateway_codes(db)

    if not enabled_codes:
        await message.answer('No payment gateways enabled. Contact admin.')
        return

    kb = InlineKeyboardBuilder()
    for code in enabled_codes:
        kb.row(InlineKeyboardButton(text=code.upper(), callback_data=f'gw:{code}'))
    await message.answer('Select gateway:', reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith('gw:'))
async def select_gateway(cb: CallbackQuery) -> None:
    way_code = cb.data.split(':', 1)[1].strip().lower()
    with SessionLocal() as db:
        gw = db.scalar(select(GatewayConfig).where(GatewayConfig.way_code == way_code, GatewayConfig.enabled.is_(True)))
        if not gw:
            await cb.message.answer('Gateway is enabled in allowlist but package config is missing. Ask admin to set /gateway_config and /package_add.')
            await _safe_cb_answer(cb)
            return
        packs = list(
            db.scalars(
                select(GatewayPackage)
                .where(GatewayPackage.gateway_id == gw.id, GatewayPackage.enabled.is_(True))
                .order_by(GatewayPackage.sort_order, GatewayPackage.amount_cents)
            )
        )

    if not packs:
        await cb.message.answer('No packages configured for this gateway.')
        await _safe_cb_answer(cb)
        return

    kb = InlineKeyboardBuilder()
    for p in packs:
        kb.row(InlineKeyboardButton(text=f'{p.label} (${p.amount_cents/100:.2f})', callback_data=f'pkg:{p.id}'))
    await cb.message.answer('Select package:', reply_markup=kb.as_markup())
    await _safe_cb_answer(cb)


@router.callback_query(F.data.startswith('pkg:'))
async def select_package(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb, 'Processing...')
    package_id = int(cb.data.split(':')[1])
    with SessionLocal() as db:
        user = get_or_create_user(db, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        denied = _check_access(user)
        if denied:
            await cb.message.answer(denied)
            await _safe_cb_answer(cb)
            return
        pack = db.get(GatewayPackage, package_id)
        if not pack:
            await cb.message.answer('Package not found.')
            await _safe_cb_answer(cb)
            return
        gateway = db.get(GatewayConfig, pack.gateway_id)
        final_amount = int(round(pack.amount_cents * (1 + settings.global_fee_percent / 100)))
        order = create_order(db, user, gateway.way_code, pack.label, pack.amount_cents, Decimal(str(settings.global_fee_percent)), final_amount)
        try:
            resp = provider.create(order.mch_order_no, final_amount, gateway.way_code, f'{gateway.title}/{pack.label}')
        except httpx.ConnectError:
            order.status = '3'
            db.commit()
            logger.exception('Provider connection failed. Check PROVIDER_BASE_URL/DNS/network.')
            await cb.message.answer(
                'Payment provider connection failed. Please contact admin.\n\n'
                'Admin check: set correct PROVIDER_BASE_URL in .env (example: https://www.ggusonepay.com), then restart bot.'
            )
            await _safe_cb_answer(cb)
            return
        except httpx.HTTPError:
            order.status = '3'
            db.commit()
            logger.exception('Provider HTTP error during create order')
            await cb.message.answer('Payment request failed due to provider HTTP error. Try again later.')
            await _safe_cb_answer(cb)
            return
        except Exception:
            order.status = '3'
            db.commit()
            logger.exception('Unexpected provider error during create order')
            await cb.message.answer('Payment request failed unexpectedly. Try again later or contact admin.')
            await _safe_cb_answer(cb)
            return

        data = resp.get('data', {}) if isinstance(resp, dict) else {}
        import json

        order.provider_raw_create = json.dumps(resp, ensure_ascii=False)
        cashier = provider._extract_cashier(resp)
        state = str(data.get('state')) if isinstance(data, dict) and data.get('state') is not None else None

        if not cashier:
            top_msg = ''
            if isinstance(resp, dict):
                top_msg = str(resp.get('msg') or resp.get('message') or '')

            if 'DUPLICATE SUBMISSION' in top_msg.upper():
                order.status = '1'
                order.pay_order_no = data.get('payOrderNo') if isinstance(data, dict) else None
                db.commit()
                await cb.message.answer(
                    'Provider is processing an existing payment for this order.\n'
                    f'Order: `{order.mch_order_no}`\n'
                    'Use /status <mchOrderNo> in 10-20 seconds, or open My Orders to refresh status.',
                    parse_mode='Markdown',
                )
                await _safe_cb_answer(cb)
                return

            order.status = '3'
            db.commit()
            await cb.message.answer(
                'Provider did not return payment link (cashierUrl).\n'
                f'Order marked as failed.\nReason: {top_msg or "unknown provider response"}'
            )
            await _safe_cb_answer(cb)
            return

        order.status = state if state in {'0', '1', '2', '3', '4', '5', '6'} else '1'
        order.pay_order_no = data.get('payOrderNo') if isinstance(data, dict) else None
        order.cashier_url = cashier
        db.commit()
    await cb.message.answer(f'Order: `{order.mch_order_no}`\nPay URL: {cashier}', parse_mode='Markdown')
    await _safe_cb_answer(cb, 'Order created')


@router.message(Command('status'))
async def status_cmd(message: Message) -> None:
    args = (message.text or '').split(maxsplit=1)
    if len(args) < 2:
        await message.answer('Usage: /status <mchOrderNo|payOrderNo>')
        return
    q = args[1].strip()
    with SessionLocal() as db:
        order = db.scalar(select(Order).where((Order.mch_order_no == q) | (Order.pay_order_no == q)))
    if not order:
        await message.answer('Order not found.')
        return
    await message.answer(f'{order.mch_order_no}: {ORDER_LABELS.get(order.status, order.status)}')


@router.message(Command('orders'))
async def orders_cmd(message: Message) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
        rows = recent_orders(db, user.id)
    if not rows:
        await message.answer('No orders.')
        return
    text = '\n'.join([f"{o.mch_order_no} | ${o.amount_cents/100:.2f} | {ORDER_LABELS.get(o.status, o.status)}" for o in rows])
    await message.answer(text)


@router.callback_query(F.data == 'menu:orders')
async def menu_orders(cb: CallbackQuery) -> None:
    await orders_cmd(cb.message)
    await _safe_cb_answer(cb)




@router.message(Command('bal'))
async def bal_cmd(message: Message) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(f'Available: ${user.balance_available}\nHold: ${user.balance_hold}')

@router.callback_query(F.data == 'menu:balance')
async def menu_balance(cb: CallbackQuery) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await cb.message.answer(f'Available: ${user.balance_available}\nHold: ${user.balance_hold}')
    await _safe_cb_answer(cb)


@router.message(Command('payoutrequest'))
async def payout_request_cmd(message: Message, state: FSMContext) -> None:
    await start_payout_flow(message, state, message.from_user.id, message.from_user.username, message.from_user.full_name)


@router.callback_query(F.data == 'menu:payout')
async def menu_payout(cb: CallbackQuery, state: FSMContext) -> None:
    await start_payout_flow(cb.message, state, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await _safe_cb_answer(cb)


async def start_payout_flow(message: Message, state: FSMContext, tg_user_id: int, username: str | None, full_name: str | None) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, tg_user_id, username, full_name)
        denied = _check_access(user)
        if denied:
            await message.answer(denied)
            return
    await state.set_state(PayoutFSM.waiting_amount)
    await message.answer('Enter payout amount (e.g., 25.50):')


@router.message(PayoutFSM.waiting_amount)
async def payout_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal(message.text.strip())
    except Exception:
        await message.answer('Invalid amount.')
        return
    if amount <= 0:
        await message.answer('Amount must be > 0')
        return
    with SessionLocal() as db:
        user = get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
        if Decimal(user.balance_available) < amount:
            await message.answer('Insufficient available balance.')
            return
    await state.update_data(amount=str(amount))
    await state.set_state(PayoutFSM.waiting_network)
    await message.answer('Choose network:', reply_markup=payout_networks())


@router.callback_query(PayoutFSM.waiting_network, F.data.startswith('payout_network:'))
async def payout_network(cb: CallbackQuery, state: FSMContext) -> None:
    network = cb.data.split(':')[1]
    await state.update_data(network=network)
    await state.set_state(PayoutFSM.waiting_address)
    await cb.message.answer('Send destination address:')
    await _safe_cb_answer(cb)


@router.message(PayoutFSM.waiting_address)
async def payout_address(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    amount = Decimal(data['amount'])
    network = data['network']
    address = message.text.strip()
    with SessionLocal() as db:
        user = get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
        if Decimal(user.balance_available) < amount:
            await message.answer('Balance changed, insufficient funds.')
            await state.clear()
            return
        payout = create_payout_request(db, user, amount, network, address)
    await state.clear()
    await message.answer(f'Payout request #{payout.id} submitted.')
