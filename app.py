from flask import Flask, request, abort
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    PostbackEvent,
    JoinEvent,
    LeaveEvent,
    TextMessageContent
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    TextMessage,
    PostbackAction,
    FlexMessage,
    FlexContainer,
    DatetimePickerAction
)
import json
from pymongo.mongo_client import MongoClient
import threading
import time
from datetime import datetime
import os
import pytz

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
MONGODB_URI = os.getenv("MONGODB_URI")
PUSH_HOUR = 7
PUSH_MINUTE = 30
USER_ID = os.getenv("USER_ID")
LASTPUSHDATE = None

mongo_client = MongoClient(MONGODB_URI)
    
line_handler = WebhookHandler(CHANNEL_SECRET)

configuration = Configuration(
    access_token=CHANNEL_ACCESS_TOKEN
)

try:
    db = mongo_client.NotifyBotDB
    print("成功連結到資料庫")
except Exception as e:
    print("連結失敗")
    print(e)

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # parse webhook body
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@line_handler.add(JoinEvent)
def handle_join(event):
    group_id = event.source.group_id
    # insert_data("GroupInfo", {"group_id": group_id, "active": True, "timestamp": event.timestamp, "members": []})
    insert_data("Log", {"group_id": group_id, "timestamp": event.timestamp, "funcs": ""})
    reply_line_message(event, [TextMessage(text="你好我是紀錄機器人")])
    return

@line_handler.add(LeaveEvent)
def handle_leave(event):
    group_id = event.source.group_id
    # delete_data("GroupInfo", {"group_id": group_id})
    delete_data("Log", {"group_id": group_id})
    delete_data("Event", {"group_id": group_id})
    reply_line_message(event, [TextMessage(text="掰掰")])
    return

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    message = event.message.text
    if message == "紀錄":
        if get_cols("Log").find_one({"user_id": event.source.user_id})["funcs"] == "":
            update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": "funcs_menu"}})
            generate_quick_reply_response(event, "請選擇以下功能", [
                QuickReplyItem(
                    action=DatetimePickerAction(
                        label="新增紀錄",
                        data="select",
                        mode="date"
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label="查詢紀錄",
                        data="get"
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label="退出",
                        data="exit"
                    )
                )
            ])
            return
        else:
            update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": ""}})
            reply_line_message(event, [TextMessage(text="請重新開始記錄")])
            return
    else:
        # 處於建立紀錄流程中
        if get_cols("Log").find_one({"user_id": event.source.user_id})["funcs"] == "create_record":
            record_date = get_cols("Log").find_one({"user_id": event.source.user_id}).get("date")
            if record_date:
                insert_data("Event", {
                    "user_id": event.source.user_id,
                    "timestamp": event.timestamp,
                    "record_date": record_date,
                    "content": message
                })
                update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": ""}})
                reply_line_message(event, [TextMessage(text="紀錄完成")])
                return
            else:
                update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": ""}})
                reply_line_message(event, [TextMessage(text="未正確選擇時間，請重新開始記錄")])
                return
        else:
            # 其他狀況暫不處理
            update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": ""}})
            return

