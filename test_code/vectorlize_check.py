from dotenv import load_dotenv
from openai import OpenAI
import os
from pymongo import MongoClient
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()
OpenAI_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_USER = os.getenv("MONGODB_USER")
DB_PASS = os.getenv("MONGODB_PASSWORD") 
DB_NAME = os.getenv("MONGODB_DBNAME")

# MongoDB 連接字串
uri = f"mongodb+srv://{DB_USER}:{DB_PASS}@welcome.j3ma8ab.mongodb.net/{DB_NAME}?retryWrites=true&w=majority&tls=true"

mongo_client = MongoClient(uri)
db = mongo_client["GDG-QA"]
qa_collection = db["qa_vectors"]

def embed_text(text):
    """使用 OpenAI embedding 生成向量"""
    response = OpenAI_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def detect_similar_aliases(qa_data, similarity_threshold=0.88):
    """
    檢測 QA 內部 aliases 的相似度，只報告不移除
    """
    print(f"\n=== QA內部 Aliases 相似度檢測 (相似度閾值: {similarity_threshold}) ===")
    
    similarity_report = []
    
    for item_idx, item in enumerate(qa_data):
        print(f"\n檢測 QA 項目 {item_idx + 1}: 「{item['label']}」")
        aliases_count = len(item["aliases"])
        print(f"Aliases 數量: {aliases_count}")
        
        if aliases_count <= 1:
            print("Aliases 數量不足，跳過相似度檢測")
            continue
            
        # 生成所有 aliases 的 embeddings
        aliases = item["aliases"]
        print("正在生成 embeddings...")
        embeddings = []
        for alias in aliases:
            embedding = embed_text(alias)
            embeddings.append(embedding)
        
        # 檢測相似的 aliases 組合
        similar_pairs = []
        
        for i in range(len(aliases)):
            for j in range(i + 1, len(aliases)):
                similarity = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                
                if similarity > similarity_threshold:
                    similar_pair = {
                        "alias_1": aliases[i],
                        "alias_2": aliases[j],
                        "similarity": similarity
                    }
                    similar_pairs.append(similar_pair)

        if similar_pairs:
            qa_similarity = {
                "qa_label": item["label"],
                "qa_index": item_idx,
                "total_aliases": aliases_count,
                "similar_pairs": similar_pairs,
                "similar_pairs_count": len(similar_pairs)
            }
            similarity_report.append(qa_similarity)
        else:
            print(" 沒有發現相似的 aliases")
    
    print(f"\n=== Aliases 相似度檢測完成 ===")
    print(f"總共在 {len(similarity_report)} 個 QA 項目中發現相似的 aliases")
    
    return similarity_report

def detect_cross_qa_similarities(qa_data, similarity_threshold=0.85):
    """
    檢測跨 QA 項目的相似問題，只報告不移除
    """
    print(f"\n=== 跨 QA 項目相似度檢測 (相似度閾值: {similarity_threshold}) ===")
    
    # 收集所有問題文本和其對應的 QA 索引
    all_questions = []  # (問題文本, qa_index, question_type)
    
    for qa_idx, qa_item in enumerate(qa_data):
        # 主要 label
        all_questions.append((qa_item["label"], qa_idx, "label"))
        
        # 所有 aliases
        for alias_idx, alias in enumerate(qa_item["aliases"]):
            all_questions.append((alias, qa_idx, "alias"))
    
    print(f"總共收集到 {len(all_questions)} 個問題文本")
    
    # 生成所有問題的 embeddings
    print("正在生成所有問題的 embeddings...")
    embeddings = []
    for question_text, _, _ in all_questions:
        embedding = embed_text(question_text)
        embeddings.append(embedding)
    
    # 尋找相似的問題組合
    print("正在分析跨 QA 相似問題...")
    similar_pairs = []
    
    for i in range(len(all_questions)):
        question_i = all_questions[i]
        embedding_i = embeddings[i]
        
        for j in range(i + 1, len(all_questions)):
            question_j = all_questions[j]
            embedding_j = embeddings[j]
            
            if question_i[1] == question_j[1]:
                print(f"  跳過同一 QA 內部比較: [{question_i[1]}] {question_i[0]} vs {question_j[0]}")
                continue
            if question_i[2] == "label" or question_j[2] == "label":
                print(f"  跳過Label : [{question_i[1]}] {question_i[0]} vs {question_j[0]}")
                continue
            
            # 計算相似度
            similarity = cosine_similarity([embedding_i], [embedding_j])[0][0]
            
            if similarity > similarity_threshold:
                similar_pair = {
                    "similarity": similarity,
                    "question_1": {
                        "qa_label": qa_data[question_i[1]]["label"],
                        "text": question_i[0],
                        "qa_index": question_i[1],
                    },
                    "question_2": {
                        "qa_label": qa_data[question_j[1]]["label"],
                        "text": question_j[0],
                        "qa_index": question_j[1],
                    }
                }
                
                similar_pairs.append(similar_pair)

    print(f"\n=== 跨 QA 相似度檢測完成 ===")
    print(f"發現 {len(similar_pairs)} 組跨 QA 相似問題")
    
    return similar_pairs

