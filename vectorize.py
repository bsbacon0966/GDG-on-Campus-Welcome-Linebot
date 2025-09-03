from dotenv import load_dotenv
from openai import OpenAI
import os

from pymongo import MongoClient

load_dotenv()
OpenAI_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_USER = os.getenv("MONGODB_USER")  # 從環境變數讀取
DB_PASS = os.getenv("MONGODB_PASSWORD")  # 從環境變數讀取
DB_NAME = os.getenv("MONGODB_DBNAME")

# 生產環境級 MongoDB 連接字串
uri = f"mongodb+srv://{DB_USER}:{DB_PASS}@welcome.j3ma8ab.mongodb.net/{DB_NAME}?retryWrites=true&w=majority&tls=true"

mongo_client = MongoClient(uri)
db = mongo_client["Closed-QA"]
faq_collection = db["faq"]

def embed_text(text):
    response = OpenAI_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

faq_data = [
    {"question": "營業時間是？", "answer": "我們每天 9:00-18:00 營業"},
    {"question": "地址在哪裡？", "answer": "台北市信義區OO路123號"},
    {"question": "客服電話是多少？", "answer": "0800-123-456"}
]

for item in faq_data:
    item["embedding"] = embed_text(item["question"])
    faq_collection.insert_one(item)

print("FAQ 已存入並建立向量！")