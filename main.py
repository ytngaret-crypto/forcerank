import os, re, asyncio
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import basedata as db

TOKEN=os.getenv("BOT_TOKEN","")
OWNER_ID=int(os.getenv("OWNER_ID","0"))
OWNER_ID_2=int(os.getenv("OWNER_ID_2","0") or 0)
OWNER_USERNAME=os.getenv("OWNER_USERNAME","")

db.init_db()

def owners(): return {x for x in (OWNER_ID,OWNER_ID_2) if x}
def is_owner(uid): return uid in owners()
def rank_link(): return db.get_config("rank_link","")
def sub_channel(): return db.get_config("sub_channel","")

async def delete_later(msg, seconds=3):
    await asyncio.sleep(seconds)
    try: await msg.delete()
    except: pass

async def can_use(uid):
    if is_owner(uid): return True
    a=db.get_access(uid)
    if not a: return False
    try: return datetime.fromisoformat(a["expires_at"]) > datetime.now(timezone.utc)
    except: return False

def main_menu(owner=False):
    rows=[
      [InlineKeyboardButton("🔇 FORCE RANK",callback_data="force_help"),InlineKeyboardButton("🔊 UNFORCE",callback_data="unforce_help")],
      [InlineKeyboardButton("📋 DAFTAR FORCE",callback_data="list_force")],
      [InlineKeyboardButton("⚙️ SETELAN",callback_data="settings")],
      [InlineKeyboardButton("💰 BUY AKSES BOT",callback_data="buy_access")],
    ]
    if owner: rows.append([InlineKeyboardButton("👑 OWNER PANEL",callback_data="owner_panel")])
    return InlineKeyboardMarkup(rows)

async def start(update,context):
    u=update.effective_user
    await update.message.reply_text("🤖 FORCE RANK BOT\n\nPilih menu:",reply_markup=main_menu(is_owner(u.id)))

async def require_access(update):
    uid=update.effective_user.id
    if await can_use(uid): return True
    await update.effective_message.reply_text("🔒 Akses belum aktif.\n\nSilakan beli akses terlebih dahulu.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 BUY AKSES BOT",callback_data="buy_access")]]))
    return False

def target_from(update,context):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        raw=context.args[0]
        if raw.startswith("@"): raw=raw[1:]
        return None,raw
    return None

async def resolve_target(update,context):
    if update.message.reply_to_message: return update.message.reply_to_message.from_user
    if context.args:
        raw=context.args[0].lstrip("@")
        try: return await context.bot.get_chat_member(update.effective_chat.id,raw)
        except: 
            try: return await context.bot.get_chat(raw)
            except: return None
    return None

async def forcerank(update,context):
    if not await require_access(update): return
    if update.effective_chat.type=="private": return await update.message.reply_text("Gunakan perintah ini di grup.")
    user=await resolve_target(update,context)
    if not user: return await update.message.reply_text("❌ Target tidak ditemukan. Gunakan reply atau /forcerank @username")
    if hasattr(user,"user"): user=user.user
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id,user.id,ChatPermissions(can_send_messages=False))
    except Exception as e:
        return await update.message.reply_text(f"❌ Gagal mute: {e}")
    db.add_force(update.effective_chat.id,user.id,user.username or "",user.full_name)
    rl=rank_link(); sc=sub_channel()
    buttons=[]
    if rl: buttons.append([InlineKeyboardButton("📝 ISI RANK",url=rl)])
    if sc:
        url=sc if sc.startswith("http") else "https://t.me/"+sc.lstrip("@")
        buttons.append([InlineKeyboardButton("📢 IKUTI CHANNEL",url=url)])
    buttons.append([InlineKeyboardButton("✅ SAYA SUDAH JOIN",callback_data=f"check:{update.effective_chat.id}:{user.id}")])
    msg=await update.message.reply_text(f"""🔔 FORCE RANK

👤 User: {user.full_name}
💎 Username: @{user.username or '-'}

🔇 Status: MUTED
📝 Rank: BELUM DIISI
📢 Subscribe: BELUM

Silakan isi rank dan subscribe channel.
Setelah keduanya terpenuhi, mute dibuka otomatis.""",reply_markup=InlineKeyboardMarkup(buttons))
    asyncio.create_task(delete_later(update.message,3))

async def unforcerank(update,context):
    if not await require_access(update): return
    user=await resolve_target(update,context)
    if not user: return await update.message.reply_text("❌ Gunakan reply atau /unforcerank @username")
    if hasattr(user,"user"): user=user.user
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id,user.id,ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_voice_notes=True,can_send_video_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True))
    except Exception as e: return await update.message.reply_text(f"❌ Gagal unmute: {e}")
    db.remove_force(update.effective_chat.id,user.id)
    await update.message.reply_text(f"🔊 @{user.username or user.full_name} telah di-unmute.")

