import os
import re
import html
import logging

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.constants import (
    ChatMemberStatus
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from database import (
    init_db,
    save_user,
    find_user_by_username,
    add_force_rank,
    get_force_rank,
    get_all_force_rank,
    get_force_rank_by_user,
    remove_force_rank
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# CHANNEL RANK
RANK_CHANNEL = "abshsjjjv"
RANK_POST_ID = 9

RANK_LINK = (
    f"https://t.me/"
    f"{RANK_CHANNEL}/"
    f"{RANK_POST_ID}"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    level=logging.INFO
)

logger = logging.getLogger(
    "FORCE-RANK"
)


# ============================================================
# TOKEN
# ============================================================

if not BOT_TOKEN:

    raise RuntimeError(
        "BOT_TOKEN belum diisi di Railway."
    )


# ============================================================
# FORMAT USER
# ============================================================

def mention_user(user):

    name = html.escape(
        user.full_name or "User"
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{name}'
        f'</a>'
    )


def username_text(user):

    if user.username:

        return (
            "@"
            + html.escape(
                user.username
            )
        )

    return "Tidak ada username"


# ============================================================
# SAVE USER
# ============================================================

def remember_user(message):

    if not message:
        return

    if not message.from_user:
        return

    if message.chat.type not in (
        "group",
        "supergroup"
    ):
        return

    user = message.from_user

    try:

        save_user(
            chat_id=message.chat.id,
            user_id=user.id,
            name=user.full_name,
            username=user.username
        )

    except Exception as e:

        logger.exception(
            "Gagal save user: %s",
            e
        )


# ============================================================
# ADMIN CHECK
# ============================================================

async def is_admin(
    update,
    context
):

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return False

    try:

        member = await context.bot.get_chat_member(
            chat.id,
            user.id
        )

        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )

    except Exception as e:

        logger.exception(
            "Admin check error: %s",
            e
        )

        return False


# ============================================================
# BOT ADMIN CHECK
# ============================================================

async def bot_is_admin(
    chat_id,
    context
):

    try:

        me = await context.bot.get_me()

        member = await context.bot.get_chat_member(
            chat_id,
            me.id
        )

        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )

    except Exception:

        return False


# ============================================================
# TARGET DARI TEXT MENTION
# ============================================================

def get_text_mentioned_user(
    message
):

    if not message:
        return None

    if not message.entities:
        return None

    text = message.text or ""

    for entity in message.entities:

        if entity.type == "text_mention":

            try:

                return entity.user

            except Exception:

                return None

    return None


# ============================================================
# GET TARGET
# ============================================================

async def get_target_user(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:

        return None, (
            "❌ Target tidak ditemukan."
        )

    # ========================================================
    # 1. REPLY
    # ========================================================

    if message.reply_to_message:

        target = (
            message
            .reply_to_message
            .from_user
        )

        if target:

            return target, None

    # ========================================================
    # 2. TEXT MENTION
    # ========================================================

    mentioned = get_text_mentioned_user(
        message
    )

    if mentioned:

        return mentioned, None

    # ========================================================
    # 3. ARGUMENT
    # ========================================================

    if not context.args:

        return None, (
            "❌ <b>Target belum ditentukan.</b>\n\n"

            "Gunakan:\n\n"

            "1️⃣ Reply pesan member\n"
            "<code>/forcerank</code>\n\n"

            "2️⃣ Username\n"
            "<code>/forcerank @username</code>\n\n"

            "3️⃣ Mention member dengan memilih "
            "nama member dari daftar Telegram."
        )

    target_text = (
        context.args[0]
        .strip()
    )

    # ========================================================
    # USER ID
    # ========================================================

    if re.fullmatch(
        r"\d+",
        target_text
    ):

        try:

            user_id = int(
                target_text
            )

            member = await context.bot.get_chat_member(
                chat.id,
                user_id
            )

            return member.user, None

        except Exception:

            return None, (
                "❌ User ID tidak ditemukan "
                "di grup."
            )

    # ========================================================
    # USERNAME
    # ========================================================

    username = (
        target_text
        .replace("@", "")
        .strip()
        .lower()
    )

    stored = find_user_by_username(
        chat.id,
        username
    )

    if stored:

        try:

            member = await context.bot.get_chat_member(
                chat.id,
                stored["user_id"]
            )

            return member.user, None

        except Exception:

            pass

    return None, (
        f"❌ Saya belum mengenal "
        f"<b>@{html.escape(username)}</b>.\n\n"

        "Gunakan <b>reply</b> ke pesan member "
        "atau mention member dengan memilih "
        "user dari daftar Telegram.\n\n"

        "Username yang diketik manual hanya "
        "bisa digunakan jika user tersebut "
        "sudah pernah terdeteksi bot."
    )


# ============================================================
# MUTE
# ============================================================

async def mute_user(
    context,
    chat_id,
    user_id
):

    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )

    await context.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=permissions,
        use_independent_chat_permissions=True
    )


