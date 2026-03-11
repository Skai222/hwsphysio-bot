 #!/usr/bin/env python3
import logging, json, os, asyncio
from datetime import time, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import anthropic
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, Defaults, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN", "DEIN_TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "DEIN_ANTHROPIC_KEY")
TIMEZONE = ZoneInfo("Europe/Berlin")
IMAGES_DIR = Path(__file__).parent / "images"
DATA_FILE = Path(__file__).parent / "user_data.json"
SCHEDULE = {"morning": time(hour=7, minute=0, tzinfo=TIMEZONE), "midday": time(hour=12, minute=0, tzinfo=TIMEZONE), "evening": time(hour=19, minute=0, tzinfo=TIMEZONE)}

claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

SYSTEM_PROMPT = """Du bist Kirills persoenlicher Gesundheitsassistent im Telegram. Du sprichst Deutsch und duzt Kirill.

KIRILLS GESUNDHEITSPROFIL:
- HWS-Steilstellung (Verlust der zervikalen Lordose), bestaetigt per MRT
- Taeglicher zervikogener Kopfschmerz, linksseitig frontal (Stirn/Augenbraue links)
- Somatosensorischer Tinnitus (modulierbar durch Kieferbewegungen und Nackendehnung)
- Versteifter M. Sternocleidomastoideus (SCM), besonders links
- Kiefergelenksbeteiligung (TMJ/CMD): Kieferknacken ohne aktuelle Schmerzen
- Keine Nerveneinklemmung im MRT
- Beginn vor ca. 1 Jahr: Morgens aufgewacht mit Schwindel, Hoerknall, ploetzlicher Tinnitus
- Verschlechterung im Liegen (egal welches Kissen)
- Besser bei aufrechter Haltung

AKTUELLES UEBUNGSPROGRAMM (Jull-Protokoll, 4 Phasen):
- Phase 1 (Woche 1-2): CCF-Training + Haltungskorrektur + SCM-Triggerpunktbehandlung
- Phase 2 (Woche 3-4): + Isometrische Rotation + SCM-Dehnung + Skapulaere Reeduktion
- Phase 3 (Woche 5-6): + Extensoren + Subokzipitale Release
- Phase 4 (Woche 7+): + Kieferuebungen + BWS-Extension

INTERESSEN: Lion's Mane, Nootropika, evidenzbasierte Gesundheit
ARBEIT: BOLD & EPIC Transform GmbH (ERP-Consulting, Stuttgart)

AUFGABEN:
1. Gesundheitsfragen zu HWS/Tinnitus/Kopfschmerz/CMD/SCM beantworten (mit Studien)
2. Symptomanalyse im Kontext seines Profils, Muster erkennen, Red Flags warnen
3. Ernaehrungsberatung: Mahlzeitenplaene, Rezepte, Einkaufslisten (entzuendungshemmend)
4. Supplements evidenzbasiert beraten (Lion's Mane, Magnesium, Omega-3, etc.)
5. Arzt-Fahrplan empfehlen
6. Uebungsprogramm erklaeren und anpassen

REGELN:
- IMMER Deutsch, duzen
- Praegnant (Telegram = kurze Nachrichten, max 4000 Zeichen)
- HTML-Formatierung (<b>, <i>) statt Markdown
- Klar sagen wenn etwas aerztlich abgeklaert werden muss
- Emojis sparsam aber gezielt"""

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO, handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", encoding="utf-8")])
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger("NackenBot")

def load_data():
    try:
        with open(DATA_FILE) as f: return json.load(f)
    except: return {}
def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)
def get_user(cid):
    data = load_data(); sid = str(cid)
    if sid not in data:
        data[sid] = {"phase":1,"week":1,"start_date":datetime.now().isoformat(),"active":True,"pain_log":[],"chat_history":[],"health_notes":[]}
        save_data(data)
    return data[sid]
def set_user(cid, user):
    data = load_data(); data[str(cid)] = user; save_data(data)
def get_active_users():
    data = load_data(); return [int(k) for k,v in data.items() if v.get("active")]

