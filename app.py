from flask import Flask, render_template, request, jsonify
import requests
import datetime
import uuid
import os
import re

app = Flask(__name__)

# Configuration - Railway environment variables only
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

def needs_web_search(message):
    """Determine if message needs current web information"""
    search_triggers = [
        # Weather and conditions
        'weather', 'temperature', 'forecast', 'rain', 'snow', 'sunny', 'cloudy',
        # News and current events
        'news', 'latest', 'recent', 'current', 'breaking', 'happening', 'today',
        # Financial
        'stock', 'price', 'cost', 'worth', 'value', 'market', 'crypto', 'bitcoin',
        # Time-sensitive
        'now', 'today', 'this week', 'this month', 'currently',
        # Sports and events
        'score', 'game', 'match', 'winner', 'result', 'championship',
        # Business hours and availability
        'hours', 'open', 'closed', 'available',
        # Traffic and travel
        'traffic', 'route', 'directions', 'flight'
    ]
    
    message_lower = message.lower()
    return any(trigger in message_lower for trigger in search_triggers)

def web_search(query, num_results=3):
    """Search the web for current information using DuckDuckGo"""
    try:
        # DuckDuckGo Instant Answer API (free, no key required)
        search_url = "https://api.duckduckgo.com/"
        params = {
            'q': query,
            'format': 'json',
            'no_redirect': '1',
            'no_html': '1',
            'skip_disambig': '1'
        }
        
        response = requests.get(search_url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Try to get instant answer
            if data.get('AbstractText'):
                return f"Current information: {data['AbstractText'][:300]}"
            
            # Try to get definition
            if data.get('Definition'):
                return f"Current definition: {data['Definition'][:300]}"
            
            # Try to get answer
            if data.get('Answer'):
                return f"Current info: {data['Answer'][:300]}"
            
            # Try to get related topics
            if data.get('RelatedTopics'):
                topics = data['RelatedTopics'][:2]
                results = []
                for topic in topics:
                    if isinstance(topic, dict) and topic.get('Text'):
                        results.append(topic['Text'][:200])
                if results:
                    return f"Current information: {' | '.join(results)}"
        
        return f"I searched for current information about '{query}' but couldn't find specific real-time data. I'll provide a general response based on my knowledge."
        
    except Exception as e:
        print(f"Web search error: {e}")
        return None

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
                "bot_id": "flask_web_bot_level3",
                "question": message,
                "tags": "web_chat_level3"
            }
        }
        
        question_resp = requests.post(AIRTABLE_ENDPOINT, headers=AIRTABLE_HEADERS, json=question_payload, timeout=15)
        
        # Save bot response
        response_payload = {
            "fields": {
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "user_id": user_id,
                "bot_id": "flask_web_bot_level3",
                "response": response[:1000],  # Limit length for Airtable
                "tags": "web_chat_level3"
            }
        }
        
        response_resp = requests.post(AIRTABLE_ENDPOINT, headers=AIRTABLE_HEADERS, json=response_payload, timeout=15)
        
        return question_resp.status_code in (200, 201) and response_resp.status_code in (200, 201)
        
    except Exception as e:
        print(f"Error saving to Airtable: {e}")
        return False

def get_ai_response(message, conversation_history, user_id, search_results=None):
    """Get Level 3 AI response with conversation context and optional search results"""
    try:
        # Enhanced system prompt for Level 3
        system_prompt = """You are an intelligent AI assistant with perfect memory and access to current information. 

Key capabilities:
- You remember all previous conversations with this user
- You have access to real-time web search results when needed
- You provide contextual responses based on conversation history
- You're helpful, accurate, and engaging

Use conversation history to provide personalized responses. When you have current search results, integrate them naturally into your response."""

        # Build conversation context
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add recent conversation history for context
        for msg in conversation_history[-6:]:
            if msg.startswith("User: "):
                messages.append({"role": "user", "content": msg[6:]})
            elif msg.startswith("Assistant: "):
                messages.append({"role": "assistant", "content": msg[11:]})
        
        # Add current message with search context if available
        current_message = message
        if search_results:
            current_message = f"User question: {message}\n\nCurrent information from web search: {search_results}\n\nPlease provide a helpful response that incorporates the current information with your knowledge and our conversation history."
        
        messages.append({"role": "user", "content": current_message})
        
        # Call OpenAI API with enhanced parameters for Level 3
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": messages,
            "max_tokens": 400,
            "temperature": 0.7,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1
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
    """Handle chat messages with Level 3 intelligence"""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        user_id = data.get('user_id')
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Generate user_id if not provided
        if not user_id:
            user_id = str(uuid.uuid4())
        
        print(f"Level 3 chat request from user {user_id}: {user_message}")
        
        # Get conversation history
        conversation_history = get_conversation_history(user_id)
        
        # Check if we need to search the web
        search_results = None
        if needs_web_search(user_message):
            print("Performing web search for current information...")
            search_results = web_search(user_message)
            if search_results:
                print(f"Search results: {search_results[:100]}...")
        
        # Get Level 3 AI response with search context
        ai_response = get_ai_response(user_message, conversation_history, user_id, search_results)
        
        # Save conversation to Airtable
        save_success = save_to_airtable(user_id, user_message, ai_response)
        
        if not save_success:
            print("Warning: Failed to save conversation to Airtable")
        
        return jsonify({
            'response': ai_response,
            'user_id': user_id,
            'used_search': search_results is not None
        })
        
    except Exception as e:
        print(f"Error in Level 3 chat endpoint: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy', 
        'version': 'Level 3',
        'features': ['AI', 'Memory', 'Web Search'],
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
