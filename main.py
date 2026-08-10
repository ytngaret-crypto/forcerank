import os
import logging
import html

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

logger = logging.getLogger(__name__)


# ============================================================
# TOKEN CHECK
# ============================================================

if not BOT_TOKEN:

    raise RuntimeError(
        "BOT_TOKEN belum dibuat di Railway Variables."
    )


# ============================================================
# MENTION USER
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
# CHECK ADMIN
# ============================================================

async def is_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:

        return False

    try:

        member = await context.bot.get_chat_member(
            chat_id=chat.id,
            user_id=user.id
        )

        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )

    except Exception as e:

        logger.exception(
            "Gagal mengecek admin: %s",
            e
        )

        return False


# ============================================================
# MUTE
# ============================================================

async def mute_user(
    bot,
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
        can_add_web_page_previews=True
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
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:

        return

    await update.message.reply_text(
        "🤖 <b>FORCE RANK BOT</b>\n\n"
        "Bot aktif.\n\n"
        "Command admin:\n\n"
        "• /forcerank\n"
        "• /unforcerank\n"
        "• /forceranklist",
        parse_mode="HTML"
    )


# ============================================================
# FORCE RANK
# ============================================================

async def force_rank(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    chat = update.effective_chat
    admin = update.effective_user

    if not message or not chat or not admin:

        return

    # --------------------------------------------------------
    # GROUP ONLY
    # --------------------------------------------------------

    if chat.type not in (
        "group",
        "supergroup"
    ):

        await message.reply_text(
            "❌ Command ini hanya dapat "
            "digunakan di grup."
        )

        return

    # --------------------------------------------------------
    # ADMIN CHECK
    # --------------------------------------------------------

    if not await is_admin(
        update,
        context
    ):

        await message.reply_text(
            "❌ Command ini hanya dapat "
            "digunakan oleh admin."
        )

        return

    # --------------------------------------------------------
    # REPLY CHECK
    # --------------------------------------------------------

    if not message.reply_to_message:

        await message.reply_text(
            "❌ Kamu harus reply pesan "
            "member terlebih dahulu.\n\n"
            "Contoh:\n"
            "Reply pesan member lalu ketik:\n"
            "/forcerank"
        )

        return

    target = (
        message
        .reply_to_message
        .from_user
    )

    if not target:

        await message.reply_text(
            "❌ User tidak ditemukan."
        )

        return

    # --------------------------------------------------------
    # BOT CHECK
    # --------------------------------------------------------

    if target.is_bot:

        await message.reply_text(
            "❌ Bot tidak bisa terkena "
            "Force Rank."
        )

        return

    # --------------------------------------------------------
    # TARGET MEMBER
    # --------------------------------------------------------

    try:

        target_member = (
            await context.bot
            .get_chat_member(
                chat_id=chat.id,
                user_id=target.id
            )
        )

    except Exception as e:

        logger.exception(e)

        await message.reply_text(
            "❌ Gagal mendapatkan "
            "informasi member."
        )

        return

    # --------------------------------------------------------
    # ADMIN / OWNER
    # --------------------------------------------------------

    if target_member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ):

        await message.reply_text(
            "❌ Tidak bisa melakukan "
            "Force Rank kepada admin."
        )

        return

    # --------------------------------------------------------
    # CHECK EXISTING
    # --------------------------------------------------------

    existing = get_force_rank(
        chat.id,
        target.id
    )

    if existing:

        await message.reply_text(
            f"⚠️ {mention_user(target)} "
            "sudah sedang terkena Force Rank.",
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
            "Gagal mute: %s",
            e
        )

        await message.reply_text(
            "❌ <b>Gagal mute member.</b>\n\n"
            "Pastikan bot merupakan admin "
            "dan memiliki izin:\n"
            "✅ Restrict Members",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # SAVE DATABASE
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

    markup = InlineKeyboardMarkup(
        keyboard
    )

    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------

    text = (
        "🔔 <b>FORCE RANK</b>\n\n"

        f"👤 User: {mention_user(target)}\n"
        f"🔹 Username: "
        f"{username_text(target)}\n\n"

        "🔇 <b>Status: MUTED</b>\n"
        "📝 <b>Rank: BELUM DIISI</b>\n\n"

        "Silakan isi rank melalui "
        "komentar pada postingan rank.\n\n"

        "Setelah kamu memberikan komentar "
        "pada postingan rank, bot akan "
        "otomatis membuka mute kamu.\n\n"

        "👇 <b>Klik tombol berikut:</b>"
    )

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=markup
    )


# ============================================================
# UNFORCERANK
# ============================================================

async def unforce_rank(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
            "❌ Command ini khusus admin."
        )

        return

    if not message.reply_to_message:

        await message.reply_text(
            "❌ Reply pesan member "
            "lalu ketik /unforcerank."
        )

        return

    target = (
        message
        .reply_to_message
        .from_user
    )

    if not target:

        return

    existing = get_force_rank(
        chat.id,
        target.id
    )

    if not existing:

        await message.reply_text(
            "⚠️ Member tersebut tidak "
            "sedang terkena Force Rank."
        )

        return

    try:

        await unmute_user(
            context.bot,
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
        "✅ <b>FORCE RANK DIBATALKAN</b>\n\n"
        f"👤 {mention_user(target)}\n"
        "🔊 Status: <b>UNMUTED</b>",
        parse_mode="HTML"
    )


# ============================================================
# FORCE RANK LIST
# ============================================================

async def force_rank_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
            "❌ Command ini khusus admin."
        )

        return

    users = get_all_force_rank(
        chat.id
    )

    if not users:

        await message.reply_text(
            "✅ Tidak ada member yang "
            "sedang terkena Force Rank."
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
            user["nama"] or "Unknown"
        )

        if user["username"]:

            username = (
                "@"
                + html.escape(
                    user["username"]
                )
            )

        else:

            username = "tanpa username"

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
# CEK KOMENTAR RANK
# ============================================================