async def ask_claude(chat_id, user_message):
    user = get_user(chat_id)
    context_parts = []
    pain_log = user.get("pain_log", [])
    if pain_log:
        recent = pain_log[-14:]
        pain_summary = "\n".join([f"  {e['date']} {e.get('time','')}: {e['score']}/10 (Phase {e.get('phase',1)})" for e in recent])
        context_parts.append(f"Schmerztagebuch (letzte 14):\n{pain_summary}")
    notes = user.get("health_notes", [])
    if notes:
        context_parts.append("Notizen:\n" + "\n".join([f"  [{n['date']}] {n['note']}" for n in notes[-20:]]))
    context_parts.append(f"Aktuelle Phase: {user.get('phase',1)}, Woche {user.get('week',1)}")
    context = "\n".join(context_parts)
    history = user.get("chat_history", [])[-10:]
    messages = [{"role":m["role"],"content":m["content"]} for m in history]
    full_msg = user_message + (f"\n\n[Kontext: {context}]" if context else "")
    messages.append({"role":"user","content":full_msg})
    try:
        response = await asyncio.get_event_loop().run_in_executor(None, lambda: claude.messages.create(model="claude-sonnet-4-20250514", max_tokens=1500, system=SYSTEM_PROMPT, messages=messages))
        answer = response.content[0].text
        history.append({"role":"user","content":user_message})
        history.append({"role":"assistant","content":answer})
        user["chat_history"] = history[-20:]
        set_user(chat_id, user)
        return answer
    except anthropic.AuthenticationError: return "API-Key ungueltig! Pruefe ANTHROPIC_API_KEY."
    except anthropic.RateLimitError: return "Rate Limit. Warte kurz."
    except Exception as e: logger.error(f"Claude: {e}"); return f"Fehler: {str(e)[:200]}"

