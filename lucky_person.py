import firebase_admin
from firebase_admin import credentials, firestore
# 用來抽籤"已經存在的流水號"的程式碼
# 初始化 Firebase Admin SDK
cred = credentials.Certificate("serviceAccount.json")  
firebase_admin.initialize_app(cred)

db = firestore.client()

def export_document_ids_to_txt(collection_name, output_file):
    collection_ref = db.collection(collection_name)
    docs = collection_ref.stream()  # 取得所有文件(流水號是以doc儲存)
    with open(output_file, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(doc.id + "\n")
    print(f"已將 {collection_name} 的 document IDs 輸出到 {output_file}")

if __name__ == "__main__":
    export_document_ids_to_txt("test_collection", "document_keys.txt")