def is_rank_comment(message):

    if not message:

        return False

    if not message.from_user:

        return False

    replied = message.reply_to_message

    if not replied:

        return False

    # ========================================================
    # TELEGRAM BOT API BARU
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
            and origin_message_id == RANK_POST_ID
        ):

            channel_username = (
                getattr(
                    origin_chat,
                    "username",
                    ""
                )
                or ""
            ).lower()

            if (
                channel_username
                == RANK_CHANNEL.lower()
            ):

                return True

    # ========================================================
    # TELEGRAM API LAMA
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
        ).lower()

        if (
            channel_username
            == RANK_CHANNEL.lower()
            and old_message_id
            == RANK_POST_ID
        ):

            return True

    return False


# ============================================================
# KOMENTAR RANK HANDLER
# ============================================================

async def rank_comment_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:

        return

    # --------------------------------------------------------
    # BUKAN KOMENTAR RANK
    # --------------------------------------------------------

    if not is_rank_comment(message):

        return

    user = message.from_user

    if not user:

        return

    logger.info(
        "===================================="
    )

    logger.info(
        "KOMENTAR RANK TERDETEKSI"
    )

    logger.info(
        "User: %s",
        user.full_name
    )

    logger.info(
        "User ID: %s",
        user.id
    )

    logger.info(
        "===================================="
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

        main_chat_id = record["chat_id"]

        forced_by = record["forced_by"]

        try:

            # ================================================
            # UNMUTE
            # ================================================

            await unmute_user(
                context.bot,
                main_chat_id,
                user.id
            )

            logger.info(
                "User %s berhasil di-unmute dari %s",
                user.id,
                main_chat_id
            )

        except Exception as e:

            logger.exception(
                "Gagal unmute user: %s",
                e
            )

            continue

        # ================================================
        # REMOVE DATABASE
        # ================================================

        remove_force_rank(
            main_chat_id,
            user.id
        )

        # ================================================
        # USER MENTION
        # ================================================

        mention = mention_user(
            user
        )

        username = username_text(
            user
        )

        # ================================================
        # NOTIFIKASI GROUP
        # ================================================

        group_notification = (
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
                text=group_notification,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.exception(
                "Gagal mengirim notifikasi grup: %s",
                e
            )

        # ================================================
        # NOTIFIKASI ADMIN
        # ================================================

        admin_notification = (
            "🔔 <b>NOTIFIKASI FORCE RANK</b>\n\n"

            f"👤 User: {mention}\n"
            f"🔹 Username: {username}\n\n"

            "✅ Telah mengisi rank\n"
            "🔊 Telah di-unmute otomatis\n\n"

            "📌 Postingan rank:\n"
            f"{RANK_LINK}"
        )

        try:

            await context.bot.send_message(
                chat_id=forced_by,
                text=admin_notification,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.warning(
                "Tidak bisa DM admin %s: %s",
                forced_by,
                e
            )

            
        # ================================================
        # REPLY KOMENTAR
        # ================================================

        try:

            await message.reply_text(
                "✅ <b>Rank terdeteksi!</b>\n\n"
                "🔊 Kamu sudah di-unmute "
                "dari grup.\n\n"
                "🎉 Selamat datang kembali!",
                parse_mode="HTML"
            )

        except Exception as e:

            logger.warning(
                "Gagal reply komentar: %s",
                e
            )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.exception(
        "Terjadi error:",
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

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # KOMENTAR RANK
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.ALL,
            rank_comment_handler
        )
    )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    print("")
    print("========================================")
    print("🤖 FORCE RANK BOT")
    print("========================================")
    print(
        "📌 Channel :",
        RANK_CHANNEL
    )
    print(
        "📌 Post    :",
        RANK_POST_ID
    )
    print(
        "🔗 Link    :",
        RANK_LINK
    )
    print("========================================")
    print("✅ BOT ONLINE")
    print("========================================")
    print("")

    # --------------------------------------------------------
    # POLLING
    # --------------------------------------------------------

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
         
