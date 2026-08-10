import os
import html
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions
)

from telegram.constants import ChatMemberStatus

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
    find_user,
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

# CHANNEL RANK KAMU
RANK_CHANNEL = "abshsjjjv"

# POST RANK
RANK_POST_ID = 9

RANK_LINK = (
    f"https://t.me/{RANK_CHANNEL}/{RANK_POST_ID}"
)


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger("FORCERANK")


# ============================================================
# CHECK TOKEN
# ============================================================

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN belum diisi di Railway."
    )


# ============================================================
# USER FORMAT
# ============================================================

def mention(user):

    name = html.escape(
        user.full_name or "User"
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{name}</a>'
    )


def username(user):

    if user.username:
        return (
            "@"
            + html.escape(user.username)
        )

    return "Tidak ada username"


# ============================================================
# SAVE USER
# ============================================================

def remember(message):

    if not message:
        return

    if not message.from_user:
        return

    if message.chat.type not in (
        "group",
        "supergroup"
    ):
        return

    try:

        save_user(
            message.chat.id,
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username
        )

    except Exception as e:

        logger.error(
            "SAVE USER ERROR: %s",
            e
        )


# ============================================================
# ADMIN CHECK
# ============================================================

async def admin_check(
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

    except Exception:

        return False


# ============================================================
# BOT ADMIN
# ============================================================

async def bot_admin(
    chat_id,
    context
):

    try:

        bot = await context.bot.get_me()

        member = await context.bot.get_chat_member(
            chat_id,
            bot.id
        )

        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )

    except Exception:

        return False


# ============================================================
# GET TARGET
# ============================================================

async def get_target(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat

    # --------------------------------------------------------
    # REPLY
    # --------------------------------------------------------

    if message.reply_to_message:

        user = message.reply_to_message.from_user

        if user:
            return user, None

    # --------------------------------------------------------
    # USERNAME / ID
    # --------------------------------------------------------

    if not context.args:

        return None, (
            "❌ <b>Target belum ditentukan.</b>\n\n"
            "Reply pesan member lalu:\n"
            "<code>/forcerank</code>\n\n"
            "atau:\n"
            "<code>/forcerank @username</code>"
        )

    target = context.args[0]

    # --------------------------------------------------------
    # ID
    # --------------------------------------------------------

    if target.isdigit():

        try:

            member = await context.bot.get_chat_member(
                chat.id,
                int(target)
            )

            return member.user, None

        except Exception:

            return None, (
                "❌ User ID tidak ditemukan."
            )

    # --------------------------------------------------------
    # USERNAME
    # --------------------------------------------------------

    stored = find_user(
        chat.id,
        target
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
        "❌ Username tersebut belum dikenal bot.\n\n"
        "Cara paling aman:\n"
        "reply pesan user lalu gunakan:\n"
        "<code>/forcerank</code>"
    )


# ============================================================
# MUTE
# ============================================================

async def mute(
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
        permissions=permissions
    )


# ============================================================
# UNMUTE
# ============================================================

async def unmute(
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
        permissions=permissions
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

        "/forcerank\n"
        "/unforcerank\n"
        "/forceranklist\n"
        "/mute\n"
        "/unmute",
        parse_mode="HTML"
    )


# ============================================================
# FORCE RANK
# ============================================================

async def forcerank(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat
    admin = update.effective_user

    if chat.type not in (
        "group",
        "supergroup"
    ):
        return

    if not await admin_check(
        update,
        context
    ):

        await message.reply_text(
            "❌ Hanya admin yang bisa "
            "menggunakan command ini."
        )

        return

    if not await bot_admin(
        chat.id,
        context
    ):

        await message.reply_text(
            "❌ Bot harus menjadi admin "
            "dan memiliki izin Restrict Members."
        )

        return

    target, error = await get_target(
        update,
        context
    )

    if not target:

        await message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    if target.is_bot:

        await message.reply_text(
            "❌ Bot tidak bisa di-Force Rank."
        )

        return

    try:

        member = await context.bot.get_chat_member(
            chat.id,
            target.id
        )

    except Exception:

        await message.reply_text(
            "❌ Member tidak ditemukan."
        )

        return

    if member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ):

        await message.reply_text(
            "❌ Admin/Owner tidak bisa "
            "di-Force Rank."
        )

        return

    if get_force_rank(
        chat.id,
        target.id
    ):

        await message.reply_text(
            f"⚠️ {mention(target)} "
            "sudah terkena Force Rank.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # SAVE USER
    # --------------------------------------------------------

    save_user(
        chat.id,
        target.id,
        target.full_name,
        target.username
    )

    # --------------------------------------------------------
    # MUTE
    # --------------------------------------------------------

    try:

        await mute(
            context,
            chat.id,
            target.id
        )

    except Exception as e:

        logger.error(
            "MUTE ERROR: %s",
            e
        )

        await message.reply_text(
            "❌ Gagal mute member.\n\n"
            "Pastikan bot memiliki izin "
            "<b>Restrict Members</b>.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    add_force_rank(
        chat.id,
        target.id,
        target.full_name,
        target.username,
        admin.id
    )

    # --------------------------------------------------------
    # BUTTON
    # --------------------------------------------------------

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📝 ISI RANK",
                url=RANK_LINK
            )
        ]
    ])

    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------

    text = (
        "🔔 <b>FORCE RANK</b>\n\n"

        f"👤 User: {mention(target)}\n"
        f"🔹 Username: {username(target)}\n\n"

        "🔇 Status: <b>MUTED</b>\n"
        "📝 Rank: <b>BELUM DIISI</b>\n\n"

        "Silakan isi rank terlebih dahulu.\n\n"

        "👇 Klik tombol <b>ISI RANK</b> "
        "dan berikan komentar pada postingan rank.\n\n"

        "Setelah komentar berhasil terdeteksi, "
        "user akan <b>di-unmute otomatis</b>."
    )

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    logger.info(
        "FORCE RANK: %s | %s",
        target.full_name,
        target.id
    )


