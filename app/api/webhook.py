import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.db.models import Order
from app.db.session import SessionLocal
from app.services.repositories import credit_order_success, register_callback_event, update_order_status
from app.services.signing import verify_sign
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
app = FastAPI(title='FlamePayBot Webhook')


@app.get('/health')
async def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/notify')
async def notify(request: Request) -> JSONResponse:
    payload: dict[str, Any] = await request.json()
    if not verify_sign(payload, settings.provider_key, payload.get('signType', settings.provider_sign_type)):
        logger.warning('Invalid callback signature')
        return JSONResponse({'code': -1, 'msg': 'invalid sign'}, status_code=400)

    mch_order_no = payload.get('mchOrderNo')
    pay_order_no = payload.get('payOrderNo')
    state = str(payload.get('state', ''))
    event_key = f"{mch_order_no}:{pay_order_no}:{state}"

    with SessionLocal() as db:
        if not register_callback_event(db, event_key, payload):
            return JSONResponse({'code': 0, 'msg': 'duplicate ignored'})

        order = db.scalar(select(Order).where(Order.mch_order_no == mch_order_no))
        if not order:
            logger.warning('Order not found for callback %s', mch_order_no)
            return JSONResponse({'code': 0, 'msg': 'ok'})

        if state in {'0', '1', '2', '3', '4', '5', '6'}:
            update_order_status(db, order, state, pay_order_no=pay_order_no, provider_payload=payload)
            if state == '2':
                credit_order_success(db, order)

    return JSONResponse({'code': 0, 'msg': 'success'})