async def setrank(update,context):
    if not is_owner(update.effective_user.id): return
    if context.args:
        db.set_config("rank_link",context.args[0])
        await update.message.delete(); return
    m=await update.message.reply_text("📝 Kirim link post rank, contoh:\nhttps://t.me/channel/9")
    context.user_data["waiting"]="rank"
    asyncio.create_task(delete_later(m,10))

async def setsub(update,context):
    if not is_owner(update.effective_user.id): return
    if context.args:
        db.set_config("sub_channel",context.args[0])
        await update.message.delete(); return
    m=await update.message.reply_text("📢 Kirim @channel wajib subscribe.")
    context.user_data["waiting"]="sub"
    asyncio.create_task(delete_later(m,10))

async def text_setup(update,context):
    w=context.user_data.get("waiting")
    if not w: return
    if w=="rank": db.set_config("rank_link",update.message.text.strip())
    else: db.set_config("sub_channel",update.message.text.strip())
    context.user_data.pop("waiting",None)
    try: await update.message.delete()
    except: pass

async def check_sub(context,channel,uid):
    if not channel: return False
    try:
        m=await context.bot.get_chat_member(channel,uid)
        return m.status in (ChatMemberStatus.MEMBER,ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.OWNER)
    except Exception as e:
        print("SUB CHECK ERROR:",e); return False

async def try_unmute(context,chat_id,uid):
    row=db.get_force(chat_id,uid)
    if not row: return False
    sub=await check_sub(context,sub_channel(),uid)
    db.mark_sub(chat_id,uid,int(sub))
    if not (row["rank_filled"] and sub): return False
    try:
        perms=ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_voice_notes=True,can_send_video_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True)
        await context.bot.restrict_chat_member(chat_id,uid,perms)
    except Exception as e: print("UNMUTE ERROR:",e); return False
    db.remove_force(chat_id,uid)
    try:
        u=await context.bot.get_chat_member(chat_id,uid)
        name=u.user.full_name; un=u.user.username
    except: name=str(uid); un=""
    await context.bot.send_message(chat_id,f"🔔 FORCE RANK SELESAI\n\n👤 {name}\n💎 @{un or '-'}\n\n✅ Rank: SUDAH DIISI\n✅ Subscribe: SUDAH\n🔓 Status: OTOMATIS DI-UNMUTE")
    return True

async def check_button(update,context):
    q=update.callback_query; await q.answer()
    _,chat,uid=q.data.split(":"); chat=int(chat); uid=int(uid)
    if q.from_user.id!=uid: return await q.answer("❌ Tombol ini bukan untuk kamu.",show_alert=True)
    ok=await try_unmute(context,chat,uid)
    row=db.get_force(chat,uid)
    if ok: await q.edit_message_text("🎉 Semua persyaratan terpenuhi.\n🔓 Kamu telah di-unmute otomatis.")
    else:
        sub=await check_sub(context,sub_channel(),uid)
        rank=bool(row and row["rank_filled"])
        await q.answer(("❌ Belum subscribe." if not sub else "❌ Rank belum terdeteksi." if not rank else "⏳ Sedang diproses."),show_alert=True)

async def rank_comment(update,context):
    m=update.message
    if not m or not m.from_user: return
    # Discussion replies carry the channel post id in reply_to_message
    if not m.reply_to_message: return
    rl=rank_link()
    if not rl: return
    match=re.match(r"https?://t\.me/[^/]+/(\d+)",rl)
    if not match: return
    target_post=int(match.group(1))
    root=m.reply_to_message
    # root may be the forwarded/channel post or its discussion copy
    root_id=getattr(root,"message_id",0)
    if root_id!=target_post and getattr(root,"forward_from_message_id",None)!=target_post:
        # allow replies in configured discussion topic when text/link matches; conservative fallback
        return
    for row in db.list_force(m.chat.id):
        if row["user_id"]==m.from_user.id:
            db.mark_rank(m.chat.id,m.from_user.id)
            await try_unmute(context,m.chat.id,m.from_user.id)

async def periodic(context):
    for row in db.list_force_all() if hasattr(db,"list_force_all") else []:
        pass
    # iterate all force rows with a new helper below
    for row in db.all_force():
        sub=await check_sub(context,sub_channel(),row["user_id"])
        db.mark_sub(row["chat_id"],row["user_id"],int(sub))
        if row["rank_filled"] and sub: await try_unmute(context,row["chat_id"],row["user_id"])

