from flask import Flask, render_template, request, jsonify
import requests
import datetime
import uuid
import os

app = Flask(__name__)

# Configuration - will use environment variables on Railway
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.getenv('AIRTABLE_TABLE_NAME')

# API endpoints
AIRTABLE_ENDPOINT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Headers for API calls
AIRTABLE_HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}

OPENAI_HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

def get_conversation_history(user_id, limit=5):
    """Get recent conversation history from Airtable"""
    try:
        params = {
            'filterByFormula': f"{{user_id}} = '{user_id}'",
            'sort[0][field]': 'timestamp',
            'sort[0][direction]': 'desc',
            'maxRecords': limit * 2
        }
        
        response = requests.get(AIRTABLE_ENDPOINT, headers=AIRTABLE_HEADERS, params=params, timeout=10)
        
        if response.status_code == 200:
            records = response.json().get('records', [])
            conversation = []
            
            for record in reversed(records):
                fields = record['fields']
                if 'question' in fields and fields['question']:
                    conversation.append(f"User: {fields['question']}")
                if 'response' in fields and fields['response']:
                    conversation.append(f"Assistant: {fields['response']}")
            
            return conversation[-10:]  # Return last 10 messages
        else:
            print(f"Error fetching conversation history: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"Error getting conversation history: {e}")
        return []

def save_to_airtable(user_id, message, response):
    """Save conversation exchange to Airtable"""
    try:
        # Save user question
        question_payload = {
            "fields": {
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "user_id": user_id,
                "bot_id": "flask_web_bot",
                "question": message,
                "tags": "web_chat"
            }
        }
        
        question_resp = requests.post(AIRTABLE_ENDPOINT, headers=AIRTABLE_HEADERS, json=question_payload, timeout=15)
        
        # Save bot response
        response_payload = {
            "fields": {
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "user_id": user_id,
                "bot_id": "flask_web_bot",
                "response": response[:1000],  # Limit length for Airtable
                "tags": "web_chat"
            }
        }
        
        response_resp = requests.post(AIRTABLE_ENDPOINT, headers=AIRTABLE_HEADERS, json=response_payload, timeout=15)
        
        return question_resp.status_code in (200, 201) and response_resp.status_code in (200, 201)
        
    except Exception as e:
        print(f"Error saving to Airtable: {e}")
        return False

def get_ai_response(message, conversation_history, user_id):
    """Get AI response with conversation context"""
    try:
        # Build conversation context
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant with memory. Use conversation history to provide contextual responses. Be friendly and remember details from previous messages."}
        ]
        
        # Add conversation history
        for msg in conversation_history[-6:]:  # Last 6 messages for context
            if msg.startswith("User: "):
                messages.append({"role": "user", "content": msg[6:]})
            elif msg.startswith("Assistant: "):
                messages.append({"role": "assistant", "content": msg[11:]})
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        # Call OpenAI API
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": messages,
            "max_tokens": 300,
            "temperature": 0.7
        }
        
        response = requests.post(OPENAI_ENDPOINT, headers=OPENAI_HEADERS, json=payload, timeout=30)
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip()
        else:
            print(f"OpenAI API error: {response.status_code}")
            return "I'm having trouble generating a response right now. Please try again."
            
    except Exception as e:
        print(f"Error getting AI response: {e}")
        return "I encountered an error while processing your message. Please try again."

@app.route('/')
def index():
    """Serve the chat interface"""
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages"""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        user_id = data.get('user_id')
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Generate user_id if not provided
        if not user_id:
            user_id = str(uuid.uuid4())
        
        print(f"Chat request from user {user_id}: {user_message}")
        
        # Get conversation history
        conversation_history = get_conversation_history(user_id)
        
        # Get AI response
        ai_response = get_ai_response(user_message, conversation_history, user_id)
        
        # Save conversation to Airtable
        save_success = save_to_airtable(user_id, user_message, ai_response)
        
        if not save_success:
            print("Warning: Failed to save conversation to Airtable")
        
        return jsonify({
            'response': ai_response,
            'user_id': user_id
        })
        
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.datetime.utcnow().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=5001, debug=True)