import json

qa_data = json.load(open(r".\test_code\describe.json", "r", encoding="utf-8"))
total_texts = sum(1 + len(item["aliases"]) for item in qa_data)
avg_length = sum(len(item["label"]) + sum(len(alias) for alias in item["aliases"]) 
                 for item in qa_data) / total_texts

print(f"QA數量: {len(qa_data)}")
print(f"總文本數: {total_texts}")
print(f"平均文本長度: {avg_length:.1f}字符")
print(f"預估cost: ${total_texts * avg_length / 4 * 0.02 / 1000000:.6f}")