"""Keep secrets out of logs.

httpx logs every request URL at INFO level ("HTTP Request: POST https://api.telegram.org/bot<TOKEN>/..."),
and Telegram's API puts the bot token in the URL. Raising these loggers to WARNING keeps the token (and any
API key in a URL) out of Render's logs, whatever LOG_LEVEL is set to.
"""
import logging

NOISY = ("httpx", "httpcore")


def quiet_http_loggers() -> None:
    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
