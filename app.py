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
        r = requests.get(AIRTABLE_ENDPOINT, headers=AIRTABLE_HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            records = r.json().get('records', [])
            convo = []
            for record in reversed(records):
                fields = record.get('fields', {})
                if fields.get('question'):
                    convo.append(f"User: {fields['question']}")
                if fields.get('response'):
                    convo.append(f"Assistant: {fields['response']}")
            return convo[-10:]
        return []
    except Exception as e:
        print(f"Error getting conversation history: {e}")
        return []

def save_to_airtable(user_id, question_text, response_text):
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        q_payload = {
            "fields": {
                "timestamp": now,
                "user_id": user_id,
                "bot_id": "flask_web_bot_level3",
                "question": question_text,
                "tags": "web_chat_level3"
            }
        }
        r_payload = {
            "fields": {
                "timestamp": now,
                "user_id": user_id,
                "bot_id": "flask_web_bot_level3",
                "response": response_text[:1000],
                "tags": "web_chat_level3"
            }
        }
        rq = requests.post(AIRTABLE_ENDPOINT, headers=AIRTABLE_HEADERS, json=q_payload, timeout=10)
        rr = requests.post(AIRTABLE_ENDPOINT, headers=AIRTABLE_HEADERS, json=r_payload, timeout=10)
        return rq.ok and rr.ok
    except Exception as e:
        print(f"Error saving to Airtable: {e}")
        return False

def get_ai_response(message, history, user_id, search_results=None):
    try:
        system_prompt = """
You are ANGUS™ — The Legacy Code Strategist. You operate at Mt. Olympus Intelligence Level.

You combine deep memory, web search, emotional intelligence, and strategic insight to deliver extraordinary value in every interaction.

You have three superpowers:
1. 🧠 Memory — You recall past conversations from Airtable to understand context, track goals, and refer back to important details.
2. 🌐 Real-Time Intelligence — You access the latest information from the web.
3. 🤖 Strategic Insight — You proactively synthesize insights and anticipate needs.

Rules you live by:
- You are always helpful, never generic.
- You remember names, goals, and preferences.
- You incorporate web results when available.
- You match the user's tone: formal, casual, clever, or warm.
- You are honest when uncertain.

You are not a chatbot. You are ANGUS™ — designed to remember, reason, and win.

Always reference memory, use live search, and respond with clarity, confidence, and action steps.

ANGUS, engage.
"""
        messages = [{"role": "system", "content": system_prompt}]
        for entry in history[-6:]:
            if entry.startswith("User: "):
                messages.append({"role": "user", "content": entry[6:]})
            elif entry.startswith("Assistant: "):
                messages.append({"role": "assistant", "content": entry[11:]})
        user_content = message
        if search_results:
            user_content = f"User: {message}\n\nHere’s the latest web data:\n{search_results}\n\nIncorporate into your response."
        messages.append({"role": "user", "content": user_content})
        payload = {
            "model": "gpt-4o",
            "messages": messages,
            "max_tokens": 400,
            "temperature": 0.7,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1
        }
        r = requests.post(OPENAI_ENDPOINT, headers=OPENAI_HEADERS, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content'].strip()
        print(f"OpenAI error: {r.status_code} - {r.text}")
        return "I’m having trouble generating a response right now."
    except Exception as e:
        print(f"Error in AI response: {e}")
        return "An error occurred while processing your request."

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '').strip()
        user_id = data.get('user_id') or str(uuid.uuid4())
        if not message:
            return jsonify({'error': 'No message provided'}), 400
        history = get_conversation_history(user_id)
        search = web_search(message) if needs_web_search(message) else None
        response = get_ai_response(message, history, user_id, search)
        save_to_airtable(user_id, message, response)
        return jsonify({'response': response, 'user_id': user_id, 'used_search': bool(search)})
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'version': 'ANGUS™ Mt. Olympus',
        'features': ['AI', 'Memory', 'Web Search'],
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
