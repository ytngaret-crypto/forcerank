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
    get_force_rank_by_user,
    remove_force_rank,
    get_all_force_rank
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")


# ============================================================
# CHANNEL RANK
# ============================================================

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
        "BOT_TOKEN belum diatur di Railway."
    )


# ============================================================
# MENTION
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


# ============================================================
# USERNAME
# ============================================================

def format_username(user):

    if user.username:

        return (
            "@"
            + html.escape(
                user.username
            )
        )

    return "Tidak ada username"


# ============================================================
# SAVE USER DARI MESSAGE
# ============================================================

def remember_user(message):

    if not message:
        return

    user = message.from_user

    chat = message.chat

    if not user:
        return

    if not chat:
        return

    # Hanya simpan member grup
    if chat.type not in (
        "group",
        "supergroup"
    ):
        return

    try:

        save_user(
            chat_id=chat.id,
            user_id=user.id,
            nama=user.full_name,
            username=user.username
        )

    except Exception as e:

        logger.exception(
            "Gagal menyimpan user: %s",
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

        member = (
            await context.bot
            .get_chat_member(
                chat.id,
                user.id
            )
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
# GET TARGET DARI REPLY / USERNAME
# ============================================================

async def get_target_user(
    update,
    context
):

    message = update.effective_message

    chat = update.effective_chat

    if not message or not chat:

        return None, None

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
    # 2. ARGUMENT
    # ========================================================

    args = context.args

    if not args:

        return None, (
            "❌ Target tidak ditemukan.\n\n"
            "Gunakan salah satu cara:\n\n"
            "1️⃣ Reply pesan member:\n"
            "<code>/forcerank</code>\n\n"
            "2️⃣ Username:\n"
            "<code>/forcerank @username</code>\n\n"
            "3️⃣ Mention member dengan memilih "
            "user dari daftar Telegram."
        )

    target_text = args[0].strip()

    # ========================================================
    # 3. USER ID
    # ========================================================

    if re.fullmatch(
        r"-?\d+",
        target_text
    ):

        try:

            user_id = int(
                target_text
            )

            member = (
                await context.bot
                .get_chat_member(
                    chat.id,
                    user_id
                )
            )

            return (
                member.user,
                None
            )

        except Exception:

            return None, (
                "❌ User ID tersebut "
                "tidak ditemukan di grup."
            )

    # ========================================================
    # 4. USERNAME
    # ========================================================

    if target_text.startswith("@"):

        username = (
            target_text
            .lstrip("@")
            .strip()
            .lower()
        )

    else:

        username = (
            target_text
            .strip()
            .lower()
        )

    # --------------------------------------------------------
    # Cari dari database
    # --------------------------------------------------------

    stored = find_user_by_username(
        chat.id,
        username
    )

    if stored:

        try:

            member = (
                await context.bot
                .get_chat_member(
                    chat.id,
                    stored["user_id"]
                )
            )

            return (
                member.user,
                None
            )

        except Exception:

            pass

    # ========================================================
    # GAGAL
    # ========================================================

    return None, (
        f"❌ Saya belum mengenal @{username}.\n\n"
        "Telegram Bot API tidak menyediakan "
        "daftar semua member berdasarkan username.\n\n"
        "Gunakan:\n"
        "• reply pesan member, atau\n"
        "• pastikan member tersebut sudah "
        "pernah mengirim pesan setelah bot aktif."
    )


# ============================================================
# MUTE
# ============================================================

async def mute_user(
    bot,
    chat_id,
    user_id
):

    permissions = (
        ChatPermissions.no_permissions()
    )

    await bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=permissions,
        use_independent_chat_permissions=True
    )


# ============================================================
# UNMUTE
# ============================================================

async def unmute_user(
    bot,
    chat_id,
    user_id
):

    permissions = (
        ChatPermissions.all_permissions()
    )

    await bot.restrict_chat_member(
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

    message = update.effective_message

    if not message:

        return

    await message.reply_text(
        "🤖 <b>FORCE RANK BOT</b>\n\n"
        "Bot sedang aktif.\n\n"

        "👮 <b>ADMIN COMMAND</b>\n\n"

        "🔇 /forcerank\n"
        "🔊 /unforcerank\n"
        "📋 /forceranklist\n\n"

        "<b>Contoh:</b>\n\n"

        "<code>/forcerank @username</code>\n\n"

        "atau reply pesan member:\n"
        "<code>/forcerank</code>",
        parse_mode="HTML"
    )


# ============================================================
# /FORCERANK
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

    # --------------------------------------------------------
    # GROUP
    # --------------------------------------------------------

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
            "❌ Command ini hanya "
            "untuk admin."
        )

        return

    # --------------------------------------------------------
    # TARGET
    # --------------------------------------------------------

    target, error = (
        await get_target_user(
            update,
            context
        )
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
            "terkena Force Rank."
        )

        return

    # --------------------------------------------------------
    # SAVE USER
    # --------------------------------------------------------

    save_user(
        chat_id=chat.id,
        user_id=target.id,
        nama=target.full_name,
        username=target.username
    )

    # --------------------------------------------------------
    # TARGET MEMBER
    # --------------------------------------------------------

    try:

        target_member = (
            await context.bot
            .get_chat_member(
                chat.id,
                target.id
            )
        )

    except Exception as e:

        logger.exception(e)

        await message.reply_text(
            "❌ Gagal mengecek member."
        )

        return

    # --------------------------------------------------------
    # ADMIN TARGET
    # --------------------------------------------------------

    if target_member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ):

        await message.reply_text(
            "❌ Tidak bisa Force Rank "
            "admin/owner."
        )

        return

    # --------------------------------------------------------
    # ALREADY FORCE RANK
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
    # MUTE
    # --------------------------------------------------------

    try:

        await mute_user(
            context.bot,
            chat.id,
            target.id
        )

    except Exception as e:

        logger.exception(
            "Mute gagal: %s",
            e
        )

        await message.reply_text(
            "❌ <b>Gagal mute member.</b>\n\n"
            "Pastikan bot adalah admin dan "
            "memiliki izin <b>Restrict Members</b>.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # SAVE FORCE RANK
    # --------------------------------------------------------

    add_force_rank(
        chat_id=chat.id,
        user_id=target.id,
        nama=target.full_name,
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

    markup = (
        InlineKeyboardMarkup(
            keyboard
        )
    )

    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------

    text = (
        "🔔 <b>FORCE RANK</b>\n\n"

        f"👤 User: {mention_user(target)}\n"
        f"🔹 Username: "
        f"{format_username(target)}\n\n"

        "🔇 <b>Status: MUTED</b>\n"
        "📝 <b>Rank: BELUM DIISI</b>\n\n"

        "Kamu diwajibkan mengisi rank.\n\n"

        "Silakan klik tombol "
        "<b>ISI RANK</b> di bawah "
        "dan berikan komentar pada "
        "postingan rank.\n\n"

        "Setelah komentar kamu terdeteksi, "
        "mute akan dibuka otomatis."
    )

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=markup
    )

    logger.info(
        "FORCE RANK: %s (%s)",
        target.full_name,
        target.id
    )


# ============================================================
# /UNFORCERANK
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

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if not await is_admin(
        update,
        context
    ):

        await message.reply_text(
            "❌ Command ini hanya "
            "untuk admin."
        )

        return

    # --------------------------------------------------------
    # TARGET
    # --------------------------------------------------------

    target, error = (
        await get_target_user(
            update,
            context
        )
    )

    if not target:

        await message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # CEK DATABASE
    # --------------------------------------------------------

    existing = get_force_rank(
        chat.id,
        target.id
    )

    if not existing:

        await message.reply_text(
            f"⚠️ {mention_user(target)} "
            "tidak sedang terkena Force Rank.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # UNMUTE
    # --------------------------------------------------------

    try:

        await unmute_user(
            context.bot,
            chat.id,
            target.id
        )

    except Exception as e:

        logger.exception(e)

        await message.reply_text(
            "❌ Gagal membuka mute."
        )

        return

    # --------------------------------------------------------
    # REMOVE
    # --------------------------------------------------------

    remove_force_rank(
        chat.id,
        target.id
    )

    # --------------------------------------------------------
    # NOTIFY
    # --------------------------------------------------------

    await message.reply_text(
        "🔊 <b>FORCE RANK DIBATALKAN</b>\n\n"

        f"👤 User: {mention_user(target)}\n"

        "🔊 Status: <b>UNMUTED</b>\n"
        "📝 Force Rank: <b>DIBATALKAN</b>",
        parse_mode="HTML"
    )

    logger.info(
        "UNFORCERANK: %s (%s)",
        target.full_name,
        target.id
    )


# ============================================================
# /FORCERANKLIST
# ============================================================

async def force_rank_list(
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
            "❌ Command ini hanya "
            "untuk admin."
        )

        return

    users = get_all_force_rank(
        chat.id
    )

    if not users:

        await message.reply_text(
            "✅ Tidak ada member "
            "yang sedang terkena "
            "Force Rank."
        )

        return

    text = (
        "🔒 <b>FORCE RANK AKTIF</b>\n\n"
    )

    for number, user in enumerate(
        users,
        start=1
    ):

        nama = html.escape(
            user["nama"]
            or "Unknown"
        )

        if user["username"]:

            username = (
                "@"
                + html.escape(
                    user["username"]
                )
            )

        else:

            username = (
                "tanpa username"
            )

        text += (
            f"<b>{number}. {nama}</b>\n"
            f"   ├ {username}\n"
            f"   └ 🔇 BELUM ISI RANK\n\n"
        )

    await message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# CHECK RANK COMMENT
# ============================================================

def is_rank_comment(message):

    if not message:

        return False

    if not message.from_user:

        return False

    replied = (
        message.reply_to_message
    )

    if not replied:

        return False

    # ========================================================
    # BOT API BARU
    # ========================================================

    origin = getattr(
        replied,
        "forward_origin",
        None
    )

    if origin:

        origin_type = getattr(
            origin,
            "type",
            None
        )

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

        if (
            origin_type == "channel"
            and origin_chat
            and origin_message_id
            == RANK_POST_ID
        ):

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
            ):

                return True

    # ========================================================
    # API LAMA
    # ========================================================

    old_chat = getattr(
        replied,
        "forward_from_chat",
        None
    )

    old_message_id = getattr(
        replied,
        "forward_from_message_id",
        None
    )

    if old_chat and old_message_id:

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
# HANDLE RANK COMMENT
# ============================================================

async def rank_comment_handler(
    update,
    context
):

    message = update.effective_message

    if not message:

        return

    # --------------------------------------------------------
    # SIMPAN USER JIKA DARI GRUP
    # --------------------------------------------------------

    remember_user(
        message
    )

    # --------------------------------------------------------
    # CEK KOMENTAR RANK
    # --------------------------------------------------------

    if not is_rank_comment(
        message
    ):

        return

    user = message.from_user

    if not user:

        return

    logger.info(
        "=================================="
    )

    logger.info(
        "KOMENTAR RANK TERDETEKSI"
    )

    logger.info(
        "User: %s",
        user.full_name
    )

    logger.info(
        "ID: %s",
        user.id
    )

    logger.info(
        "=================================="
    )

    # --------------------------------------------------------
    # CARI FORCE RANK
    # --------------------------------------------------------

    records = (
        get_force_rank_by_user(
            user.id
        )
    )

    if not records:

        logger.info(
            "User tidak sedang Force Rank."
        )

        return

    # --------------------------------------------------------
    # PROSES SETIAP GRUP
    # --------------------------------------------------------

    for record in records:

        main_chat_id = (
            record["chat_id"]
        )

        forced_by = (
            record["forced_by"]
        )

        # ====================================================
        # UNMUTE
        # ====================================================

        try:

            await unmute_user(
                context.bot,
                main_chat_id,
                user.id
            )

        except Exception as e:

            logger.exception(
                "Gagal unmute: %s",
                e
            )

            continue

        # ====================================================
        # REMOVE DATABASE
        # ====================================================

        remove_force_rank(
            main_chat_id,
            user.id
        )

        # ====================================================
        # DATA
        # ====================================================

        mention = mention_user(
            user
        )

        username = format_username(
            user
        )

        # ====================================================
        # GROUP NOTIFICATION
        # ====================================================

        group_text = (
            "✅ <b>FORCE RANK SELESAI</b>\n\n"

            f"👤 User: {mention}\n"
            f"🔹 Username: {username}\n\n"

            "📝 Rank: <b>SUDAH DIISI</b>\n"
            "💬 Komentar: <b>TERDETEKSI</b>\n"
            "🔊 Status: <b>UNMUTED OTOMATIS</b>\n\n"

            "🎉 User telah menyelesaikan "
            "Force Rank."
        )

        try:

            await context.bot.send_message(
                chat_id=main_chat_id,
                text=group_text,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.exception(
                "Gagal kirim notifikasi grup: %s",
                e
            )

        # ====================================================
        # ADMIN NOTIFICATION
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
                "Tidak bisa DM admin %s: %s",
                forced_by,
                e
            )

        # ====================================================
        # REPLY KOMENTAR
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
                "Gagal reply komentar: %s",
                e
            )


# ============================================================
# TRACK USER
# ============================================================

async def track_user_handler(
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
# ERROR
# ============================================================

async def error_handler(
    update,
    context
):

    logger.exception(
        "BOT ERROR:",
        exc_info=context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    init_db()

    # --------------------------------------------------------
    # APPLICATION
    # --------------------------------------------------------

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # ========================================================
    # COMMANDS
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

    # ========================================================
    # RANK COMMENT
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

    # ========================================================
    # LOG
    # ========================================================

    print("")
    print("==========================================")
    print("🤖 FORCE RANK BOT")
    print("==========================================")
    print(
        "📌 Rank Channel :",
        RANK_CHANNEL
    )
    print(
        "📌 Rank Post    :",
        RANK_POST_ID
    )
    print(
        "🔗 Rank Link    :",
        RANK_LINK
    )
    print("==========================================")
    print("✅ DATABASE READY")
    print("✅ BOT ONLINE")
    print("==========================================")
    print("")

    # ========================================================
    # POLLING
    # ========================================================

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()