import os
import re
import asyncio
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

import basedata as db

TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
OWNER_ID_2 = int(os.getenv("OWNER_ID_2", "0") or 0)
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "").lstrip("@")

db.init_db()


def owners():
    return {x for x in (OWNER_ID, OWNER_ID_2) if x}


def is_owner(uid):
    return uid in owners()


def rank_link():
    return db.get_config("rank_link", "")


def sub_channel():
    return db.get_config("sub_channel", "")


def owner_chat_url():
    return f"https://t.me/{OWNER_USERNAME}" if OWNER_USERNAME else None


async def delete_later(message, seconds=10):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except Exception:
        pass


async def send_temporary(chat, text, reply_markup=None, seconds=10):
    msg = await chat.send_message(text, reply_markup=reply_markup)
    asyncio.create_task(delete_later(msg, seconds))
    return msg


async def can_use(uid):
    if is_owner(uid):
        return True
    row = db.get_access(uid)
    if not row:
        return False
    try:
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > datetime.now(timezone.utc)
    except Exception:
        return False


def main_menu(owner=False):
    rows = [
        [InlineKeyboardButton("🔇 FORCE RANK", callback_data="force_help"),
         InlineKeyboardButton("🔊 UNFORCE", callback_data="unforce_help")],
        [InlineKeyboardButton("📋 DAFTAR FORCE", callback_data="list_force")],
        [InlineKeyboardButton("⚙️ SETELAN", callback_data="settings")],
        [InlineKeyboardButton("💰 BUY AKSES BOT", callback_data="buy_access")],
    ]
    if owner:
        rows.append([InlineKeyboardButton("👑 OWNER PANEL", callback_data="owner_panel")])
    rows.append([InlineKeyboardButton("🗑️ HAPUS MENU", callback_data="delete_menu")])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(
        "🤖 FORCE RANK BOT\n\nPilih menu:",
        reply_markup=main_menu(is_owner(u.id)),
    )


async def require_access(update):
    uid = update.effective_user.id
    if await can_use(uid):
        return True
    kb = [[InlineKeyboardButton("💰 BUY AKSES BOT", callback_data="buy_access")]]
    await update.effective_message.reply_text(
        "🔒 AKSES BELUM AKTIF\n\nSilakan beli akses bot terlebih dahulu.",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return False


async def resolve_target(update, context):
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        return update.message.reply_to_message.from_user
    if context.args:
        raw = context.args[0].lstrip("@")
        try:
            chat = await context.bot.get_chat("@" + raw)
            return chat
        except Exception:
            return None
    return None


async def forcerank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_access(update):
        return
    if update.effective_chat.type == "private":
        return await update.message.reply_text("Gunakan perintah ini di grup.")

    user = await resolve_target(update, context)
    if not user:
        return await update.message.reply_text("❌ Target tidak ditemukan. Gunakan reply atau /forcerank @username")

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user.id,
            ChatPermissions(can_send_messages=False),
        )
    except Exception as e:
        return await update.message.reply_text(f"❌ Gagal mute: {e}")

    db.add_force(update.effective_chat.id, user.id, user.username or "", user.full_name)

    rl = rank_link()
    sc = sub_channel()
    buttons = []

    if rl:
        buttons.append([InlineKeyboardButton("📝 ISI RANK", url=rl)])
    else:
        buttons.append([InlineKeyboardButton("📝 ISI RANK", callback_data="rank_not_set")])

    if sc:
        url = sc if sc.startswith("http") else "https://t.me/" + sc.lstrip("@")
        buttons.append([InlineKeyboardButton("📢 IKUTI CHANNEL", url=url)])
    else:
        buttons.append([InlineKeyboardButton("📢 IKUTI CHANNEL", callback_data="sub_not_set")])

    buttons.append([
        InlineKeyboardButton(
            "✅ SAYA SUDAH JOIN",
            callback_data=f"check:{update.effective_chat.id}:{user.id}",
        )
    ])

    text = (
        "🔔 FORCE RANK\n\n"
        f"👤 User: {user.full_name}\n"
        f"💎 Username: @{user.username or '-'}\n\n"
        "🔇 Status: MUTED\n"
        "📝 Rank: BELUM DIISI\n"
        "📢 Subscribe: BELUM\n\n"
        "Silakan isi rank dan subscribe channel.\n"
        "Setelah keduanya terpenuhi, mute dibuka otomatis."
    )
    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    # Hapus command admin 3 detik kemudian, notifikasi Force tetap ada.
    asyncio.create_task(delete_later(update.message, 3))


