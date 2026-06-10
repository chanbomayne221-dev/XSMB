"""
Telegram bot: gửi KQXS Miền Bắc khi gõ /xsmb, và auto gửi 18:30 (giờ VN) mỗi ngày.
Chạy ổn định trên Render (Free tier) — có HTTP health server bind cổng PORT.
"""
import os
import re
import html as ihtml
import logging
import asyncio
from datetime import time, datetime
from zoneinfo import ZoneInfo

import httpx
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, Defaults,
)

# ============ CONFIG ============
BOT_TOKEN = os.environ["BOT_TOKEN"]                  # bắt buộc
CHAT_ID   = os.getenv("CHAT_ID")                     # cho job tự gửi 18:30; có thể để trống
PORT      = int(os.getenv("PORT", "10000"))
VN_TZ     = ZoneInfo("Asia/Ho_Chi_Minh")

XSMB_URL  = "https://xosodaiphat.com/xsmb-xo-so-mien-bac.html"
UA = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("xsmb-bot")


# ============ SCRAPER ============
async def fetch_xsmb() -> str:
    """Tải HTML, trích các giải theo id 'mb_prize_*_item_*', trả về message đã format."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": UA}) as cli:
        r = await cli.get(XSMB_URL)
        r.raise_for_status()
        html = r.text

    def grab(prize_key: str) -> list[str]:
        # bắt mọi span có id=mb_prize_{key}_item_N, lấy nội dung số bên trong
        pat = re.compile(
            rf'id=["\']?mb_prize_{re.escape(prize_key)}_item_\d+["\']?[^>]*>(.*?)</span>',
            re.S,
        )
        out = []
        for m in pat.finditer(html):
            txt = re.sub(r"<[^>]+>", "", m.group(1))
            txt = ihtml.unescape(txt).strip()
            if txt:
                out.append(txt)
        return out

    db   = grab("DB")
    g1   = grab("1")
    g2   = grab("2")
    g3   = grab("3")
    g4   = grab("4")
    g5   = grab("5")
    g6   = grab("6")
    g7   = grab("7")

    if not db or not g1:
        raise RuntimeError("Không trích được dữ liệu (trang có thể đổi cấu trúc).")

    # lấy ngày từ trang nếu có
    mdate = re.search(r"ngày\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})", html, re.I)
    ngay  = mdate.group(1) if mdate else datetime.now(VN_TZ).strftime("%d/%m/%Y")

    def join(arr: list[str]) -> str:
        return " - ".join(arr) if arr else "—"

    msg = (
        "🎯 *KẾT QUẢ XỔ SỐ MIỀN BẮC*\n\n"
        f"📅 Ngày: *{ngay}*\n\n"
        f"🏆 Đặc Biệt: `{join(db)}`\n\n"
        f"🥇 Giải nhất: `{join(g1)}`\n\n"
        f"🥈 Giải nhì: `{join(g2)}`\n\n"
        f"🥉 Giải ba: `{join(g3)}`\n\n"
        f"🎖 Giải tư: `{join(g4)}`\n\n"
        f"🎯 Giải năm: `{join(g5)}`\n\n"
        f"🎲 Giải sáu: `{join(g6)}`\n\n"
        f"🍀 Giải bảy: `{join(g7)}`\n\n"
    )
    return msg


# ============ HANDLERS ============
async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Xin chào! Gõ /xsmb để xem kết quả Xổ Số Miền Bắc hôm nay.\n"
        "Bot tự gửi kết quả mỗi ngày lúc 18:30 (giờ VN)."
    )

async def cmd_chatid(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Chat ID: `{update.effective_chat.id}`",
                                    parse_mode="Markdown")

async def cmd_xsmb(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await fetch_xsmb()
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        log.exception("xsmb fail")
        await update.message.reply_text(f"❌ Không lấy được kết quả XSMB: {e}")

async def job_daily(ctx: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        log.warning("CHAT_ID chưa cấu hình; bỏ qua job hàng ngày.")
        return
    try:
        msg = await fetch_xsmb()
        await ctx.bot.send_message(chat_id=int(CHAT_ID), text=msg, parse_mode="Markdown")
    except Exception as e:
        log.exception("daily job fail")
        try:
            await ctx.bot.send_message(chat_id=int(CHAT_ID),
                                       text=f"❌ Lỗi gửi KQXSMB tự động: {e}")
        except Exception:
            pass


# ============ HEALTH SERVER (cho Render) ============
async def start_health_server():
    async def health(_req): return web.Response(text="ok")
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("Health server listening on :%s", PORT)


# ============ MAIN ============
async def post_init(app: Application):
    await start_health_server()
    # Job 18:30 giờ VN, mỗi ngày
    app.job_queue.run_daily(
        job_daily,
        time=time(hour=18, minute=30, tzinfo=VN_TZ),
        name="xsmb_daily_1830",
    )
    log.info("Đã lên lịch job 18:30 Asia/Ho_Chi_Minh.")


def main():
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .defaults(Defaults(parse_mode=None))
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("xsmb", cmd_xsmb))
    application.add_handler(CommandHandler("chatid", cmd_chatid))
    log.info("Bot starting…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