async def forcelist(update,context):
    if not await require_access(update): return
    rows=db.list_force(update.effective_chat.id)
    if not rows: return await update.message.reply_text("📋 Tidak ada member yang sedang Force Rank.")
    text="📋 DAFTAR FORCE RANK\n\n"
    for i,r in enumerate(rows,1): text+=f"{i}. @{r['username'] or r['name']} — {'✅' if r['rank_filled'] else '📝'} Rank / {'✅' if r['subscribed'] else '📢'} Subs\n"
    await update.message.reply_text(text)

async def aktif(update,context):
    if not is_owner(update.effective_user.id): return
    if len(context.args)<2: return await update.message.reply_text("/aktif 30d @username")
    dur=context.args[0].lower(); raw=context.args[1].lstrip("@")
    m=re.fullmatch(r"(\d+)([dhm])",dur)
    if not m: return await update.message.reply_text("Format: 30d / 12h / 30m")
    user=await context.bot.get_chat(raw)
    if not user: return await update.message.reply_text("User tidak ditemukan.")
    unit={"d":"days","h":"hours","m":"minutes"}[m.group(2)]
    exp=datetime.now(timezone.utc)+timedelta(**{unit:int(m.group(1))})
    db.set_access(user.id,raw,exp.isoformat())
    await update.message.reply_text(f"✅ Akses @{raw} aktif sampai {exp.astimezone().strftime('%d-%m-%Y %H:%M')}.")

async def settings(update,context):
    q=update.callback_query; await q.answer()
    rows=db.list_force(q.message.chat.id)
    text=f"""⚙️ SETELAN

📝 Link Rank:
{rank_link() or '❌ Belum diatur'}

📢 Channel Subscribe:
{sub_channel() or '❌ Belum diatur'}

🔇 Sedang Force:
{len(rows)} member"""
    kb=[
      [InlineKeyboardButton("📝 SET RANK",callback_data="set_rank_prompt"),InlineKeyboardButton("📢 SET SUBS",callback_data="set_sub_prompt")],
      [InlineKeyboardButton("🔄 REFRESH",callback_data="settings"),InlineKeyboardButton("🔙 MENU",callback_data="menu")]
    ]
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup(kb))

async def owner_panel(update,context):
    q=update.callback_query; await q.answer()
    if not is_owner(q.from_user.id): return
    await q.edit_message_text("👑 OWNER PANEL\n\nGunakan /aktif, /setrank, /setsub.\n\nKonfigurasi dan daftar Force membaca database yang sama.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MENU",callback_data="menu")]]))

async def callbacks(update,context):
    q=update.callback_query; d=q.data
    if d.startswith("check:"): return await check_button(update,context)
    if d=="settings": return await settings(update,context)
    if d=="owner_panel": return await owner_panel(update,context)
    if d=="menu":
        await q.answer(); return await q.edit_message_text("🤖 FORCE RANK BOT\n\nPilih menu:",reply_markup=main_menu(is_owner(q.from_user.id)))
    if d=="buy_access":
        await q.answer(); return await q.edit_message_text("💰 BUY AKSES BOT\n\nPilih paket dan hubungi owner.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 HUBUNGI OWNER",url=("https://t.me/"+OWNER_USERNAME if OWNER_USERNAME else "https://t.me/"))],[InlineKeyboardButton("🔙 MENU",callback_data="menu")]]))
    if d in ("force_help","unforce_help","list_force"):
        await q.answer()
        if not await can_use(q.from_user.id): return await q.answer("🔒 Akses belum aktif. Gunakan BUY AKSES BOT.",show_alert=True)
        if d=="list_force": return await q.edit_message_text("Gunakan /forcelist di grup.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MENU",callback_data="menu")]]))
        return await q.edit_message_text("Gunakan /forcerank @username atau reply pesan member.\n\n/unforcerank @username untuk membuka mute.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MENU",callback_data="menu")]]))
    if d=="set_rank_prompt":
        await q.answer("Gunakan /setrank URL di chat.",show_alert=True)
    if d=="set_sub_prompt":
        await q.answer("Gunakan /setsub @channel di chat.",show_alert=True)

def add_handlers(app):
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("forcerank",forcerank))
    app.add_handler(CommandHandler("unforcerank",unforcerank))
    app.add_handler(CommandHandler("forcelist",forcelist))
    app.add_handler(CommandHandler("setrank",setrank))
    app.add_handler(CommandHandler("setsub",setsub))
    app.add_handler(CommandHandler("aktif",aktif))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_setup),group=0)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, rank_comment),group=1)
    if app.job_queue: app.job_queue.run_repeating(periodic,interval=20,first=10)

if __name__=="__main__":
    if not TOKEN: raise RuntimeError("BOT_TOKEN belum diisi")
    app=ApplicationBuilder().token(TOKEN).build()
    add_handlers(app)
    print("FORCERANK V3 RUNNING")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
