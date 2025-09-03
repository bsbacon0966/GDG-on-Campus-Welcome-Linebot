import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv
from pymongo.server_api import ServerApi

def get_db():
    load_dotenv()
    DB_USER = os.getenv("MONGODB_USER")  # 從環境變數讀取
    DB_PASS = os.getenv("MONGODB_PASSWORD")  # 從環境變數讀取
    DB_NAME = os.getenv("MONGODB_DBNAME")

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

def export_unique_codes(collection_name, output_file):
    """導出已完成問答的使用者獎勵代碼"""
    try:
        db = get_db()
        collection = db[collection_name]

        # 查詢 finish=true 的使用者
        query = {"finish": True}
        projection = {"unique_code": 1, "_id": 0}  # 只取 unique_code，不要 _id
        docs = collection.find(query, projection)

        # 統計相關資訊
        total_count = 0
        valid_code_count = 0

        with open(output_file, "w", encoding="utf-8") as f:
            for doc in docs:
                total_count += 1
                unique_code = doc.get("unique_code")
                if unique_code:
                    f.write(f"{unique_code}\n")
                    valid_code_count += 1
                else:
                    print(f"警告: 發現已完成但無獎勵代碼的記錄: {doc}")

        print(f"導出完成!")
        print(f"集合名稱: {collection_name}")
        print(f"查詢條件: finish=true")
        print(f"總共找到: {total_count} 筆記錄")
        print(f"有效代碼: {valid_code_count} 個")
        print(f"輸出檔案: {output_file}")
        
        # 驗證檔案是否成功創建
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            print(f"檔案大小: {file_size} bytes")
        
        return valid_code_count

    except Exception as e:
        print(f"導出過程發生錯誤: {e}")
        raise

def show_collection_stats(collection_name):
    """顯示集合的統計資訊"""
    try:
        db = get_db()
        collection = db[collection_name]
        
        total_users = collection.count_documents({})
        finished_users = collection.count_documents({"finish": True})
        unfinished_users = collection.count_documents({"finish": False})
        
        print(f"\n=== {collection_name} 集合統計 ===")
        print(f"總使用者數: {total_users}")
        print(f"已完成問答: {finished_users}")
        print(f"未完成問答: {unfinished_users}")
        print("=" * 30)
        
    except Exception as e:
        print(f"統計資訊獲取失敗: {e}")

if __name__ == "__main__":
    try:
        # 顯示統計資訊
        show_collection_stats("users")
        
        # 導出獎勵代碼
        exported_count = export_unique_codes("users", "unique_codes.txt")
        
        if exported_count > 0:
            print(f"\n成功導出 {exported_count} 個獎勵代碼到 unique_codes.txt")
        else:
            print("\n沒有找到任何已完成的問答記錄")
            
    except Exception as e:
        print(f"程式執行失敗: {e}", file=sys.stderr)
        sys.exit(1)