import os
import logging
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # group chat id để gửi tự động lúc 18:30
API_URL = "https://api-ban-xo-so-cua-ban.com/xsmb"

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


async def fetch_xsmb() -> str:
    """Gọi API và format kết quả XSMB."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(API_URL)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.exception("Lỗi gọi API")
        return f"❌ Không lấy được kết quả XSMB: {e}"

    # Cố gắng đọc linh hoạt các key phổ biến
    d = data.get("data", data)

    def g(*keys, default="..."):
        for k in keys:
            if isinstance(d, dict) and k in d and d[k]:
                v = d[k]
                if isinstance(v, list):
                    return " - ".join(str(x) for x in v)
                return str(v)
        return default

    ngay = g("date", "ngay", "Ngay", default=datetime.now(VN_TZ).strftime("%d/%m/%Y"))
    db = g("special", "dac_biet", "DB", "ĐB")
    g1 = g("first", "giai_nhat", "G1")
    g2 = g("second", "giai_nhi", "G2")
    g3 = g("third", "giai_ba", "G3")
    g4 = g("fourth", "giai_tu", "G4")
    g5 = g("fifth", "giai_nam", "G5")
    g6 = g("sixth", "giai_sau", "G6")
    g7 = g("seventh", "giai_bay", "G7")

    return (
        "🎯 KẾT QUẢ XỔ SỐ MIỀN BẮC\n\n"
        f"📅 Ngày: {ngay}\n\n"
        f"🏆 Đặc Biệt: {db}\n"
        f"🥇 Giải nhất: {g1}\n"
        f"🥈 Giải nhì: {g2}\n"
        f"🥉 Giải ba: {g3}\n"
        f"🎖 Giải tư: {g4}\n"
        f"🎯 Giải năm: {g5}\n"
        f"🎲 Giải sáu: {g6}\n"
        f"🍀 Giải bảy: {g7}"
    )


async def xsmb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await fetch_xsmb()
    await update.message.reply_text(msg)


async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        logger.warning("Chưa cấu hình CHAT_ID, bỏ qua job tự động.")
        return
    msg = await fetch_xsmb()
    await context.bot.send_message(chat_id=int(CHAT_ID), text=msg)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot XSMB sẵn sàng! Gõ /xsmb để xem kết quả.")


async def run_health_server():
    """Mở port HTTP cho Render web service."""
    from aiohttp import web

    async def health(_):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health server listening on :{port}")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Thiếu BOT_TOKEN env var")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("xsmb", xsmb_cmd))

    # Job mỗi ngày 18:30 giờ VN
    application.job_queue.run_daily(
        daily_job,
        time=time(hour=18, minute=30, tzinfo=VN_TZ),
        name="xsmb_daily",
    )

    await run_health_server()

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("Bot đang chạy...")
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