# ============================================================
# UNFORCERANK
# ============================================================

async def unforcerank(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat

    if not await admin_check(
        update,
        context
    ):

        await message.reply_text(
            "❌ Hanya admin."
        )

        return

    target, error = await get_target(
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
            "⚠️ <b>User tersebut tidak sedang "
            "terkena Force Rank.</b>",
            parse_mode="HTML"
        )

        return

    try:

        await unmute(
            context,
            chat.id,
            target.id
        )

    except Exception:

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
        f"👤 User: {mention(target)}\n"
        f"🔹 Username: {username(target)}\n\n"
        "Status: <b>UNMUTED</b>",
        parse_mode="HTML"
    )


# ============================================================
# MUTE MANUAL
# ============================================================

async def mute_command(
    update,
    context
):

    if not await admin_check(
        update,
        context
    ):

        await update.effective_message.reply_text(
            "❌ Hanya admin."
        )

        return

    target, error = await get_target(
        update,
        context
    )

    if not target:

        await update.effective_message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    try:

        await mute(
            context,
            update.effective_chat.id,
            target.id
        )

        await update.effective_message.reply_text(
            "🔇 <b>MUTE BERHASIL</b>\n\n"
            f"👤 {mention(target)}",
            parse_mode="HTML"
        )

    except Exception:

        await update.effective_message.reply_text(
            "❌ Gagal mute."
        )


# ============================================================
# UNMUTE MANUAL
# ============================================================

