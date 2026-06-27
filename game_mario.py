"""🍄 بازی ماریو دونفره با سیستم لابی"""

import random
import string
from datetime import datetime, timedelta
from collections import defaultdict

class MarioGame:
    """Single Mario Game Instance"""
    
    def __init__(self, lobby_code):
        self.lobby_code = lobby_code
        self.players = {}  # {user_id: {"name": ..., "x": 0, "y": 3, "lives": 3, ...}}
        self.enemies = [(3, 4), (6, 4)]
        self.coins = [(3, 1), (7, 2)]
        self.coins_collected = defaultdict(int)
        self.active = True
        self.winner = None
        
        self.map = [
            "☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️",
            "☁️ ☁️ ☁️ ❓ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️",
            "☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ 🏰",
            "🟫🌱🌱🌱🌱🌱🌱🌱🌱🟫",
            "🟫🟫🟫🌱🌱🟫🟫🌱🟫🟫",
        ]
    
    def add_player(self, user_id, name):
        """Add player to game"""
        self.players[user_id] = {
            "name": name,
            "x": 0,
            "y": 3,
            "lives": 3,
            "score": 0,
        }
    
    def move(self, user_id, direction):
        """Move player"""
        if user_id not in self.players or not self.active:
            return "بازی شروع نشده!"
        
        player = self.players[user_id]
        px, py = player["x"], player["y"]
        
        # حرکت
        if direction == "right" and px < 9:
            px += 1
        elif direction == "left" and px > 0:
            px -= 1
        elif direction == "up" and py == 3:
            py = 2
            # سکه
            if (px, 1) in self.coins:
                self.coins.remove((px, 1))
                self.coins_collected[user_id] += 1
                player["score"] += 10
        
        # گرانش
        if py == 2 and direction != "up":
            py = 3
        
        # دشمن
        if (px, py) in self.enemies:
            player["lives"] -= 1
            if player["lives"] <= 0:
                self.active = False
                player["score"] -= 50
            px, py = 0, 3
        
        # سکه روزمین
        if (px, py) in self.coins:
            self.coins.remove((px, py))
            self.coins_collected[user_id] += 1
            player["score"] += 10
        
        # رسیدن به هدف
        if px == 9 and py in [2, 3]:
            self.active = False
            self.winner = user_id
            player["score"] += 100
        
        player["x"], player["y"] = px, py
        
        return self.render()
    
    def render(self):
        """Render game state"""
        lines = []
        for y, row in enumerate(self.map):
            line = ""
            for x, cell in enumerate(row):
                # بازیکن‌ها
                players_here = [uid for uid, p in self.players.items() if p["x"] == x and p["y"] == y]
                if players_here:
                    if len(players_here) > 1:
                        line += "👥"
                    else:
                        line += "🍄"
                # دشمن
                elif any(ex == x and ey == y for ex, ey in self.enemies):
                    line += "👾"
                # سکه
                elif any(cx == x and cy == y for cx, cy in self.coins):
                    line += "🪙"
                # هدف
                elif x == 9 and y == 2:
                    line += "🏰"
                else:
                    line += cell
            lines.append(line)
        
        # Stats
        stats = "\n════════════════════\n"
        for uid, player in self.players.items():
            stats += f"🍄 {player['name']}: ❤️ {player['lives']} | 🪙 {self.coins_collected[uid]} | 🏆 {player['score']}\n"
        
        if self.winner:
            winner_name = self.players[self.winner]["name"]
            stats += f"\n🎉 {winner_name} برنده شد!"
        elif not self.active:
            stats += f"\n💀 بازی تموم شد!"
        
        return "\n".join(lines) + stats


class MarioLobby:
    """Mario Lobby Manager"""
    
    def __init__(self):
        self.lobbies = {}  # {code: {"owner": user_id, "players": [...], "game": MarioGame, "created": datetime}}
        self.user_lobbies = {}  # {user_id: lobby_code}
    
    def create_lobby(self, user_id, name):
        """Create new lobby"""
        code = self._generate_code()
        
        self.lobbies[code] = {
            "owner": user_id,
            "owner_name": name,
            "players": [user_id],
            "player_names": {user_id: name},
            "game": None,
            "created": datetime.now(),
            "active": True,
        }
        
        self.user_lobbies[user_id] = code
        return code
    
    def join_lobby(self, code, user_id, name):
        """Join existing lobby"""
        if code not in self.lobbies:
            return "❌ کد صحیح نیست"
        
        lobby = self.lobbies[code]
        
        if not lobby["active"]:
            return "❌ لابی بسته شده"
        
        if len(lobby["players"]) >= 2:
            return "❌ لابی پر شده"
        
        lobby["players"].append(user_id)
        lobby["player_names"][user_id] = name
        self.user_lobbies[user_id] = code
        
        if len(lobby["players"]) == 2:
            return "both_ready"
        
        return "joined_waiting"
    
    def start_game(self, code):
        """Start game"""
        if code not in self.lobbies:
            return None
        
        lobby = self.lobbies[code]
        
        if len(lobby["players"]) != 2:
            return None
        
        game = MarioGame(code)
        for uid in lobby["players"]:
            game.add_player(uid, lobby["player_names"][uid])
        
        lobby["game"] = game
        return game
    
    def get_lobby_owner(self, code):
        """Get lobby owner"""
        if code in self.lobbies:
            return self.lobbies[code]["owner"]
        return None
    
    def get_user_lobby(self, user_id):
        """Get user's lobby code"""
        return self.user_lobbies.get(user_id)
    
    def get_game(self, code):
        """Get game from lobby"""
        if code in self.lobbies:
            return self.lobbies[code]["game"]
        return None
    
    def _generate_code(self):
        """Generate 6-digit code"""
        while True:
            code = ''.join(random.choices(string.digits, k=6))
            if code not in self.lobbies:
                return code
    
    def cleanup_old_lobbies(self, max_age_minutes=10):
        """Remove old lobbies"""
        now = datetime.now()
        to_remove = []
        
        for code, lobby in self.lobbies.items():
            age = (now - lobby["created"]).total_seconds() / 60
            if age > max_age_minutes:
                to_remove.append(code)
                # Remove from user_lobbies
                for uid in lobby["players"]:
                    if self.user_lobbies.get(uid) == code:
                        del self.user_lobbies[uid]
        
        for code in to_remove:
            del self.lobbies[code]
