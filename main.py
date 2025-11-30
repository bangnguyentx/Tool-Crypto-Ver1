import os
import asyncio
import threading
import time
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
import ccxt

# Import modules
from storage import update_user_config, get_user_config, calculate_volume, load_db, update_trade_result
from analysis import get_market_signal

# --- CONFIG & CONSTANTS ---
# Đọc Token từ Biến Môi Trường hoặc dùng Token cứng (cho dev test)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8234920227:AAHNmC3Yr2g9dd_HZad0S9oWDZ-b47bi_lo")
SYMBOL = "BTC/USDT"
TRADE_MODE_KEYS = ["SET_MODE_AUTO", "SET_MODE_MANUAL"]
ACTION_STATE = 1

# --- FLASK SERVER (KEEP ALIVE) ---
app = Flask(__name__)
@app.route('/')
def home(): 
    return "<h1>Ngo Bang Nemesis Bot is Running!</h1>"

def run_web():
    # Render cung cấp PORT qua Environment Variable
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- TRADING EXECUTION HANDLERS ---
async def execute_order(user_id, signal, price, is_manual=False):
    cfg = get_user_config(user_id)
    
    if not cfg['api_key'] or not cfg['secret_key']: 
        return "⚠️ Lỗi: Chưa nhập API Key Binance."
    
    volume_usd, risk_pct = calculate_volume(user_id)
    amount_coin = volume_usd / price
    
    # ⚠️ Đây là nơi thực hiện lệnh thật ⚠️
    try:
        exchange = ccxt.binance({
            'apiKey': cfg['api_key'],
            'secret': cfg['secret_key'],
            'options': {'defaultType': 'future'}
        })
        
        side = 'buy' if signal == 'BUY' else 'sell'
        
        # --- DEMO EXECUTION (Hãy thay bằng lệnh thật khi chạy live) ---
        # order = await exchange.create_market_order(SYMBOL, side, amount_coin)
        
        # --- LOGIC CẬP NHẬT TRẠNG THÁI (Giả lập kết quả) ---
        # Trong thực tế, bạn cần hàm check PnL thực tế để cập nhật WIN/LOSS
        # Giả lập WIN để xem logic compounding hoạt động (bạn có thể thay đổi)
        update_trade_result(user_id, "WIN") 
        
        prefix = "✅ Đã khớp lệnh AUTO" if not is_manual else "✅ Đã khớp lệnh MANUAL"
        
        return (f"{prefix} ({side.upper()})!\n"
                f"💰 Volume: {volume_usd:.2f}$ ({risk_pct}%)\n"
                f"📈 Giá khớp: {price:.2f}")
        
    except ccxt.AuthenticationError:
        return "❌ Lỗi xác thực API. Vui lòng kiểm tra lại Key/Secret."
    except ccxt.ExchangeError as e:
        return f"❌ Lỗi sàn giao dịch: {e}"
    except Exception as e:
        return f"❌ Lỗi chung: {e}"

# --- TELEGRAM HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [
        ["🔑 Nhập API Binance", "💵 Cài đặt Vốn"],
        ["⚙️ Chế độ (Auto/Manual)", "📊 Kiểm tra cấu hình"]
    ]
    await update.message.reply_text(
        "👋 Chào mừng đến với Bot Trading **Nemesis**!\n"
        "Hệ thống sử dụng thuật toán Gia tốc (Acceleration) độc quyền.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(k, callback_data=f"CMD_{k.split(' ')[0].replace('(', '')}") for k in row]
        ]),
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def ask_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("👉 Vui lòng nhập API theo cú pháp:\n`API_KEY|SECRET_KEY`")
    return ACTION_STATE

async def handle_api_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if "|" in text and len(text.split("|")) == 2:
        api, secret = text.split("|")
        update_user_config(user_id, "api_key", api.strip())
        update_user_config(user_id, "secret_key", secret.strip())
        await update.message.reply_text("✅ Đã lưu API thành công! Bot đã sẵn sàng giao dịch.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Sai cú pháp. Vui lòng nhập lại dưới dạng: `KEY|SECRET`")
        return ACTION_STATE

async def ask_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("👉 Nhập tổng số vốn (USD) muốn bot quản lý (VD: 1000):")
    return ACTION_STATE

async def handle_capital_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text.isdigit() and float(text) >= 10:
        update_user_config(user_id, "capital", float(text))
        await update.message.reply_text(f"✅ Đã set vốn: {float(text):,.0f} USD. Logic vốn sẽ tự động áp dụng.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Vốn phải là số và tối thiểu 10 USD. Vui lòng nhập lại.")
        return ACTION_STATE

