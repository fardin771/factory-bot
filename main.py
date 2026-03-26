from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
import anthropic
import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime

app = Flask(__name__)

# ─── কনফিগারেশন ───────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_SHEET_ID   = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON")

# ─── Google Sheets কানেকশন ────────────────────────────────
def get_sheet():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_SHEET_ID).sheet1

def get_stock_data():
    """Google Sheets থেকে স্টক ডেটা পড়ে"""
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        stock_text = "বর্তমান স্টক:\n"
        for row in records:
            stock_text += f"- {row['পণ্যের নাম']}: {row['পরিমাণ']} {row['একক']}\n"
        return stock_text, records
    except Exception as e:
        print(f"Sheet Error: {e}")
        return "স্টক তথ্য বর্তমানে পাওয়া যাচ্ছে না।", []

def update_stock(product_name, quantity_change, reason="অর্ডার"):
    """স্টক আপডেট করে"""
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if row['পণ্যের নাম'].strip() == product_name.strip():
                current = int(row['পরিমাণ'])
                new_qty = current + quantity_change
                sheet.update_cell(i, 2, new_qty)
                
                # লগ যোগ করা
                try:
                    log_sheet = sheet.spreadsheet.worksheet("লগ")
                except:
                    log_sheet = sheet.spreadsheet.add_worksheet("লগ", 1000, 5)
                    log_sheet.append_row(["তারিখ", "পণ্য", "পরিবর্তন", "নতুন স্টক", "কারণ"])
                
                log_sheet.append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    product_name,
                    quantity_change,
                    new_qty,
                    reason
                ])
                return True, new_qty
        return False, 0
    except Exception as e:
        print(f"Update Error: {e}")
        return False, 0

# ─── Claude AI কথোপকথন ────────────────────────────────────
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
conversations = {}

def get_ai_response(call_sid, user_message):
    stock_info, _ = get_stock_data()
    system_prompt = f"""তুমি একটি ফ্যাক্টরির AI রিসেপশনিস্ট। তোমার নাম "রাহেলা"।
তুমি সবসময় বাংলায় কথা বলবে। সংক্ষিপ্ত ও স্পষ্ট উত্তর দেবে (ফোনে কথা বলার মতো)।

{stock_info}

তোমার কাজ:
1. কারো অর্ডার নেওয়া
2. স্টক সম্পর্কে তথ্য দেওয়া
3. অর্ডার নিলে বলো: "অর্ডার নিলাম: [পণ্য] [পরিমাণ]" — এই ফরম্যাটে

যদি স্টকে না থাকে বা কম থাকে তাহলে বিনয়ের সাথে জানাও।
উত্তর সবসময় ৩-৪ বাক্যের মধ্যে রাখো।"""

    if call_sid not in conversations:
        conversations[call_sid] = []

    conversations[call_sid].append({"role": "user", "content": user_message})

    response = client.messages.create(
        model="claude-3-sonnet-20240229", # মডেলের নাম আপডেট করা হয়েছে
        max_tokens=300,
        system=system_prompt,
        messages=conversations[call_sid]
    )

    ai_reply = response.content[0].text
    conversations[call_sid].append({"role": "assistant", "content": ai_reply})

    if "অর্ডার নিলাম:" in ai_reply:
        parse_and_update_order(ai_reply)

    return ai_reply

def parse_and_update_order(ai_reply):
    try:
        lines = ai_reply.split('\n')
        for line in lines:
            if "অর্ডার নিলাম:" in line:
                parts = line.replace("অর্ডার নিলাম:", "").strip().split()
                if len(parts) >= 2:
                    product = parts[0]
                    qty_str = ''.join(filter(str.isdigit, parts[1]))
                    if qty_str:
                        qty = int(qty_str)
                        update_stock(product, -qty, "ফোন অর্ডার")
    except Exception as e:
        print(f"Parsing error: {e}")

# ─── Twilio Webhook Routes ─────────────────────────────────
@app.route("/voice", methods=["GET", "POST"])
def voice():
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        language="bn-BD",
        action="/respond",
        method="POST",
        timeout=5,
        speech_timeout="auto"
    )
    # ভয়েস ইঞ্জিন আপডেট করা হয়েছে যাতে আরও স্বাভাবিক শোনায়
    gather.say("আসসালামু আলাইকুম। আমি রাহেলা, ফ্যাক্টরির এআই সহকারী। আপনি কি জানতে চান বা অর্ডার দিতে চান?", 
               language="bn-BD", voice="Google.bn-IN-Standard-A")
    resp.append(gather)
    return Response(str(resp), mimetype="text/xml")

@app.route("/respond", methods=["GET", "POST"])
def respond():
    call_sid = request.form.get("CallSid")
    user_speech = request.form.get("SpeechResult", "")
    resp = VoiceResponse()

    if not user_speech:
        resp.say("দুঃখিত, আপনার কথা শুনতে পাইনি। আবার বলুন।", language="bn-BD")
        resp.redirect("/voice")
        return Response(str(resp), mimetype="text/xml")

    try:
        ai_reply = get_ai_response(call_sid, user_speech)
    except Exception as e:
        print(f"AI Error: {e}")
        ai_reply = "দুঃখিত, আমি এই মুহূর্তে কানেক্ট করতে পারছি না।"

    gather = Gather(
        input="speech",
        language="bn-BD",
        action="/respond",
        method="POST",
        timeout=5,
        speech_timeout="auto"
    )
    gather.say(ai_reply, language="bn-BD")
    resp.append(gather)

    return Response(str(resp), mimetype="text/xml")

@app.route("/")
def home():
    return "ফ্যাক্টরি AI রিসেপশনিস্ট চালু আছে ✅"

@app.route("/respond", methods=["GET", "POST"])
def respond():
    """ব্যবহারকারীর কথার উত্তর দেয় এবং এখানে AI প্রসেসিং হবে"""
    call_sid = request.form.get("CallSid")
    user_speech = request.form.get("SpeechResult", "")
    resp = VoiceResponse()

    if not user_speech:
        resp.say("দুঃখিত, আপনার কথা শুনতে পাইনি। আবার বলুন।", language="bn-BD")
        resp.redirect("/voice")
        return Response(str(resp), mimetype="text/xml")

    try:
        ai_reply = get_ai_response(call_sid, user_speech)
    except Exception as e:
        print(f"AI Error: {e}")
        ai_reply = "দুঃখিত, আমি এই মুহূর্তে কানেক্ট করতে পারছি না।"

    gather = Gather(
        input="speech",
        language="bn-BD",
        action="/respond",
        method="POST",
        timeout=5,
        speech_timeout="auto"
    )
    gather.say(ai_reply, language="bn-BD")
    resp.append(gather)

    return Response(str(resp), mimetype="text/xml")

@app.route("/")
def home():
    return "ফ্যাক্টরি AI রিসেপশনিস্ট চালু আছে ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