# ============================================================
# UNMUTE
# ============================================================

async def unmute_user(
    context,
    chat_id,
    user_id
):

    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True
    )

    await context.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=permissions,
        use_independent_chat_permissions=True
    )


# ============================================================
# START
# ============================================================

async def start(
    update,
    context
):

    await update.effective_message.reply_text(
        "🤖 <b>FORCE RANK BOT</b>\n\n"

        "Bot aktif.\n\n"

        "👮 <b>COMMAND ADMIN</b>\n\n"

        "🔇 /forcerank\n"
        "🔊 /unforcerank\n"
        "🔊 /unmute\n"
        "🔇 /mute\n"
        "📋 /forceranklist\n\n"

        "<b>Contoh:</b>\n"
        "<code>/forcerank @username</code>\n\n"

        "atau reply pesan member:\n"
        "<code>/forcerank</code>",
        parse_mode="HTML"
    )


# ============================================================
# FORCE RANK
# ============================================================

async def force_rank(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat
    admin = update.effective_user

    if not message or not chat or not admin:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):

        await message.reply_text(
            "❌ Command ini hanya "
            "untuk grup."
        )

        return

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if not await is_admin(
        update,
        context
    ):

        await message.reply_text(
            "❌ Hanya admin yang "
            "bisa menggunakan command ini."
        )

        return

    # --------------------------------------------------------
    # BOT ADMIN
    # --------------------------------------------------------

    if not await bot_is_admin(
        chat.id,
        context
    ):

        await message.reply_text(
            "❌ Bot belum menjadi admin grup."
        )

        return

    # --------------------------------------------------------
    # TARGET
    # --------------------------------------------------------

    target, error = await get_target_user(
        update,
        context
    )

    if not target:

        await message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # BOT
    # --------------------------------------------------------

    if target.is_bot:

        await message.reply_text(
            "❌ Bot tidak dapat "
            "di-Force Rank."
        )

        return

    # --------------------------------------------------------
    # MEMBER CHECK
    # --------------------------------------------------------

    try:

        member = await context.bot.get_chat_member(
            chat.id,
            target.id
        )

    except Exception:

        await message.reply_text(
            "❌ User tersebut "
            "tidak ditemukan di grup."
        )

        return

    # --------------------------------------------------------
    # ADMIN / OWNER
    # --------------------------------------------------------

    if member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ):

        await message.reply_text(
            "❌ Admin/Owner tidak bisa "
            "di-Force Rank."
        )

        return

    # --------------------------------------------------------
    # ALREADY FORCE
    # --------------------------------------------------------

    existing = get_force_rank(
        chat.id,
        target.id
    )

    if existing:

        await message.reply_text(
            f"⚠️ {mention_user(target)} "
            "sudah terkena Force Rank.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # SAVE USER
    # --------------------------------------------------------

    save_user(
        chat_id=chat.id,
        user_id=target.id,
        name=target.full_name,
        username=target.username
    )

    # --------------------------------------------------------
    # MUTE
    # --------------------------------------------------------

    try:

        await mute_user(
            context,
            chat.id,
            target.id
        )

    except Exception as e:

        logger.exception(
            "Mute gagal: %s",
            e
        )

        await message.reply_text(
            "❌ <b>Gagal mute user.</b>\n\n"
            "Pastikan bot memiliki izin "
            "<b>Restrict Members</b>.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    add_force_rank(
        chat_id=chat.id,
        user_id=target.id,
        name=target.full_name,
        username=target.username,
        forced_by=admin.id
    )

    # --------------------------------------------------------
    # BUTTON
    # --------------------------------------------------------

    keyboard = [
        [
            InlineKeyboardButton(
                "📝 ISI RANK",
                url=RANK_LINK
            )
        ]
    ]

    markup = InlineKeyboardMarkup(
        keyboard
    )

    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------

    text = (
        "🔔 <b>FORCE RANK</b>\n\n"

        f"👤 User: {mention_user(target)}\n"
        f"🔹 Username: {username_text(target)}\n\n"

        "🔇 <b>Status: MUTED</b>\n"
        "📝 <b>Rank: BELUM DIISI</b>\n\n"

        "Silakan isi rank terlebih dahulu.\n\n"

        "👇 Klik tombol <b>ISI RANK</b> "
        "di bawah dan berikan komentar "
        "pada postingan rank.\n\n"

        "Setelah komentar terdeteksi, "
        "kamu akan <b>di-unmute otomatis</b>."
    )

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=markup
    )

    logger.info(
        "FORCE RANK -> %s (%s)",
        target.full_name,
        target.id
    )