P1 = {
    "morning": [
        {"photo":"01_ccf_training.jpg","caption":"☀️ <b>Phase 1 — Morgen (1/2)</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>CCF-TRAINING</b>\n\n📍 Rueckenlage, Knie gebeugt\n📍 Sanft nicken wie Ja — MINIMAL\n📍 Kopf bleibt auf Unterlage\n📍 SCM-Kontrolle: Finger an Hals!\n\n⏱ <b>10 Wdh. x 10 Sek.</b>\n\n💡 <i>Jull 2002: 72% Kopfschmerzreduktion</i>"},
        {"photo":"02_haltungskorrektur.jpg","caption":"☀️ <b>Phase 1 — Morgen (2/2)</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>HALTUNGSKORREKTUR</b>\n\n1️⃣ Becken neutral\n2️⃣ Brust heben\n3️⃣ Kinn einziehen\n\n⏱ <b>10 Wdh. x 10 Sek.</b>\n🔄 Alle 30-60 Min.!"},
    ],
    "midday": [{"photo":"02_haltungskorrektur.jpg","caption":"🌞 <b>Phase 1 — Mittag</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>HALTUNG</b> ⏱ 10x10 Sek.\n\n😌 <b>KIEFER:</b> Lippen zu, Zaehne auseinander, Zunge oben."}],
    "evening": [
        {"photo":"01_ccf_training.jpg","caption":"🌙 <b>Phase 1 — Abend (1/2)</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>CCF-TRAINING</b>\n⏱ 10 Wdh. x 10 Sek.\n\n📝 /schmerz [0-10] nicht vergessen!"},
        {"photo":"03_scm_selbstbehandlung.jpg","caption":"🌙 <b>Phase 1 — Abend (2/2)</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>SCM-TRIGGERPUNKTE</b>\n\n📍 Pinzettengriff am SCM\n📍 Druckpunkte 30-60 Sek. halten\n📍 Schluesselbein → Ohr\n\n⏱ <b>2-3 Min./Seite, LINKS zuerst</b>\n⚠️ Nicht auf Halsschlagader!"},
    ],
}
P2 = {
    "morning": P1["morning"] + [{"photo":"04_isometrische_rotation.jpg","caption":"☀️ <b>Phase 2 NEU!</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>ISOMETRISCHE ROTATION</b>\n\nHand an Kopf, dagegen druecken.\nKEINE Bewegung! 10-20% Kraft.\n\n⏱ <b>5 Wdh. x 5 Sek./Seite</b>"}],
    "midday": P1["midday"],
    "evening": P1["evening"] + [
        {"photo":"05_scm_dehnung.jpg","caption":"🌙 <b>Phase 2 NEU!</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>SCM-DEHNUNG</b>\n\nKopf wegdrehen + leicht reklinieren.\n⏱ <b>3 Wdh. x 30 Sek./Seite</b>"},
        {"photo":"06_skapula.jpg","caption":"🌙 <b>Phase 2 NEU!</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>SKAPULA-RETRAKTION</b>\n⏱ <b>10 Wdh. x 10 Sek.</b>"},
    ],
}
P3 = {
    "morning": [P1["morning"][0], P2["morning"][2],
        {"photo":"07_extensor_vierfuessler.jpg","caption":"☀️ <b>Phase 3 NEU!</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>EXTENSOREN VIERFUESSLER</b>\n\nKopf langsam senken, ueber CCF zurueck.\n⏱ <b>5-10 Wdh., 3-5 Sek. iso</b>"},
        P1["morning"][1]],
    "midday": P1["midday"] + [{"photo":"06_skapula.jpg","caption":"🌞 <b>SKAPULA + CHIN TUCK</b>\n⏱ 10x10 Sek."}],
    "evening": [P1["evening"][1], P2["evening"][2],
        {"photo":"08_subokzipital.jpg","caption":"🌙 <b>Phase 3 NEU!</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>TENNISBALL RELEASE</b>\n\nUnter Hinterkopf, Knoten suchen.\n⏱ <b>2-3 Minuten</b>"},
        {"photo":None,"caption":"🌙 <b>KIEFERENTSPANNUNG</b>\n😌 Lippen zu, Zaehne auseinander, Zunge oben.\n📝 /schmerz [0-10]\n✅ Gute Nacht!"}],
}
P4 = {
    "morning": [P1["morning"][0], P3["morning"][2], P2["morning"][2],
        {"photo":"06_skapula.jpg","caption":"☀️ <b>SKAPULA-AUSDAUER</b>\nBauchlage Y-Raises.\n⏱ <b>5-10 Wdh. x 5-10 Sek.</b>"}],
    "midday": P1["midday"] + [
        {"photo":"09_kiefer_mundoeffnung.jpg","caption":"🌞 <b>Phase 4 NEU!</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>KONTROLLIERTE MUNDOEFFNUNG</b>\n\nZunge am Gaumen halten!\nMund nur oeffnen solange Zunge oben bleibt.\n\n⏱ <b>10-20 Wdh., 3x/Tag</b>"},
        {"photo":"10_kiefer_widerstand.jpg","caption":"🌞 <b>Phase 4 NEU!</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>KIEFER-KOORDINATION</b>\n\nFinger ans Kinn, symmetrisch oeffnen.\n⏱ <b>10 Wdh., 2x/Tag</b>"}],
    "evening": [P1["evening"][1], P2["evening"][2], P3["evening"][2],
        {"photo":"11_bws_extension.jpg","caption":"🌙 <b>Phase 4 NEU!</b>\n━━━━━━━━━━━━━━━━━━\n\n🔹 <b>BWS-EXTENSION</b>\n\nUeber Stuhllehne strecken.\n⏱ <b>10 Wdh. x 2 Saetze</b>"},
        {"photo":None,"caption":"🌙 <b>KIEFERENTSPANNUNG</b>\n😌 Lippen zu, Zaehne auseinander, Zunge oben.\n📝 /schmerz [0-10]\n✅ Gute Nacht!"}],
}

PHASES = {1:P1, 2:P2, 3:P3, 4:P4}
PHASE_INFO = {1:"🟢 <b>Phase 1: Motorikkontrolle</b> (Woche 1-2)\nCCF + Haltung + SCM-Triggerpunkte",2:"🟡 <b>Phase 2: Ko-Kontraktion</b> (Woche 3-4)\n+ Isometrie + SCM-Dehnung + Skapula",3:"🟠 <b>Phase 3: Kraeftigung</b> (Woche 5-6)\n+ Extensoren + Subokzipitale Release",4:"🔴 <b>Phase 4: Integration</b> (Woche 7+)\n+ Kieferuebungen + BWS-Extension"}

