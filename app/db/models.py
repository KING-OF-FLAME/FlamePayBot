from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ORDER_STATUSES = ('0', '1', '2', '3', '4', '5', '6')
PAYOUT_NETWORKS = ('TRC20', 'BEP20')
PAYOUT_STATUSES = ('pending', 'approved', 'rejected')
LEDGER_TYPES = ('deposit_credit', 'payout_hold', 'payout_approve', 'payout_reject_return')


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    balance_available: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    balance_hold: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AccessCode(Base):
    __tablename__ = 'access_codes'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GatewayConfig(Base):
    __tablename__ = 'gateway_configs'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    way_code: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GatewayPackage(Base):
    __tablename__ = 'gateway_packages'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gateway_id: Mapped[int] = mapped_column(ForeignKey('gateway_configs.id', ondelete='CASCADE'))
    label: Mapped[str] = mapped_column(String(100))
    amount_cents: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    gateway = relationship('GatewayConfig')


class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (UniqueConstraint('mch_order_no', name='uq_orders_mch_order_no'),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    mch_no: Mapped[str] = mapped_column(String(32), index=True)
    mch_order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    pay_order_no: Mapped[str | None] = mapped_column(String(64), index=True)
    way_code: Mapped[str] = mapped_column(String(50))
    package_label: Mapped[str] = mapped_column(String(100))
    amount_cents: Mapped[int] = mapped_column(Integer)
    fee_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    final_amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default='USD')
    status: Mapped[str] = mapped_column(Enum(*ORDER_STATUSES), default='0')
    cashier_url: Mapped[str | None] = mapped_column(Text)
    provider_raw_create: Mapped[str | None] = mapped_column(Text)
    provider_raw_notify: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship('User')


class BalanceLedger(Base):
    __tablename__ = 'balance_ledger'
    __table_args__ = (Index('idx_ledger_user_time', 'user_id', 'created_at'),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    entry_type: Mapped[str] = mapped_column(Enum(*LEDGER_TYPES))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    ref_order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'))
    ref_payout_id: Mapped[int | None] = mapped_column(ForeignKey('payout_requests.id'))
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PayoutRequest(Base):
    __tablename__ = 'payout_requests'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    network: Mapped[str] = mapped_column(Enum(*PAYOUT_NETWORKS))
    address: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(Enum(*PAYOUT_STATUSES), default='pending')
    admin_note: Mapped[str | None] = mapped_column(String(255))
    txid: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_tg_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    detail_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CallbackEvent(Base):
    __tablename__ = 'callback_events'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(128), unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
