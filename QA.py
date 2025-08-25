import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
)
import openai
from google.cloud import firestore

# --- Flask App ---
app = Flask(__name__)

# --- LINE BOT 設定 ---
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_TOKEN_STUDENT")   # 主 bot token
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET_STUDENT")               # 主 bot secret
FORWARD_CHANNEL_TOKEN = os.getenv("CHANNEL_TOKEN_A") # 另一個 bot token
FORWARD_USER_ID = os.getenv("FORWARD_USER_ID")             # 接收轉發的 user ID

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# --- Firestore 初始化 ---
db = firestore.Client()

# --- OpenAI 設定 ---
openai.api_key = os.getenv("OPENAI_API_KEY")

# --- 建立 O/X Flex Message ---
def build_feedback_message():
    return FlexSendMessage(
        alt_text="是否有回答到你的問題？",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "是否有回答到你的問題？",
                        "weight": "bold",
                        "size": "lg",
                        "wrap": True
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "sm",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#109D58",
                                "action": {
                                    "type": "message",
                                    "label": "O",
                                    "text": "O"
                                }
                            },
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#E94436",
                                "action": {
                                    "type": "message",
                                    "label": "X",
                                    "text": "X"
                                }
                            }
                        ]
                    }
                ]
            }
        }
    )

# --- AI 回答 ---
def get_ai_answer(question: str) -> str:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是個知識豐富的助理"},
                {"role": "user", "content": question}
            ]
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"AI 回答失敗：{e}"

# --- Firebase 操作（簡化版）---
def update_user_state(user_id, data: dict):
    try:
        db.collection("linebot_users").document(user_id).set(data, merge=True)
    except Exception as e:
        print(f"Firestore 更新錯誤: {e}")

def get_user_state(user_id):
    try:
        doc = db.collection("linebot_users").document(user_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        print(f"Firestore 讀取錯誤: {e}")
        return None

# --- Webhook Route ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- Message Event ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id

    # Step 1: 使用者說 "/我想詢問"
    if user_message == "/我想詢問":
        update_user_state(user_id, {"status": "waiting_question"})
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="好的，請輸入你的問題，我會幫你找答案。")
        )
        return

    # Step 2: 使用者輸入問題 → AI 回答 + O/X
    user_in_QA = get_user_state(user_id)
    if user_in_QA and user_in_QA.get("status") == "waiting_question" and user_message not in ["O", "X"]:
        ai_answer = get_ai_answer(user_message)
        update_user_state(user_id, {
            "latest_question": user_message,
            "latest_answer": ai_answer,
            "status": "answered"
        })
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text=ai_answer),
                build_feedback_message()
            ]
        )
        return

    # Step 3: 使用者按 O / X
    if user_in_QA and user_in_QA.get("status") == "answered":
        if user_message == "O":
            update_user_state(user_id, {"feedback": "O"})
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="太好了！很高興能幫助到你 😊")
            )
            
        elif user_message == "X":
            update_user_state(user_id, {"feedback": "X"})
            state = get_user_state(user_id)
            if state:
                last_q = state.get("latest_question", "（未知問題）")
                # 把問題轉發到另一個 bot
                if FORWARD_CHANNEL_TOKEN and FORWARD_USER_ID:
                    try:
                        forward_bot = LineBotApi(FORWARD_CHANNEL_TOKEN)
                        forward_bot.push_message(
                            FORWARD_USER_ID,
                            TextSendMessage(text=f"使用者有未解決的問題：\n{last_q}")
                        )
                    except Exception as e:
                        print(f"轉發失敗: {e}")
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="已將你的問題轉交給專人處理 🙏")
            )

# --- 主程式 ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))