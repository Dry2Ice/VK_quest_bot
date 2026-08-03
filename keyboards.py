from vkbottle import Keyboard, KeyboardButtonColor, Text


def continue_keyboard():
    kb = Keyboard(inline=True)
    kb.add(Text("Продолжить", payload={"cmd": "continue"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def check_sub_keyboard():
    kb = Keyboard(inline=True)
    kb.add(Text("Проверить подписку", payload={"cmd": "check_sub"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def check_qr2_keyboard():
    kb = Keyboard(inline=True)
    kb.add(Text("Я отсканировал QR", payload={"cmd": "check_qr2"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def check_qr3_keyboard():
    kb = Keyboard(inline=True)
    kb.add(Text("Я отсканировал QR", payload={"cmd": "check_qr3"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()