async def unmute_command(
    update,
    context
):

    if not await admin_check(
        update,
        context
    ):

        await update.effective_message.reply_text(
            "❌ Hanya admin."
        )

        return

    target, error = await get_target(
        update,
        context
    )

    if not target:

        await update.effective_message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    try:

        await unmute(
            context,
            update.effective_chat.id,
            target.id
        )

        remove_force_rank(
            update.effective_chat.id,
            target.id
        )

        await update.effective_message.reply_text(
            "🔊 <b>UNMUTE BERHASIL</b>\n\n"
            f"👤 {mention(target)}",
            parse_mode="HTML"
        )

    except Exception:

        await update.effective_message.reply_text(
            "❌ Gagal unmute."
        )


# ============================================================
# FORCE RANK LIST
# ============================================================

async def forceranklist(
    update,
    context
):

    if not await admin_check(
        update,
        context
    ):

        await update.effective_message.reply_text(
            "❌ Hanya admin."
        )

        return

    rows = get_all_force_rank(
        update.effective_chat.id
    )

    if not rows:

        await update.effective_message.reply_text(
            "✅ <b>Tidak ada Force Rank aktif.</b>",
            parse_mode="HTML"
        )

        return

    text = (
        "🔒 <b>FORCE RANK AKTIF</b>\n\n"
    )

    for i, row in enumerate(
        rows,
        1
    ):

        name = html.escape(
            row["name"] or "Unknown"
        )

        user = (
            "@"
            + html.escape(row["username"])
            if row["username"]
            else "Tanpa username"
        )

        text += (
            f"<b>{i}. {name}</b>\n"
            f"👤 {user}\n"
            f"🔇 MUTED\n\n"
        )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# CEK APAKAH KOMENTAR BERASAL DARI POST RANK
# ============================================================

