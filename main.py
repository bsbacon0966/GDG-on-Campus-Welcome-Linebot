import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, MessageAction,
    FollowEvent, FlexSendMessage
)
from linebot.exceptions import InvalidSignatureError
import firebase_admin
from firebase_admin import credentials, firestore
import hashlib
from dotenv import load_dotenv
import threading

# 全域流水號 & 鎖
global_counter = 0
counter_lock = threading.Lock()

# 載入 .env
load_dotenv()

app = Flask(__name__)

# --- LINE BOT 設定 ---
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_TOKEN_B')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET_B')

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    print("請確認 .env 設定了 CHANNEL_TOKEN 和 CHANNEL_SECRET")
    exit(1)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# --- Firebase 初始化 ---
cred = credentials.Certificate('serviceAccount.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- 加密 userID ---
def encrypt_userid(user_id):
    return hashlib.sha256(user_id.encode()).hexdigest()

# --- 生成獨特代碼 (XXX + YYYY格式) ---
def generate_unique_code(user_id_hash):
    global global_counter
    prefix = user_id_hash[:3].upper()
    with counter_lock:
        serial_number = global_counter % 10000
        global_counter += 1
    return f"{prefix}{serial_number:04d}"

# --- 題目與答案 ---
QUESTIONS = {
    1: "社團名稱是？\n(A)GDG on Campus NTPU\n(B)GDSC NTPU\n(C)GDG\n(D)GDE",
    2: "社團名稱是？\n(A)GDG on Campus NTPU\n(B)GDSC NTPU\n(C)GDG\n(D)GDE",
    3: "社團名稱是？\n(A)GDG on Campus NTPU\n(B)GDSC NTPU\n(C)GDG\n(D)GDE",
    4: "社團名稱是？\n(A)GDG on Campus NTPU\n(B)GDSC NTPU\n(C)GDG\n(D)GDE",
    5: "社團名稱是？\n(A)GDG on Campus NTPU\n(B)GDSC NTPU\n(C)GDG\n(D)GDE"
}

DETAIL_DESCRIBE = {
    1: "我們是Google社群中，一群熱愛開發、研究科技的學生組織，在校園內建立的Google Developer Group喔，所以很歡迎任何人參與，沒有任何限制!",
    2: "我們是Google社群中，一群熱愛開發、研究科技的學生組織，在校園內建立的Google Developer Group喔，所以很歡迎任何人參與，沒有任何限制!",
    3: "我們是Google社群中，一群熱愛開發、研究科技的學生組織，在校園內建立的Google Developer Group喔，所以很歡迎任何人參與，沒有任何限制!",
    4: "我們是Google社群中，一群熱愛開發、研究科技的學生組織，在校園內建立的Google Developer Group喔，所以很歡迎任何人參與，沒有任何限制!",
    5: "我們是Google社群中，一群熱愛開發、研究科技的學生組織，在校園內建立的Google Developer Group喔，所以很歡迎任何人參與，沒有任何限制!"
}

CORRECT_ANSWERS = {1:"A", 2:"A", 3:"A", 4:"A", 5:"A"}
ANSWER_OPTIONS = ["A","B","C","D"]

# --- 每題對應的圖片網址 ---
IMAGE_URLS = {
    1: "https://drive.google.com/uc?export=view&id=19ORm5uKzHp59_Fg_CNDwazKZfr718wGa",
    2: "https://drive.google.com/uc?export=view&id=18QUSCuFyFiNpxLdq4QpXke8CYhxjTG19",
    3: "https://drive.google.com/uc?export=view&id=1maZH35tbSQVnttIHwTZva3by8ovNMV1C",
    4: "https://drive.google.com/uc?export=view&id=1jQSZ8j721VH8TWy0TU92RhpKzJslz1Sv",
    5: "https://drive.google.com/uc?export=view&id=1jQSZ8j721VH8TWy0TU92RhpKzJslz1Sv"
}

# --- 建立 Flex Message 題目 ---
def build_question_message(current):
    question_text = QUESTIONS[current]
    image_url = IMAGE_URLS.get(current)

    # 按鈕顏色
    button_colors = ["#E94436", "#109D58","#4385F3", "#FABC05"]

    # 分成兩行，每行兩個按鈕
    buttons_rows = []
    for row in range(2):
        row_buttons = []
        for col in range(2):
            idx = row*2 + col
            option = ANSWER_OPTIONS[idx]
            row_buttons.append({
                "type": "button",
                "style": "primary",
                "color": button_colors[idx],
                "action": {
                    "type": "message",
                    "label": option,
                    "text": option
                }
            })
        buttons_rows.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": row_buttons
        })

    flex_message = FlexSendMessage(
        alt_text=f"第 {current} 題: {question_text}",
        contents={
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": image_url,
                "size": "full",
                "aspectRatio": "20:13",
                "aspectMode": "cover"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"第 {current} 題", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": question_text, "wrap": True}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": buttons_rows
            }
        }
    )
    return flex_message
