# 「Google學生開發者社群 - 臺北大學」
import os
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
import linebot_object.QA as QA
import linebot_object.welcome_gameplay as gameplay

# 載入 .env
load_dotenv()
app = Flask(__name__)
# LINE BOT 設定
# CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_TOKEN_STUDENT')
# CHANNEL_SECRET = os.getenv('CHANNEL_SECRET_STUDENT')

CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_TOKEN_TEST')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET_TEST')

CHANNEL_ACCESS_TOKEN_ADMIN = os.getenv('CHANNEL_ACCESS_TOKEN_ADMIN')
ADMIN_ID = os.getenv('ADMIN_ID')

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    print("請確認 .env 設定了 CHANNEL_TOKEN 和 CHANNEL_SECRET")
    exit(1)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
line_bot_api_admin = LineBotApi(CHANNEL_ACCESS_TOKEN_ADMIN)
handler = WebhookHandler(CHANNEL_SECRET)

DB_USER = os.getenv("MONGODB_USER")  
DB_PASS = os.getenv("MONGODB_PASSWORD")  
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
qa_collection = None  # 新增 QA 集合

if client is not None:
    try:
        db = client[DB_NAME]
        users_collection = db['users']
        counters_collection = db['counters']
        qa_db = client["GDG-QA"]
        qa_collection = qa_db["qa_vectors"]
        
        # QA 系統初始化（只保留這一次）
        import linebot_object.QA as qa_module
        qa_module.init_qa_collection(qa_collection)
        print("QA 系統初始化完成")

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

# 改良版的流水號生成函數
@db_operation_retry()
def generate_unique_code_mongodb(user_id_hash):
    if db is None:
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


# 打亂使用者 ID，以避免創造者竊取使用者ID
def encrypt_userid(user_id):
    # return user_id
    return hashlib.sha256(user_id.encode()).hexdigest()

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
                "finish_gameplay": False,
                "has_seen_answer_description": False
            })
            if not success:
                print("警告: 無法將新使用者存入資料庫")
    except Exception as e:
        print(f"處理 FollowEvent 時發生錯誤: {e}")

    line_bot_api.reply_message(event.reply_token, [
        gameplay.build_reply_flex("歡迎加入 GDG on Campus", "歡迎加入互動帳號！",
        "我們是由 Google 官方支持成立、立足北大的開發者社群",
        "想知道我們的日常", "那我們都在幹什麼","#4385F3")
    ])
    
