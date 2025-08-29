from flask import Flask, render_template, request, jsonify
import requests
import datetime
import uuid
import os

app = Flask(__name__)

# ENV CONFIG
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.getenv('AIRTABLE_TABLE_NAME')
GOOGLE_CSE_API_KEY = os.getenv('GOOGLE_CSE_API_KEY')
GOOGLE_CSE_CX_ID = os.getenv('GOOGLE_CSE_CX_ID')

AIRTABLE_ENDPOINT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

AIRTABLE_HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}
OPENAI_HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

def needs_web_search(message):
    triggers = ['weather','news','stock','today','price','crypto','bitcoin','traffic','open','hours','game','score','latest','currently']
    return any(t in message.lower() for t in triggers)

def web_search(query, num_results=3):
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': GOOGLE_CSE_API_KEY,
            'cx': GOOGLE_CSE_CX_ID,
            'q': query,
            'num': num_results
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            items = r.json().get('items', [])
            if items:
                return "\n".join([f"- {item['title']}: {item.get('snippet', '')}" for item in items])
            return f"No results found for '{query}'."
        return f"Search error {r.status_code}"
    except Exception as e:
        return f"Search failed: {e}"

def get_conversation_history(user_id, limit=5):
    try:
        params = {
            'filterByFormula': f"{{user_id}} = '{user_id}'",
            'sort[0][field]': 'timestamp',
            'sort[0][direction]': 'desc',
            'maxRecords': limit * 2
        }
        r = requests.get(AIRTABLE_ENDPOINT_