# ============================================================
# UNFORCERANK
# ============================================================

async def unforce_rank(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):
        return

    if not await is_admin(
        update,
        context
    ):

        await message.reply_text(
            "❌ Hanya admin yang "
            "bisa menggunakan command ini."
        )

        return

    target, error = await get_target_user(
        update,
        context
    )

    if not target:

        await message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    existing = get_force_rank(
        chat.id,
        target.id
    )

    if not existing:

        await message.reply_text(
            "⚠️ <b>User tersebut tidak "
            "sedang terkena Force Rank.</b>",
            parse_mode="HTML"
        )

        return

    try:

        await unmute_user(
            context,
            chat.id,
            target.id
        )

    except Exception as e:

        logger.exception(e)

        await message.reply_text(
            "❌ Gagal melakukan unmute."
        )

        return

    remove_force_rank(
        chat.id,
        target.id
    )

    await message.reply_text(
        "🔊 <b>FORCE RANK DIBUKA</b>\n\n"

        f"👤 User: {mention_user(target)}\n"
        f"🔹 Username: {username_text(target)}\n\n"

        "🔊 Status: <b>UNMUTED</b>\n"
        "📝 Force Rank: <b>DIBATALKAN</b>",
        parse_mode="HTML"
    )


# ============================================================
# /UNMUTE
# ============================================================

