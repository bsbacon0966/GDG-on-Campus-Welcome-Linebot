import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# 載入 .env
load_dotenv()

app = Flask(__name__)

# --- LINE Bot A 設定 ---
CHANNEL_ACCESS_TOKEN_A = os.getenv("CHANNEL_TOKEN_A")
CHANNEL_SECRET_A = os.getenv("CHANNEL_SECRET_A")
line_bot_api_A = LineBotApi(CHANNEL_ACCESS_TOKEN_A)
handler_A = WebhookHandler(CHANNEL_SECRET_A)

# --- LINE Bot B 設定（用來推訊息給使用者）---
CHANNEL_ACCESS_TOKEN_B = os.getenv("CHANNEL_TOKEN_B")
line_bot_api_B = LineBotApi(CHANNEL_ACCESS_TOKEN_B)

# --- Firebase 初始化 ---
cred = credentials.Certificate("serviceAccount.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- Webhook Route ---
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    app.logger.info(f"Webhook body: {body}")

    try:
        handler_A.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        app.logger.error(f"Webhook error: {e}", exc_info=True)
        return "ERROR", 200

    return "OK"

# --- 處理文字訊息 ---
@handler_A.add(MessageEvent, message=TextMessage)
def handle_message(event):
    code = event.message.text.strip()
    check_ref = db.collection("check_list").document(code)

    doc = check_ref.get()
    if doc.exists:
        data = doc.to_dict()
        user_id = data.get("userID")
        try:
            # 更新 is_here
            check_ref.update({"is_here": True})

            # 用 Bot B 推訊息給使用者
            line_bot_api_B.push_message(user_id, TextSendMessage(text="恭喜你登入成功"))

            # 回覆 Bot A
            line_bot_api_A.reply_message(event.reply_token, TextSendMessage(text="已經傳送資訊"))
        except Exception as e:
            app.logger.error(f"更新或推送失敗: {e}")
            line_bot_api_A.reply_message(event.reply_token, TextSendMessage(text="傳送資料失敗"))
    else:
        # 沒找到文件
        line_bot_api_A.reply_message(event.reply_token, TextSendMessage(text="傳送資料失敗"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
