"""
LINE Stock Bot
User sends a Taiwan stock code → returns 20-day institutional buy/sell
and margin trading balance.
"""

import os
import re

from dotenv import load_dotenv
from flask import Flask, abort, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from stock_data import (
    format_combined,
    get_institutional,
    get_margin,
)

load_dotenv()

app = Flask(__name__)

_cfg = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
_handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

_HELP = (
    "📌 股票查詢機器人\n\n"
    "輸入台灣股票代號（4~6 碼），即可查詢近 20 日：\n"
    "・三大法人買賣超（外資／投信／自營）\n"
    "・融資融券餘額\n\n"
    "範例：\n"
    "  2330   → 台積電\n"
    "  2317   → 鴻海\n"
    "  0050   → 元大台灣50\n\n"
    "輸入「help」可再次顯示此說明。"
)

_STOCK_RE = re.compile(r"^\d{4,6}$")


# ──────────────────────────────────────────────
# Webhook endpoint
# ──────────────────────────────────────────────

@app.route("/callback", methods=["POST"])
def callback():
    sig = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        _handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return "OK"


# ──────────────────────────────────────────────
# Message handler
# ──────────────────────────────────────────────

@_handler.add(MessageEvent, message=TextMessageContent)
def on_message(event: MessageEvent):
    text = event.message.text.strip()

    if text.lower() in ("help", "/help", "說明", "使用說明"):
        messages = [TextMessage(text=_HELP)]
    elif _STOCK_RE.match(text):
        messages = _query_stock(text)
    else:
        messages = [TextMessage(text=_HELP)]

    with ApiClient(_cfg) as client:
        MessagingApi(client).reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=messages)
        )


def _query_stock(stock_id: str) -> list[TextMessage]:
    try:
        inst_rows = get_institutional(stock_id)
        margin_rows = get_margin(stock_id)
    except Exception as exc:
        return [TextMessage(text=f"查詢失敗，請稍後再試。\n錯誤：{exc}")]

    msg = format_combined(stock_id, inst_rows, margin_rows)
    return [TextMessage(text=msg)]


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
