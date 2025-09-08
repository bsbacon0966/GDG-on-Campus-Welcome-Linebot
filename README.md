# GDG on Campus Welcome Linebot


## Overall (加入後QA遊戲與生成抽獎代碼)
<img width="1404" height="640" alt="overall drawio (2)" src="https://github.com/user-attachments/assets/34c4248d-f70a-402a-a6ad-79eb767faa14" />

### mongoDB資料存放
- current_state : 確認使用者在一開始加入好友的QA遊戲進度
- finish_gameplay : 確認使用者是否由玩結束(之間，會生成特殊碼，當作完成QA遊戲的使用者一個抽獎代碼)
- has_seen_answer_description : 如果玩家答錯，是否看過詳解，用來決定是否顯示詳解

## Overall (社團LLM設計)
<img width="1106" height="660" alt="未命名绘图 drawio (2)" src="https://github.com/user-attachments/assets/f2b238ad-38a4-45d0-855a-155138cbf29c" />