# MessageEvent : 面對使用者回應所設計的判斷，邏輯上跟著Message的按鈕走就可以觸發到當前所有判斷
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    
    user_id = event.source.user_id
    user_id_hash = encrypt_userid(user_id)
    user_text = event.message.text.strip()
    
    try:
        # 從 MongoDB 獲取使用者資料
        user_data = find_user(user_id_hash)
        current = user_data.get("current_state", 1)
        is_finished = user_data.get("finish_gameplay", False)
        has_seen_answer_description = user_data.get("has_seen_answer_description", False)
        want_to_talk = user_data.get("want_to_talk", False)
        request_for_review = user_data.get("request_for_review", False)
            
        # 處理固定的按鈕回應（優先處理）
        if user_text == "那我們都在幹什麼":
            line_bot_api.reply_message(event.reply_token, [
                gameplay.build_reply_flex("GDG on Campus 的我們", "GDG on Campus NTPU的我們",
                "會定期舉辦各式技術教學課程、交流活動、豐富的講座與工作坊，甚至是企業參訪！\n不僅提升你的開發能力，也能增廣見聞、結交志同道合的夥伴！",
                "原來如此！", "我想加入！", color="#34A853")
            ])
            return

        if user_text == "我想加入！":
            line_bot_api.reply_message(event.reply_token, [
                gameplay.build_reply_flex("參加問答活動有驚喜！", "參加問答活動有驚喜！",
                "現在參加本帳號的互動問答，且皆回答正確，就能獲得專屬碼！\n我們將在 9/30 12:10 ~ 13:00 的「2025 招生說明會」上，即可憑此碼參與抽獎哦🎁～",
                "馬上開始！", "準備好了！", color="#FBBC05")
            ])
            return

        if user_text == "準備好了！":
            if not is_finished:
                line_bot_api.reply_message(event.reply_token, gameplay.build_question_message(current))
            else:
                unique_code = user_data.get("unique_code")
                line_bot_api.reply_message(event.reply_token, [
                    gameplay.build_award_code_flex(unique_code),
                    TextSendMessage(text="【Google 學生開發者社群】 9/30 12:10 ~ 13:00 招生說明會抽獎 ✨，現在就火速報名吧！"),
                    QA.build_talk_to_me_message("還想多認識我們嗎?","社團LLM回答您","如果您想要更認識我們的話，就呼叫社團LLM來幫你解答吧")
                ])
            return

        # 處理已完成問答的使用者
        if is_finished:
            if not want_to_talk and user_text == "@呼叫社團LLM":
                update_user(user_id_hash, {"want_to_talk": True})
                line_bot_api.reply_message(event.reply_token, 
                    TextSendMessage(text="Hi！我是 GDG on Campus NTPU 的專屬AI助手，有什麼想了解的嗎？\n\n(請將您的問題詳述說明(30字內)，以利於我們進一步收集問題並回覆您!)"))
                return

            elif not want_to_talk:
                line_bot_api.reply_message(event.reply_token, [
                        QA.build_talk_to_me_message("還想多認識我們嗎?","社團LLM回答您","如果您想要更認識我們的話，就呼叫社團LLM來幫你解答吧")
                    ])
                return
                
            elif want_to_talk:
                if not request_for_review:
                    update_user(user_id_hash, {"request_for_review": True})
                    # 這裡使用 QA 系統處理使用者的問題
                    answer = QA.qa_pipeline(user_text)
                    line_bot_api.reply_message(event.reply_token, [
                        TextSendMessage(text=answer),
                        QA.build_evaluation_message()
                    ])
                    return
                elif request_for_review == True:
                    if user_text == "O":
                        line_bot_api.reply_message(event.reply_token, [
                            TextSendMessage(text="謝謝您的肯定！"),
                            QA.build_talk_to_me_message("還有問題想要解答嗎?","社團LLM回答您","如果您想要更認識我們的話，就呼叫社團LLM來幫你解答吧")
                        ])
                        update_user(user_id_hash, {"want_to_talk": False, "request_for_review": False})
                    elif user_text == "X":
                        
                        user_profile = line_bot_api.get_profile(event.source.user_id)
                        user_name = user_profile.display_name

                        line_bot_api.reply_message(event.reply_token, [
                            TextSendMessage(text="好的，很感謝您的回饋，我們之後會派工作人員回答您的問題，之後還請您注意，謝謝！"),
                            QA.build_talk_to_me_message("還有其他問題想要問嗎?","社團LLM(應該都能)回答您","如果您想要更認識我們的話，就呼叫社團LLM來幫你解答吧")
                        ])
                        update_user(user_id_hash, {"want_to_talk": False, "request_for_review": False})
                        
                        target_user_id = ADMIN_ID   
                        line_bot_api_admin.push_message(
                            target_user_id,
                            TextSendMessage(text=f"用戶 {user_name} 提交了回饋請求，需要工作人員處理")
                        )
                        print(f"成功推送訊息給管理員: {target_user_id}")
                        
                    else:
                        line_bot_api.reply_message(event.reply_token, 
                            QA.build_evaluation_message())
                return

        # 處理題目進行中的邏輯
        if not is_finished:
            ans = user_text.upper()
            # 檢查答案是否為有效選項
            
            if ans in gameplay.get_answer_options(current):
                correct = gameplay.get_correct_answer(current)
                describe_text = gameplay.get_correct_detail(current)
                if ans == correct:
                    current += 1
                    # 更新使用者狀態
                    update_success = update_user(user_id_hash, {"current_state": current})
                    if not update_success:
                        print(f"警告: 無法更新使用者 {user_id_hash} 的狀態")

                    if current > 5:
                        unique_code = generate_unique_code_mongodb(user_id_hash)
                        line_bot_api.reply_message(event.reply_token, [
                            TextSendMessage(text="正確答案～這五題都答對了！！"),
                            *( [TextSendMessage(text=describe_text)] if has_seen_answer_description == False else [] ),
                            gameplay.build_award_code_flex(unique_code),
                            TextSendMessage(text="【Google 學生開發者社群】9/30 12:10 ~ 13:00 招生說明會抽獎 ✨，現在就火速報名吧！"),
                            QA.build_talk_to_me_message("還有問題想要解答嗎?","社團LLM回答您","如果您想要更認識我們的話，就呼叫社團LLM來幫你解答吧")
                        ])
                        update_user(user_id_hash, {"has_seen_answer_description": False})


                        # 更新使用者完成狀態和獎勵代碼
                        update_success = update_user(user_id_hash, {"finish_gameplay": True, "unique_code": unique_code})
                        if not update_success:
                            print(f"警告: 無法更新使用者 {user_id_hash} 的完成狀態")

                    else:
                        line_bot_api.reply_message(event.reply_token, [
                            TextSendMessage(text="正確答案～"),
                            *( [TextSendMessage(text=describe_text)] if has_seen_answer_description == False else [] ),
                            TextSendMessage(text="那就再來一題！"),
                            gameplay.build_question_message(current)
                        ])
                        update_user(user_id_hash, {"has_seen_answer_description": False})
                else:
                    line_bot_api.reply_message(event.reply_token, [
                        TextSendMessage(text="答錯了，再接再厲～"),
                        TextSendMessage(text=describe_text),
                        TextSendMessage(text="再試一次！"),
                        gameplay.build_question_message(current)
                    ])
                    update_user(user_id_hash, {"has_seen_answer_description": True})
            else:
                # 使用者輸入了無效的選項，重新顯示題目
                line_bot_api.reply_message(event.reply_token, [
                    TextSendMessage(text="請選擇正確的選項哦！"),
                    gameplay.build_question_message(current)
                ])
            return

    except Exception as e:
        print(f"處理 MessageEvent 時發生錯誤: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))