@line_handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    if data == "select":
        record = get_cols("Log").find_one({"user_id": event.source.user_id})
        if record and record.get("funcs") == "funcs_menu":
            update_data("Log", {"user_id": event.source.user_id}, {"$set": {
                "timestamp": event.timestamp,
                "funcs": "create_record",
                "date": event.postback.params["date"]
            }})
            reply_line_message(event, [
                TextMessage(text=f"已選擇日期: {event.postback.params['date']}"),
                TextMessage(text="請輸入內容")
            ])
            return
        else:
            update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": ""}})
            reply_line_message(event, [TextMessage(text="未正確選擇功能，請重新開始記錄")])
            return

    if data == "get":
        records = list(get_cols("Event").find({"user_id": event.source.user_id}))
        if records:
            contents = []
            for rec in records:
                block = {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "contents": [
                                        {
                                            "type": "text",
                                            "text": rec.get("content"),
                                            "wrap": True,
                                            "weight": "bold"
                                        },
                                        {
                                            "type": "text",
                                            "text": "期限：" + rec.get("record_date"),
                                            "flex": 2,
                                            "weight": "bold"
                                        }
                                    ],
                                    "flex": 3,
                                    "alignItems": "flex-start"
                                },
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "刪除",
                                        "data": f"delete&{rec.get('content')}"
                                    },
                                    "style": "primary",
                                    "flex": 1,
                                    "margin": "none",
                                    "color": "#c1121f",
                                    "height": "sm"
                                }
                            ],
                            "alignItems": "center"
                        }
                    ]
                }
                contents.append(block)
            
            # 將所有區塊放進同一個 bubble 的 body 中
            flex_message_json = {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": contents
                },
                "styles": {
                    "body": {
                        "backgroundColor": "#fdf0d5"
                    }
                }
            }
            flex_message_str = json.dumps(flex_message_json)
            reply_line_message(event, [FlexMessage(alt_text='紀錄', contents=FlexContainer.from_json(flex_message_str))])
        else:
            reply_line_message(event, [TextMessage(text="無紀錄")])
        return

    if data == "exit":
        update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": ""}})
        reply_line_message(event, [TextMessage(text="退出紀錄")])
        return

    if "delete" in data:
        content = data.split("&")[1]
        delete_data("Event", {"user_id": event.source.user_id, "content": content})
        reply_line_message(event, [TextMessage(text="刪除成功")])
        update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": ""}})
        return

    else:
        update_data("Log", {"user_id": event.source.user_id}, {"$set": {"timestamp": event.timestamp, "funcs": ""}})
        return

def generate_quick_reply_response(event, message, items):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(
                        text=message,
                        quick_reply=QuickReply(
                            items=items
                        )
                    )
                ]
            )
        )

def reply_line_message(event, messages):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages
            )
        )

def handle_flex_json(event, flex_json):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    FlexMessage(
                        alt_text="Flex Message",
                        contents=flex_json
                    )
                ]
            )
        )

# 定時推播訊息
def push_message_job():
    global LASTPUSHDATE
    taipei_tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(taipei_tz)
    current_time_str = now.strftime("%H:%M")
    records = list(get_cols("Event").find({"user_id": USER_ID}))
    if records:
        contents = []
        for rec in records:
            block = {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": rec.get("content"),
                                        "wrap": True,
                                        "weight": "bold"
                                    },
                                    {
                                        "type": "text",
                                        "text": "期限：" + rec.get("record_date"),
                                        "flex": 2,
                                        "weight": "bold"
                                    }
                                ],
                                "flex": 3,
                                "alignItems": "flex-start"
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "刪除",
                                    "data": f"delete&{rec.get('content')}"
                                },
                                "style": "primary",
                                "flex": 1,
                                "margin": "none",
                                "color": "#c1121f",
                                "height": "sm"
                            }
                        ],
                        "alignItems": "center"
                    }
                ]
            }
            contents.append(block)
        
        # 將所有區塊放進同一個 bubble 的 body 中
        flex_message_json = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": contents
            },
            "styles": {
                "body": {
                    "backgroundColor": "#fdf0d5"
                }
            }
        }
        flex_message_str = json.dumps(flex_message_json)

    # 檢查現在時間是否符合條件
    if now.hour == PUSH_HOUR and now.minute == PUSH_MINUTE:
        if LASTPUSHDATE != now.date():  # 確保今天還沒推播過
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=USER_ID,
                        messages=[FlexMessage(alt_text='紀錄', contents=FlexContainer.from_json(flex_message_str))]
                    )
                )
                print(f"[{current_time_str}] 訊息已推送")
                LASTPUSHDATE = now.date()

def schedule_loop():
    while True:
        push_message_job()
        time.sleep(30)  # 每 30 秒檢查一次

# 啟動背景檢查
threading.Thread(target=schedule_loop, daemon=True).start()

# 資料庫CRUD
def get_cols(collection):
    return db[collection]

def find_all_data(collection):
    return get_cols(collection).find()

def insert_data(collection, data):
    get_cols(collection).insert_one(data)

def update_data(collection, query, data):
    get_cols(collection).update_one(query, data)

def delete_data(collection, data):
    get_cols(collection).delete_one(data)

if __name__ == "__main__":
    app.run()