import logging
import html

from telegram import (
    Update,
    ChatPermissions
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ChatMemberHandler,
    MessageHandler,
    filters
)

from telegram.constants import ChatMemberStatus

from database import (
    init_db,
    add_force_rank,
    get_force_rank,
    remove_force_rank,
    get_all_force_rank
)


# ============================================================
# TOKEN
# ============================================================

BOT_TOKEN = "8922784238:AAHFLJJFa_vktTSxQOmoRDL76YWwReJv-8c"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


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

    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )

    return member.status in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ]


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
# MUTE USER
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
        permissions=permissions
    )


# ============================================================
# UNMUTE USER
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
        permissions=permissions
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

    # --------------------------------------------------------
    # HARUS GROUP
    # --------------------------------------------------------

    if update.effective_chat.type not in [
        "group",
        "supergroup"
    ]:

        await message.reply_text(
            "❌ Command ini hanya bisa digunakan di grup."
        )

        return

    # --------------------------------------------------------
    # CEK ADMIN
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
            "❌ Reply pesan orang yang ingin di-force rank.\n\n"
            "Contoh:\n"
            "Reply pesan A lalu ketik /forcerank"
        )

        return

    target = message.reply_to_message.from_user

    if not target:

        await message.reply_text(
            "❌ User tidak ditemukan."
        )

        return

    # --------------------------------------------------------
    # JANGAN FORCE BOT
    # --------------------------------------------------------

    if target.is_bot:

        await message.reply_text(
            "❌ Bot tidak bisa di-force rank."
        )

        return

    chat_id = update.effective_chat.id

    # --------------------------------------------------------
    # CEK TARGET ADMIN
    # --------------------------------------------------------

    target_member = await context.bot.get_chat_member(
        chat_id,
        target.id
    )

    if target_member.status in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ]:

        await message.reply_text(
            "❌ Tidak bisa memute admin/owner."
        )

        return

    # --------------------------------------------------------
    # CEK SUDAH FORCE RANK
    # --------------------------------------------------------

    existing = get_force_rank(
        chat_id,
        target.id
    )

    if existing:

        await message.reply_text(
            f"⚠️ {mention_user(target)} "
            f"sudah masuk daftar Force Rank.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # MUTE
    # --------------------------------------------------------

    try:

        await mute_user(
            context.bot,
            chat_id,
            target.id
        )

    except Exception as e:

        logger.exception(e)

        await message.reply_text(
            "❌ Gagal mute user.\n\n"
            "Pastikan bot adalah admin dan memiliki "
            "izin Restrict Members."
        )

        return

    # --------------------------------------------------------
    # SIMPAN DATABASE
    # --------------------------------------------------------

    add_force_rank(
        chat_id=chat_id,
        user_id=target.id,
        nama=target.full_name,
        username=target.username,
        forced_by=update.effective_user.id
    )

    # --------------------------------------------------------
    # PESAN
    # --------------------------------------------------------

    username_text = (
        f"@{html.escape(target.username)}"
        if target.username
        else "Tidak ada username"
    )

    text = (
        "🔔 <b>FORCE RANK</b>\n\n"

        f"👤 User: {mention_user(target)}\n"
        f"🔹 Username: {username_text}\n\n"

        "🔇 <b>Status: MUTED</b>\n"
        "📝 <b>Rank: BELUM DIISI</b>\n\n"

        "Silakan isi rank terlebih dahulu.\n"
        "Setelah rank selesai, user akan "
        "<b>otomatis di-unmute</b>."
    )

    await message.reply_text(
        text,
        parse_mode="HTML"
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

    if update.effective_chat.type not in [
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
            "❌ Reply pesan user lalu ketik /unforcerank"
        )

        return

    target = message.reply_to_message.from_user

    if not target:
        return

    chat_id = update.effective_chat.id

    existing = get_force_rank(
        chat_id,
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
            chat_id,
            target.id
        )

    except Exception as e:

        logger.exception(e)

        await message.reply_text(
            "❌ Gagal melakukan unmute."
        )

        return

    remove_force_rank(
        chat_id,
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

    if update.effective_chat.type not in [
        "group",
        "supergroup"
    ]:

        return

    if not await is_admin(update, context):

        await message.reply_text(
            "❌ Command ini khusus admin."
        )

        return

    chat_id = update.effective_chat.id

    users = get_all_force_rank(chat_id)

    if not users:

        await message.reply_text(
            "✅ Tidak ada member yang sedang "
            "terkena Force Rank."
        )

        return

    text = "🔒 <b>FORCE RANK AKTIF</b>\n\n"

    for index, user in enumerate(users, start=1):

        nama = html.escape(
            user["nama"] or "Unknown"
        )

        if user["username"]:

            username = f"@{html.escape(user['username'])}"

        else:

            username = "tanpa username"

        text += (
            f"<b>{index}.</b> {nama}\n"
            f"   └ {username}\n"
            f"   └ 🔇 BELUM ISI RANK\n\n"
        )

    await message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# DETEKSI MEMBER UNMUTE
# ============================================================

async def member_status_changed(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    chat_member_update = update.chat_member

    if not chat_member_update:
        return

    chat = chat_member_update.chat

    # Hanya group
    if chat.type not in [
        "group",
        "supergroup"
    ]:

        return

    old_member = chat_member_update.old_chat_member
    new_member = chat_member_update.new_chat_member

    user = new_member.user

    if user.is_bot:
        return

    # --------------------------------------------------------
    # CEK DATABASE
    # --------------------------------------------------------

    tracked = get_force_rank(
        chat.id,
        user.id
    )

    if not tracked:
        return

    # --------------------------------------------------------
    # STATUS LAMA
    # --------------------------------------------------------

    old_restricted = (
        old_member.status == ChatMemberStatus.RESTRICTED
    )

    # --------------------------------------------------------
    # STATUS BARU
    # --------------------------------------------------------

    new_is_member = (
        new_member.status == ChatMemberStatus.MEMBER
    )

    # --------------------------------------------------------
    # CEK APAKAH BENAR-BENAR SUDAH BISA NGOMONG
    # --------------------------------------------------------

    new_can_send = True

    if new_member.status == ChatMemberStatus.RESTRICTED:

        new_can_send = bool(
            getattr(
                new_member,
                "can_send_messages",
                False
            )
        )

    # --------------------------------------------------------
    # UNMUTE TERDETEKSI
    # --------------------------------------------------------

    if old_restricted and (
        new_is_member or new_can_send
    ):

        logger.info(
            "Force Rank selesai: %s (%s)",
            user.full_name,
            user.id
        )

        # ----------------------------------------------------
        # HAPUS DATABASE
        # ----------------------------------------------------

        remove_force_rank(
            chat.id,
            user.id
        )

        # ----------------------------------------------------
        # NOTIFIKASI KE ADMIN
        # ----------------------------------------------------

        mention = mention_user(user)

        text = (
            "✅ <b>FORCE RANK SELESAI</b>\n\n"

            f"👤 User: {mention}\n\n"

            "📝 Rank: <b>SUDAH DIISI</b>\n"
            "🔊 Status: <b>UNMUTED OTOMATIS</b>\n\n"

            "🎉 User telah menyelesaikan "
            "proses Force Rank."
        )

        try:

            admins = await context.bot.get_chat_administrators(
                chat.id
            )

            for admin in admins:

                admin_user = admin.user

                if admin_user.is_bot:
                    continue

                try:

                    await context.bot.send_message(
                        chat_id=admin_user.id,
                        text=text,
                        parse_mode="HTML"
                    )

                except Exception:

                    # Admin mungkin belum pernah
                    # membuka chat bot
                    pass

            # ------------------------------------------------
            # NOTIFIKASI DI GRUP
            # ------------------------------------------------

            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "🎉 <b>FORCE RANK SELESAI</b>\n\n"
                    f"{mention} telah mengisi rank.\n"
                    "🔊 User telah di-unmute otomatis."
                ),
                parse_mode="HTML"
            )

        except Exception as e:

            logger.exception(e)


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🤖 <b>Force Rank Bot</b>\n\n"
        "Bot aktif.\n\n"
        "Admin:\n"
        "• /forcerank — Force Rank user\n"
        "• /unforcerank — Batalkan Force Rank\n"
        "• /forceranklist — Lihat daftar\n\n"
        "Gunakan command dengan cara reply "
        "pesan user.",
        parse_mode="HTML"
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

    # Database
    init_db()

    # Application
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "forcerank",
            force_rank
        )
    )

    app.add_handler(
        CommandHandler(
            "unforcerank",
            unforce_rank
        )
    )

    app.add_handler(
        CommandHandler(
            "forceranklist",
            force_rank_list
        )
    )

    # --------------------------------------------------------
    # CHAT MEMBER HANDLER
    # --------------------------------------------------------

    app.add_handler(
        ChatMemberHandler(
            member_status_changed,
            ChatMemberHandler.CHAT_MEMBER
        )
    )

    # Error
    app.add_error_handler(
        error_handler
    )

    print("===================================")
    print("🤖 FORCE RANK BOT")
    print("===================================")
    print("✅ Bot sedang berjalan...")
    print("===================================")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
