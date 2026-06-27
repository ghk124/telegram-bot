"""🧠 موتور AI با حافظه و OpenAI"""

import json
import os
from datetime import datetime
from collections import defaultdict
import openai

class AIEngine:
    def __init__(self, api_key):
        """Initialize AI"""
        openai.api_key = api_key
        self.user_memory = defaultdict(list)  # {user_id: [messages]}
        self.max_memory = 1000  # کلمات
    
    def add_to_memory(self, user_id, message):
        """Add message to memory"""
        words = len(message.split())
        self.user_memory[user_id].append({
            "text": message,
            "time": datetime.now().isoformat(),
            "words": words
        })
        
        # محدود کردن حافظه
        while self._count_words(user_id) > self.max_memory:
            self.user_memory[user_id].pop(0)
    
    def _count_words(self, user_id):
        """Count total words in memory"""
        return sum(msg["words"] for msg in self.user_memory[user_id])
    
    def get_user_memory(self, user_id):
        """Get user memory"""
        return [msg["text"] for msg in self.user_memory[user_id]]
    
    def get_response(self, user_id, message):
        """Get AI response"""
        # ذخیره پیام
        self.add_to_memory(user_id, message)
        
        try:
            # Build context from memory
            memory_text = "\n".join(self.get_user_memory(user_id)[-10:])  # آخرین ۱۰ پیام
            
            system_prompt = f"""تو ربات هوشمند فارسی هستی.
            
مکالمات قبلی کاربر:
{memory_text}

با دقت و طبیعی جواب بده. فارسی صحیح استفاده کن."""
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                temperature=0.7,
                max_tokens=200,
                timeout=10
            )
            
            ai_response = response.choices[0].message.content
            self.add_to_memory(user_id, f"AI: {ai_response}")
            
            return ai_response
        
        except Exception as e:
            # Fallback
            return f"معذرت، خطا: {str(e)}\n\nپیامت: {message}"
    
    def clear_memory(self, user_id):
        """Clear user memory"""
        self.user_memory[user_id] = []