async def send_exercises(context: ContextTypes.DEFAULT_TYPE):
    tod = context.job.data
    for cid in get_active_users():
        user = get_user(cid); phase = user.get("phase",1)
        for ex in PHASES.get(phase,P1).get(tod,[]):
            try:
                p,c = ex["photo"],ex["caption"]
                if p and (IMAGES_DIR/p).exists():
                    with open(IMAGES_DIR/p,"rb") as f: await context.bot.send_photo(chat_id=cid,photo=f,caption=c,parse_mode="HTML")
                else: await context.bot.send_message(chat_id=cid,text=c,parse_mode="HTML")
            except Exception as e:
                if "Forbidden" in str(e): user["active"]=False; set_user(cid,user); break

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_chat.id); user["active"]=True; set_user(u.effective_chat.id, user)
    await u.message.reply_text("✅ <b>HWS Physio Bot v3 + KI-Assistent!</b>\n\n" + PHASE_INFO[user.get('phase',1)] + "\n\n⏰ Uebungen: 07:00, 12:00, 19:00\n\n🤖 <b>KI-Assistent:</b> Schreibe einfach eine Nachricht!\nBeispiele:\n• Welche Supplements bei Tinnitus?\n• Essensplan fuer die Woche\n• Welchen Arzt zuerst?\n• Was ist der SCM?\n\n📋 /phase /schmerz /tagebuch /notiz /arztplan /uebungen /test /reset /stop", parse_mode="HTML")

async def cmd_phase(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_chat.id); phase = user.get("phase",1)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{'✅ ' if phase==i else ''}Phase {i}",callback_data=f"phase_{i}") for i in range(1,5)]])
    await u.message.reply_text(f"📊 <b>Phase {phase}</b>\n\n{PHASE_INFO[phase]}\n\n⬇️ Phase wechseln:", parse_mode="HTML", reply_markup=kb)

