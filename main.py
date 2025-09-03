# 「Google學生開發者社群 - 臺北大學」
import os
import threading
import hashlib
import time

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FollowEvent, FlexSendMessage
)
from linebot.exceptions import InvalidSignatureError
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure
from dotenv import load_dotenv
from pymongo.server_api import ServerApi

# 全域流水號 & 鎖
global_counter = 0
counter_lock = threading.Lock()

# 載入 .env
load_dotenv()

app = Flask(__name__)

# LINE BOT 設定
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_TOKEN_STUDENT')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET_STUDENT')


# CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_TOKEN_TEST')
# CHANNEL_SECRET = os.getenv('CHANNEL_SECRET_TEST')


CHANNEL_ACCESS_TOKEN_ADMIN = os.getenv('CHANNEL_ACCESS_TOKEN_ADMIN')
ADMIN_ID = os.getenv('ADMIN_ID')
if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    print("請確認 .env 設定了 CHANNEL_TOKEN 和 CHANNEL_SECRET")
    exit(1)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
line_bot_api_admin = LineBotApi(CHANNEL_ACCESS_TOKEN_ADMIN)
handler = WebhookHandler(CHANNEL_SECRET)


# MongoDB 初始化 ################################################################################
DB_USER = os.getenv("MONGODB_USER")  # 從環境變數讀取
DB_PASS = os.getenv("MONGODB_PASSWORD")  # 從環境變數讀取
DB_NAME = os.getenv("MONGODB_DBNAME")

# 生產環境級 MongoDB 連接字串
uri = f"mongodb+srv://{DB_USER}:{DB_PASS}@welcome.j3ma8ab.mongodb.net/{DB_NAME}?retryWrites=true&w=majority&tls=true"

