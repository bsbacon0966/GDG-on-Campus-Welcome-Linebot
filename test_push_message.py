# The easiest way to test push messages

import os
from linebot import LineBotApi
from linebot.models import TextSendMessage
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import random

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_TOKEN')
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)

# 初始化 Firebase（只需執行一次）
if not firebase_admin._apps:
    cred = credentials.Certificate('serviceAccount.json')
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 讀取 check_list 中所有 document 的 key
docs = list(db.collection('check_list').stream())
all_keys = [doc.id for doc in docs]

if not all_keys:
    print("check_list 沒有任何紀錄")
else:
    unique_code = random.choice(all_keys)
    print(f"抽中的 unique_code: {unique_code}")

    doc = db.collection('check_list').document(unique_code).get()
    if doc.exists:
        user_id = doc.to_dict().get('userID')
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text=f"恭喜你中獎！\n請截圖保存此代碼！\n你的代碼：{unique_code}")
        )
    else:
        print("查無此中獎紀錄")

