"""Generate an Arabic kids story with Gemini, split into illustrated scenes.
Returns dict: title, story, description, tags, character, scenes[{narration,image_prompt,search}], thumbnail_prompt."""
import json, os, re, random, time, requests

HISTORY_FILE = os.getenv("HISTORY_FILE", "kids_history.json")
MODELS = [m.strip() for m in os.getenv("GEMINI_MODEL", "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-flash-latest").split(",") if m.strip()]
N_SCENES = int(os.getenv("N_SCENES", "18"))
MODE = os.getenv("CONTENT_MODE", "edu")   # edu = short educational rhyme (ages 3-7) with a fixed mascot cast; story = long story
EDU_SCENES = int(os.getenv("EDU_SCENES", "10"))
# Fixed recurring cast: same words + same seed in every video = a recognizable brand look
MASCOT_NAME, MASCOT = "لولو", "a small round fluffy orange baby fox cub with big friendly eyes and a blue scarf"
FRIEND_NAME, FRIEND = "بيبو", "a cute round light-blue baby elephant with big ears and a yellow bow"
MASCOT_SEED = int(os.getenv("MASCOT_SEED", "20260"))
# Weekly content pillars (approved plan): weekday in Cairo time -> topic keywords. Mon=0 ... Sun=6
PILLARS = {5: ("حروف الهجاء",), 6: ("الأرقام",), 0: ("الألوان", "الأشكال"), 1: ("قول من فضلك", "غسل اليدين", "المشاركة", "السلام", "ترتيب الألعاب", "المشاعر"),
           2: ("أصوات الحيوانات", "الحيوانات", "الفواكه"), 3: ("حروف الهجاء", "الأرقام"), 4: ("الأرقام",)}
def cairo_now():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Africa/Cairo"))
def pillar_topics(topics):
    force = os.getenv("FORCE_DAY")
    day = int(force) if force not in (None, "") else cairo_now().weekday()
    keys = PILLARS.get(day, ())
    sel = [t for t in topics if any(k in t for k in keys)]
    return sel or topics, day

EDU_TOPICS = [
    "حروف الهجاء: الألف والباء والتاء والثاء (كل حرف مع كلمة وشيء يبدأ به)", "حروف الهجاء: الجيم والحاء والخاء والدال",
    "حروف الهجاء: الذال والراء والزاي والسين", "حروف الهجاء: الشين والصاد والضاد والطاء",
    "حروف الهجاء: الظاء والعين والغين والفاء", "حروف الهجاء: القاف والكاف واللام والميم", "حروف الهجاء: النون والهاء والواو والياء",
    "الأرقام من 1 إلى 5 (عد الأشياء)", "الأرقام من 6 إلى 10 (عد الأشياء)", "الألوان الأساسية (أحمر أزرق أصفر أخضر)",
    "الأشكال (دائرة مربع مثلث مستطيل)", "أيام الأسبوع", "أصوات الحيوانات وأسماؤها", "أسماء الفواكه والخضروات",
    "أجزاء الجسم", "قول من فضلك وشكرا وعفوا", "غسل اليدين وتنظيف الأسنان", "المشاركة واللعب مع الأصدقاء",
    "السلام وتحية الجيران واحترام الكبار", "ترتيب الألعاب والنظافة", "المشاعر: سعيد وحزين وغاضب وخائف", "الأضداد: كبير وصغير، طويل وقصير",
]
THEMES = ["الصدق", "الكرم والمشاركة", "مساعدة الآخرين", "الشجاعة", "الصبر", "احترام الوالدين",
          "النظافة", "الصداقة", "الاعتذار", "عدم التنمر", "التعاون", "الشكر والامتنان", "حب الحيوانات", "الاجتهاد"]
HEROES = ["أرنب صغير", "قطة", "فيل", "عصفورة", "سلحفاة", "طفل اسمه يوسف", "طفلة اسمها ليلى", "دب", "نحلة", "زرافة"]


def uploaded_today():
    today = cairo_now().strftime("%Y-%m-%d")
    return any(h.get("date") == today for h in load_history())


def load_history():
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(h):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h[-200:], f, ensure_ascii=False, indent=1)


