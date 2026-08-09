import os
import logging
import html

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.constants import ChatMemberStatus

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ChatMemberHandler,
    filters
)

from database import (
    init_db,
    add_force_rank,
    get_force_rank,
    remove_force_rank,
    get_all_force_rank
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Channel tempat rank diisi
RANK_CHANNEL = "abshsjjjv"

# Nomor postingan rank
RANK_POST_ID = 9

# Link postingan rank
RANK_LINK = f"https://t.me/{RANK_CHANNEL}/{RANK_POST_ID}"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ============================================================
# CEK TOKEN
# ============================================================

if not BOT_TOKEN:

    raise RuntimeError(
        "BOT_TOKEN belum diatur di Railway Variables."
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
# CEK ADMIN
# ============================================================

async def is_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_chat:
        return False

    if not update.effective_user:
        return False

    try:

        member = await context.bot.get_chat_member(
            update.effective_chat.id,
            update.effective_user.id
        )

        return member.status in [
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ]

    except Exception as e:

        logger.exception(e)

        return False


# ============================================================
# MUTE
# ============================================================

async def mute_user(
    bot,
    chat_id,
    user_id
):

    permissions = ChatPermissions.no_permissions()

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

    permissions = ChatPermissions.all_permissions()

    await bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=permissions,
        use_independent_chat_permissions=True
    )


# ============================================================
# /START
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
        "Admin:\n"
        "• /forcerank\n"
        "• /unforcerank\n"
        "• /forceranklist",
        parse_mode="HTML"
    )


# ============================================================
# /FORCERANK
# ============================================================

async def force_rank(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    chat = update.effective_chat

    # --------------------------------------------------------
    # HARUS GROUP
    # --------------------------------------------------------

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        await message.reply_text(
            "❌ Command ini hanya bisa digunakan di grup."
        )

        return

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if not await is_admin(update, context):

        await message.reply_text(
            "❌ Command ini khusus admin."
        )

        return

    # --------------------------------------------------------
    # HARUS REPLY
    # --------------------------------------------------------

    if not message.reply_to_message:

        await message.reply_text(
            "❌ Reply pesan member yang ingin "
            "di-force rank.\n\n"
            "Contoh:\n"
            "Reply pesan A lalu ketik:\n"
            "/forcerank"
        )

        return

    target = message.reply_to_message.from_user

    if not target:

        await message.reply_text(
            "❌ User tidak ditemukan."
        )

        return

    # --------------------------------------------------------
    # BOT
    # --------------------------------------------------------

    if target.is_bot:

        await message.reply_text(
            "❌ Bot tidak bisa di-force rank."
        )

        return

    # --------------------------------------------------------
    # CEK TARGET
    # --------------------------------------------------------

    try:

        target_member = await context.bot.get_chat_member(
            chat.id,
            target.id
        )

    except Exception as e:

        logger.exception(e)

        await message.reply_text(
            "❌ Gagal mendapatkan data member."
        )

        return

    # --------------------------------------------------------
    # ADMIN / OWNER
    # --------------------------------------------------------

    if target_member.status in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ]:

        await message.reply_text(
            "❌ Tidak bisa melakukan Force Rank "
            "kepada admin/owner."
        )

        return

    # --------------------------------------------------------
    # SUDAH TERDAFTAR?
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

        logger.exception(e)

        await message.reply_text(
            "❌ <b>Gagal mute member.</b>\n\n"
            "Pastikan bot merupakan admin grup "
            "dan memiliki izin <b>Restrict Members</b>.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    add_force_rank(
        chat_id=chat.id,
        user_id=target.id,
        nama=target.full_name,
        username=target.username,
        forced_by=update.effective_user.id
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

    reply_markup = InlineKeyboardMarkup(
        keyboard
    )

    username = (
        f"@{html.escape(target.username)}"
        if target.username
        else "Tidak ada username"
    )

    # --------------------------------------------------------
    # PESAN FORCE RANK
    # --------------------------------------------------------

    text = (
        "🔔 <b>FORCE RANK</b>\n\n"

        f"👤 User: {mention_user(target)}\n"
        f"🔹 Username: {username}\n\n"

        "🔇 <b>Status: MUTED</b>\n"
        "📝 <b>Rank: BELUM DIISI</b>\n\n"

        "Silakan isi rank terlebih dahulu "
        "dengan memberikan komentar pada "
        "postingan rank.\n\n"

        "Setelah kamu berkomentar di postingan "
        "rank, bot akan otomatis membuka mute.\n\n"

        "👇 <b>Klik tombol di bawah:</b>"
    )

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )


# ============================================================
# /UNFORCERANK
# ============================================================

async def unforce_rank(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    chat = update.effective_chat

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        return

    if not await is_admin(update, context):

        await message.reply_text(
            "❌ Command ini khusus admin."
        )

        return

    if not message.reply_to_message:

        await message.reply_text(
            "❌ Reply pesan user lalu ketik "
            "/unforcerank"
        )

        return

    target = message.reply_to_message.from_user

    if not target:
        return

    existing = get_force_rank(
        chat.id,
        target.id
    )

    if not existing:

        await message.reply_text(
            "⚠️ User tersebut tidak sedang "
            "terkena Force Rank."
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
        "🔊 Status: UNMUTED",
        parse_mode="HTML"
    )


# ============================================================
# /FORCERANKLIST
# ============================================================

async def force_rank_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    chat = update.effective_chat

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        return

    if not await is_admin(update, context):

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

    for index, user in enumerate(
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
            f"<b>{index}. {nama}</b>\n"
            f"   ├ Username: {username}\n"
            f"   └ 🔇 BELUM ISI RANK\n\n"
        )

    await message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# CEK APAKAH PESAN ADALAH KOMENTAR RANK
# ============================================================

def is_rank_comment(message):

    if not message:
        return False

    # --------------------------------------------------------
    # Harus punya user
    # --------------------------------------------------------

    if not message.from_user:

        return False

    # --------------------------------------------------------
    # Harus berupa reply
    # --------------------------------------------------------

    replied = message.reply_to_message

    if not replied:

        return False

    # --------------------------------------------------------
    # Cara baru PTB / Bot API
    # --------------------------------------------------------

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

            username = (
                origin_chat.username or ""
            ).lower()

            if username == RANK_CHANNEL.lower():

                return True

    # --------------------------------------------------------
    # Kompatibilitas versi lama
    # --------------------------------------------------------

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

        username = (
            old_chat.username or ""
        ).lower()

        if (
            username == RANK_CHANNEL.lower()
            and old_message_id == RANK_POST_ID
        ):

            return True

    return False


# ============================================================
# KOMENTAR RANK TERDETEKSI
# ============================================================

async def rank_comment_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    # --------------------------------------------------------
    # CEK APAKAH KOMENTAR DI POST #9
    # --------------------------------------------------------

    if not is_rank_comment(message):

        return

    user = message.from_user

    if not user:

        return

    logger.info(
        "Komentar rank terdeteksi: %s (%s)",
        user.full_name,
        user.id
    )

    # --------------------------------------------------------
    # CARI SEMUA GROUP YANG USER INI SEDANG FORCE RANK
    # --------------------------------------------------------

    # Karena satu user bisa berada di beberapa grup,
    # kita cari berdasarkan database.

    # Ambil chat_id dari context cache sederhana.
    #
    # Kita akan menggunakan database function tambahan
    # di bawah.
