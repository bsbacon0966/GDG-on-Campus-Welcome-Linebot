import os
import hashlib
import time

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FollowEvent, FlexSendMessage
)


# 題目資料 
QUESTIONS = {
    1: "請問我們的社團名稱是？\nA. GDG on Campus NTPU\nB. GDSC NTPU\nC. GDG\nD. GDE",
    2: "請問 GDG on Campus NTPU 是否會參加 9/24 的社團聯展？",
    3: "加入 GDG on Campus NTPU 一年後，你最可能成為什麼樣的人？\nA. 了解近年新穎科技趨勢的人\nB. 擁有亮眼專案開發經歷的人\nC. 擅長與夥伴們高效合作的人\nD. 以上皆是",
    4: "請問我們去年的活動主題不包含？\nA. UI/UX\nB. PM（專案經理）演講\nC. 數據分析\nD. 以上都辦過",
    5: "我們是北大最厲害的學術型社團嗎？"
}

DETAIL_DESCRIBE = {
    1: "B. 是我們的舊名，C. 跟 D. 則是 Google 官方其他面向社會人士的計畫，為了替各位提供產業前沿見解、分享職涯經驗，本社也會盡可能增加和他們交流互動的機會哦！",
    2: "我們將參與今年的聯展，當天將會有不少社團介紹環節，有興趣的朋友千萬不要錯過～",
    3: "除了社課，我們也有幹部與社員一同參與開發與討論的「專案制度」。\n每位社員都能發揮自己的專長領域與創意，彼此互相學習、互相支持，社團才得以茁壯💪！",
    4: "我們的社團課程與活動，除了上述領域之外，今年也會新增 AI、生產力工具主題，以及基礎程式教學，不僅生活實用性高，也十分適合想要跨領域的各位加入。",
    5: "不用懷疑，我們就是最厲害的學術性社團，我們已經連續兩年拿到北大社團評鑑的學術性特優了🏆！"
}

CORRECT_ANSWERS = {1:"A", 2:"O", 3:"D", 4:"D", 5:"O"}
QUESTION_TYPE = {1: "choice", 2: "bool", 3: "choice", 4: "choice", 5: "bool"}

ANSWER_OPTIONS = {
    1: ["A", "B", "C", "D"],
    2: ["O", "X"],
    3: ["A", "B", "C", "D"],
    4: ["A", "B", "C", "D"],
    5: ["O", "X"]
}

IMAGE_URLS = {
    1: "https://drive.google.com/uc?export=view&id=1ZB5JuJQVE4RQURNftU9tJ3QMRxEpbshC",
    2: "https://drive.google.com/uc?export=view&id=1kGnqsYLJd3ZuNwwNJkps8o6rdaj2i06k",
    3: "https://drive.google.com/uc?export=view&id=1VbIgbcDWzWfW9ZqAZYLtoGWUe2Rte-dz",
    4: "https://drive.google.com/uc?export=view&id=1FapjSmiyKKgA4vzpA27WG2uzs-3X1r4I",
    5: "https://drive.google.com/uc?export=view&id=1QHQKI0lQYSKf2l1viUIklj6QgyFbDYSC"
}


# 專屬題目的Message程式碼 
def build_question_message(current):
    question_text = QUESTIONS[current]
    image_url = IMAGE_URLS.get(current)
    options = ANSWER_OPTIONS[current]

    button_colors = ["#E94436", "#109D58", "#4385F3", "#FABC05"] if QUESTION_TYPE[current] == "choice" else ["#109D58", "#E94436"]

    # 產生按鈕
    def build_button(option, color):
        return {
            "type": "button",
            "style": "primary",
            "color": color,
            "action": {"type": "message", "label": option, "text": option}
        }

    if QUESTION_TYPE[current] == "choice": # 選擇題
        buttons_rows = [
            {"type": "box", "layout": "horizontal", "spacing": "sm",
             "contents": [build_button(options[i], button_colors[i]) for i in range(row*2, row*2+2)]}
            for row in range(2)
        ]
    else: # 是非題
        buttons_rows = [{"type": "box", "layout": "horizontal", "spacing": "sm",
                         "contents": [build_button(opt, button_colors[idx]) for idx, opt in enumerate(options)]}]

    return FlexSendMessage(
        alt_text=f"第 {current} 題: {question_text}",
        contents={
            "type": "bubble",
            "hero": {"type": "image", "url": image_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": f"第 {current} 題", "weight": "bold", "size": "lg"},
                {"type": "text", "text": question_text, "wrap": True}
            ]},
            "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": buttons_rows}
        }
    )


# 使用者填完題目後的獎勵Message
def build_award_code_flex(unique_code):
    return FlexSendMessage(
        alt_text="恭喜完成所有題目！您的專屬獎獎代碼",
        contents={
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "md", "contents": [
                    {"type": "text", "text": "🎉 恭喜完成所有題目！ 🎉", "weight": "bold", "size": "xl", "align": "center", "color": "#34A853"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": "您的專屬獎獎代碼", "weight": "bold", "size": "md", "align": "center", "color": "#555555", "margin": "md"},
                    {"type": "text", "text": unique_code, "weight": "bold", "size": "xxl", "color": "#EA4335", "align": "center", "margin": "md"},
                    {"type": "text", "text": "9/30 12:10~13:00 活動現場將憑此參加抽獎", "size": "sm", "color": "#888888", "align": "center", "wrap": True, "margin": "md"}
                ]
            }
        }
    )
    

def build_reply_flex(alt, title, desc, btn_label, btn_text, color):
    flex_content = {
        "type": "bubble",
        "body": {
            "type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "lg"},
                {"type": "text", "text": desc, "wrap": True, "margin": "md"},
                {"type": "button", "style": "primary", "color": color,
                 "action": {"type": "message", "label": btn_label, "text": btn_text}, "margin": "md"}
            ]
        }
    }
    return FlexSendMessage(alt_text=alt, contents=flex_content)

def get_correct_answer(question_number):
    return CORRECT_ANSWERS.get(question_number)

def get_correct_detail(question_number):
    return DETAIL_DESCRIBE.get(question_number)

def get_question_type(question_number):
    return QUESTION_TYPE.get(question_number)

def get_answer_options(question_number):
    return ANSWER_OPTIONS.get(question_number)