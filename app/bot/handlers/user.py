from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
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
    get_gateway_packages,
    get_enabled_gateways,
    get_or_create_user,
    recent_orders,
)

router = Router()
settings = get_settings()
provider = ProviderClient()


class PayoutFSM(StatesGroup):
    waiting_amount = State()
    waiting_network = State()
    waiting_address = State()


@router.message(Command('start'))
async def start(message: Message) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
    txt = 'Welcome. Use /activate <code> first.' if not user.is_active else 'Welcome back.'
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
        ok, msg = activate_with_code(db, user, code)
    await message.answer(msg)


def _check_access(user: User) -> str | None:
    if user.is_banned:
        return 'You are banned.'
    if not user.is_active:
        return 'Activate first with /activate <code>.'
    return None


@router.message(Command('pay'))
async def pay(message: Message) -> None:
    await send_gateways(message)


@router.callback_query(F.data == 'menu:pay')
async def menu_pay(cb: CallbackQuery) -> None:
    await send_gateways(cb.message)
    await cb.answer()


async def send_gateways(message: Message) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, message.chat.id, message.chat.username, message.chat.full_name)
        denied = _check_access(user)
        if denied:
            await message.answer(denied)
            return
        gateways = get_enabled_gateways(db)
    if not gateways:
        await message.answer('No gateways enabled.')
        return
    buttons = [[{'text': g.title, 'callback_data': f'gw:{g.id}'}] for g in gateways]
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for row in buttons:
        kb.row(*[__import__('aiogram').types.InlineKeyboardButton(**b) for b in row])
    await message.answer('Select gateway:', reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith('gw:'))
async def select_gateway(cb: CallbackQuery) -> None:
    gateway_id = int(cb.data.split(':')[1])
    with SessionLocal() as db:
        packs = get_gateway_packages(db, gateway_id)
    if not packs:
        await cb.message.answer('No packages configured for this gateway.')
        await cb.answer()
        return
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for p in packs:
        kb.row(__import__('aiogram').types.InlineKeyboardButton(text=f'{p.label} (${p.amount_cents/100:.2f})', callback_data=f'pkg:{p.id}'))
    await cb.message.answer('Select package:', reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith('pkg:'))
async def select_package(cb: CallbackQuery) -> None:
    package_id = int(cb.data.split(':')[1])
    with SessionLocal() as db:
        user = get_or_create_user(db, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        denied = _check_access(user)
        if denied:
            await cb.message.answer(denied)
            await cb.answer()
            return
        pack = db.get(GatewayPackage, package_id)
        gateway = db.get(GatewayConfig, pack.gateway_id)
        final_amount = int(round(pack.amount_cents * (1 + settings.global_fee_percent / 100)))
        order = create_order(db, user, gateway.way_code, pack.label, pack.amount_cents, Decimal(str(settings.global_fee_percent)), final_amount)
        resp = provider.create(order.mch_order_no, final_amount, gateway.way_code, f'{gateway.title}/{pack.label}')
        data = resp.get('data', {}) if isinstance(resp, dict) else {}
        order.status = str(data.get('state', '0'))
        order.pay_order_no = data.get('payOrderNo')
        order.cashier_url = data.get('cashierUrl')
        import json

        order.provider_raw_create = json.dumps(resp, ensure_ascii=False)
        db.commit()
    cashier = data.get('cashierUrl', 'N/A')
    await cb.message.answer(f'Order: `{order.mch_order_no}`\nPay URL: {cashier}', parse_mode='Markdown')
    await cb.answer('Order created')


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
    await cb.answer()


@router.callback_query(F.data == 'menu:balance')
async def menu_balance(cb: CallbackQuery) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await cb.message.answer(f'Available: ${user.balance_available}\nHold: ${user.balance_hold}')
    await cb.answer()


@router.message(Command('payoutrequest'))
async def payout_request_cmd(message: Message, state: FSMContext) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
        denied = _check_access(user)
        if denied:
            await message.answer(denied)
            return
    await state.set_state(PayoutFSM.waiting_amount)
    await message.answer('Enter payout amount (e.g., 25.50):')


@router.callback_query(F.data == 'menu:payout')
async def menu_payout(cb: CallbackQuery, state: FSMContext) -> None:
    await payout_request_cmd(cb.message, state)
    await cb.answer()


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
    await cb.answer()


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