def create_similarity_report(aliases_similarities, cross_qa_similarities):
    
    # 統計 aliases 相似度
    total_alias_pairs = sum(qa["similar_pairs_count"] for qa in aliases_similarities)
    qa_with_similar_aliases = len(aliases_similarities)
    
    report = {
        "detection_summary": {
            "aliases_similarity_detection": {
                "qa_items_with_similar_aliases": qa_with_similar_aliases,
                "total_similar_alias_pairs": total_alias_pairs
            },
            "cross_qa_similarity_detection": {
                "total_cross_qa_similar_pairs": len(cross_qa_similarities)
            },
            "overall_summary": {
                "total_similar_pairs_found": total_alias_pairs + len(cross_qa_similarities),
                "requires_manual_review": total_alias_pairs + len(cross_qa_similarities) > 0
            }
        },
        "detailed_findings": {
            "aliases_similarities": aliases_similarities,
            "cross_qa_similarities": cross_qa_similarities
        },
        "recommendations": {
            "aliases_review": "檢查同一 QA 項目內相似的 aliases，考慮是否需要合併或保留差異",
            "cross_qa_review": "檢查不同 QA 項目間的相似問題，考慮是否需要合併 QA 項目或調整分類",
            "action_needed": total_alias_pairs + len(cross_qa_similarities) > 0
        }
    }
    return report

def detect_qa_similarities_comprehensive(aliases_threshold=0.88, cross_qa_threshold=0.85):
    
    # 載入原始 QA 資料
    print("載入原始 QA 資料...")
    qa_data = json.load(open(r".\test_code\describe.json", "r", encoding="utf-8"))
    print(f"載入了 {len(qa_data)} 個 QA 項目")
    
    # 開始確認相似度
    aliases_similarities = detect_similar_aliases(qa_data, aliases_threshold)
    cross_qa_similarities = detect_cross_qa_similarities(qa_data, cross_qa_threshold)
    similarity_report = create_similarity_report(aliases_similarities, cross_qa_similarities)
    
    # 儲存相似度檢測報告
    with open("qa_similarity_detection_report.json", "w", encoding="utf-8") as f:
        json.dump(similarity_report, f, ensure_ascii=False, indent=2)
    print("相似度檢測報告已儲存至 qa_similarity_detection_report.json")


    print(f"\n=== 檢測結果摘要 ===")
    summary = similarity_report["detection_summary"]
    if summary['overall_summary']['requires_manual_review']:
        print("建議進行人工審查，決定是否需要合併或調整")
    else:
        print("沒有發現明顯的相似問題")
    
    return similarity_report


if __name__ == "__main__":
    print("=== JSON 文件相似度檢測與報告生成 ===")
    
    # 參數說明：
    # aliases_threshold: QA 內部 aliases 相似度閾值 (建議 0.88)
    # cross_qa_threshold: 跨 QA 項目相似度閾值 (建議 0.85)
    
    similarity_report = detect_qa_similarities_comprehensive(
        aliases_threshold=0.8, 
        cross_qa_threshold=0.7
    )