# --- Helper: 發送題目 ---
def send_question(reply_token, current):
    line_bot_api.reply_message(
        reply_token,
        [build_question_message(current)]
    )

# --- Helper: 答錯重試 ---
def send_retry_question(reply_token, current):
    describe_text = DETAIL_DESCRIBE[current]
    line_bot_api.reply_message(
        reply_token,
        [
            TextSendMessage(text="答錯囉！"),
            TextSendMessage(text=describe_text),
            build_question_message(current)
        ]
    )

# --- Webhook Route ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    app.logger.info(f"Webhook body: {body}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("簽名驗證失敗")
        abort(400)
    except Exception as e:
        app.logger.error(f"Webhook 處理錯誤: {e}", exc_info=True)
        return 'ERROR', 200
    return 'OK'

# --- FollowEvent ---
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    user_id_hash = encrypt_userid(user_id)
    
    doc_ref = db.collection('users').document(user_id_hash)
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.set({"current_state":1, "finish":False})

    # 發送介紹訊息
    line_bot_api.push_message(
        user_id,
        TemplateSendMessage(
            alt_text='社團介紹與開始按鈕',
            template=ButtonsTemplate(
                title='歡迎加入 GDG on Campus',
                text='我們是校園 GDG 社團，定期舉辦技術交流與活動，讓你學習最新技術、拓展人脈！\n準備好了嗎？',
                actions=[MessageAction(label='準備好了', text='準備好了')]
            )
        )
    )
    app.logger.info(f"FollowEvent 觸發: {user_id}")

# --- MessageEvent ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_id_hash = encrypt_userid(user_id)
    doc_ref = db.collection('users').document(user_id_hash)
    doc = doc_ref.get()
    data = doc.to_dict()
    current = data.get("current_state", 1)
    is_finished = data.get("finish", False)

    if event.message.text == "準備好了":
        if not is_finished:
            send_question(event.reply_token, current)
        else:
            unique_code = data.get("unique_code")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"恭喜完成所有題目！\n您的獎獎代碼是: {unique_code}\n請截圖保存此代碼！")
            )
        return

    ans = event.message.text.upper().strip()
    correct = CORRECT_ANSWERS[current]

    if ans == correct:
        current += 1
        doc_ref.update({"current_state": current})
        if current > len(QUESTIONS):
            unique_code = generate_unique_code(user_id_hash)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"恭喜完成所有題目！\n您的獎獎代碼是: {unique_code}\n請截圖保存此代碼！")
            )
            doc_ref.update({"finish":True, "unique_code":unique_code})
            check_list_ref = db.collection('check_list').document(unique_code)
            check_list_ref.set({"userID":user_id, "is_here":False})
        else:
            send_question(event.reply_token, current)
    else:
        send_retry_question(event.reply_token, current)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