# 生產環境級 MongoDB 客戶端配置
def create_mongodb_client():
    """創建具有重試機制的 MongoDB 客戶端"""
    max_retries = 3
    base_delay = 1
    
    for attempt in range(max_retries):
        try:
            client = MongoClient(
                uri,
                server_api=ServerApi('1'),
                # SSL/TLS 配置
                tls=True,
                tlsAllowInvalidHostnames=True,
                tlsAllowInvalidCertificates=True,
                # 連接池配置
                maxPoolSize=40,
                minPoolSize=5,
                # 超時配置
                serverSelectionTimeoutMS=10000,  
                connectTimeoutMS=10000,          
                socketTimeoutMS=20000,           
                # 重試配置
                retryWrites=True,
                retryReads=True,
                # 心跳配置
                heartbeatFrequencyMS=10000,
                # 其他配置
                maxIdleTimeMS=50000,
                waitQueueTimeoutMS=10000
            )
            
            # 測試連接
            client.admin.command('ping')
            print(f"MongoDB 連接成功 (嘗試 {attempt + 1})")
            return client
            
        except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as e:
            print(f"MongoDB 連接嘗試 {attempt + 1} 失敗: {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # 指數退避
                print(f"等待 {delay} 秒後重試...")
                time.sleep(delay)
            else:
                print("所有連接嘗試都失敗，使用備用策略")
                raise e

# 創建 MongoDB client
try:
    client = create_mongodb_client()
    print("成功連接到 MongoDB Atlas!")
except Exception as e:
    print(f"MongoDB 連線失敗: {e}")
    print("應用程式將繼續運行，但資料庫操作可能會失敗")
    client = None

# 建立集合（如果客戶端存在）
db = None
users_collection = None
counters_collection = None 

if client is not None:
    try:
        db = client[DB_NAME]
        users_collection = db['users']
        counters_collection = db['counters'] 
    except Exception as e:
        print(f"建立資料庫集合失敗: {e}")

# 資料庫操作裝飾器，用於處理連接失敗
def db_operation_retry(max_retries=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            global client, db, users_collection
            
            for attempt in range(max_retries):
                try:
                    if client is None:
                        client = create_mongodb_client()
                        db = client[DB_NAME]
                        users_collection = db['users']
                    
                    return func(*args, **kwargs)
                    
                except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as e:
                    print(f"資料庫操作失敗 (嘗試 {attempt + 1}): {e}")
                    client = None
                    db = None
                    users_collection = None
                    
                    if attempt < max_retries - 1:
                        time.sleep(1 * (2 ** attempt))
                    else:
                        print("資料庫操作最終失敗，返回默認值")
                        return None
                        
        return wrapper
    return decorator

# MongoDB 初始化 ################################################################################



# 打亂使用者 ID，以避免創造者竊取使用者ID
def encrypt_userid(user_id):
    # return user_id
    return hashlib.sha256(user_id.encode()).hexdigest()

# 改良版的流水號生成函數
@db_operation_retry()
def generate_unique_code_mongodb(user_id_hash):
    if db is None:
        # 如果資料庫連接失敗，回到原來的記憶體方式作為備案
        print("警告: 資料庫連接失敗，使用記憶體備案方式")
        return generate_unique_code_fallback(user_id_hash)
    
    try:
        # 使用 MongoDB 原子操作更新計數器
        result = counters_collection.find_one_and_update(
            {"_id": "global_counter"},
            {"$inc": {"counter": 1}},
            upsert=True,  # 如果不存在就創建
            return_document=True  # 返回更新後的文檔
        )
        
        prefix = user_id_hash[:3].upper()
        serial_number = result['counter'] % 10000
        return f"{prefix}{serial_number:04d}"
        
    except Exception as e:
        print(f"MongoDB 流水號生成失敗: {e}")
        return generate_unique_code_fallback(user_id_hash)

# 備案函數（保留原始邏輯）
def generate_unique_code_fallback(user_id_hash):
    prefix = user_id_hash[:3].upper()
    import time
    timestamp = int(time.time() * 1000) % 10000
    return f"{prefix}{timestamp:04d}"

# 初始化計數器（可選，在應用啟動時執行一次）
@db_operation_retry()
def initialize_counter():
    if counters_collection is None:
        return
    try:
        # 檢查計數器是否已存在
        existing = counters_collection.find_one({"_id": "global_counter"})
        if existing is None:
            # 如果不存在，初始化為 0
            counters_collection.insert_one({
                "_id": "global_counter",
                "counter": 0,
                "created_at": time.time()
            })
            print("全局計數器初始化完成")
    except Exception as e:
        print(f"初始化計數器失敗: {e}")

# 在應用啟動時調用（加在 if __name__ == "__main__": 之前）
if client is not None:
    initialize_counter()

# 安全的資料庫查詢函數
@db_operation_retry()
def find_user(user_id_hash):
    if users_collection is None:
        return None
    return users_collection.find_one({"_id": user_id_hash})

@db_operation_retry()
def insert_user(user_data):
    if users_collection is None:
        return False
    try:
        users_collection.insert_one(user_data)
        return True
    except Exception as e:
        print(f"插入使用者失敗: {e}")
        return False

@db_operation_retry()
def update_user(user_id_hash, update_data):
    if users_collection is None:
        return False
    try:
        users_collection.update_one(
            {"_id": user_id_hash},
            {"$set": update_data}
        )
        return True
    except Exception as e:
        print(f"更新使用者失敗: {e}")
        return False

# 題目資料 
QUESTIONS = {
    1: "請問我們的社團名稱是？\nA. GDG on Campus NTPU\nB. GDSC NTPU\nC. GDG\nD. GDE",
    2: "請問 GDG on Campus NTPU 是否會參加 9/24 的社團聯展？",
    3: "加入 GDG on Campus NTPU 一年後，你最可能成為什麼樣的人？\nA. 了解近年新穎科技趨勢的人\nB. 擁有亮眼專案開發經歷的人\nC. 擅長與夥伴們高效合作的人\nD. 以上皆是",
    4: "請問我們去年的活動主題不包含？\nA. UI/UX\nB. PM（專案經理）演講\nC. 數據分析\nD. 以上都辦過",
    5: "我們是北大最厲害的學術型社團嗎？"
}

DETAIL_DESCRIBE = {
    1: "B. 是我們的舊名，C. 跟 D. 則是 Google 官方其他面向社會人士的計畫，為了替各位提供產業前沿見解、分享職涯經驗，本社也會盡可能增加和他們交流互動的機會哦！",
    2: "我們將參與今年的聯展，當天將會有不少社團介紹環節，有興趣的朋友千萬不要錯過～",
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
                    {"type": "text", "text": "9/30 12:10~13:00 活動現場將憑此參加抽獎", "size": "sm", "color": "#888888", "align": "center", "wrap": True, "margin": "md"}
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

def build_evaluation_message():
    flex_content = {
        "type": "bubble",
        "body": {
            "type": "box", 
            "layout": "vertical", 
            "contents": [
                {
                    "type": "text", 
                    "text": "你認為我回答得如何？", 
                    "weight": "bold", 
                    "size": "md", 
                    "align": "center"
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
                            "action": {"type": "message", "label": "我了解了", "text": "O"},
                            "flex": 1
                        },
                        {
                            "type": "button",
                            "style": "primary", 
                            "color": "#E94436",
                            "action": {"type": "message", "label": "我還是很困惑", "text": "X"},
                            "flex": 1
                        }
                    ]
                }
            ]
        }
    }
    
    return FlexSendMessage(alt_text="請評價回答", contents=flex_content)

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
    
    try:
        # 檢查使用者是否已存在
        existing_user = find_user(user_id_hash)
        if existing_user is None:
            success = insert_user({
                "_id": user_id_hash,
                "current_state": 1,
                "finish": False
            })
            if not success:
                print("警告: 無法將新使用者存入資料庫")

        reply_flex(event.reply_token, "歡迎加入 GDG on Campus", "歡迎加入互動帳號！",
                   "我們是由 Google 官方支持成立、立足北大的開發者社群",
                   "想知道我們的日常", "那我們都在幹什麼")
    except Exception as e:
        print(f"處理 FollowEvent 時發生錯誤: {e}")
        # 仍然發送歡迎訊息，即使資料庫操作失敗
        reply_flex(event.reply_token, "歡迎加入 GDG on Campus", "歡迎加入互動帳號！",
                   "我們是由 Google 官方支持成立、立足北大的開發者社群",
                   "想知道我們的日常", "那我們都在幹什麼")

# MessageEvent : 面對使用者回應所設計的判斷，邏輯上跟著Message的按鈕走就可以觸發到當前所有判斷
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    
    user_id = event.source.user_id
    user_id_hash = encrypt_userid(user_id)
    user_text = event.message.text.strip()
    
    try:
        # 從 MongoDB 獲取使用者資料
        user_data = find_user(user_id_hash)
        if user_data is None:
            success = insert_user({
                "_id": user_id_hash,
                "current_state": 1,
                "finish": False,
                "want_to_talk": False,
                "request_for_review": False
            })
            if success:
                current = 1
                is_finished = False
                want_to_talk = False
                request_for_review=False
            else:
                print("警告: 無法創建新使用者，使用預設值")
                current = 1
                is_finished = False
                want_to_talk = False
                request_for_review=False
        else:
            current = user_data.get("current_state", 1)
            is_finished = user_data.get("finish", False)
            want_to_talk = user_data.get("want_to_talk", False)
            request_for_review = user_data.get("request_for_review", False)
            
        # 處理固定的按鈕回應（優先處理）
        if user_text == "那我們都在幹什麼":
            reply_flex(event.reply_token, "GDG on Campus 的我們", "GDG on Campus NTPU的我們",
                       "會定期舉辦各式技術教學課程、交流活動、豐富的講座與工作坊，甚至是企業參訪！\n不僅提升你的開發能力，也能增廣見聞、結交志同道合的夥伴！",
                       "原來如此！", "我想加入！", color="#34A853")
            return

        if user_text == "我想加入！":
            reply_flex(event.reply_token, "參加問答活動有驚喜！", "參加問答活動有驚喜！",
                       "現在參加本帳號的互動問答，且皆回答正確，就能獲得專屬碼！\n我們將在 9/30 12:10 ~ 13:00 的「2025 招生說明會」上，即可憑此碼參與抽獎哦🎁～",
                       "馬上開始！", "準備好了！", color="#FBBC05")
            return

        if user_text == "準備好了！":
            if not is_finished:
                line_bot_api.reply_message(event.reply_token, build_question_message(current))
            else:
                unique_code = user_data.get("unique_code")
                line_bot_api.reply_message(event.reply_token, [
                    build_award_code_flex(unique_code),
                    TextSendMessage(text="【Google 學生開發者社群】 9/30 12:10 ~ 13:00 招生說明會抽獎 ✨，現在就火速報名吧！")
                ])
            return


        if is_finished :
            if not want_to_talk and user_text == "@呼叫社團LLM":
                update_user(user_id_hash, {"want_to_talk": True})
                line_bot_api.reply_message(event.reply_token, 
                    TextSendMessage(text="Hi！我是 GDG on Campus NTPU 的專屬AI助手，有什麼想了解的嗎？\n(請將您的問題詳述說明(30字內)，以利於我們進一步收集問題並回覆您!)"))
                return

            elif not want_to_talk:
                reply_flex(event.reply_token, "看來是想要和我們聊聊", "還想要聊聊嗎？",
                       "看來你還想多認識我們呢，想要問我們問題嗎？",
                       "我想提問", "@呼叫社團LLM", color="#FBBC05")
                return
            elif want_to_talk:
                if not request_for_review:
                    update_user(user_id_hash, {"request_for_review": True})
                    line_bot_api.reply_message(event.reply_token, [
                        TextSendMessage(text="(LLM尚未實裝，敬請期待!) \n GDG on Campus NTPU 是適合學生參與的社群，而我們注重學員在社團中能夠學習技能、實作專案、拓展人脈，之中，我們將會有多樣化的活動讓學員參與其中。\n敬請期待之後的社團博覽會、聯展以及招生說明會，謝謝!"),
                        build_evaluation_message()
                    ])
                    return
                elif request_for_review == True:
                    if user_text == "O":
                        line_bot_api.reply_message(event.reply_token, 
                        TextSendMessage(text="謝謝您的肯定！"))
                        update_user(user_id_hash, {"want_to_talk": False,"request_for_review": False})
                    elif user_text == "X":
                        try:
                            user_profile = line_bot_api.get_profile(event.source.user_id)
                            user_name = user_profile.display_name
                        except Exception as e:
                            user_name = "未知用戶"
                            print(f"無法獲取用戶資訊: {e}")
                            
                        line_bot_api.reply_message(event.reply_token, 
                        TextSendMessage(text="好的，很感謝您的回饋，我們之後會派工作人員回答您的問題，之後還請您注意，謝謝！"))
                        update_user(user_id_hash, {"want_to_talk": False,"request_for_review": False})
                        target_user_id = ADMIN_ID   # 確保這個是有效的 LINE User ID
        
                        # 調試信息：檢查 ADMIN_ID 的值
                        print(f"ADMIN_ID: {target_user_id}")
                        print(f"ADMIN_ID 長度: {len(target_user_id) if target_user_id else 0}")
                        
                        # 檢查 ADMIN_ID 是否存在且格式正確
                        if not target_user_id:
                            print("錯誤: ADMIN_ID 為空")
                        elif not target_user_id.startswith('U'):
                            print(f"警告: ADMIN_ID 格式可能不正確: {target_user_id}")
                        elif len(target_user_id) != 33:  # LINE User ID 通常是33個字符
                            print(f"警告: ADMIN_ID 長度不正確: {len(target_user_id)}")
                        else:
                            # 發送推送訊息
                            line_bot_api_admin.push_message(
                                target_user_id,
                                TextSendMessage(text=f"用戶 {user_name} 提交了回饋請求，需要工作人員處理")
                            )
                            print(f"成功推送訊息給管理員: {target_user_id}")
                    else:
                        line_bot_api.reply_message(event.reply_token, [
                        build_evaluation_message()
                    ])

        # 處理題目進行中的邏輯
        if not is_finished:
            ans = user_text.upper()
            correct = CORRECT_ANSWERS.get(current)
            
            # 檢查答案是否為有效選項
            if current in ANSWER_OPTIONS and ans in ANSWER_OPTIONS[current]:
                if ans == correct:
                    describe_text = DETAIL_DESCRIBE[current]
                    current += 1

                    # 更新使用者狀態
                    update_success = update_user(user_id_hash, {"current_state": current})
                    if not update_success:
                        print(f"警告: 無法更新使用者 {user_id_hash} 的狀態")

                    if current > len(QUESTIONS):
                        unique_code = generate_unique_code_mongodb(user_id_hash)
                        line_bot_api.reply_message(event.reply_token, [
                            TextSendMessage(text="正確答案～這五題都答對了！！"),
                            TextSendMessage(text=describe_text),
                            build_award_code_flex(unique_code),
                            TextSendMessage(text="【Google 學生開發者社群】9/30 12:10 ~ 13:00 招生說明會抽獎 ✨，現在就火速報名吧！"),
                        ])

                        # 更新使用者完成狀態和獎勵代碼
                        update_success = update_user(user_id_hash, {"finish": True, "unique_code": unique_code})
                        if not update_success:
                            print(f"警告: 無法更新使用者 {user_id_hash} 的完成狀態")

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
            else:
                # 使用者輸入了無效的選項，重新顯示題目
                line_bot_api.reply_message(event.reply_token, [
                    TextSendMessage(text="請選擇正確的選項哦！"),
                    build_question_message(current)
                ])
            return

    except Exception as e:
        print(f"處理 MessageEvent 時發生錯誤: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))