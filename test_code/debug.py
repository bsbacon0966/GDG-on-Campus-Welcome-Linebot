from dotenv import load_dotenv
from openai import OpenAI
import os
from pymongo import MongoClient

load_dotenv()
OpenAI_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_USER = os.getenv("MONGODB_USER")
DB_PASS = os.getenv("MONGODB_PASSWORD") 
DB_NAME = os.getenv("MONGODB_DBNAME")

uri = f"mongodb+srv://{DB_USER}:{DB_PASS}@welcome.j3ma8ab.mongodb.net/{DB_NAME}?retryWrites=true&w=majority&tls=true"
mongo_client = MongoClient(uri)
db = mongo_client["GDG-QA"]
qa_collection = db["qa_vectors"]

def embed_text(text):
    response = OpenAI_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def debug_database():
    """診斷資料庫內容"""
    print("=== 診斷資料庫 ===")
    
    # 1. 檢查資料筆數
    total_docs = qa_collection.count_documents({})
    print(f"總文檔數: {total_docs}")
    
    # 2. 檢查資料結構
    sample_docs = list(qa_collection.find().limit(3))
    for i, doc in enumerate(sample_docs):
        print(f"\n文檔 {i+1}:")
        print(f"  text: {doc.get('text', 'N/A')}")
        print(f"  label: {doc.get('label', 'N/A')}")
        print(f"  category: {doc.get('category', 'N/A')}")
        print(f"  embedding 長度: {len(doc.get('embedding', []))}")
        print(f"  is_primary: {doc.get('is_primary', 'N/A')}")
    
    # 3. 檢查有哪些 labels
    labels = qa_collection.distinct("label")
    print(f"\n所有 labels: {labels}")
    
    # 4. 檢查有哪些 texts
    texts = list(qa_collection.find({}, {"text": 1, "label": 1}).limit(10))
    print(f"\n前 10 個文本:")
    for text_doc in texts:
        print(f"  {text_doc.get('label')} -> {text_doc.get('text')}")

def test_vector_search_debug(query):
    """測試向量搜尋並顯示詳細資訊"""
    print(f"\n=== 測試向量搜尋: {query} ===")
    
    try:
        # 生成查詢向量
        query_embedding = embed_text(query)
        print(f"查詢向量長度: {len(query_embedding)}")
        
        # 嘗試不同的 pipeline
        pipelines = [
            # Pipeline 1: 使用 $vectorSearch (新版)
            {
                "name": "$vectorSearch (新版)",
                "pipeline": [
                    {
                        "$vectorSearch": {
                            "index": "vector_search_index",
                            "path": "embedding",
                            "queryVector": query_embedding,
                            "numCandidates": 100,
                            "limit": 5
                        }
                    },
                    {
                        "$project": {
                            "text": 1,
                            "label": 1,
                            "answer": 1,
                            "score": {"$meta": "vectorSearchScore"}
                        }
                    }
                ]
            },
            # Pipeline 2: 使用 $search + knnBeta (舊版)
            {
                "name": "$search + knnBeta (舊版)",
                "pipeline": [
                    {
                        "$search": {
                            "index": "vector_search_index",
                            "knnBeta": {
                                "vector": query_embedding,
                                "path": "embedding",
                                "k": 5
                            }
                        }
                    },
                    {
                        "$project": {
                            "text": 1,
                            "label": 1,
                            "answer": 1,
                            "score": {"$meta": "searchScore"}
                        }
                    }
                ]
            }
        ]
        
        for pipeline_info in pipelines:
            print(f"\n--- 嘗試 {pipeline_info['name']} ---")
            try:
                results = list(qa_collection.aggregate(pipeline_info['pipeline']))
                print(f"結果數量: {len(results)}")
                
                for i, result in enumerate(results[:3]):
                    print(f"  結果 {i+1}:")
                    print(f"    text: {result.get('text', 'N/A')}")
                    print(f"    label: {result.get('label', 'N/A')}")
                    print(f"    score: {result.get('score', 'N/A')}")
                    
                if results:
                    return results  # 如果有結果就返回
                    
            except Exception as e:
                print(f"    錯誤: {e}")
        
        print("所有 pipeline 都沒有結果")
        return []
        
    except Exception as e:
        print(f"整體錯誤: {e}")
        return []

def test_simple_search():
    """測試簡單的非向量搜尋"""
    print("\n=== 測試簡單文字搜尋 ===")
    
    # 直接用 label 搜尋
    result = qa_collection.find_one({"label": "社員能力要求"})
    if result:
        print("找到 '社員能力要求' 的資料")
        print(f"   text: {result.get('text')}")
        print(f"   answer: {result.get('answer')[:50]}...")
    else:
        print("找不到 '社員能力要求' 的資料")
    
    # 檢查是否有 embedding
    result_with_embedding = qa_collection.find_one({"label": "社員能力要求", "embedding": {"$exists": True}})
    if result_with_embedding:
        print("資料有 embedding")
        print(f"   embedding 長度: {len(result_with_embedding.get('embedding', []))}")
    else:
        print("資料沒有 embedding")

def check_index_status():
    """檢查索引狀態 (需要手動確認)"""
    print("\n=== 索引檢查 ===")
    print("請手動確認以下項目:")
    print("1. MongoDB Atlas 中的 vector_search_index 狀態是否為 'Active'")
    print("2. 索引是否建立在正確的 database.collection (GDG-QA.qa_vectors)")
    print("3. 索引設定:")
    print("   - path: 'embedding'")
    print("   - numDimensions: 1536") 
    print("   - similarity: 'cosine'")

if __name__ == "__main__":
    # 診斷步驟
    debug_database()
    
    print("\n" + "="*60)
    test_simple_search()
    
    print("\n" + "="*60)
    check_index_status()
    
    print("\n" + "="*60)
    # 測試向量搜尋
    test_vector_search_debug("社員能力要求")
    
    print("\n" + "="*60)
    test_vector_search_debug("非資工學生可以參加嗎？")