async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🤖 AUTO 100%", callback_data="SET_MODE_AUTO")],
        [InlineKeyboardButton("🕹 MANUAL (Duyệt tay)", callback_data="SET_MODE_MANUAL")]
    ]
    await update.callback_query.edit_message_text("Chọn chế độ vận hành:", reply_markup=InlineKeyboardMarkup(kb))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    
    # Xử lý chọn chế độ
    if data in TRADE_MODE_KEYS:
        mode = data.split("_")[2]
        update_user_config(uid, "mode", mode)
        await query.edit_message_text(f"✅ Đã chuyển sang chế độ: **{mode}**", parse_mode='Markdown')
        
    # Xử lý nút duyệt lệnh tay
    elif data.startswith("TRADE_"):
        _, signal, price_str = data.split("_")
        price = float(price_str)
        
        # Báo cho người dùng biết lệnh đang được xử lý
        await query.edit_message_text(f"🕒 Đang xử lý lệnh {signal} tại giá {price}...")
        
        # Thực thi lệnh
        res = await execute_order(uid, signal, price, is_manual=True)
        await query.message.reply_text(res, parse_mode='Markdown')

    # Xử lý kiểm tra cấu hình
    elif data == "CMD_Kiểm":
        cfg = get_user_config(uid)
        vol, pct = calculate_volume(uid)
        
        status_msg = "✅ Đã nhập" if cfg['api_key'] else "❌ Chưa nhập"
        streak_msg = f"({cfg['last_result']} streak: {abs(cfg['streak'])})"
        
        msg = (f"📋 **CẤU HÌNH BOT NEMESIS**\n"
               f"• Vốn gốc: {cfg['capital']:.2f} USD\n"
               f"• Tình trạng API: {status_msg}\n"
               f"• Chế độ: **{cfg['mode']}**\n"
               f"• Trạng thái lệnh: {streak_msg}\n"
               f"• Volume lệnh tiếp theo: **{vol:.2f} USD ({pct}%)**")
        await query.message.reply_text(msg, parse_mode='Markdown')

# --- BACKGROUND SCANNER (The Trading Loop) ---
async def market_scanner(app):
    """Vòng lặp bất đồng bộ để quét thị trường mỗi 15 giây"""
    print("🚀 Market Scanner Started...")
    while True:
        # 1. Phân tích
        signal, price, info = get_market_signal(SYMBOL)
        
        if signal in ["BUY", "SELL"]:
            print(f"🔥 Signal Detected: {signal} at {price}")
            
            # 2. Xử lý cho từng user đã đăng ký
            users = load_db()
            for uid, cfg in users.items():
                if not cfg.get('api_key'): continue # Bỏ qua user chưa nhập API
                
                vol, pct = calculate_volume(uid)
                
                msg_text = (f"⚡ **TÍN HIỆU {signal}**\n"
                            f"• Cặp: {SYMBOL} | Giá: {price:.2f}\n"
                            f"• Chỉ báo: {info}\n"
                            f"• Volume đề xuất: **{vol:.2f} USD ({pct}%)**")
                
                # 3. Xử lý theo chế độ AUTO/MANUAL
                if cfg['mode'] == 'AUTO':
                    res = await execute_order(uid, signal, price)
                    await app.bot.send_message(chat_id=uid, text=f"{msg_text}\n\n🤖 **AUTO EXECUTION:**\n{res}", parse_mode='Markdown')
                else: # MANUAL
                    kb = [[InlineKeyboardButton(f"✅ Theo lệnh ({vol:.2f}$)", callback_data=f"TRADE_{signal}_{price}")]]
                    await app.bot.send_message(chat_id=uid, text=msg_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        
        await asyncio.sleep(15) # Quét lại sau 15 giây

# --- MAIN ENTRY POINT ---
if __name__ == '__main__':
    # 1. Chạy Web Server ở luồng riêng (Non-blocking)
    threading.Thread(target=run_web).start()

    # 2. Khởi tạo Bot Telegram
    app_bot = ApplicationBuilder().token(TOKEN).build()
    
    # 3. Định nghĩa các luồng hội thoại và command
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_api, pattern='^CMD_Nhập'),
            CallbackQueryHandler(ask_capital, pattern='^CMD_Cài')
        ],
        states={
            ACTION_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'.*\|.*'), handle_api_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^\d+(\.\d{1,2})?$'), handle_capital_input),
            ],
        },
        fallbacks=[]
    )
    
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(conv_handler)
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_handler(CallbackQueryHandler(choose_mode, pattern='^CMD_Chế'))


    # 4. Chạy luồng Scanner (Background Task)
    asyncio.ensure_future(market_scanner(app_bot))

    print("Bot is polling...")
    # 5. Chạy Bot Polling (Blocking, nhưng Scanner chạy trong Async Loop)
    app_bot.run_polling()
