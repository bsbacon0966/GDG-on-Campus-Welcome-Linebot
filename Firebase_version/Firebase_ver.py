# 「Google學生開發者社群 - 臺北大學」
import os
import threading
import hashlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FollowEvent, FlexSendMessage
)
from linebot.exceptions import InvalidSignatureError
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# 全域流水號 & 鎖
global_counter = 0
counter_lock = threading.Lock()

# 載入 .env
load_dotenv()

app = Flask(__name__)

# --- LINE BOT 設定 ---
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_TOKEN_STUDENT')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET_STUDENT')

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    print("請確認 .env 設定了 CHANNEL_TOKEN 和 CHANNEL_SECRET")
    exit(1)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# --- Firebase 初始化 ---
cred = credentials.Certificate('serviceAccount.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- Helper Functions ---
def encrypt_userid(user_id):
    return hashlib.sha256(user_id.encode()).hexdigest()

def generate_unique_code(user_id_hash):
    global global_counter
    prefix = user_id_hash[:3].upper()
    with counter_lock:
        serial_number = global_counter % 10000
        global_counter += 1
    return f"{prefix}{serial_number:04d}"

# --- 資料 ---
QUESTIONS = {
    1: "請問我們的社團名稱是？\nA. GDG on Campus NTPU\nB. GDSC NTPU\nC. GDG\nD. GDE",
    2: "請問 GDG on Campus NTPU 是否會參加 9/24 的社團聯展？",
    3: "加入 GDG on Campus NTPU 一年後，你最可能成為什麼樣的人？\nA. 了解近年新穎科技趨勢的人\nB. 擁有亮眼專案開發經歷的人\nC. 擅長與夥伴們高效合作的人\nD. 以上皆是",
    4: "請問我們去年的活動主題不包含？\nA. UI/UX\nB. PM（專案經理）演講\nC. 數據分析\nD. 以上都辦過",
    5: "我們是北大最厲害的學術型社團嗎？"
}

DETAIL_DESCRIBE = {
    1: "B. 是我們的舊名，C. 跟 D. 則是 Google 官方其他面向社會人士的計畫，為了替各位提供產業前沿見解、分享職涯經驗，本社也會盡可能增加和他們交流互動的機會哦！",
    2: "我們將參與今年的聯展，當天將會有XXX與XXX環節，有興趣的朋朋不要錯過～",
    3: "除了社課，我們也有幹部與社員一同參與開發與討論的「專案制度」。\n每位社員都能發揮自己的專長領域與創意，彼此互相學習、互相支持，社團才得以茁壯💪！",
    4: "我們的社團課程與活動，除了上述領域之外，今年也會新增 AI、生產力工具主題，以及基礎程式教學，不僅生活實用性高，也十分適合想要跨領域的各位加入。",
    5: "不用懷疑，我們就是最厲害的學術性社團，我們已經連續兩年拿到北大社團評鑑的學術性特優了🏆！"
}

CORRECT_ANSWERS = {1:"A", 2:"O", 3:"D", 4:"D", 5:"O"}

QUESTION_TYPE = {1: "choice", 2: "bool", 3: "choice", 4: "choice", 5: "bool"}
ANSWER_OPTIONS = {
    1: ["A", "B", "C", "D"],
    2: ["O", "X"],
    3: ["A", "B", "C", "D"],
    4: ["A", "B", "C", "D"],
    5: ["O", "X"]
}

IMAGE_URLS = {
    1: "https://drive.google.com/uc?export=view&id=1ZB5JuJQVE4RQURNftU9tJ3QMRxEpbshC",
    2: "https://drive.google.com/uc?export=view&id=1kGnqsYLJd3ZuNwwNJkps8o6rdaj2i06k",
    3: "https://drive.google.com/uc?export=view&id=1VbIgbcDWzWfW9ZqAZYLtoGWUe2Rte-dz",
    4: "https://drive.google.com/uc?export=view&id=1FapjSmiyKKgA4vzpA27WG2uzs-3X1r4I",
    5: "https://drive.google.com/uc?export=view&id=1QHQKI0lQYSKf2l1viUIklj6QgyFbDYSC"
}

# 專屬題目的Message程式碼 
def build_question_message(current):
    question_text = QUESTIONS[current]
    image_url = IMAGE_URLS.get(current)
    options = ANSWER_OPTIONS[current]

    button_colors = ["#E94436", "#109D58", "#4385F3", "#FABC05"] if QUESTION_TYPE[current] == "choice" else ["#109D58", "#E94436"]

    # 產生按鈕
    def build_button(option, color):
        return {
            "type": "button",
            "style": "primary",
            "color": color,
            "action": {"type": "message", "label": option, "text": option}
        }

    if QUESTION_TYPE[current] == "choice": # 選擇題
        buttons_rows = [
            {"type": "box", "layout": "horizontal", "spacing": "sm",
             "contents": [build_button(options[i], button_colors[i]) for i in range(row*2, row*2+2)]}
            for row in range(2)
        ]
    else: # 是非題
        buttons_rows = [{"type": "box", "layout": "horizontal", "spacing": "sm",
                         "contents": [build_button(opt, button_colors[idx]) for idx, opt in enumerate(options)]}]

    return FlexSendMessage(
        alt_text=f"第 {current} 題: {question_text}",
        contents={
            "type": "bubble",
            "hero": {"type": "image", "url": image_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": f"第 {current} 題", "weight": "bold", "size": "lg"},
                {"type": "text", "text": question_text, "wrap": True}
            ]},
            "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": buttons_rows}
        }
    )
