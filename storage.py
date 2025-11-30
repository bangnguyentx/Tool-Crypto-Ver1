import json
import os
import threading

DATA_FILE = "user_data.json"
# Sử dụng Lock để ngăn xung đột khi nhiều luồng cùng ghi vào file JSON
lock = threading.Lock()

def load_db():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r") as f:
        try: return json.load(f)
        except json.JSONDecodeError: return {}

def save_db(data):
    with lock:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)

def get_user_config(user_id):
    db = load_db()
    return db.get(str(user_id), {
        "api_key": None, "secret_key": None,
        "capital": 1000, "mode": "MANUAL", 
        "streak": 0, "last_result": "LOSS" # Chuỗi thắng (>=0) hoặc chuỗi thua (<=0)
    })

def update_user_config(user_id, key, value):
    db = load_db()
    uid = str(user_id)
    if uid not in db: db[uid] = get_user_config(uid)
    db[uid][key] = value
    save_db(db)

def update_trade_result(user_id, result):
    """Cập nhật trạng thái Streak và Last Result sau mỗi lệnh"""
    cfg = get_user_config(user_id)
    current_streak = cfg['streak']
    
    if result == "WIN":
        new_streak = current_streak + 1
        update_user_config(user_id, "last_result", "WIN")
    else: # LOSS
        new_streak = current_streak - 1 # Dùng số âm để đánh dấu chuỗi thua
        update_user_config(user_id, "last_result", "LOSS")
        
    update_user_config(user_id, "streak", new_streak)


def calculate_volume(user_id):
    """Tính toán Volume theo Logic Smart Martingale (0.5% -> 2.0%)"""
    cfg = get_user_config(user_id)
    capital = cfg['capital']
    streak = cfg['streak']
    
    risk_pct = 0.5 # Mặc định
    
    # 1. Logic Phục hồi/Reset
    if streak <= -2:
        risk_pct = 0.5 # Thua lệnh gỡ -> Reset về mức an toàn 0.5%
    elif streak == -1:
        risk_pct = 1.0 # Thua lệnh đầu 0.5% -> Gấp lên 1.0% để gỡ
    
    # 2. Logic Lãi kép/Compounding
    elif streak >= 0:
        if streak == 0: risk_pct = 0.5
        elif streak == 1: risk_pct = 1.0
        elif streak == 2: risk_pct = 1.25
        else: risk_pct = 2.0 # Max
    
    amount_usd = (capital * risk_pct) / 100
    return amount_usd, risk_pct