async def manual_unmute(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    if not await is_admin(
        update,
        context
    ):

        await message.reply_text(
            "❌ Hanya admin."
        )

        return

    target, error = await get_target_user(
        update,
        context
    )

    if not target:

        await message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    try:

        await unmute_user(
            context,
            chat.id,
            target.id
        )

        # Kalau ternyata Force Rank,
        # hapus juga datanya.

        remove_force_rank(
            chat.id,
            target.id
        )

        await message.reply_text(
            "🔊 <b>UNMUTE BERHASIL</b>\n\n"
            f"👤 User: {mention_user(target)}",
            parse_mode="HTML"
        )

    except Exception:

        await message.reply_text(
            "❌ Gagal melakukan unmute."
        )


# ============================================================
# /MUTE
# ============================================================

async def manual_mute(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat
    admin = update.effective_user

    if not message or not chat or not admin:
        return

    if not await is_admin(
        update,
        context
    ):

        await message.reply_text(
            "❌ Hanya admin."
        )

        return

    target, error = await get_target_user(
        update,
        context
    )

    if not target:

        await message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    try:

        await mute_user(
            context,
            chat.id,
            target.id
        )

        await message.reply_text(
            "🔇 <b>MUTE BERHASIL</b>\n\n"
            f"👤 User: {mention_user(target)}",
            parse_mode="HTML"
        )

    except Exception:

        await message.reply_text(
            "❌ Gagal melakukan mute."
        )


# ============================================================
# FORCE RANK LIST
# ============================================================

async def force_rank_list(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    if not await is_admin(
        update,
        context
    ):

        await message.reply_text(
            "❌ Hanya admin."
        )

        return

    users = get_all_force_rank(
        chat.id
    )

    if not users:

        await message.reply_text(
            "✅ <b>FORCE RANK KOSONG</b>\n\n"
            "Tidak ada member yang sedang "
            "terkena Force Rank.",
            parse_mode="HTML"
        )

        return

    text = (
        "🔒 <b>FORCE RANK AKTIF</b>\n\n"
    )

    for number, user in enumerate(
        users,
        start=1
    ):

        name = html.escape(
            user["name"] or "Unknown"
        )

        if user["username"]:

            username = (
                "@"
                + html.escape(
                    user["username"]
                )
            )

        else:

            username = "Tanpa username"

        text += (
            f"<b>{number}. {name}</b>\n"
            f"├ 👤 {username}\n"
            f"└ 🔇 BELUM ISI RANK\n\n"
        )

    await message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# DETEKSI POST RANK
# ============================================================

def is_rank_comment(
    message
):

    if not message:
        return False

    if not message.from_user:
        return False

    reply = message.reply_to_message

    if not reply:
        return False

    # ========================================================
    # BOT API BARU
    # ========================================================

    origin = getattr(
        reply,
        "forward_origin",
        None
    )

    if origin:

        origin_chat = getattr(
            origin,
            "chat",
            None
        )

        origin_message_id = getattr(
            origin,
            "message_id",
            None
        )

        if origin_chat:

            channel_username = (
                getattr(
                    origin_chat,
                    "username",
                    ""
                )
                or ""
            )

            if (
                channel_username.lower()
                == RANK_CHANNEL.lower()
                and origin_message_id
                == RANK_POST_ID
            ):

                return True

    # ========================================================
    # FALLBACK API LAMA
    # ========================================================

    old_chat = getattr(
        reply,
        "forward_from_chat",
        None
    )

    old_message_id = getattr(
        reply,
        "forward_from_message_id",
        None
    )

    if old_chat:

        channel_username = (
            getattr(
                old_chat,
                "username",
                ""
            )
            or ""
        )

        if (
            channel_username.lower()
            == RANK_CHANNEL.lower()
            and old_message_id
            == RANK_POST_ID
        ):

            return True

    return False


# ============================================================
# RANK COMMENT HANDLER
# ============================================================

async def rank_comment_handler(
    update,
    context
):

    message = update.effective_message

    if not message:
        return

    # --------------------------------------------------------
    # TRACK USER
    # --------------------------------------------------------

    remember_user(
        message
    )

    # --------------------------------------------------------
    # HANYA PROSES KOMENTAR
    # --------------------------------------------------------

    if not is_rank_comment(
        message
    ):

        return

    user = message.from_user

    if not user:
        return

    logger.info(
        "RANK COMMENT TERDETEKSI: %s (%s)",
        user.full_name,
        user.id
    )

    # --------------------------------------------------------
    # CARI FORCE RANK USER
    # --------------------------------------------------------

    records = get_force_rank_by_user(
        user.id
    )

    if not records:

        logger.info(
            "User tidak sedang Force Rank."
        )

        return

    # --------------------------------------------------------
    # PROSES
    # --------------------------------------------------------

    for record in records:

        group_id = record["chat_id"]

        forced_by = record["forced_by"]

        # ====================================================
        # UNMUTE
        # ====================================================

        try:

            await unmute_user(
                context,
                group_id,
                user.id
            )

        except Exception as e:

            logger.exception(
                "AUTO UNMUTE GAGAL: %s",
                e
            )

            continue

        # ====================================================
        # HAPUS DATABASE
        # ====================================================

        remove_force_rank(
            group_id,
            user.id
        )

        # ====================================================
        # USER DATA
        # ====================================================

        mention = mention_user(
            user
        )

        username = username_text(
            user
        )

        # ====================================================
        # NOTIFIKASI GRUP
        # ====================================================

        group_text = (
            "✅ <b>FORCE RANK SELESAI</b>\n\n"

            f"👤 User: {mention}\n"
            f"🔹 Username: {username}\n\n"

            "📝 Rank: <b>SUDAH DIISI</b>\n"
            "💬 Komentar: <b>TERDETEKSI</b>\n"
            "🔊 Status: <b>UNMUTED OTOMATIS</b>\n\n"

            "🎉 User sudah menyelesaikan "
            "Force Rank."
        )

        try:

            await context.bot.send_message(
                chat_id=group_id,
                text=group_text,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.warning(
                "Notif grup gagal: %s",
                e
            )

        # ====================================================
        # NOTIF ADMIN
        # ====================================================

        admin_text = (
            "🔔 <b>NOTIFIKASI FORCE RANK</b>\n\n"

            f"👤 User: {mention}\n"
            f"🔹 Username: {username}\n\n"

            "✅ Telah mengisi rank\n"
            "💬 Komentar berhasil terdeteksi\n"
            "🔊 Telah di-unmute otomatis\n\n"

            "📌 Postingan rank:\n"
            f"{RANK_LINK}"
        )

        try:

            await context.bot.send_message(
                chat_id=forced_by,
                text=admin_text,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.warning(
                "DM admin gagal: %s",
                e
            )

        # ====================================================
        # BALAS KOMENTAR
        # ====================================================

        try:

            await message.reply_text(
                "✅ <b>RANK TERDETEKSI!</b>\n\n"

                "📝 Rank kamu sudah dianggap "
                "selesai.\n\n"

                "🔊 Kamu telah di-unmute "
                "otomatis dari grup.\n\n"

                "🎉 Selamat datang kembali!",
                parse_mode="HTML"
            )

        except Exception as e:

            logger.warning(
                "Reply komentar gagal: %s",
                e
            )


# ============================================================
# TRACK MEMBER
# ============================================================

async def track_handler(
    update,
    context
):

    message = update.effective_message

    if not message:
        return

    remember_user(
        message
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context
):

    logger.exception(
        "BOT ERROR",
        exc_info=context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    init_db()

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # ========================================================
    # COMMAND
    # ========================================================

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "forcerank",
            force_rank
        )
    )

    application.add_handler(
        CommandHandler(
            "unforcerank",
            unforce_rank
        )
    )

    application.add_handler(
        CommandHandler(
            "forceranklist",
            force_rank_list
        )
    )

    application.add_handler(
        CommandHandler(
            "unmute",
            manual_unmute
        )
    )

    application.add_handler(
        CommandHandler(
            "mute",
            manual_mute
        )
    )

    # ========================================================
    # SEMUA PESAN
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.ALL,
            rank_comment_handler
        )
    )

    # ========================================================
    # ERROR
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    print("")
    print("======================================")
    print("🤖 FORCE RANK BOT V2")
    print("======================================")
    print("CHANNEL :", RANK_CHANNEL)
    print("POST    :", RANK_POST_ID)
    print("LINK    :", RANK_LINK)
    print("DATABASE: READY")
    print("STATUS  : ONLINE")
    print("======================================")
    print("")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()