def _call(model, prompt, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(url, params={"key": key}, timeout=180, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"}})
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def generate_story():
    if MODE == "edu":
        return generate_edu()
    return generate_story_long()


def record_history(data):
    h = load_history(); h.append({"title": data["title"], "theme": data.get("_theme"), "date": cairo_now().strftime("%Y-%m-%d")}); save_history(h)


def generate_edu():
    key = os.environ["GEMINI_API_KEY"]
    hist = load_history()
    used = [h["title"] for h in hist[-40:]]
    done_topics = [h.get("theme") for h in hist if h.get("theme")]
    pool, _day = pillar_topics(EDU_TOPICS)
    left = [t for t in pool if t not in done_topics] or pool
    print("pillar day:", _day, "| topic:", left[0])
    topic = left[0] if os.getenv("EDU_ORDERED", "1") == "1" else random.choice(left)
    prompt = f"""اكتب أنشودة تعليمية قصيرة بالعربية الفصحى المبسطة لأطفال من 3 إلى 7 سنوات.
موضوع الدرس: {topic}.
الأبطال الثابتون: {MASCOT_NAME} ({MASCOT}) و{FRIEND_NAME} ({FRIEND}). يعلّمان الأطفال بمرح.
الشروط: {EDU_SCENES} مشاهد، كل مشهد من 20 إلى 32 كلمة، جمل قصيرة جدا موزونة ومقفاة كالأناشيد، مع لازمة (جملة ختام قصيرة مكررة بنفس اللفظ) في آخر كل مشهدين. المشهد الأول يبدأ بسؤال جذاب للأطفال أو نداء مرح فورا (بدون مقدمة طويلة). كل مشهد يعلّم عنصرا واحدا واضحا ويكرره. المشهد الأخير: مراجعة سريعة للدرس وتحية ختام سعيدة وتشجيع.
ممنوع: العنف والرعب والسياسة وأي محتوى غير مناسب. لا تكرر هذه العناوين: {used}
لكل مشهد حقل obj: كلمة إنجليزية واحدة فقط من هذه القائمة تمثل الشيء الذي يتعلمه الطفل في المشهد (rabbit, duck, apple, banana, star, ball, flower, fish, cat, tree, sun, house, heart, car, fox) واختر الأقرب، وحقل count: عدد النسخ من الشيء في الصورة من 1 إلى 5 (للأرقام فقط، وإلا 1).
لكل مشهد حقل on_screen: النص الكبير الذي سيظهر على الشاشة بالعربية (حرف مع كلمة مثل "أ: أرنب"، أو رقم وكلمته "3: ثلاثة"، أو اللون، أو الكلمة المهمة)، أقل من 4 كلمات.
لكل مشهد image_prompt بالإنجليزية (جملتان): ما يحدث بالضبط، والشخصية {MASCOT_NAME} بوصفها الحرفي: {MASCOT}، وعند ظهور {FRIEND_NAME} بوصفه الحرفي: {FRIEND}. أظهر في الصورة الأشياء التي يتعلمها الطفل (مثلا ثلاث تفاحات لرقم 3) بشكل كبير وواضح، لقطة متوسطة أو واسعة، بدون أي كتابة داخل الصورة، خلفية ملونة مبهجة.
رجّع JSON فقط بهذه المفاتيح: title (عنوان قصير جذاب بالعربية فيه كلمة تعليمي أو أنشودة), description (سطران بالعربية), tags (8 كلمات), hook_title (2 إلى 5 كلمات تظهر في أول ثانيتين), thumbnail_text (2 إلى 4 كلمات), thumbnail_prompt (بالإنجليزية: {MASCOT_NAME} مبتسم يشير إلى عنصر الدرس الرئيسي، لقطة متوسطة),
scenes (قائمة: narration, on_screen, obj, count, image_prompt, search)."""
    last = None
    for model in MODELS:
        for _try in range(4):
            try:
                txt = _call(model, prompt, key)
                data = json.loads(re.sub(r"^```json|```$", "", txt.strip()).strip())
                scenes = [s for s in data["scenes"] if s.get("narration", "").strip()]
                if len(scenes) < 6:
                    raise ValueError("too few scenes")
                data["scenes"] = scenes
                data["character"], data["friend"] = MASCOT, FRIEND
                data["story"] = " ".join(s["narration"].strip() for s in scenes)
                if len(data["story"].split()) < 100:
                    raise ValueError("lesson too short")
                data["_theme"] = topic  # recorded in history by the uploader only after a successful upload
                return data
            except Exception as e:
                last = e
                print(f"[gemini:{model}] {e}")
                time.sleep(10 * (_try + 1))
    raise RuntimeError(f"Edu generation failed: {last}")


def generate_story_long():
    key = os.environ["GEMINI_API_KEY"]
    hist = load_history()
    used = [h["title"] for h in hist[-30:]]
    theme, hero = random.choice(THEMES), random.choice(HEROES)
    prompt = f"""اكتب قصة أطفال بالعربية الفصحى المبسطة (يفهمها طفل من 4 إلى 8 سنين).
الفكرة/القيمة: {theme}. البطل: {hero}.
الشروط: من 600 إلى 900 كلمة، جمل قصيرة وواضحة، أسلوب دافئ ومرح، حوار بسيط، تكرار لطيف لجملة أو صوت مرح يحبه الأطفال، نهاية سعيدة فيها عبرة.
ممنوع تماما: العنف، الرعب، الألفاظ السيئة، السياسة، الدين الخلافي، أي محتوى غير مناسب للأطفال.
لا تكرر هذه القصص: {used}

قسّم القصة إلى {N_SCENES} مشهدا متتاليا، كل مشهد قصير حوالي 30 إلى 45 كلمة، ودمج المشاهد بالترتيب يعطي القصة كاملة.
قواعد الافتتاحية والخاتمة: المشهد الأول يبدأ بجملة جذب قصيرة جدا (أقل من 15 كلمة) تشد الطفل من أول ثانية: إما سؤال موجه للأطفال مثل "هل تعرفون ماذا حدث لـ...؟" أو البطل في موقف مشكلة أو مفاجأة فورا (بدون مقدمات وبدون "كان يا ما كان" طويلة)، ثم تكمل الحكاية. المشهد الأخير نهاية سعيدة واضحة: المشكلة انحلت، الجميع يضحك ويحتفل، وجملة ختام قصيرة دافئة فيها العبرة وتحية للأطفال.
لكل مشهد اكتب image_prompt بالإنجليزية (جملتان): وصف بصري حيوي ومحدد لما يحدث في هذا المشهد بالذات: حدث وحركة واضحة (يجري، يقفز، يضحك، يساعد، يتفاجأ...)، ومكان مختلف أو زاوية تصوير مختلفة عن المشهد السابق (wide shot, medium shot, from above, low angle, side view; avoid extreme close-ups of eyes or faces)، ومشاعر الشخصية.
القواعد: في كل image_prompt اكتب وصف كل شخصية تظهر فيه كاملا وبنفس الكلمات بالضبط في كل مرة (الشخصية الرئيسية كما في character، وأي شخصية ثانية تظهر كما في friend)، حتى تبقى الشخصيات متطابقة. استخدم شخصية ثانية (صديق أو حيوان آخر) في نصف المشاهد على الأقل عندما يناسب القصة. كل الشخصيات حيوانات أو أطفال كرتونيين لطيفين. بدون أي نص مكتوب داخل الصورة.

رجّع JSON فقط بهذه المفاتيح:
title (عنوان قصير جذاب بالعربية), description (وصف يوتيوب من سطرين بالعربية), tags (قائمة 8 كلمات مفتاحية),
friend (بالإنجليزية: وصف ثابت ومفصل لشخصية ثانية صديقة للبطل، حيوان آخر بلون مختلف), character (بالإنجليزية: وصف ثابت قصير جدا للشخصية الرئيسية، من 8 إلى 14 كلمة: النوع واللون وملمح مميز واحد أو اثنين، مثل: a small round gray baby elephant with big ears and a red scarf),
scenes (قائمة من {N_SCENES} كائنا، كل كائن فيه: narration (نص المشهد بالعربية فقط بدون رموز), image_prompt (بالإنجليزية), search (كلمتان إنجليزيتان بسيطتان لصورة احتياطية)),
thumbnail_prompt (بالإنجليزية: لقطة قريبة مبهجة جدا للشخصية الرئيسية بوجه سعيد معبر وألوان زاهية وخلفية بسيطة، مع ترك مساحة فارغة في الأسفل),
hook_title (عنوان قصير جدا من 2 إلى 5 كلمات بالعربية يظهر على شاشة العنوان في أول ثانيتين، مثير للفضول),
thumbnail_text (من كلمتين إلى 4 كلمات بالعربية جذابة للغلاف)."""
    last = None
    for model in MODELS:
        for _try in range(4):
            try:
                txt = _call(model, prompt, key)
                data = json.loads(re.sub(r"^```json|```$", "", txt.strip()).strip())
                scenes = [s for s in data["scenes"] if s.get("narration", "").strip()]
                if len(scenes) < 8:
                    raise ValueError("too few scenes")
                data["scenes"] = scenes
                data["story"] = " ".join(s["narration"].strip() for s in scenes)
                if len(data["story"].split()) < 250:
                    raise ValueError("story too short")
                hist.append({"title": data["title"], "theme": theme})
                save_history(hist)
                return data
            except Exception as e:
                last = e
                print(f"[gemini:{model}] {e}")
                time.sleep(10 * (_try + 1))
    raise RuntimeError(f"Story generation failed: {last}")


if __name__ == "__main__":
    print(json.dumps(generate_story(), ensure_ascii=False, indent=2))
