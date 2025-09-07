#!/usr/bin/env python3
# insert_test_data.py
import os
from pymongo import MongoClient
from dotenv import load_dotenv
from pymongo.server_api import ServerApi
def get_db():
    load_dotenv()
    DB_USER = "jerry109a"
    DB_PASS = os.getenv("MONGODB_PASSWORD")  # 從環境變數讀取
    DB_NAME = "welcome"

    uri = f"mongodb+srv://{DB_USER}:{DB_PASS}@welcome.j3ma8ab.mongodb.net/{DB_NAME}?retryWrites=true&w=majority&appName=welcome"

    # 建立 MongoDB client，指定 Server API 版本
    client = MongoClient(uri, server_api=ServerApi('1'))

    # 測試連線
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB Atlas!")
    except Exception as e:
        print("MongoDB 連線失敗:", e)
        
    return client[DB_NAME]
def insert_test_users():
    
    db = get_db()
    users = db["users"]

    test_docs = []
    for i in range(1, 301):  # X001 ~ X300
        user_doc = {
            "_id": f"test_user_{i:03d}",  # 假設 _id 不重複
            "finish": True,
            "unique_code": f"X{i:03d}",
            "current_state": 999  # 測試用狀態
        }
        test_docs.append(user_doc)

    # 插入資料（如果已存在會拋錯，可改用 update/upsert）
    try:
        users.insert_many(test_docs)
        print("已成功插入 300 筆測試資料！")
    except Exception as e:
        print(f"插入失敗: {e}")

if __name__ == "__main__":
    insert_test_users()
