from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
import anthropic
import gspread
from google.oauth2.service_account import Credentials
import json
import os

app = Flask(__name__)

# ENV Variables
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_SHEET_ID   = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON")

def get_ai_response(user_message):
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        # স্টক ডাটা ছাড়াই সিম্পল রেসপন্স টেস্ট করার জন্য
        system_prompt = "তুমি রাহেলার নামে একজন ফ্যাক্টরি এসিস্ট্যান্ট। বাংলায় ছোট উত্তর দাও।"
        
        response = client.messages.create(
            model="claude-3-haiku-20240307", # দ্রুত গতির জন্য Haiku মডেল
            max_tokens=150,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"AI Error: {e}")
        return "আমি আপনার কথা বুঝতে পেরেছি, কিন্তু আমার সার্ভারে একটু সমস্যা হচ্ছে।"

@app.route("/voice", methods=["GET", "POST"])
def voice():
    resp = VoiceResponse()
    gather = Gather(input="speech", language="bn-BD", action="/respond", method="POST", timeout=5)
    gather.say("আসসালামু আলাইকুম। আমি রাহেলা। আমি আপনাকে কীভাবে সাহায্য করতে পারি?", language="bn-BD")
    resp.append(gather)
    return Response(str(resp), mimetype="text/xml")

@app.route("/respond", methods=["GET", "POST"])
def respond():
    user_speech = request.form.get("SpeechResult", "")
    resp = VoiceResponse()

    if not user_speech:
        resp.say("দুঃখিত, শুনতে পাইনি।", language="bn-BD")
        resp.redirect("/voice")
    else:
        # AI উত্তর জেনারেট করা
        ai_reply = get_ai_response(user_speech)
        gather = Gather(input="speech", language="bn-BD", action="/respond", method="POST", timeout=5)
        gather.say(ai_reply, language="bn-BD")
        resp.append(gather)

    return Response(str(resp), mimetype="text/xml")

@app.route("/")
def home():
    return "সার্ভার রানিং ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
