# 只用於測試FireBase
def generate_txt_file(output_file="document_keys.txt"):
    with open(output_file, "w", encoding="utf-8") as f:
        for i in range(1, 1000):
            f.write(f"X{i:03d}\n")  # 每行寫入 X001 ~ X999
    print(f"已成功生成 {output_file}")

if __name__ == "__main__":
    generate_txt_file()