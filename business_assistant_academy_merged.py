
# Business Assistant Academy: one-file Telegram Mini App + FastAPI + Gemini
# Python 3.11+
# Install: pip install fastapi uvicorn aiogram google-genai google-auth requests itsdangerous
# Required env: BOT_TOKEN, APP_URL (HTTPS), GEMINI_API_KEY, GOOGLE_CLIENT_ID
# Optional: SESSION_SECRET, DB_PATH=/var/data/academy.db, GEMINI_MODEL=gemini-3.8-flash
# Start: uvicorn business_assistant_academy_merged:app --host 0.0.0.0 --port $PORT
# On Render: use a paid persistent disk mounted at /var/data for SQLite durability.
# IMPORTANT: APP_URL is the Telegram Mini App destination (the Lovable URL by default).
# This Python file is the API/backend and also contains a standalone HTML fallback at /.
# The Lovable frontend must be configured to call this deployed backend API; merely
# setting APP_URL does not connect Lovable page buttons/forms to these API endpoints.
# Set APP_URL to the published Mini App URL and deploy this file as the backend.
# Free instances sleep after inactivity and have ephemeral local files; no host promises forever uptime.

import os, json, time, hmac, hashlib, secrets, sqlite3, asyncio, logging
from urllib.parse import parse_qsl
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google import genai
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram import F
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, MenuButtonWebApp, InlineKeyboardMarkup, InlineKeyboardButton)

BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
APP_URL=os.getenv("APP_URL","https://venture-skill-ladder.lovable.app").strip().rstrip("/")
GEMINI_API_KEY="".join(os.getenv("GEMINI_API_KEY","").split())
GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID","").strip()
MODEL="".join(os.getenv("GEMINI_MODEL","gemini-3.8-flash").split())
DB=os.getenv("DB_PATH","academy.sqlite3")
SECRET=os.getenv("SESSION_SECRET") or secrets.token_urlsafe(48)
PORT=int(os.getenv("PORT","8000"))
logging.basicConfig(level=logging.INFO)
log=logging.getLogger("academy")
signer=URLSafeTimedSerializer(SECRET,salt="academy-session")
ai=genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
bot=Bot(BOT_TOKEN) if BOT_TOKEN else None
dp=Dispatcher()

# Fixed 30-day curriculum: everyone follows the same objectives.
COURSE=[
("Соҳибкорӣ чист?","Что такое предпринимательство?","What is entrepreneurship?","Фаҳмидани соҳибкорӣ ва фарқи он аз танҳо фурӯш.","Understand entrepreneurship and how it differs from selling."),
("Тафаккури соҳибкорӣ","Предпринимательское мышление","Entrepreneurial mindset","Дидани мушкилот ҳамчун имконияти ҳалшаванда.","See problems as opportunities for solutions."),
("Идеяи хуби бизнес","Хорошая бизнес-идея","A good business idea","Интихоби идеяе, ки ба ниёзи воқеӣ ҷавоб медиҳад.","Choose an idea that answers a real need."),
("Муштарӣ кист?","Кто такой клиент?","Who is the customer?","Муайян кардани гурӯҳи муштариён ва ниёзҳои онҳо.","Identify customer groups and their needs."),
("Омӯзиши бозор","Исследование рынка","Market research","Санҷидани талабот ва рақибон.","Check demand and competitors."),
("Маҳсулот ва хизматрасонӣ","Товар и услуга","Product and service","Тавсифи равшани пешниҳоди бизнес.","Describe the business offer clearly."),
("Арзиши пешниҳод","Ценность предложения","Value proposition","Фаҳмондани сабаби интихоби маҳсулот.","Explain why customers may choose a product."),
("Буҷети шахсӣ ва бизнес","Личный и бизнес-бюджет","Personal and business budget","Ҷудо кардани даромад, хароҷот ва пасандоз.","Separate income, expenses, and savings."),
("Сармояи оғоз","Стартовый капитал","Startup capital","Ҳисоб кардани захираҳои зарурӣ.","Estimate resources needed to start."),
("Хароҷоти доимӣ ва тағйирёбанда","Постоянные и переменные расходы","Fixed and variable costs","Фарқ кардани ду намуди хароҷот.","Distinguish two types of costs."),
("Даромад, хароҷот ва фоида","Выручка, расходы и прибыль","Revenue, costs and profit","Ҳисоб кардани фоида бо формулаи оддӣ.","Calculate profit with a simple formula."),
("Нуқтаи безарарӣ","Точка безубыточности","Break-even point","Фаҳмидани ҳаҷми фурӯш барои пӯшонидани хароҷот.","Understand sales needed to cover costs."),
("Нақшаи бизнес","Бизнес-план","Business plan","Навиштани нақшаи кӯтоҳи яксаҳифагӣ.","Write a concise one-page business plan."),
("Ном ва бренд","Название и бренд","Name and brand","Фаҳмидани шахсияти бренд ва эътимод.","Understand brand identity and trust."),
("Асосҳои маркетинг","Основы маркетинга","Marketing basics","Интихоби паём ва канали мувофиқ.","Choose a suitable message and channel."),
("Маркетинги рақамӣ","Цифровой маркетинг","Digital marketing","Фаҳмидани мундариҷа, аудитория ва натиҷа.","Understand content, audience, and results."),
("Маҳорати фурӯш","Навыки продаж","Sales skills","Гӯш кардан ва пешниҳоди роҳи ҳал.","Listen and offer a solution."),
("Муносибат бо муштарӣ","Работа с клиентами","Customer service","Ҷавоби эҳтиромона ба савол ва шикоят.","Respond respectfully to questions and complaints."),
("Идоракунии вақт","Управление временем","Time management","Ҷудо кардани вазифаҳои муҳим.","Prioritize important tasks."),
("Кори дастаҷамъӣ","Командная работа","Teamwork","Тақсим кардани масъулият.","Share responsibilities."),
("Баҳисобгирӣ","Учёт","Bookkeeping","Сабти дурусти даромад ва хароҷот.","Record income and expenses accurately."),
("Пасандоз ва захираи эҳтиётӣ","Сбережения и резерв","Savings and emergency reserve","Сохтани захираи эҳтиётӣ.","Build an emergency reserve."),
("Қарз ва ӯҳдадориҳо","Долги и обязательства","Debt and obligations","Арзёбии масъулият ва арзиши қарз.","Assess obligations and debt cost."),
("Хавфҳои бизнес","Бизнес-риски","Business risks","Шинохтани хавф ва нақшаи эҳтиётӣ.","Recognize risks and prepare a backup plan."),
("Рақобат ва фарқият","Конкуренция и отличие","Competition and differentiation","Ёфтани бартарии воқеӣ.","Find a genuine advantage."),
("Рушди бизнес","Развитие бизнеса","Business growth","Рушди тадриҷӣ бо нигоҳ доштани сифат.","Grow gradually while maintaining quality."),
("Қарорҳои молиявӣ","Финансовые решения","Financial decisions","Муқоисаи интихобҳо бо буҷети виртуалӣ.","Compare choices using a virtual budget."),
("Қабули қарор","Принятие решений","Decision-making","Истифодаи маълумот пеш аз қарор.","Use information before deciding."),
("Лоиҳаи ниҳоӣ: нақшаи бизнес","Итоговый проект: бизнес-план","Final project: business plan","Омода кардани нақшаи хурди тиҷоратӣ.","Prepare a small business plan."),
("Имтиҳон ва муаррифии лоиҳа","Экзамен и презентация проекта","Final assessment and presentation","Нишон додани фаҳмиш ва пешниҳоди лоиҳа.","Demonstrate understanding and present the project.")
]
LANG={
"tj":{"welcome":"Хуш омадӣ ба Business Assistant Academy","choose":"Забонро интихоб кун","objective":"Ҳадаф","homework":"Вазифаи хонагӣ","hint":"Натиҷаи вазифаро навис...","complete":"Анҷом додани дарс","finish":"Офарин! Дарс анҷом ёфт ва пешрафт сабт шуд.","error":"Хато рӯй дод. Бори дигар кӯшиш кун.","loading":"Лутфан интизор шав...","teacher":"Омӯзгори AI","signin":"Бо Google ё Telegram ворид шав."},
"ru":{"welcome":"Добро пожаловать в Business Assistant Academy","choose":"Выберите язык","objective":"Цель","homework":"Домашнее задание","hint":"Опишите результат задания...","complete":"Завершить урок","finish":"Отлично! Урок завершён, прогресс сохранён.","error":"Ошибка. Попробуйте ещё раз.","loading":"Пожалуйста, подождите...","teacher":"AI-преподаватель","signin":"Войдите через Google или Telegram."},
"en":{"welcome":"Welcome to Business Assistant Academy","choose":"Choose language","objective":"Objective","homework":"Homework","hint":"Write what you did...","complete":"Complete lesson","finish":"Great work! Lesson complete and progress saved.","error":"Something went wrong. Try again.","loading":"Please wait...","teacher":"AI Teacher","signin":"Sign in with Google or Telegram."}}

