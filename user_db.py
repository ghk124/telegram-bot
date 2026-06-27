"""💾 دیتابیس کاربر و جدول امتیازات"""

import json
import os
from datetime import datetime
from collections import defaultdict

class UserDatabase:
    """User database with JSON storage"""
    
    def __init__(self, db_file="users_data.json"):
        self.db_file = db_file
        self.users = self._load_db()
    
    def _load_db(self):
        """Load database from file"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_db(self):
        """Save database to file"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving DB: {e}")
    
    def create_user(self, user_id, name):
        """Create new user if not exists"""
        user_id_str = str(user_id)
        
        if user_id_str not in self.users:
            self.users[user_id_str] = {
                "id": user_id,
                "name": name,
                "score": 0,
                "games_played": 0,
                "wins": 0,
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "stats": {
                    "mario_games": 0,
                    "mario_wins": 0,
                    "total_score": 0,
                }
            }
            self._save_db()
    
    def update_user(self, user_id, **kwargs):
        """Update user data"""
        user_id_str = str(user_id)
        
        if user_id_str in self.users:
            self.users[user_id_str].update(kwargs)
            self.users[user_id_str]["last_active"] = datetime.now().isoformat()
            self._save_db()
    
    def add_score(self, user_id, points, game_type="general"):
        """Add score to user"""
        user_id_str = str(user_id)
        
        if user_id_str in self.users:
            self.users[user_id_str]["score"] += points
            self.users[user_id_str]["stats"]["total_score"] += points
            
            if game_type == "mario":
                self.users[user_id_str]["stats"]["mario_games"] += 1
            
            self._save_db()
    
    def add_win(self, user_id, game_type="general"):
        """Add win to user"""
        user_id_str = str(user_id)
        
        if user_id_str in self.users:
            self.users[user_id_str]["wins"] += 1
            self.users[user_id_str]["games_played"] += 1
            
            if game_type == "mario":
                self.users[user_id_str]["stats"]["mario_wins"] += 1
                self.users[user_id_str]["stats"]["mario_games"] += 1
            
            self._save_db()
    
    def get_user(self, user_id):
        """Get user data"""
        user_id_str = str(user_id)
        return self.users.get(user_id_str)
    
    def get_leaderboard(self, limit=10, sort_by="score"):
        """Get leaderboard"""
        users_list = list(self.users.values())
        
        if sort_by == "score":
            users_list.sort(key=lambda x: x.get("score", 0), reverse=True)
        elif sort_by == "wins":
            users_list.sort(key=lambda x: x.get("wins", 0), reverse=True)
        elif sort_by == "mario_wins":
            users_list.sort(key=lambda x: x.get("stats", {}).get("mario_wins", 0), reverse=True)
        
        return [(u["name"], u.get(sort_by, 0)) for u in users_list[:limit]]
    
    def get_mario_leaderboard(self, limit=10):
        """Get mario specific leaderboard"""
        users_list = list(self.users.values())
        users_list.sort(key=lambda x: x.get("stats", {}).get("mario_wins", 0), reverse=True)
        
        result = []
        for u in users_list[:limit]:
            if u.get("stats", {}).get("mario_games", 0) > 0:
                wins = u.get("stats", {}).get("mario_wins", 0)
                games = u.get("stats", {}).get("mario_games", 0)
                result.append((u["name"], wins, games))
        
        return result
    
    def get_stats(self, user_id):
        """Get user stats"""
        user = self.get_user(user_id)
        if not user:
            return None
        
        return {
            "name": user["name"],
            "score": user.get("score", 0),
            "wins": user.get("wins", 0),
            "games": user.get("games_played", 0),
            "mario_wins": user.get("stats", {}).get("mario_wins", 0),
            "mario_games": user.get("stats", {}).get("mario_games", 0),
        }