def is_rank_comment(message):

    if not message:
        return False

    # Komentar channel selalu berada
    # sebagai reply terhadap post utama
    root = message.reply_to_message

    if not root:
        return False

    # ========================================================
    # CARA BARU TELEGRAM
    # ========================================================

    origin = getattr(
        root,
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
                    None
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
    # TELEGRAM LAMA
    # ========================================================

    old_chat = getattr(
        root,
        "forward_from_chat",
        None
    )

    old_message_id = getattr(
        root,
        "forward_from_message_id",
        None
    )

    if old_chat:

        channel_username = (
            getattr(
                old_chat,
                "username",
                None
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

    # ========================================================
    # FALLBACK AUTO FORWARD
    # ========================================================

    if getattr(
        root,
        "is_automatic_forward",
        False
    ):

        sender_chat = getattr(
            root,
            "sender_chat",
            None
        )

        if sender_chat:

            channel_username = (
                getattr(
                    sender_chat,
                    "username",
                    None
                )
                or ""
            )

            if (
                channel_username.lower()
                == RANK_CHANNEL.lower()
            ):

                # Jika Telegram tidak memberikan
                # origin ID, tetap cek channel.
                return True

    return False


# ============================================================
# KOMENTAR RANK
# ============================================================

async def comment_handler(
    update,
    context
):

    message = update.effective_message

    if not message:
        return

    # --------------------------------------------------------
    # SIMPAN USER
    # --------------------------------------------------------

    remember(message)

    # --------------------------------------------------------
    # HANYA KOMENTAR RANK
    # --------------------------------------------------------

    if not is_rank_comment(
        message
    ):

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
        "USER: %s",
        user.full_name
    )

    logger.info(
        "ID: %s",
        user.id
    )

    logger.info(
        "===================================="
    )

    # --------------------------------------------------------
    # CARI SEMUA FORCE RANK
    # --------------------------------------------------------

    rows = get_force_rank_by_user(
        user.id
    )

    if not rows:

        logger.info(
            "User tidak memiliki Force Rank."
        )

        return

    # --------------------------------------------------------
    # PROSES SATU PER SATU
    # --------------------------------------------------------

    for row in rows:

        group_id = row["chat_id"]
        forced_by = row["forced_by"]

        # ----------------------------------------------------
        # UNMUTE
        # ----------------------------------------------------

        try:

            await unmute(
                context,
                group_id,
                user.id
            )

        except Exception as e:

            logger.error(
                "AUTO UNMUTE ERROR: %s",
                e
            )

            continue

        # ----------------------------------------------------
        # HAPUS DATABASE
        # ----------------------------------------------------

        remove_force_rank(
            group_id,
            user.id
        )

        # ----------------------------------------------------
        # NOTIFIKASI GRUP
        # ----------------------------------------------------

        group_text = (
            "✅ <b>FORCE RANK SELESAI</b>\n\n"

            f"👤 User: {mention(user)}\n"
            f"🔹 Username: {username(user)}\n\n"

            "📝 Rank: <b>SUDAH DIISI</b>\n"
            "💬 Komentar: <b>TERDETEKSI</b>\n"
            "🔊 Status: <b>AUTO UNMUTE</b>\n\n"

            "🎉 User telah menyelesaikan "
            "Force Rank."
        )

        try:

            await context.bot.send_message(
                chat_id=group_id,
                text=group_text,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.error(
                "NOTIF GROUP ERROR: %s",
                e
            )

        # ----------------------------------------------------
        # NOTIFIKASI ADMIN
        # ----------------------------------------------------

        admin_text = (
            "🔔 <b>NOTIFIKASI FORCE RANK</b>\n\n"

            f"👤 User: {mention(user)}\n"
            f"🔹 Username: {username(user)}\n\n"

            "✅ Telah mengisi rank.\n"
            "💬 Komentar berhasil terdeteksi.\n"
            "🔊 Telah di-unmute otomatis.\n\n"

            "🔗 <b>Post Rank:</b>\n"
            f"{RANK_LINK}"
        )

        try:

            await context.bot.send_message(
                chat_id=forced_by,
                text=admin_text,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.error(
                "NOTIF ADMIN ERROR: %s",
                e
            )

        # ----------------------------------------------------
        # BALAS KOMENTAR
        # ----------------------------------------------------

        try:

            await message.reply_text(
                "✅ <b>RANK BERHASIL TERDETEKSI!</b>\n\n"
                "📝 Rank kamu sudah tercatat.\n"
                "🔊 Kamu telah di-unmute otomatis.\n\n"
                "🎉 Selamat datang kembali!",
                parse_mode="HTML"
            )

        except Exception as e:

            logger.error(
                "REPLY ERROR: %s",
                e
            )


# ============================================================
# TRACK USER SEMUA PESAN
# ============================================================

async def track_messages(
    update,
    context
):

    message = update.effective_message

    if not message:
        return

    remember(message)


# ============================================================
# ERROR
# ============================================================

async def error_handler(
    update,
    context
):

    logger.error(
        "ERROR:",
        exc_info=context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    init_db()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # ========================================================
    # COMMAND
    # ========================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "forcerank",
            forcerank
        )
    )

    app.add_handler(
        CommandHandler(
            "unforcerank",
            unforcerank
        )
    )

    app.add_handler(
        CommandHandler(
            "forceranklist",
            forceranklist
        )
    )

    app.add_handler(
        CommandHandler(
            "mute",
            mute_command
        )
    )

    app.add_handler(
        CommandHandler(
            "unmute",
            unmute_command
        )
    )

    # ========================================================
    # KOMENTAR RANK
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.ALL,
            comment_handler
        ),
        group=1
    )

    # ========================================================
    # TRACK USER
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.ALL,
            track_messages
        ),
        group=2
    )

    # ========================================================
    # ERROR
    # ========================================================

    app.add_error_handler(
        error_handler
    )

    logger.info(
        "======================================"
    )

    logger.info(
        "FORCE RANK BOT ONLINE"
    )

    logger.info(
        "CHANNEL: @%s",
        RANK_CHANNEL
    )

    logger.info(
        "POST: %s",
        RANK_POST_ID
    )

    logger.info(
        "LINK: %s",
        RANK_LINK
    )

    logger.info(
        "======================================"
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()