async def unforcerank(update, context):
    if not await require_access(update):
        return
    if update.effective_chat.type == "private":
        return await update.message.reply_text("Gunakan perintah ini di grup.")
    user = await resolve_target(update, context)
    if not user:
        return await update.message.reply_text("❌ Gunakan reply atau /unforcerank @username")
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user.id,
            ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_voice_notes=True,
                can_send_video_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
    except Exception as e:
        return await update.message.reply_text(f"❌ Gagal unmute: {e}")
    db.remove_force(update.effective_chat.id, user.id)
    msg = await update.message.reply_text(f"🔊 @{user.username or user.full_name} telah di-unmute.")
    asyncio.create_task(delete_later(update.message, 3))
    asyncio.create_task(delete_later(msg, 10))


async def save_setup(update, key, value, delete_command=True):
    value = value.strip()
    db.set_config(key, value)
    if delete_command:
        try:
            await update.message.delete()
        except Exception:
            pass
    label = "📝 LINK RANK" if key == "rank_link" else "📢 CHANNEL SUBSCRIBE"
    msg = await update.effective_chat.send_message(
        f"✅ {label} BERHASIL DISIMPAN\n\n{value}\n\nPesan ini akan dihapus otomatis dalam 10 detik."
    )
    asyncio.create_task(delete_later(msg, 10))


async def setrank(update, context):
    if not is_owner(update.effective_user.id):
        return
    if context.args:
        await save_setup(update, "rank_link", context.args[0])
        return
    try:
        await update.message.delete()
    except Exception:
        pass
    context.user_data["waiting"] = "rank"
    msg = await update.effective_chat.send_message(
        "📝 KIRIM LINK POST RANK\n\nContoh:\nhttps://t.me/channel/9\n\nPesan ini akan dihapus otomatis dalam 10 detik."
    )
    asyncio.create_task(delete_later(msg, 10))


async def setsub(update, context):
    if not is_owner(update.effective_user.id):
        return
    if context.args:
        await save_setup(update, "sub_channel", context.args[0])
        return
    try:
        await update.message.delete()
    except Exception:
        pass
    context.user_data["waiting"] = "sub"
    msg = await update.effective_chat.send_message(
        "📢 KIRIM CHANNEL WAJIB SUBSCRIBE\n\nContoh: @channelkamu\n\nPesan ini akan dihapus otomatis dalam 10 detik."
    )
    asyncio.create_task(delete_later(msg, 10))


async def text_setup(update, context):
    w = context.user_data.get("waiting")
    if not w or not update.message or not update.message.text:
        return
    value = update.message.text.strip()
    context.user_data.pop("waiting", None)
    key = "rank_link" if w == "rank" else "sub_channel"
    try:
        await update.message.delete()
    except Exception:
        pass
    label = "📝 LINK RANK" if key == "rank_link" else "📢 CHANNEL SUBSCRIBE"
    db.set_config(key, value)
    msg = await update.effective_chat.send_message(
        f"✅ {label} BERHASIL DISIMPAN\n\n{value}\n\nPesan ini akan dihapus otomatis dalam 10 detik."
    )
    asyncio.create_task(delete_later(msg, 10))