# 使用者填完題目後的獎勵Message
def build_award_code_flex(unique_code):
    return FlexSendMessage(
        alt_text="恭喜完成所有題目！您的專屬獎獎代碼",
        contents={
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "md", "contents": [
                    {"type": "text", "text": "🎉 恭喜完成所有題目！ 🎉", "weight": "bold", "size": "xl", "align": "center", "color": "#34A853"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": "您的專屬獎獎代碼", "weight": "bold", "size": "md", "align": "center", "color": "#555555", "margin": "md"},
                    {"type": "text", "text": unique_code, "weight": "bold", "size": "xxl", "color": "#EA4335", "align": "center", "margin": "md"},
                    {"type": "text", "text": "9/30 活動現場將憑此參加抽獎", "size": "sm", "color": "#888888", "align": "center", "wrap": True, "margin": "md"}
                ]
            }
        }
    )

# 一個簡單的回覆 Message (用於開頭類似加油打氣的設計)
def reply_flex(token, alt, title, desc, btn_label, btn_text, color="#4385F3"):
    flex_content = {
        "type": "bubble",
        "body": {
            "type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "lg"},
                {"type": "text", "text": desc, "wrap": True, "margin": "md"},
                {"type": "button", "style": "primary", "color": color,
                 "action": {"type": "message", "label": btn_label, "text": btn_text}, "margin": "md"}
            ]
        }
    }
    line_bot_api.reply_message(token, FlexSendMessage(alt_text=alt, contents=flex_content))

# Webhook Route
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    app.logger.info(f"Webhook body: {body}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        app.logger.error(f"Webhook 處理錯誤: {e}", exc_info=True)
        return 'ERROR', 200
    return 'OK'

# FollowEvent : 當使用者加入我們的Bot好友時跳出的Event
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    user_id_hash = encrypt_userid(user_id)
    doc_ref = db.collection('users').document(user_id_hash)
    if not doc_ref.get().exists:
        doc_ref.set({"current_state":1, "finish":False})

    reply_flex(event.reply_token, "歡迎加入 GDG on Campus", "歡迎加入互動帳號！",
               "我們是由 Google 官方支持成立、立足北大的開發者社群",
               "想知道我們的日常", "那我們都在幹什麼")

# MessageEvent : 面對使用者回應所設計的判斷，邏輯上跟著Message的按鈕走就可以觸發到當前所有判斷
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_id_hash = encrypt_userid(user_id)
    doc_ref = db.collection('users').document(user_id_hash)
    data = doc_ref.get().to_dict() or {}
    current = data.get("current_state", 1)
    is_finished = data.get("finish", False)

    text = event.message.text.strip()

    if text == "那我們都在幹什麼":
        reply_flex(event.reply_token, "GDG on Campus 的我們", "GDG on Campus NTPU的我們",
                   "會定期舉辦各式技術教學課程、交流活動、豐富的講座與工作坊，甚至是企業參訪！\n不僅提升你的開發能力，也能增廣見聞、結交志同道合的夥伴！",
                   "原來如此！", "我想加入！", color="#34A853")
        return

    if text == "我想加入！":
        reply_flex(event.reply_token, "參加問答活動有驚喜！", "參加問答活動有驚喜！",
                   "現在參加本帳號的互動問答，且皆回答正確，就能獲得專屬碼！\n我們將在 9/30（二）時間:時間 - 時間:時間 的「2025 招生說明會」上，即可憑此碼參與抽獎哦🎁～",
                   "馬上開始！", "準備好了！", color="#FBBC05")
        return

    if text == "準備好了！":
        if not is_finished:
            line_bot_api.reply_message(event.reply_token, build_question_message(current))
        else:
            unique_code = data.get("unique_code")
            line_bot_api.reply_message(event.reply_token, [
                build_award_code_flex(unique_code),
                TextSendMessage(text="【Google 學生開發者社群】9/30 招生說明會抽獎 ✨，現在就火速報名吧！")
            ])
        return

    # 答題流程
    ans = text.upper()
    correct = CORRECT_ANSWERS[current]

    if ans == correct:
        describe_text = DETAIL_DESCRIBE[current]
        current += 1
        doc_ref.update({"current_state": current})
        if current > len(QUESTIONS):
            unique_code = generate_unique_code(user_id_hash)
            line_bot_api.reply_message(event.reply_token, [
                TextSendMessage(text="正確答案～這五題都答對了！！"),
                TextSendMessage(text=describe_text),
                build_award_code_flex(unique_code),
                TextSendMessage(text="【Google 學生開發者社群】9/30 招生說明會抽獎 ✨，現在就火速報名吧！"),
            ])
            doc_ref.update({"finish": True, "unique_code": unique_code})
            db.collection('check_list').document(unique_code).set({"is_here": False})
        else:
            line_bot_api.reply_message(event.reply_token, [
                TextSendMessage(text="正確答案～"),
                TextSendMessage(text=describe_text),
                TextSendMessage(text="那就再來一題！"),
                build_question_message(current)
            ])
    else:
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text="答錯了，再接再厲～"),
            TextSendMessage(text=DETAIL_DESCRIBE[current]),
            TextSendMessage(text="再試一次！"),
            build_question_message(current)
        ])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
