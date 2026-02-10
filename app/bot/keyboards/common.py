from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Recharge', callback_data='menu:pay')],
            [InlineKeyboardButton(text='My Orders', callback_data='menu:orders')],
            [InlineKeyboardButton(text='Payout Request', callback_data='menu:payout')],
            [InlineKeyboardButton(text='Balance', callback_data='menu:balance')],
        ]
    )


def payout_networks() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='USDT TRC20', callback_data='payout_network:TRC20')],
            [InlineKeyboardButton(text='USDT BEP20', callback_data='payout_network:BEP20')],
        ]
    )