def db():
    c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;return c
def init_db():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT,email TEXT DEFAULT '',lang TEXT DEFAULT 'tj',completed INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS progress(uid TEXT,lesson INTEGER,homework TEXT,done_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(uid,lesson))")
        c.execute("CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY,uid TEXT,role TEXT,body TEXT)")
        c.execute("""CREATE TABLE IF NOT EXISTS bot_state(
            uid TEXT PRIMARY KEY, state TEXT DEFAULT 'idle', part INTEGER DEFAULT 0,
            quiz_index INTEGER DEFAULT 0, quiz_json TEXT DEFAULT '',
            correct INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
def save_user(uid,name,email=""):
    with db() as c:c.execute("INSERT INTO users(id,name,email) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,email=CASE WHEN excluded.email='' THEN users.email ELSE excluded.email END",(uid,name,email))
    return get_user(uid)
def get_user(uid):
    with db() as c:r=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    return dict(r) if r else None
def auth_user(req:Request):
    tok=req.cookies.get("ba_session")
    if not tok:raise HTTPException(401,"Please sign in")
    try:uid=signer.loads(tok,max_age=1209600)["uid"]
    except (BadSignature,SignatureExpired):raise HTTPException(401,"Session expired")
    u=get_user(uid)
    if not u:raise HTTPException(401,"User not found")
    return u
def cookie(uid):
    r=JSONResponse({"ok":True})
    r.set_cookie("ba_session",signer.dumps({"uid":uid}),httponly=True,secure=True,samesite="none",max_age=1209600)
    return r
def check_tg(raw):
    if not BOT_TOKEN:raise HTTPException(503,"BOT_TOKEN missing")
    p=dict(parse_qsl(raw,keep_blank_values=True));h=p.pop("hash",None);p.pop("signature",None)
    if not h:raise HTTPException(401,"Telegram hash missing")
    msg="\n".join(f"{k}={v}" for k,v in sorted(p.items()))
    key=hmac.new(b"WebAppData",BOT_TOKEN.encode(),hashlib.sha256).digest()
    calc=hmac.new(key,msg.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc,h):raise HTTPException(401,"Invalid Telegram signature")
    if time.time()-int(p.get("auth_date","0"))>86400:raise HTTPException(401,"Telegram data expired")
    try:return json.loads(p["user"])
    except Exception:raise HTTPException(401,"Invalid Telegram user data")

def generate(prompt,lang,tokens=2400):
    if not ai:raise HTTPException(503,"GEMINI_API_KEY is not configured")
    ln={"tj":"Tajik","ru":"Russian","en":"English"}[lang]
    system=f"You are a professional, patient AI teacher in Business Assistant Academy. Reply in {ln}. Never pretend to be human or founder. Teach beginners thoroughly: define terms, explain step by step, give realistic examples, show calculations where useful, common mistakes and a recap. Keep the fixed curriculum objective. No guaranteed income claims. Virtual budgets only. Be respectful."
    r=ai.models.generate_content(model=MODEL,contents=system+"\n\n"+prompt,config={"temperature":0.4,"max_output_tokens":tokens})
    return (r.text or "").strip()


# 40 embedded lesson illustrations. Each lesson receives its own topic-specific visual.
ILLUSTRATIONS = [('💡', 'Идеяи тиҷорат', 'Business idea'), ('🧠', 'Тафаккури соҳибкорӣ', 'Entrepreneurial mindset'), ('✨', 'Эҷоди идея', 'Idea creation'), ('👥', 'Муштарӣ', 'Customer'), ('🔎', 'Таҳқиқи бозор', 'Market research'), ('📦', 'Маҳсулот', 'Product'), ('⭐', 'Арзиши пешниҳод', 'Value proposition'), ('🧾', 'Буҷет', 'Budget'), ('🏦', 'Сармояи оғоз', 'Startup capital'), ('🧮', 'Хароҷот', 'Costs'), ('📊', 'Фоида', 'Profit'), ('⚖️', 'Нуқтаи безарарӣ', 'Break-even point'), ('🗂️', 'Нақшаи бизнес', 'Business plan'), ('🎨', 'Бренд', 'Brand'), ('📣', 'Маркетинг', 'Marketing'), ('📱', 'Маркетинги рақамӣ', 'Digital marketing'), ('🤝', 'Фурӯш', 'Sales'), ('💬', 'Хизматрасонӣ', 'Customer service'), ('⏱️', 'Идоракунии вақт', 'Time management'), ('🧑\u200d🤝\u200d🧑', 'Кори дастаҷамъӣ', 'Teamwork'), ('📒', 'Баҳисобгирӣ', 'Bookkeeping'), ('🐷', 'Пасандоз', 'Savings'), ('📑', 'Ӯҳдадориҳо', 'Obligations'), ('🛡️', 'Хавфҳо', 'Risks'), ('🏁', 'Рақобат', 'Competition'), ('🌱', 'Рушди бизнес', 'Business growth'), ('🧭', 'Қарори молиявӣ', 'Financial decision'), ('📈', 'Қабули қарор', 'Decision-making'), ('🧩', 'Лоиҳаи ниҳоӣ', 'Final project'), ('🏆', 'Имтиҳони ниҳоӣ', 'Final assessment'), ('🏪', 'Дӯкони хурд', 'Small shop'), ('🚚', 'Расонидан', 'Delivery'), ('🗓️', 'Нақшаи ҳафта', 'Weekly plan'), ('🎯', 'Ҳадаф', 'Goal'), ('🔢', 'Ҳисобкунӣ', 'Calculation'), ('🗨️', 'Суҳбат бо муштарӣ', 'Customer conversation'), ('💎', 'Сифат', 'Quality'), ('🌐', 'Тиҷорати онлайн', 'Online business'), ('🖥️', 'Муаррифӣ', 'Presentation'), ('🌟', 'Пешрафт', 'Progress')]

def diagram(n, lang):
    idx = max(0, min(29, n-1))
    icon, tj_title, en_title = ILLUSTRATIONS[idx]
    ru_titles = ["Бизнес-идея","Предпринимательское мышление","Создание идеи","Клиент","Исследование рынка",
                 "Продукт","Ценность предложения","Бюджет","Стартовый капитал","Расходы","Прибыль",
                 "Точка безубыточности","Бизнес-план","Бренд","Маркетинг","Цифровой маркетинг",
                 "Продажи","Обслуживание клиентов","Управление временем","Командная работа","Учёт",
                 "Сбережения","Обязательства","Риски","Конкуренция","Развитие бизнеса",
                 "Финансовое решение","Принятие решений","Итоговый проект","Итоговая оценка"]
    title = tj_title if lang == "tj" else (ru_titles[idx] if lang == "ru" else en_title)
    hue = (idx * 37 + 255) % 360
    bars = "".join(
        f'<rect x="210" y="{y}" width="{w}" height="13" rx="6" fill="{fill}"/>'
        for y, w, fill in [(76,250,"#394363"),(105,190,"#303a58"),(134,220,"#303a58")]
    )
    # A different motif for every illustration, with topic icon, progress bars and a unique pattern.
    motif = "".join(
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="hsl({hue},75%,68%)" opacity=".82"/>'
        for x, y, r in [(60+(idx*17)%65,185,8+(idx%4)*3),(95+(idx*13)%65,215,7+(idx%5)*2),(135+(idx*11)%45,175,6+(idx%3)*4)]
    )
    return (
        '<div class="academy-visual-card"><svg viewBox="0 0 520 260" role="img" '
        'aria-label="'+title+'" xmlns="http://www.w3.org/2000/svg">'
        '<defs><linearGradient id="lessonbg'+str(n)+'" x2="1" y2="1">'
        '<stop stop-color="#242d4d"/><stop offset="1" stop-color="#101629"/></linearGradient></defs>'
        '<rect width="520" height="260" rx="22" fill="url(#lessonbg'+str(n)+')"/>'
        '<text x="24" y="27" fill="#bcaeff" font-size="10" font-weight="700" letter-spacing="2">BUSINESS ASSISTANT ACADEMY</text>'
        f'<circle cx="112" cy="112" r="62" fill="hsl({hue},70%,60%)" opacity=".14"/>'
        f'<circle cx="112" cy="112" r="47" fill="none" stroke="hsl({hue},75%,72%)" stroke-width="2"/>'
        f'<text x="112" y="130" text-anchor="middle" font-size="48">{icon}</text>'
        f'{bars}{motif}'
        '<path d="M210 178 H460" stroke="#4b5677" stroke-width="2"/>'
        '<text x="260" y="226" fill="#f6f3ff" font-size="18" font-weight="700" text-anchor="middle">{title}</text>'
        '</svg></div>'
    )


PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#090b18"><title>Business Assistant Academy</title><script src="https://telegram.org/js/telegram-web-app.js"></script><script src="https://accounts.google.com/gsi/client" async defer></script>
<style>
:root{--bg:#090b18;--card:#171c30;--line:#303754;--text:#f5f3ff;--muted:#aab1c8}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 20% 0,#29204e,transparent 42%),var(--bg);color:var(--text);font-family:Inter,system-ui,Arial}.wrap{max-width:760px;margin:auto;padding:18px 15px 100px}.top{display:flex;justify-content:space-between;padding:12px 3px 20px}.brand{font-weight:850}.brand span{color:#e8c77a}.card{background:linear-gradient(145deg,#1b2036,#111629);border:1px solid var(--line);border-radius:21px;padding:20px;margin:12px 0}.tag{font-size:11px;letter-spacing:2px;color:#c4b5fd;font-weight:800}h1{font-size:27px;line-height:1.2}p{line-height:1.7;color:#d6d9e7}.btn{width:100%;border:0;border-radius:13px;padding:14px;background:linear-gradient(110deg,#9b7cff,#6f52d6);color:white;font-weight:800;margin-top:10px}.gold{background:linear-gradient(110deg,#efd58f,#b58b42);color:#171323}.tile{width:100%;text-align:left;color:white;background:#202640;border:1px solid #394263;border-radius:14px;padding:14px;margin:5px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.progress{height:9px;background:#2a304a;border-radius:20px;overflow:hidden}.progress i{display:block;height:100%;background:linear-gradient(90deg,#9270ff,#e9c979)}textarea,select{width:100%;padding:13px;border-radius:12px;background:#0c1224;border:1px solid #394263;color:white;font:inherit}textarea{min-height:110px}.svg svg{width:100%;height:auto}.content{white-space:pre-wrap;line-height:1.8;color:#e4e6f0}.stats{display:flex;justify-content:space-between;color:#aab1c8;margin:9px 0}.nav{position:fixed;bottom:0;left:0;right:0;background:#0b1022ed;border-top:1px solid var(--line);display:flex;justify-content:center;gap:8px;padding:12px 5px calc(12px + env(safe-area-inset-bottom))}.nav button{background:transparent;border:0;color:#c4c9da;padding:9px;font-size:12px}.hidden{display:none!important}.bubble{padding:13px;background:#202640;border-radius:13px;margin:9px 0}.toast{position:fixed;top:10px;left:5%;width:90%;background:#392b59;padding:12px;border-radius:12px;z-index:9}
</style></head><body><div class="wrap"><header class="top"><div class="brand">BUSINESS <span>ASSISTANT</span></div><span id="badge">ACADEMY</span></header>
<section id="auth" class="card"><div class="tag">YOUR LEARNING JOURNEY</div><h1 id="welcome">Business Assistant Academy</h1><p id="choose">Choose language.</p><select id="language" onchange="setLang(this.value)"><option value="tj">Тоҷикӣ</option><option value="ru">Русский</option><option value="en">English</option></select><div id="googleButton" style="margin-top:16px"></div><p id="authNote">Open from Telegram or sign in with Google.</p></section>
<main id="main" class="hidden"><section id="homeView"><div class="card"><div class="tag">PERSONAL LEARNING SPACE</div><h1 id="hello"></h1><p id="intro"></p><div class="stats"><span>Course progress</span><b id="pct">0%</b></div><div class="progress"><i id="bar" style="width:0"></i></div><button class="btn" onclick="startCurrent()" id="continueBtn">Continue</button></div><div class="grid"><button class="tile" onclick="view('lessonsView')">📚 <b id="lessonsText">Lessons</b></button><button class="tile" onclick="view('progressView')">📈 <b id="progressText">Progress</b></button></div><div class="card"><h2 id="teacherText">AI Teacher</h2><button class="btn" onclick="view('teacherView')" id="askBtn">Ask teacher</button></div></section>
<section id="lessonsView" class="hidden card"><h2>30 lessons</h2><div id="lessonList"></div></section>
<section id="lessonView" class="hidden card"><div class="tag" id="lessonNo"></div><h1 id="lessonTitle"></h1><b id="objLabel">Objective</b><p id="objective"></p><div class="svg" id="visual"></div><div class="content" id="content"></div><h2 id="hwTitle">Homework</h2><textarea id="homework"></textarea><button class="btn gold" onclick="finishLesson()" id="finishBtn">Complete lesson</button></section>
<section id="teacherView" class="hidden card"><h2 id="teacherHeading">AI Teacher</h2><div id="chatLog"></div><textarea id="chatInput" placeholder="Ask your question..."></textarea><button class="btn" onclick="sendChat()" id="sendBtn">Send</button></section>
<section id="progressView" class="hidden card"><h2>Progress</h2><div id="progressDetails"></div></section></main></div>
<nav id="nav" class="nav hidden"><button onclick="view('homeView')">⌂ Home</button><button onclick="view('lessonsView')">▤ Lessons</button><button onclick="view('progressView')">◷ Progress</button><button onclick="view('teacherView')">✦ Teacher</button></nav><div id="toast" class="toast hidden"></div>
<script>
const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand()}let lang=localStorage.getItem('ba_lang')||'tj',me=null,current=1;
const D={tj:{welcome:'Хуш омадӣ ба Business Assistant Academy',choose:'Забонро интихоб кун',objective:'Ҳадаф',homework:'Вазифаи хонагӣ',hint:'Натиҷаи вазифаро навис...',complete:'Анҷом додани дарс',finish:'Дарс анҷом ёфт ва пешрафт сабт шуд.',error:'Хато рӯй дод',loading:'Лутфан интизор шав...',teacher:'Омӯзгори AI',ask:'Савол ба омӯзгор',send:'Фиристодан',continue:'Идома',signin:'Бо Google ё Telegram ворид шав.'},ru:{welcome:'Добро пожаловать в Business Assistant Academy',choose:'Выберите язык',objective:'Цель',homework:'Домашнее задание',hint:'Опишите результат задания...',complete:'Завершить урок',finish:'Урок завершён, прогресс сохранён.',error:'Ошибка',loading:'Пожалуйста, подождите...',teacher:'AI-преподаватель',ask:'Спросить преподавателя',send:'Отправить',continue:'Продолжить',signin:'Войдите через Google или Telegram.'},en:{welcome:'Welcome to Business Assistant Academy',choose:'Choose language',objective:'Objective',homework:'Homework',hint:'Write what you did...',complete:'Complete lesson',finish:'Lesson complete. Progress saved.',error:'Error',loading:'Please wait...',teacher:'AI Teacher',ask:'Ask the teacher',send:'Send',continue:'Continue',signin:'Sign in with Google or Telegram.'}};
function t(k){return D[lang][k]||k}function setLang(v){lang=v;localStorage.setItem('ba_lang',v);document.getElementById('badge').textContent=v.toUpperCase();document.getElementById('welcome').textContent=t('welcome');document.getElementById('choose').textContent=t('choose')}
setLang(lang);function toast(s){let x=document.getElementById('toast');x.textContent=s;x.classList.remove('hidden');setTimeout(()=>x.classList.add('hidden'),3000)}
async function api(path,b){let r=await fetch(path,{method:b?'POST':'GET',credentials:'include',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});let d=await r.json();if(!r.ok)throw Error(d.detail||t('error'));return d}
async function googleLogin(r){try{await api('/api/auth/google',{credential:r.credential});await afterLogin()}catch(e){toast(e.message)}}
async function afterLogin(){me=await api('/api/me');document.getElementById('auth').classList.add('hidden');document.getElementById('main').classList.remove('hidden');document.getElementById('nav').classList.remove('hidden');document.getElementById('hello').textContent=t('welcome')+', '+me.name;document.getElementById('teacherText').textContent=t('teacher');document.getElementById('askBtn').textContent=t('ask');document.getElementById('teacherHeading').textContent=t('teacher');document.getElementById('sendBtn').textContent=t('send');await loadHome()}
async function tgLogin(){if(!tg?.initData)return false;try{await api('/api/auth/telegram',{initData:tg.initData});await afterLogin();return true}catch(e){toast(e.message);return false}}
window.addEventListener('load',async()=>{if(tg?.initData&&await tgLogin())return;try{await afterLogin()}catch(e){if(window.GOOGLE_CLIENT_ID&&window.google){google.accounts.id.initialize({client_id:window.GOOGLE_CLIENT_ID,callback:googleLogin});google.accounts.id.renderButton(document.getElementById('googleButton'),{theme:'filled_black',size:'large',shape:'pill',width:280})}else document.getElementById('authNote').textContent=t('signin')}});
function view(id){['homeView','lessonsView','lessonView','teacherView','progressView'].forEach(x=>document.getElementById(x).classList.toggle('hidden',x!==id));if(id==='lessonsView')loadLessons();if(id==='progressView')loadProgress()}
async function loadHome(){let d=await api('/api/dashboard');current=d.current;let p=Math.round(d.completed/30*100);document.getElementById('pct').textContent=p+'%';document.getElementById('bar').style.width=p+'%'}
async function loadLessons(){let d=await api('/api/lessons');document.getElementById('lessonList').innerHTML=d.items.map(x=>`<button class="tile" onclick="startLesson(${x.no})">${x.no<=me.completed?'✓':x.no===d.current?'▶':'•'} ${esc(x.title)}</button>`).join('')}
async function startCurrent(){await startLesson(current)}
async function startLesson(n){try{view('lessonView');document.getElementById('content').textContent=t('loading');let d=await api('/api/lesson',{lesson_no:n});current=n;document.getElementById('lessonNo').textContent='LESSON '+n+' / 30';document.getElementById('lessonTitle').textContent=d.title;document.getElementById('objLabel').textContent=t('objective');document.getElementById('objective').textContent=d.objective;document.getElementById('visual').innerHTML=d.visual;document.getElementById('content').textContent=d.content;document.getElementById('hwTitle').textContent=t('homework');document.getElementById('homework').placeholder=t('hint');document.getElementById('finishBtn').textContent=t('complete')}catch(e){toast(e.message)}}
async function finishLesson(){try{let d=await api('/api/complete',{lesson_no:current,homework:document.getElementById('homework').value});toast(d.message);me=await api('/api/me');await loadHome();view('progressView')}catch(e){toast(e.message)}}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function sendChat(){let b=document.getElementById('chatInput'),m=b.value.trim();if(!m)return;b.value='';let l=document.getElementById('chatLog');l.innerHTML+=`<div class="bubble"><b>You</b><p>${esc(m)}</p></div><div class="bubble" id="wait"><b>${t('teacher')}</b><p>${t('loading')}</p></div>`;try{let d=await api('/api/chat',{message:m});document.getElementById('wait').innerHTML=`<b>${t('teacher')}</b><p>${esc(d.answer).replace(/\n/g,'<br>')}</p>`}catch(e){document.getElementById('wait').textContent=e.message}}
async function loadProgress(){let d=await api('/api/dashboard');document.getElementById('progressDetails').innerHTML=`<h1>${d.completed}/30</h1><div class="progress"><i style="width:${d.completed/30*100}%"></i></div>`+d.items.map(x=>`<div class="stats"><span>Lesson ${x.lesson}</span><b>✓</b></div>`).join('')}
</script></body></html>'''

@asynccontextmanager
async def lifespan(app):
    init_db()
    task=None
    if bot:
        async def polling():
            if APP_URL:
                try: await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Open Academy",web_app=WebAppInfo(url=APP_URL)))
                except Exception: log.exception("Could not set Telegram menu button")
            await dp.start_polling(bot)
        task=asyncio.create_task(polling())
    yield
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
    if bot: await bot.session.close()

app=FastAPI(title="Business Assistant Academy",lifespan=lifespan)
FRONTEND_ORIGINS = [x.strip() for x in os.getenv(
    "FRONTEND_ORIGINS", "https://venture-skill-ladder.lovable.app"
).split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS,
                   allow_credentials=True, allow_methods=["GET","POST","OPTIONS"],
                   allow_headers=["Content-Type","Authorization"])
@app.get("/",response_class=HTMLResponse)
async def index():
    return HTMLResponse(PAGE.replace("</head>",f"<script>window.GOOGLE_CLIENT_ID={json.dumps(GOOGLE_CLIENT_ID)};</script></head>"))
@app.get("/health")
async def health():return {"ok":True,"ai":bool(ai),"google":bool(GOOGLE_CLIENT_ID),"telegram":bool(bot)}
class GoogleBody(BaseModel):credential:str
class TelegramBody(BaseModel):initData:str
class LessonBody(BaseModel):lesson_no:int|None=None
class ChatBody(BaseModel):message:str=Field(min_length=1,max_length=5000)
class CompleteBody(BaseModel):lesson_no:int;homework:str=Field(min_length=8,max_length=4000)

@app.post("/api/auth/google")
async def auth_google(b:GoogleBody):
    if not GOOGLE_CLIENT_ID:raise HTTPException(503,"GOOGLE_CLIENT_ID not configured")
    try:
        info=id_token.verify_oauth2_token(b.credential,google_requests.Request(),GOOGLE_CLIENT_ID)
        uid="google:"+info["sub"];save_user(uid,info.get("name","Student"),info.get("email",""))
        return cookie(uid)
    except Exception as e:
        log.warning("Google auth failed: %s",e);raise HTTPException(401,"Google token verification failed")
@app.post("/api/auth/telegram")
async def auth_telegram(b:TelegramBody):
    x=check_tg(b.initData);uid="telegram:"+str(x["id"])
    save_user(uid,(x.get("first_name","")+" "+x.get("last_name","")).strip() or "Student")
    return cookie(uid)
@app.get("/api/me")
async def me(u=Depends(auth_user)):return {"id":u["id"],"name":u["name"],"email":u["email"],"lang":u["lang"],"completed":u["completed"]}
@app.get("/api/dashboard")
async def dashboard(u=Depends(auth_user)):
    with db() as c:items=[dict(x) for x in c.execute("SELECT lesson,done_at FROM progress WHERE uid=? ORDER BY lesson",(u["id"],)).fetchall()]
    return {"completed":u["completed"],"current":min(u["completed"]+1,30),"items":items}
@app.get("/api/lessons")
async def lessons(u=Depends(auth_user)):
    ix={"tj":0,"ru":1,"en":2}[u["lang"]]
    return {"current":min(u["completed"]+1,30),"items":[{"no":i+1,"title":x[ix]} for i,x in enumerate(COURSE)]}
@app.post("/api/lesson")
async def lesson(b:LessonBody,u=Depends(auth_user)):
    n=b.lesson_no or min(u["completed"]+1,30)
    if n<1 or n>30 or n>u["completed"]+1:raise HTTPException(403,"Complete previous lesson first")
    ix={"tj":0,"ru":1,"en":2}[u["lang"]];title=COURSE[n-1][ix]
    obj=COURSE[n-1][3] if u["lang"]=="tj" else COURSE[n-1][4]
    prompt=f"Write a complete high-quality beginner lesson for day {n}/30. Title: {title}. Fixed objective: {obj}. In {u['lang']}, 700-1000 words. Include why it matters, definitions, step-by-step teaching, two practical Tajikistan-relevant examples, one worked example/calculation, common mistakes, 3-point recap, and 3 reflection questions. Do not change the objective or promise income."
    try:content=await asyncio.to_thread(generate,prompt,u["lang"],2600)
    except Exception:log.exception("Lesson AI failed");raise HTTPException(503,"AI unavailable. Check GEMINI_API_KEY and model access.")
    return {"title":title,"objective":obj,"content":content,"visual":diagram(n,u["lang"])}
@app.post("/api/chat")
async def chat(b:ChatBody,u=Depends(auth_user)):
    with db() as c:hist=c.execute("SELECT role,body FROM chats WHERE uid=? ORDER BY id DESC LIMIT 8",(u["id"],)).fetchall()
    context="\n".join(f"{x['role']}: {x['body']}" for x in reversed(hist))
    prompt=f"Beginner student conversation:\n{context}\nQuestion: {b.message}\\nAnswer fully and accurately, define terms, explain step by step, give examples and recap."
    try:answer=await asyncio.to_thread(generate,prompt,u["lang"],2200)
    except Exception:log.exception("Chat AI failed");raise HTTPException(503,"AI teacher temporarily unavailable")
    with db() as c:
        c.execute("INSERT INTO chats(uid,role,body) VALUES(?,?,?)",(u["id"],"student",b.message))
        c.execute("INSERT INTO chats(uid,role,body) VALUES(?,?,?)",(u["id"],"teacher",answer))
    return {"answer":answer}
@app.post("/api/complete")
async def complete(b:CompleteBody,u=Depends(auth_user)):
    if b.lesson_no<1 or b.lesson_no>30 or b.lesson_no>u["completed"]+1:raise HTTPException(403,"Complete lessons in order")
    with db() as c:
        c.execute("INSERT INTO progress(uid,lesson,homework) VALUES(?,?,?) ON CONFLICT(uid,lesson) DO UPDATE SET homework=excluded.homework,done_at=CURRENT_TIMESTAMP",(u["id"],b.lesson_no,b.homework))
        c.execute("UPDATE users SET completed=MAX(completed,?) WHERE id=?",(b.lesson_no,u["id"]))
    return {"ok":True,"message":LANG[u["lang"]]["finish"]}


# ---------------- MERGED TELEGRAM COURSE ----------------
# Telegram bot and Mini App share the same SQLite users, curriculum and lesson progress.

def bot_uid(tg_id: int) -> str:
    return "telegram:" + str(tg_id)

def bot_user(tg_id: int, name: str):
    uid = bot_uid(tg_id)
    existing = get_user(uid)
    if existing is None:
        save_user(uid, name or "Student")
        with db() as c:
            c.execute("UPDATE users SET lang='' WHERE id=?", (uid,))
    else:
        save_user(uid, name or "Student")
    return get_user(uid)

def get_bot_state(uid: str):
    with db() as c:
        row = c.execute("SELECT * FROM bot_state WHERE uid=?", (uid,)).fetchone()
        if row is None:
            c.execute("INSERT INTO bot_state(uid) VALUES(?)", (uid,))
            row = c.execute("SELECT * FROM bot_state WHERE uid=?", (uid,)).fetchone()
        return dict(row)

def set_bot_state(uid: str, **values):
    allowed = {"state", "part", "quiz_index", "quiz_json", "correct", "total"}
    values = {k: v for k, v in values.items() if k in allowed}
    if values:
        fields = ", ".join(f"{k}=?" for k in values)
        with db() as c:
            c.execute(f"UPDATE bot_state SET {fields}, updated_at=CURRENT_TIMESTAMP WHERE uid=?",
                      (*values.values(), uid))

BOT_TEXT = {
 "tj": {
  "choose":"Забони омӯзишро интихоб кун:", "welcome":"Салом, {name}! Хуш омадӣ ба Business Assistant Academy.",
  "menu":"📚 **Business Assistant Academy**\n\nДарс: {current}/30\nАнҷомёфта: {done}/30\nИнтихоб кун:",
  "start":"Оғози дарс","lessons":"Рӯйхати дарсҳо","progress":"Пешрафт","ask":"Савол ба омӯзгори AI",
  "language":"Забон","next":"Қисми навбатӣ","quiz":"Саволи {n}/5","scenario":"Масъалаи амалӣ",
  "homework":"Вазифаи хонагӣ","answer":"Ҷавобатро навис:","done":"Офарин! Дарс анҷом ёфт ва пешрафт сабт шуд.",
  "already":"Ин дарс аллакай анҷом ёфтааст.","help":"Саволатро навис; ман ҷавоб медиҳам.",
  "progress_text":"📊 Анҷомёфта: {done}/30 дарс.\nҶавобҳои дуруст: {correct}/{total}.",
  "objective":"Ҳадаф","open":"🚀 Кушодани Mini App"
 },
 "ru": {
  "choose":"Выберите язык обучения:","welcome":"Здравствуйте, {name}! Добро пожаловать в Business Assistant Academy.",
  "menu":"📚 **Business Assistant Academy**\n\nУрок: {current}/30\nЗавершено: {done}/30\nВыберите раздел:",
  "start":"Начать урок","lessons":"Список уроков","progress":"Прогресс","ask":"Спросить AI-преподавателя",
  "language":"Язык","next":"Следующая часть","quiz":"Вопрос {n}/5","scenario":"Практическая задача",
  "homework":"Домашнее задание","answer":"Напишите свой ответ:","done":"Отлично! Урок завершён, прогресс сохранён.",
  "already":"Этот урок уже завершён.","help":"Напишите вопрос; я отвечу.",
  "progress_text":"📊 Завершено: {done}/30 уроков.\nПравильные ответы: {correct}/{total}.",
  "objective":"Цель","open":"🚀 Открыть Mini App"
 },
 "en": {
  "choose":"Choose your learning language:","welcome":"Hello, {name}! Welcome to Business Assistant Academy.",
  "menu":"📚 **Business Assistant Academy**\n\nLesson: {current}/30\nCompleted: {done}/30\nChoose a section:",
  "start":"Start lesson","lessons":"Lesson list","progress":"Progress","ask":"Ask the AI teacher",
  "language":"Language","next":"Next part","quiz":"Question {n}/5","scenario":"Practical task",
  "homework":"Homework","answer":"Write your answer:","done":"Great work! Lesson completed and progress saved.",
  "already":"This lesson is already complete.","help":"Write your question; I will answer.",
  "progress_text":"📊 Completed: {done}/30 lessons.\nCorrect answers: {correct}/{total}.",
  "objective":"Objective","open":"🚀 Open Mini App"
 }
}

def bt(lang: str, key: str, **kwargs):
    return BOT_TEXT.get(lang, BOT_TEXT["tj"]).get(key, key).format(**kwargs)

def bot_keyboard(user):
    lang = user.get("lang") or "tj"
    rows = [
      [InlineKeyboardButton(text="📖 " + bt(lang,"start"), callback_data="ba:lesson")],
      [InlineKeyboardButton(text="📚 " + bt(lang,"lessons"), callback_data="ba:lessons"),
       InlineKeyboardButton(text="📊 " + bt(lang,"progress"), callback_data="ba:progress")],
      [InlineKeyboardButton(text="🤖 " + bt(lang,"ask"), callback_data="ba:ask")],
      [InlineKeyboardButton(text="🌐 " + bt(lang,"language"), callback_data="ba:language")]
    ]
    if APP_URL.startswith("https://"):
        rows.append([InlineKeyboardButton(text=bt(lang,"open"), web_app=WebAppInfo(url=APP_URL))])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
      InlineKeyboardButton(text="🇹🇯 Тоҷикӣ", callback_data="ba:lang:tj"),
      InlineKeyboardButton(text="🇷🇺 Русский", callback_data="ba:lang:ru"),
      InlineKeyboardButton(text="🇬🇧 English", callback_data="ba:lang:en")
    ]])

def one_button(label, data):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=data)]])

async def bot_quiz(message: Message, user, index: int):
    if index >= 5:
        lang = user["lang"]
        scenario = {
          "tj":"Барои як лоиҳаи омӯзишӣ 1 000 сомонии виртуалӣ дорӣ. Онро байни маводи зарурӣ, рекламаи озмоишӣ ва захираи эҳтиётӣ чӣ гуна тақсим мекунӣ? Сабабро фаҳмон. Ин танҳо машқи омӯзишӣ аст.",
          "ru":"У тебя есть 1 000 виртуальных сомони для учебного проекта. Как распределишь их между материалами, тестовой рекламой и резервом? Объясни почему. Это учебная симуляция.",
          "en":"You have 1,000 virtual somoni for a learning project. How would you divide it between materials, test marketing and a reserve? Explain why. This is a learning simulation."
        }[lang]
        set_bot_state(user["id"], state="scenario")
        await message.answer(f"🧠 **{bt(lang,'scenario')}**\n\n{scenario}\n\n{bt(lang,'answer')}", parse_mode="Markdown")
        return

    day = min(user["completed"] + 1, 30)
    title = COURSE[day-1][{"tj":0,"ru":1,"en":2}[user["lang"]]]
    objective = COURSE[day-1][3 if user["lang"] == "tj" else 4]
    prompt = (f"Create quiz question {index+1}/5 for lesson {day}: {title}. Objective: {objective}. "
              f"Return ONLY JSON: {{\"q\":\"question\",\"a\":[\"A\",\"B\",\"C\"],"
              f"\"correct\":0,\"why\":\"explanation\"}}. Language: {user['lang']}.")
    raw = await asyncio.to_thread(generate, prompt, user["lang"], 450)
    try:
        quiz = json.loads(raw[raw.find("{"):raw.rfind("}")+1])
        if len(quiz["a"]) != 3 or int(quiz["correct"]) not in (0,1,2):
            raise ValueError("Invalid quiz")
        quiz["correct"] = int(quiz["correct"])
    except Exception:
        quiz = {
          "tj":{"q":"Чӣ барои санҷидани идея муфид аст?","a":["Пурсидани фикри муштариён","Тахмин кардан","Нодида гирифтан"],"correct":0,"why":"Пурсиши муштариён талаботро равшан мекунад."},
          "ru":{"q":"Что помогает проверить бизнес-идею?","a":["Опрос клиентов","Угадывание","Игнорирование спроса"],"correct":0,"why":"Опрос помогает понять спрос."},
          "en":{"q":"What helps validate an idea?","a":["Ask potential customers","Guess","Ignore demand"],"correct":0,"why":"Customer research helps identify demand."}
        }[user["lang"]]
    set_bot_state(user["id"], state="quiz", quiz_index=index, quiz_json=json.dumps(quiz,ensure_ascii=False))
    buttons = [[InlineKeyboardButton(text=f"{'ABC'[i]}. {a[:60]}",callback_data=f"ba:quiz:{index}:{i}")]
               for i,a in enumerate(quiz["a"])]
    await message.answer(f"❓ **{bt(user['lang'],'quiz',n=index+1)}**\n\n{quiz['q']}",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),parse_mode="Markdown")

@dp.message(CommandStart())
async def bot_start(message: Message):
    user = bot_user(message.from_user.id, message.from_user.full_name)
    if not user["lang"]:
        await message.answer(bt("tj","choose"), reply_markup=lang_keyboard())
    else:
        await message.answer(bt(user["lang"],"welcome",name=user["name"]),
                             reply_markup=bot_keyboard(user))

@dp.callback_query(F.data.startswith("ba:lang:"))
async def bot_language(call: CallbackQuery):
    lang = call.data.rsplit(":",1)[1]
    if lang not in ("tj","ru","en"):
        await call.answer()
        return
    user = bot_user(call.from_user.id,call.from_user.full_name)
    with db() as c:
        c.execute("UPDATE users SET lang=? WHERE id=?",(lang,user["id"]))
    user = get_user(user["id"])
    await call.message.answer(bt(lang,"welcome",name=user["name"]),reply_markup=bot_keyboard(user))
    await call.answer()

@dp.callback_query(F.data == "ba:language")
async def bot_language_menu(call: CallbackQuery):
    await call.message.answer(bt("tj","choose"),reply_markup=lang_keyboard())
    await call.answer()

@dp.callback_query(F.data == "ba:lesson")
async def bot_start_lesson(call: CallbackQuery):
    user = bot_user(call.from_user.id,call.from_user.full_name)
    day = min(user["completed"]+1,30)
    title = COURSE[day-1][{"tj":0,"ru":1,"en":2}[user["lang"]]]
    objective = COURSE[day-1][3 if user["lang"]=="tj" else 4]
    set_bot_state(user["id"],state="part",part=0,quiz_index=0,quiz_json="")
    await call.message.answer(
      f"📘 **{day}/30 — {title}**\n\n🎯 **{bt(user['lang'],'objective')}:** {objective}\n\nДарс аз се қисм иборат аст.",
      reply_markup=one_button(bt(user["lang"],"next"),"ba:part:0"),parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("ba:part:"))
async def bot_lesson_part(call: CallbackQuery):
    user = bot_user(call.from_user.id,call.from_user.full_name)
    part = int(call.data.rsplit(":",1)[1])
    if part not in (0,1,2):
        await call.answer()
        return
    day = min(user["completed"]+1,30)
    title = COURSE[day-1][{"tj":0,"ru":1,"en":2}[user["lang"]]]
    objective = COURSE[day-1][3 if user["lang"]=="tj" else 4]
    prompts = [
      f"Teach lesson {day}/30 '{title}', objective '{objective}'. Part 1/3: explain simply and give a daily-life example. Do not ask questions.",
      f"Teach lesson {day}/30 '{title}'. Part 2/3: give a practical example or simple calculation step by step. Avoid repeating part 1.",
      f"Teach lesson {day}/30 '{title}'. Part 3/3: summarize the key points and prepare the student for a five-question quiz. Do not reveal answers."
    ]
    content = await asyncio.to_thread(generate,prompts[part],user["lang"],850)
    if part < 2:
        set_bot_state(user["id"],state="part",part=part+1)
        await call.message.answer(content,reply_markup=one_button(bt(user["lang"],"next"),f"ba:part:{part+1}"))
    else:
        set_bot_state(user["id"],state="quiz",part=3,quiz_index=0)
        await call.message.answer(content)
        await bot_quiz(call.message,user,0)
    await call.answer()

@dp.callback_query(F.data.startswith("ba:quiz:"))
async def bot_answer_quiz(call: CallbackQuery):
    user = bot_user(call.from_user.id,call.from_user.full_name)
    try:
        _,_,idx_s,opt_s = call.data.split(":")
        idx,opt = int(idx_s),int(opt_s)
        state = get_bot_state(user["id"])
        if state["state"] != "quiz" or idx != state["quiz_index"]:
            await call.answer("Ин савол дигар фаъол нест.",show_alert=True)
            return
        quiz = json.loads(state["quiz_json"])
        is_correct = opt == int(quiz["correct"])
        set_bot_state(user["id"],correct=state["correct"]+(1 if is_correct else 0),
                      total=state["total"]+1,quiz_index=idx+1)
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer(("✅ Дуруст! " if is_correct else "❌ Ин ҷавоби дуруст нест. ")+quiz["why"])
        await call.answer("Қабул шуд")
        await bot_quiz(call.message,user,idx+1)
    except Exception:
        log.exception("Quiz handler error")
        await call.answer("Хатогӣ дар санҷиш.",show_alert=True)

@dp.callback_query(F.data == "ba:progress")
async def bot_progress(call: CallbackQuery):
    user = bot_user(call.from_user.id,call.from_user.full_name)
    state = get_bot_state(user["id"])
    await call.message.answer(bt(user["lang"],"progress_text",done=user["completed"],
                                 correct=state["correct"],total=state["total"]),
                              reply_markup=bot_keyboard(user))
    await call.answer()

@dp.callback_query(F.data == "ba:lessons")
async def bot_lessons(call: CallbackQuery):
    user = bot_user(call.from_user.id,call.from_user.full_name)
    ix = {"tj":0,"ru":1,"en":2}[user["lang"]]
    lines = []
    for n,row in enumerate(COURSE,1):
        marker = "✅" if n <= user["completed"] else "▶️" if n == user["completed"]+1 else "🔒"
        lines.append(f"{marker} {n:02d}. {row[ix]}")
    await call.message.answer("\n".join(lines),reply_markup=bot_keyboard(user))
    await call.answer()

@dp.callback_query(F.data == "ba:ask")
async def bot_ask(call: CallbackQuery):
    user = bot_user(call.from_user.id,call.from_user.full_name)
    set_bot_state(user["id"],state="ask")
    await call.message.answer(bt(user["lang"],"help"))
    await call.answer()

@dp.message()
async def bot_text(message: Message):
    if not message.from_user or not message.text:
        return
    user = bot_user(message.from_user.id,message.from_user.full_name)
    if not user["lang"]:
        await message.answer(bt("tj","choose"),reply_markup=lang_keyboard())
        return
    state = get_bot_state(user["id"])
    if state["state"] == "scenario":
        set_bot_state(user["id"],state="scenario_review")
        prompt = ("Give kind, constructive feedback on this student's virtual-budget exercise. "
                  "Comment on costs, testing demand and reserve. No real-money investment advice. "
                  "Answer in " + user["lang"] + ".\n\n" + message.text)
        feedback = await asyncio.to_thread(generate,prompt,user["lang"],450)
        await message.answer(feedback)
        day = min(user["completed"]+1,30)
        title = COURSE[day-1][{"tj":0,"ru":1,"en":2}[user["lang"]]]
        task = await asyncio.to_thread(
          generate,
          f"Create a short, safe, no-cost homework task in 3 steps for lesson '{title}'. Language: {user['lang']}.",
          user["lang"],400)
        set_bot_state(user["id"],state="homework")
        await message.answer(f"📝 **{bt(user['lang'],'homework')}**\n\n{task}\n\n{bt(user['lang'],'answer')}",
                             parse_mode="Markdown")
    elif state["state"] == "homework":
        feedback = await asyncio.to_thread(
          generate,"Give brief, respectful feedback on this homework and say the lesson is complete. "
                   "Answer in "+user["lang"]+".\n\n"+message.text,user["lang"],350)
        await message.answer(feedback)
        day = min(user["completed"]+1,30)
        with db() as c:
            c.execute("INSERT INTO progress(uid,lesson,homework) VALUES(?,?,?) "
                      "ON CONFLICT(uid,lesson) DO UPDATE SET homework=excluded.homework,done_at=CURRENT_TIMESTAMP",
                      (user["id"],day,message.text))
            c.execute("UPDATE users SET completed=MAX(completed,?) WHERE id=?",(day,user["id"]))
        set_bot_state(user["id"],state="idle")
        await message.answer(bt(user["lang"],"done"),reply_markup=bot_keyboard(get_user(user["id"])))
    elif state["state"] == "ask":
        answer = await asyncio.to_thread(generate,
            "Answer this beginner's business-learning question clearly in "+user["lang"]+":\n"+message.text,
            user["lang"],900)
        await message.answer(answer)
    else:
        await message.answer(bt(user["lang"],"menu",current=min(user["completed"]+1,30),done=user["completed"]),
                             reply_markup=bot_keyboard(user),parse_mode="Markdown")


if __name__=="__main__":
    import uvicorn
    uvicorn.run("business_assistant_academy_merged:app",host="0.0.0.0",port=PORT,reload=False)