async def check_sub(context, channel, uid):
    if not channel:
        return False
    try:
        target = channel.strip()
        member = await context.bot.get_chat_member(target, uid)
        status = member.status
        return status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }
    except Exception as e:
        print(f"SUB CHECK ERROR [{channel}] user={uid}: {e}")
        return False


def parse_rank_link(link):
    if not link:
        return None
    m = re.match(r"^https?://t\.me/([^/]+)/([0-9]+)", link.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


async def discussion_matches_rank(context, message):
    parsed = parse_rank_link(rank_link())
    if not parsed or not message.reply_to_message:
        return False
    channel_username, post_id = parsed

    try:
        channel = await context.bot.get_chat("@" + channel_username)
        linked_chat_id = getattr(channel, "linked_chat_id", None)
        if not linked_chat_id or message.chat.id != linked_chat_id:
            return False
    except Exception as e:
        print("RANK LINKED CHAT ERROR:", e)
        return False

    root = message.reply_to_message
    if root.message_id == post_id:
        return True

    origin = getattr(root, "forward_origin", None)
    if origin is not None:
        origin_chat = getattr(origin, "chat", None)
        origin_message_id = getattr(origin, "message_id", None)
        if origin_message_id == post_id and origin_chat:
            origin_username = getattr(origin_chat, "username", None)
            origin_id = getattr(origin_chat, "id", None)
            if origin_id == channel.id or origin_username == channel_username:
                return True
    return False


async def try_unmute(context, chat_id, uid):
    row = db.get_force(chat_id, uid)
    if not row:
        return False

    sub = await check_sub(context, sub_channel(), uid)
    db.mark_sub(chat_id, uid, int(sub))
    if not (bool(row["rank_filled"]) and sub):
        return False

    perms = ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_voice_notes=True,
        can_send_video_notes=True, can_send_polls=True, can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
    try:
        await context.bot.restrict_chat_member(chat_id, uid, perms)
    except Exception as e:
        print("UNMUTE ERROR:", e)
        return False

    row = db.get_force(chat_id, uid) or row
    db.remove_force(chat_id, uid)
    name = row.get("name", str(uid))
    username = row.get("username", "")

    await context.bot.send_message(
        chat_id,
        "🔔 FORCE RANK SELESAI\n\n"
        f"👤 User: {name}\n"
        f"💎 Username: @{username or '-'}\n\n"
        "✅ Rank: SUDAH DIISI\n"
        "✅ Subscribe: SUDAH\n"
        "🔓 Status: OTOMATIS DI-UNMUTE",
    )
    return True


async def check_button(update, context):
    q = update.callback_query
    await q.answer()
    try:
        _, chat, uid = q.data.split(":")
        chat, uid = int(chat), int(uid)
    except Exception:
        return
    if q.from_user.id != uid:
        return await q.answer("❌ Tombol ini bukan untuk kamu.", show_alert=True)

    row = db.get_force(chat, uid)
    if not row:
        return await q.answer("ℹ️ Kamu sudah tidak terkena Force Rank.", show_alert=True)

    sub = await check_sub(context, sub_channel(), uid)
    db.mark_sub(chat, uid, int(sub))
    rank = bool(row["rank_filled"])

    if rank and sub:
        ok = await try_unmute(context, chat, uid)
        if ok:
            try:
                await q.edit_message_text(
                    "🎉 FORCE RANK SELESAI\n\n"
                    "✅ Rank: SUDAH DIISI\n"
                    "✅ Subscribe: SUDAH\n"
                    "🔓 Kamu telah di-unmute otomatis."
                )
            except Exception:
                pass
            return

    if not rank and not sub:
        reason = "❌ Rank belum diisi dan kamu belum subscribe."
    elif not rank:
        reason = "❌ Rank belum terdeteksi."
    else:
        reason = "❌ Kamu belum subscribe channel."
    await q.answer(reason, show_alert=True)


async def rank_comment(update, context):
    m = update.message
    if not m or not m.from_user or not m.reply_to_message:
        return
    if not await discussion_matches_rank(context, m):
        return

    row = None
    # User is in the linked discussion group; find their Force record.
    for candidate in db.all_force():
        if candidate["user_id"] == m.from_user.id:
            row = candidate
            break
    if not row:
        return

    db.mark_rank(row["chat_id"], m.from_user.id)
    await try_unmute(context, row["chat_id"], m.from_user.id)


async def periodic(context):
    for row in db.all_force():
        try:
            sub = await check_sub(context, sub_channel(), row["user_id"])
            db.mark_sub(row["chat_id"], row["user_id"], int(sub))
            current = db.get_force(row["chat_id"], row["user_id"])
            if current and current["rank_filled"] and sub:
                await try_unmute(context, row["chat_id"], row["user_id"])
        except Exception as e:
            print("PERIODIC ERROR:", e)


async def forcelist(update, context):
    if not await require_access(update):
        return
    if update.effective_chat.type == "private":
        return await update.message.reply_text("Gunakan perintah ini di grup.")
    rows = db.list_force(update.effective_chat.id)
    if not rows:
        return await update.message.reply_text("📋 Tidak ada member yang sedang Force Rank.")
    text = "📋 DAFTAR FORCE RANK\n\n"
    for i, r in enumerate(rows, 1):
        text += (
            f"{i}. @{r['username'] or r['name']}\n"
            f"   📝 Rank: {'✅' if r['rank_filled'] else '❌'}\n"
            f"   📢 Subs: {'✅' if r['subscribed'] else '❌'}\n\n"
        )
    await update.message.reply_text(text)


async def aktif(update, context):
    if not is_owner(update.effective_user.id):
        return
    if len(context.args) < 2:
        return await update.message.reply_text("/aktif 30d @username")
    dur, raw = context.args[0].lower(), context.args[1].lstrip("@")
    m = re.fullmatch(r"(\d+)([dhm])", dur)
    if not m:
        return await update.message.reply_text("Format: 30d / 12h / 30m")
    try:
        user = await context.bot.get_chat("@" + raw)
    except Exception:
        return await update.message.reply_text("User tidak ditemukan.")
    unit = {"d": "days", "h": "hours", "m": "minutes"}[m.group(2)]
    exp = datetime.now(timezone.utc) + timedelta(**{unit: int(m.group(1))})
    db.set_access(user.id, raw, exp.isoformat())
    msg = await update.message.reply_text(
        f"✅ Akses @{raw} aktif sampai {exp.strftime('%d-%m-%Y %H:%M UTC')}."
    )
    asyncio.create_task(delete_later(update.message, 3))
    asyncio.create_task(delete_later(msg, 10))


async def settings(update, context):
    q = update.callback_query
    await q.answer()
    if not is_owner(q.from_user.id):
        return await q.answer("❌ Hanya owner.", show_alert=True)
    rows = db.list_force(q.message.chat.id)
    text = (
        "⚙️ SETELAN\n\n"
        f"📝 Link Rank:\n{rank_link() or '❌ Belum diatur'}\n\n"
        f"📢 Channel Subscribe:\n{sub_channel() or '❌ Belum diatur'}\n\n"
        f"🔇 Sedang Force: {len(rows)} member"
    )
    kb = [
        [InlineKeyboardButton("📝 SET RANK", callback_data="set_rank_prompt"),
         InlineKeyboardButton("📢 SET SUBS", callback_data="set_sub_prompt")],
        [InlineKeyboardButton("🔄 REFRESH", callback_data="settings"),
         InlineKeyboardButton("🗑️ HAPUS MENU", callback_data="delete_menu")],
        [InlineKeyboardButton("🔙 MENU", callback_data="menu")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def owner_panel(update, context):
    q = update.callback_query
    await q.answer()
    if not is_owner(q.from_user.id):
        return await q.answer("❌ Hanya owner.", show_alert=True)
    await q.edit_message_text(
        "👑 OWNER PANEL\n\n"
        "Gunakan tombol Setelan atau command:\n"
        "/aktif 30d @username\n"
        "/setrank LINK\n"
        "/setsub @channel",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ SETELAN", callback_data="settings")],
            [InlineKeyboardButton("🗑️ HAPUS MENU", callback_data="delete_menu")],
            [InlineKeyboardButton("🔙 MENU", callback_data="menu")],
        ]),
    )


async def callbacks(update, context):
    q = update.callback_query
    d = q.data or ""
    if d.startswith("check:"):
        return await check_button(update, context)

    await q.answer()
    if d == "delete_menu":
        try:
            await q.message.delete()
        except Exception:
            pass
        return
    if d == "settings":
        return await settings(update, context)
    if d == "owner_panel":
        return await owner_panel(update, context)
    if d == "menu":
        return await q.edit_message_text(
            "🤖 FORCE RANK BOT\n\nPilih menu:",
            reply_markup=main_menu(is_owner(q.from_user.id)),
        )
    if d == "buy_access":
        buttons = []
        if owner_chat_url():
            buttons.append([InlineKeyboardButton("👑 HUBUNGI OWNER", url=owner_chat_url())])
        buttons.append([InlineKeyboardButton("🔙 MENU", callback_data="menu")])
        return await q.edit_message_text(
            "💰 BUY AKSES BOT\n\nPilih paket akses melalui owner.\n\nSetelah pembayaran dikonfirmasi, owner akan mengaktifkan akun kamu.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    if d in ("force_help", "unforce_help", "list_force"):
        if not await can_use(q.from_user.id):
            return await q.answer("🔒 Akses belum aktif. Gunakan BUY AKSES BOT.", show_alert=True)
        if d == "list_force":
            return await q.edit_message_text(
                "📋 DAFTAR FORCE RANK\n\nGunakan /forcelist di grup.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MENU", callback_data="menu")]]),
            )
        text = "🔇 FORCE RANK\n\nGunakan /forcerank @username atau reply pesan member."
        if d == "unforce_help":
            text = "🔊 UNFORCE RANK\n\nGunakan /unforcerank @username atau reply pesan member."
        return await q.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MENU", callback_data="menu")]]),
        )
    if d == "rank_not_set":
        return await q.answer("⚠️ Link rank belum diatur owner.", show_alert=True)
    if d == "sub_not_set":
        return await q.answer("⚠️ Channel subscribe belum diatur owner.", show_alert=True)
    if d == "set_rank_prompt":
        if not is_owner(q.from_user.id):
            return await q.answer("❌ Hanya owner.", show_alert=True)
        context.user_data["waiting"] = "rank"
        await q.answer("Kirim link rank di chat ini.", show_alert=True)
        return
    if d == "set_sub_prompt":
        if not is_owner(q.from_user.id):
            return await q.answer("❌ Hanya owner.", show_alert=True)
        context.user_data["waiting"] = "sub"
        await q.answer("Kirim @channel di chat ini.", show_alert=True)
        return


def add_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("forcerank", forcerank))
    app.add_handler(CommandHandler("unforcerank", unforcerank))
    app.add_handler(CommandHandler("forcelist", forcelist))
    app.add_handler(CommandHandler("setrank", setrank))
    app.add_handler(CommandHandler("setsub", setsub))
    app.add_handler(CommandHandler("aktif", aktif))

    # Setup text must run before rank comment handler.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_setup), group=0)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, rank_comment), group=1)
    app.add_handler(CallbackQueryHandler(callbacks), group=2)

    if app.job_queue:
        app.job_queue.run_repeating(periodic, interval=20, first=10)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN belum diisi")
    app = ApplicationBuilder().token(TOKEN).build()
    add_handlers(app)
    print("FORCERANK V4 RUNNING")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