async def cb_phase(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    new = int(q.data.split("_")[1]); user = get_user(q.message.chat_id); old = user.get("phase",1)
    user["phase"] = new; set_user(q.message.chat_id, user)
    await q.edit_message_text(f"{'⬆️' if new>old else '⬇️'} Phase {old} → {new}\n\n{PHASE_INFO[new]}", parse_mode="HTML")

async def cmd_schmerz(u: Update, c: ContextTypes.DEFAULT_TYPE):
    args = c.args
    if not args or not args[0].isdigit(): await u.message.reply_text("/schmerz [0-10]"); return
    score = min(10,max(0,int(args[0]))); user = get_user(u.effective_chat.id)
    user.setdefault("pain_log",[]).append({"date":datetime.now().strftime("%d.%m.%Y"),"time":datetime.now().strftime("%H:%M"),"score":score,"phase":user.get("phase",1)})
    user["pain_log"] = user["pain_log"][-60:]; set_user(u.effective_chat.id, user)
    emoji = "🟢" if score<=2 else "🟡" if score<=5 else "🟠" if score<=7 else "🔴"
    await u.message.reply_text(f"{emoji} <b>{score}/10</b> protokolliert.", parse_mode="HTML")

async def cmd_tagebuch(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_chat.id); log = user.get("pain_log",[])
    if not log: await u.message.reply_text("📓 Noch nichts. /schmerz [0-10]"); return
    last = log[-7:]
    lines = [f"{'🟢' if e['score']<=2 else '🟡' if e['score']<=5 else '🟠' if e['score']<=7 else '🔴'} {e['date']} {e.get('time','')} | {'█'*e['score']}{'░'*(10-e['score'])} {e['score']}/10" for e in last]
    avg = sum(e["score"] for e in last)/len(last)
    await u.message.reply_text(f"📓 <b>Letzte 7</b>\n━━━━━━━━━━━━━━━━━━\n\n"+"\n".join(lines)+f"\n\nØ {avg:.1f}/10", parse_mode="HTML")

async def cmd_notiz(u: Update, c: ContextTypes.DEFAULT_TYPE):
    text = " ".join(c.args) if c.args else ""
    if not text: await u.message.reply_text("/notiz [text]"); return
    user = get_user(u.effective_chat.id)
    user.setdefault("health_notes",[]).append({"date":datetime.now().strftime("%d.%m.%Y"),"note":text})
    user["health_notes"] = user["health_notes"][-50:]; set_user(u.effective_chat.id, user)
    await u.message.reply_text(f"📝 Gespeichert: <i>{text}</i>", parse_mode="HTML")

async def cmd_arztplan(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("🏥 <b>Arzt-Checkup Fahrplan</b>\n━━━━━━━━━━━━━━━━━━\n\n<b>SOFORT:</b>\n🦷 Zahnarzt → CMD + Aufbissschiene\n🏋️ Physiotherapeut → HWS Manualtherapie\n\n<b>4 WOCHEN:</b>\n👂 HNO → Tinnitus/Hoersturz\n🧠 Neurologe → Trigeminusneuralgie DD\n\n<b>6-12 MONATE:</b>\n🔬 Orthopaede → MRT Kontrolle\n🩸 Hausarzt → Blut (Vit D, B12, Mg)\n👁️ Augenarzt → Augendruck\n\n<b>JAEHRLICH:</b>\n🫀 Check-up 35\n🦷 Zahnkontrolle + Prophylaxe", parse_mode="HTML")

async def cmd_uebungen(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_chat.id); phase = user.get("phase",1); exercises = PHASES.get(phase,P1)
    text = f"📋 <b>Phase {phase}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for tod,label in [("morning","☀️ MORGENS"),("midday","🌞 MITTAGS"),("evening","🌙 ABENDS")]:
        text += f"<b>{label}:</b>\n"
        for ex in exercises.get(tod,[]):
            for line in ex["caption"].split("\n"):
                if "🔹" in line: text += f"  {line.strip()}\n"; break
        text += "\n"
    await u.message.reply_text(text, parse_mode="HTML")

async def cmd_test(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_chat.id); ex = PHASES.get(user.get("phase",1),P1)["morning"][0]; p = ex["photo"]
    if p and (IMAGES_DIR/p).exists():
        with open(IMAGES_DIR/p,"rb") as f: await c.bot.send_photo(chat_id=u.effective_chat.id,photo=f,caption="🧪 TEST\n\n"+ex["caption"],parse_mode="HTML")
    else: await u.message.reply_text("🧪 TEST\n\n"+ex["caption"], parse_mode="HTML")

async def cmd_reset(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_chat.id); user["chat_history"]=[]; set_user(u.effective_chat.id, user)
    await u.message.reply_text("🗑️ Chat-Verlauf geloescht. Profil + Tagebuch bleiben.")

async def cmd_stop(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_chat.id); user["active"]=False; set_user(u.effective_chat.id, user)
    await u.message.reply_text("❌ Abgemeldet. /start zum Anmelden.")

async def handle_message(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not u.message or not u.message.text: return
    await c.bot.send_chat_action(chat_id=u.effective_chat.id, action="typing")
    answer = await ask_claude(u.effective_chat.id, u.message.text)
    try: await u.message.reply_text(answer, parse_mode="HTML")
    except: await u.message.reply_text(answer)

async def post_init(app):
    await app.bot.set_my_commands([BotCommand("start","Registrieren"),BotCommand("phase","Phase wechseln"),BotCommand("schmerz","Kopfschmerz 0-10"),BotCommand("tagebuch","Schmerztagebuch"),BotCommand("notiz","Notiz speichern"),BotCommand("uebungen","Uebungen"),BotCommand("arztplan","Arzt-Fahrplan"),BotCommand("test","Testuebung"),BotCommand("reset","Chat loeschen"),BotCommand("stop","Abmelden")])

async def error_handler(u,c): logger.error(f"Fehler: {c.error}")

def main():
    if BOT_TOKEN == "DEIN_TELEGRAM_TOKEN": print("export BOT_TOKEN='...'"); return
    if ANTHROPIC_KEY == "DEIN_ANTHROPIC_KEY": print("⚠️ Ohne ANTHROPIC_API_KEY kein KI-Assistent. https://console.anthropic.com")
    app = Application.builder().token(BOT_TOKEN).defaults(Defaults(parse_mode="HTML",tzinfo=TIMEZONE)).post_init(post_init).build()
    for cmd,fn in [("start",cmd_start),("phase",cmd_phase),("schmerz",cmd_schmerz),("tagebuch",cmd_tagebuch),("notiz",cmd_notiz),("uebungen",cmd_uebungen),("arztplan",cmd_arztplan),("test",cmd_test),("reset",cmd_reset),("stop",cmd_stop)]:
        app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CallbackQueryHandler(cb_phase,pattern="^phase_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    jq = app.job_queue
    for name,t in SCHEDULE.items(): jq.run_daily(send_exercises,t,data=name,name=name)
    print("🏥 HWS Physio Bot v3 + KI laeuft!")
    app.run_polling()

if __name__ == "__main__": main()
