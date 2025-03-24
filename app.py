from flask import Flask, request, abort
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)

import os

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
    
line_handler = WebhookHandler(CHANNEL_SECRET)

configuration = Configuration(
    access_token=CHANNEL_ACCESS_TOKEN
)

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

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_messsage(event):
    messages = []
    messages.append(TextMessage(text=event.message.text))
    reply_message(event, messages)
    
def reply_message(event, messages):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages
            )
        )

def delete_all_rich_menu():
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        richmenu_list = line_bot_api.get_rich_menu_list()
        for richmenu in richmenu_list.richmenus:
            richmenu_id = richmenu.rich_menu_id
            line_bot_api.delete_rich_menu(richmenu_id)
            print(f"Deleted richmenu: {richmenu_id}")

delete_all_rich_menu()
        
if __name__ == "__main__":
    app.run()