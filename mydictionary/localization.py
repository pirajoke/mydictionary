"""Small, deterministic locale catalog for the Telegram product surface."""

from __future__ import annotations

from string import Formatter
from typing import Any


INTERFACE_LOCALES = frozenset({"en", "fr", "de", "ja", "ar", "zh", "ru", "es"})
DEFAULT_INTERFACE_LOCALE = "en"

_CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "onboarding_intro": (
            "MY DICTIONARY brings short vocabulary lessons, flashcards and "
            "pronunciation practice to Telegram. The basic packs are free.\n\n"
            "Three quick steps and your first lesson is ready."
        ),
        "onboarding_try": "Try for free ✨",
        "onboarding_done": "Setup is already complete.",
        "onboarding_choose_native": (
            "Step 1 of 3. In which language would you like to see word meanings?"
        ),
        "onboarding_choose_pack": "Step 2 of 3. Which language do you want to learn?",
        "onboarding_choose_pace": (
            "Step 3 of 3. How many cards would you like to study each day?"
        ),
        "onboarding_pack_words": "{label} · {count} words",
        "pace_5": "5 cards · easy",
        "pace_10": "10 cards · regular",
        "pace_20": "20 cards · intensive",
        "pack_unavailable": "This pack is unavailable. Start setup again.",
        "choose_pack_again": "Choose a study pack again with /start.",
        "onboarding_complete": (
            "Ready ✨ The “{title}” pack is active. Your first lesson is waiting."
        ),
        "onboarding_stale": "This setup step has expired. Send /start.",
        "start_daily": "▶️ Today's lesson",
        "start_review": "🔁 Review",
        "start_topics": "📚 Topics",
        "start_stats": "📊 Progress",
        "start_settings": "⚙️ Settings",
        "mirror_capabilities": (
            "I can explain translations, grammar and pronunciation, correct "
            "phrases, practise a dialogue and review your learning progress."
        ),
        "mirror_greeting": (
            "Hi{name}! You are learning {language}. Continue your lesson or "
            "look at a word or phrase?"
        ),
        "mirror_greeting_block": (
            "Hi{name}! You are learning {language}. Continue the current block "
            "or look at another question?"
        ),
        "start_text": (
            "Hi, {name}! 👋\n\nYour short lesson is ready. Open one card at a "
            "time, listen to the pronunciation and mark the words you know.\n\n"
            "The bot will choose new words and bring them back for review at "
            "the right time. Your progress, XP and streak are saved automatically."
        ),
    },
    "fr": {
        "onboarding_intro": (
            "MY DICTIONARY propose dans Telegram de courtes leçons de "
            "vocabulaire, des cartes et la prononciation. Les packs de base "
            "sont gratuits.\n\nTrois étapes rapides et votre première leçon est prête."
        ),
        "onboarding_try": "Essayer gratuitement ✨",
        "onboarding_done": "La configuration est déjà terminée.",
        "onboarding_choose_native": (
            "Étape 1 sur 3. Dans quelle langue voulez-vous voir le sens des mots ?"
        ),
        "onboarding_choose_pack": "Étape 2 sur 3. Quelle langue voulez-vous apprendre ?",
        "onboarding_choose_pace": (
            "Étape 3 sur 3. Combien de cartes voulez-vous étudier par jour ?"
        ),
        "onboarding_pack_words": "{label} · {count} mots",
        "pace_5": "5 cartes · facile",
        "pace_10": "10 cartes · normal",
        "pace_20": "20 cartes · intensif",
        "pack_unavailable": "Ce pack n'est pas disponible. Recommencez la configuration.",
        "choose_pack_again": "Choisissez à nouveau un pack avec /start.",
        "onboarding_complete": (
            "C'est prêt ✨ Le pack « {title} » est actif. Votre première leçon vous attend."
        ),
        "onboarding_stale": "Cette étape a expiré. Envoyez /start.",
        "start_daily": "▶️ Leçon du jour",
        "start_review": "🔁 Réviser",
        "start_topics": "📚 Thèmes",
        "start_stats": "📊 Progrès",
        "start_settings": "⚙️ Réglages",
        "mirror_capabilities": (
            "Je peux expliquer les traductions, la grammaire et la prononciation, "
            "corriger des phrases, pratiquer un dialogue et analyser vos progrès."
        ),
        "mirror_greeting": (
            "Bonjour{name} ! Vous apprenez {language}. On continue la leçon ou "
            "on analyse un mot ou une phrase ?"
        ),
        "mirror_greeting_block": (
            "Bonjour{name} ! Vous apprenez {language}. On continue le bloc actuel "
            "ou on traite une autre question ?"
        ),
        "start_text": (
            "Bonjour, {name} ! 👋\n\nVotre courte leçon est prête. Ouvrez les "
            "cartes une par une, écoutez la prononciation et indiquez les mots "
            "connus.\n\nLe bot choisit les nouveaux mots et programme les "
            "révisions. Vos progrès, XP et série sont enregistrés automatiquement."
        ),
    },
    "de": {
        "onboarding_intro": (
            "MY DICTIONARY bietet kurze Vokabellektionen, Karteikarten und "
            "Aussprache direkt in Telegram. Die Basispakete sind kostenlos.\n\n"
            "Drei kurze Schritte, dann ist deine erste Lektion bereit."
        ),
        "onboarding_try": "Kostenlos testen ✨",
        "onboarding_done": "Die Einrichtung ist bereits abgeschlossen.",
        "onboarding_choose_native": (
            "Schritt 1 von 3. In welcher Sprache möchtest du die Wortbedeutungen sehen?"
        ),
        "onboarding_choose_pack": "Schritt 2 von 3. Welche Sprache möchtest du lernen?",
        "onboarding_choose_pace": (
            "Schritt 3 von 3. Wie viele Karten möchtest du täglich lernen?"
        ),
        "onboarding_pack_words": "{label} · {count} Wörter",
        "pace_5": "5 Karten · leicht",
        "pace_10": "10 Karten · normal",
        "pace_20": "20 Karten · intensiv",
        "pack_unavailable": "Dieses Paket ist nicht verfügbar. Starte die Einrichtung neu.",
        "choose_pack_again": "Wähle mit /start erneut ein Lernpaket.",
        "onboarding_complete": (
            "Fertig ✨ Das Paket „{title}“ ist aktiv. Deine erste Lektion wartet."
        ),
        "onboarding_stale": "Dieser Einrichtungsschritt ist abgelaufen. Sende /start.",
        "start_daily": "▶️ Heutige Lektion",
        "start_review": "🔁 Wiederholen",
        "start_topics": "📚 Themen",
        "start_stats": "📊 Fortschritt",
        "start_settings": "⚙️ Einstellungen",
        "mirror_capabilities": (
            "Ich kann Übersetzungen, Grammatik und Aussprache erklären, Sätze "
            "korrigieren, Dialoge üben und deinen Lernfortschritt auswerten."
        ),
        "mirror_greeting": (
            "Hallo{name}! Du lernst {language}. Möchtest du die Lektion fortsetzen "
            "oder ein Wort beziehungsweise einen Satz klären?"
        ),
        "mirror_greeting_block": (
            "Hallo{name}! Du lernst {language}. Möchtest du den aktuellen Block "
            "fortsetzen oder eine andere Frage klären?"
        ),
        "start_text": (
            "Hallo, {name}! 👋\n\nDeine kurze Lektion ist bereit. Öffne eine "
            "Karte nach der anderen, höre die Aussprache und markiere bekannte "
            "Wörter.\n\nDer Bot wählt neue Wörter und plant Wiederholungen. "
            "Fortschritt, XP und Serie werden automatisch gespeichert."
        ),
    },
    "ja": {
        "onboarding_intro": (
            "MY DICTIONARYでは、Telegramで短い単語レッスン、カード、発音練習ができます。"
            "基本パックは無料です。\n\n3つの簡単な設定で、最初のレッスンを始められます。"
        ),
        "onboarding_try": "無料で試す ✨",
        "onboarding_done": "設定はすでに完了しています。",
        "onboarding_choose_native": "ステップ1/3：単語の意味を何語で表示しますか？",
        "onboarding_choose_pack": "ステップ2/3：学びたい言語を選んでください。",
        "onboarding_choose_pace": "ステップ3/3：1日に何枚のカードを学びますか？",
        "onboarding_pack_words": "{label} · {count}語",
        "pace_5": "5枚 · やさしい",
        "pace_10": "10枚 · 標準",
        "pace_20": "20枚 · 集中",
        "pack_unavailable": "このパックは利用できません。設定をやり直してください。",
        "choose_pack_again": "/start から学習パックを選び直してください。",
        "onboarding_complete": (
            "準備完了 ✨ 「{title}」パックを有効にしました。最初のレッスンを始めましょう。"
        ),
        "onboarding_stale": "この設定ステップは期限切れです。/start を送信してください。",
        "start_daily": "▶️ 今日のレッスン",
        "start_review": "🔁 復習",
        "start_topics": "📚 トピック",
        "start_stats": "📊 進捗",
        "start_settings": "⚙️ 設定",
        "mirror_capabilities": (
            "翻訳、文法、発音の説明、文章の添削、会話練習、学習進捗の分析ができます。"
        ),
        "mirror_greeting": (
            "{name}こんにちは！{language}を学習中ですね。レッスンを続けますか、"
            "それとも単語やフレーズを確認しますか？"
        ),
        "mirror_greeting_block": (
            "{name}こんにちは！{language}を学習中ですね。現在のブロックを続けますか、"
            "それとも別の質問を確認しますか？"
        ),
        "start_text": (
            "{name}さん、こんにちは！ 👋\n\n短いレッスンの準備ができました。カードを1枚ずつ開き、"
            "発音を聞いて、知っている単語を記録しましょう。\n\n新しい単語と復習のタイミングは"
            "ボットが選びます。進捗、XP、連続学習日数は自動で保存されます。"
        ),
    },
    "ar": {
        "onboarding_intro": (
            "يقدّم MY DICTIONARY دروس مفردات قصيرة وبطاقات وتدريباً على النطق "
            "داخل Telegram. الحزم الأساسية مجانية.\n\nثلاث خطوات سريعة وتصبح حصتك الأولى جاهزة."
        ),
        "onboarding_try": "جرّب مجاناً ✨",
        "onboarding_done": "اكتمل الإعداد بالفعل.",
        "onboarding_choose_native": "الخطوة 1 من 3. بأي لغة تريد رؤية معاني الكلمات؟",
        "onboarding_choose_pack": "الخطوة 2 من 3. ما اللغة التي تريد تعلّمها؟",
        "onboarding_choose_pace": "الخطوة 3 من 3. كم بطاقة تريد دراستها يومياً؟",
        "onboarding_pack_words": "{label} · {count} كلمة",
        "pace_5": "5 بطاقات · سهل",
        "pace_10": "10 بطاقات · عادي",
        "pace_20": "20 بطاقة · مكثّف",
        "pack_unavailable": "هذه الحزمة غير متاحة. ابدأ الإعداد من جديد.",
        "choose_pack_again": "اختر حزمة تعليمية من جديد عبر /start.",
        "onboarding_complete": "تم ✨ حزمة «{title}» مفعّلة. حصتك الأولى جاهزة.",
        "onboarding_stale": "انتهت صلاحية خطوة الإعداد. أرسل /start.",
        "start_daily": "▶️ درس اليوم",
        "start_review": "🔁 مراجعة",
        "start_topics": "📚 الموضوعات",
        "start_stats": "📊 التقدّم",
        "start_settings": "⚙️ الإعدادات",
        "mirror_capabilities": (
            "يمكنني شرح الترجمة والقواعد والنطق، وتصحيح العبارات، والتدرّب على "
            "المحادثة، وتحليل تقدّمك في التعلّم."
        ),
        "mirror_greeting": (
            "مرحباً{name}! أنت تتعلّم {language}. هل نتابع الدرس أم نشرح كلمة أو عبارة؟"
        ),
        "mirror_greeting_block": (
            "مرحباً{name}! أنت تتعلّم {language}. هل نتابع المجموعة الحالية أم نناقش سؤالاً آخر؟"
        ),
        "start_text": (
            "مرحباً، {name}! 👋\n\nحصتك القصيرة جاهزة. افتح البطاقات واحدة تلو الأخرى، "
            "واستمع إلى النطق وحدد الكلمات التي تعرفها.\n\nسيختار البوت الكلمات "
            "الجديدة وموعد المراجعة. يُحفظ تقدّمك ونقاط XP وسلسلة التعلّم تلقائياً."
        ),
    },
    "zh": {
        "onboarding_intro": (
            "MY DICTIONARY 在 Telegram 中提供短词汇课、卡片和发音练习。基础词包免费。"
            "\n\n只需三个简单步骤，第一课即可开始。"
        ),
        "onboarding_try": "免费试用 ✨",
        "onboarding_done": "设置已经完成。",
        "onboarding_choose_native": "第 1/3 步：你想用哪种语言查看单词含义？",
        "onboarding_choose_pack": "第 2/3 步：你想学习哪种语言？",
        "onboarding_choose_pace": "第 3/3 步：你每天想学习多少张卡片？",
        "onboarding_pack_words": "{label} · {count} 个词",
        "pace_5": "5 张 · 轻松",
        "pace_10": "10 张 · 标准",
        "pace_20": "20 张 · 强化",
        "pack_unavailable": "此词包不可用，请重新开始设置。",
        "choose_pack_again": "请通过 /start 重新选择学习词包。",
        "onboarding_complete": "准备好了 ✨ 已启用“{title}”词包，第一课正在等你。",
        "onboarding_stale": "此设置步骤已过期，请发送 /start。",
        "start_daily": "▶️ 今日课程",
        "start_review": "🔁 复习",
        "start_topics": "📚 主题",
        "start_stats": "📊 进度",
        "start_settings": "⚙️ 设置",
        "mirror_capabilities": (
            "我可以讲解翻译、语法和发音，纠正句子，进行对话练习，并分析你的学习进度。"
        ),
        "mirror_greeting": (
            "你好{name}！你正在学习{language}。继续课程，还是讲解一个单词或短语？"
        ),
        "mirror_greeting_block": (
            "你好{name}！你正在学习{language}。继续当前学习组，还是讨论其他问题？"
        ),
        "start_text": (
            "你好，{name}！👋\n\n今天的短课已经准备好。逐张打开卡片，听发音并标记"
            "你认识的单词。\n\n机器人会选择新词并安排复习。学习进度、XP 和连续学习天数"
            "会自动保存。"
        ),
    },
    "ru": {
        "onboarding_intro": (
            "MY DICTIONARY — короткие уроки со словами, карточками и "
            "произношением прямо в Telegram. Базовые наборы бесплатны.\n\n"
            "Три коротких шага — и первый урок готов."
        ),
        "onboarding_try": "Попробовать бесплатно ✨",
        "onboarding_done": "Настройка уже завершена.",
        "onboarding_choose_native": (
            "Шаг 1 из 3. На каком языке показывать значения слов?"
        ),
        "onboarding_choose_pack": "Шаг 2 из 3. Какой язык хочешь учить?",
        "onboarding_choose_pace": (
            "Шаг 3 из 3. Сколько карточек удобно проходить в день?"
        ),
        "onboarding_pack_words": "{label} · {count} слов",
        "pace_5": "5 карточек · легко",
        "pace_10": "10 карточек · обычно",
        "pace_20": "20 карточек · интенсивно",
        "pack_unavailable": "Этот набор недоступен. Начни настройку заново.",
        "choose_pack_again": "Выбери учебный набор заново через /start.",
        "onboarding_complete": (
            "Готово ✨ Подключён набор «{title}». Первый урок уже ждёт тебя."
        ),
        "onboarding_stale": "Шаг настройки устарел. Отправь /start.",
        "start_daily": "▶️ Урок на сегодня",
        "start_review": "🔁 Повторить",
        "start_topics": "📚 Темы",
        "start_stats": "📊 Прогресс",
        "start_settings": "⚙️ Настройки",
        "mirror_capabilities": (
            "Я могу объяснить перевод, грамматику и произношение, исправить "
            "фразу, провести диалог и разобрать твой учебный прогресс."
        ),
        "mirror_greeting": (
            "Привет{name}! Вижу, у тебя сейчас {language}. Продолжим обучение "
            "или разберём слово или фразу?"
        ),
        "mirror_greeting_block": (
            "Привет{name}! Вижу, у тебя сейчас {language}. Продолжим текущий "
            "блок или разберём другой вопрос?"
        ),
        "start_text": (
            "Привет, {name}! 👋\n\nТвой короткий урок уже готов. Открывай по "
            "одной карточке, слушай произношение и отмечай, какие слова знаешь."
            "\n\nБот сам подберёт новые слова и вовремя вернёт их на повторение. "
            "Прогресс, XP и серия занятий сохраняются автоматически."
        ),
    },
    "es": {
        "onboarding_intro": (
            "MY DICTIONARY ofrece lecciones breves de vocabulario, tarjetas y "
            "pronunciación dentro de Telegram. Los paquetes básicos son gratis."
            "\n\nTres pasos rápidos y tu primera lección estará lista."
        ),
        "onboarding_try": "Probar gratis ✨",
        "onboarding_done": "La configuración ya está completa.",
        "onboarding_choose_native": (
            "Paso 1 de 3. ¿En qué idioma quieres ver el significado de las palabras?"
        ),
        "onboarding_choose_pack": "Paso 2 de 3. ¿Qué idioma quieres aprender?",
        "onboarding_choose_pace": (
            "Paso 3 de 3. ¿Cuántas tarjetas quieres estudiar al día?"
        ),
        "onboarding_pack_words": "{label} · {count} palabras",
        "pace_5": "5 tarjetas · fácil",
        "pace_10": "10 tarjetas · normal",
        "pace_20": "20 tarjetas · intensivo",
        "pack_unavailable": "Este paquete no está disponible. Inicia la configuración de nuevo.",
        "choose_pack_again": "Vuelve a elegir un paquete con /start.",
        "onboarding_complete": (
            "Listo ✨ El paquete «{title}» está activo. Tu primera lección te espera."
        ),
        "onboarding_stale": "Este paso ha caducado. Envía /start.",
        "start_daily": "▶️ Lección de hoy",
        "start_review": "🔁 Repasar",
        "start_topics": "📚 Temas",
        "start_stats": "📊 Progreso",
        "start_settings": "⚙️ Ajustes",
        "mirror_capabilities": (
            "Puedo explicar traducciones, gramática y pronunciación, corregir "
            "frases, practicar diálogos y analizar tu progreso de aprendizaje."
        ),
        "mirror_greeting": (
            "Hola{name}. Estás aprendiendo {language}. ¿Seguimos con la lección "
            "o revisamos una palabra o frase?"
        ),
        "mirror_greeting_block": (
            "Hola{name}. Estás aprendiendo {language}. ¿Seguimos con el bloque "
            "actual o revisamos otra pregunta?"
        ),
        "start_text": (
            "¡Hola, {name}! 👋\n\nTu lección breve está lista. Abre las tarjetas "
            "una a una, escucha la pronunciación y marca las palabras que "
            "conoces.\n\nEl bot elegirá palabras nuevas y programará los repasos. "
            "Tu progreso, XP y racha se guardan automáticamente."
        ),
    },
}

_LEARNING_CARD_COPY: dict[str, dict[str, str]] = {
    "en": {
        "learning_card_position": "Card {position} of {total}",
        "learning_card_hint": "First, try to recall the meaning.",
        "learning_show_meaning": "👁 Show meaning",
        "learning_listen_again": "🔊 Listen again",
        "learning_dont_know": "😵 I don't know",
        "learning_know": "✅ I know",
    },
    "fr": {
        "learning_card_position": "Carte {position} sur {total}",
        "learning_card_hint": "Essayez d’abord de vous rappeler le sens.",
        "learning_show_meaning": "👁 Afficher le sens",
        "learning_listen_again": "🔊 Réécouter",
        "learning_dont_know": "😵 Je ne sais pas",
        "learning_know": "✅ Je sais",
    },
    "de": {
        "learning_card_position": "Karte {position} von {total}",
        "learning_card_hint": "Versuche zuerst, dich an die Bedeutung zu erinnern.",
        "learning_show_meaning": "👁 Bedeutung anzeigen",
        "learning_listen_again": "🔊 Noch einmal anhören",
        "learning_dont_know": "😵 Weiß ich nicht",
        "learning_know": "✅ Weiß ich",
    },
    "ja": {
        "learning_card_position": "カード {position}/{total}",
        "learning_card_hint": "まず意味を思い出してみましょう。",
        "learning_show_meaning": "👁 意味を表示",
        "learning_listen_again": "🔊 もう一度聞く",
        "learning_dont_know": "😵 わからない",
        "learning_know": "✅ わかる",
    },
    "ar": {
        "learning_card_position": "البطاقة {position} من {total}",
        "learning_card_hint": "حاول أولاً تذكّر المعنى.",
        "learning_show_meaning": "👁 إظهار المعنى",
        "learning_listen_again": "🔊 الاستماع مجدداً",
        "learning_dont_know": "😵 لا أعرف",
        "learning_know": "✅ أعرف",
    },
    "zh": {
        "learning_card_position": "卡片 {position}/{total}",
        "learning_card_hint": "先试着回想它的意思。",
        "learning_show_meaning": "👁 显示释义",
        "learning_listen_again": "🔊 再听一次",
        "learning_dont_know": "😵 不知道",
        "learning_know": "✅ 知道",
    },
    "ru": {
        "learning_card_position": "Карточка {position} из {total}",
        "learning_card_hint": "Сначала вспомни значение.",
        "learning_show_meaning": "👁 Показать значение",
        "learning_listen_again": "🔊 Слушать ещё",
        "learning_dont_know": "😵 Не знаю",
        "learning_know": "✅ Знаю",
    },
    "es": {
        "learning_card_position": "Tarjeta {position} de {total}",
        "learning_card_hint": "Primero intenta recordar el significado.",
        "learning_show_meaning": "👁 Mostrar significado",
        "learning_listen_again": "🔊 Escuchar de nuevo",
        "learning_dont_know": "😵 No lo sé",
        "learning_know": "✅ Lo sé",
    },
}

for _locale, _messages in _LEARNING_CARD_COPY.items():
    _CATALOG[_locale].update(_messages)

_HOME_SURFACE_COPY: dict[str, dict[str, str]] = {
    "en": {
        "topic_prompt": "Choose a topic:",
        "topic_all": "🌐 All words",
        "review_empty": "Everything is reviewed for today. You can start a new lesson.",
        "review_start_lesson": "▶️ Start a new lesson",
        "mirror_style_teacher": "Teacher",
        "mirror_style_conversation": "Conversation",
        "mirror_style_coach": "Coach",
        "mirror_style_brief": "Concise",
        "mirror_style_practice": "Practice",
        "mirror_style_exam": "Exam",
        "mirror_depth_compact": "Short",
        "mirror_depth_balanced": "Balanced",
        "mirror_depth_deep": "In depth",
        "mirror_level_adaptive": "Auto",
        "settings_text": (
            "⚙️ *Settings*\n\nLanguage: *{pack}*\nCards per lesson: *{pace}*\n"
            "AI style: *{style}*\n\nDepth: *{depth}* · level: *{level}*\n\n"
            "Choose a language, pace, or response format:"
        ),
        "stats_weak_empty": "None for now",
        "stats_next_level": " ({remaining} to level {level})",
        "stats_text": (
            "📊 *Statistics* ({pack})\n\n📈 *Level {level} · {title}* — {xp_line}\n"
            "🔥 Streak: {streak} days (best: {streak_best})\n⭐ Today: +{today_xp} XP\n\n"
            "📚 Words: {total} | Studied: {seen} | Mastered: {learned}\n"
            "⏰ Due for review: {overdue}\n\n✅ Correct: {correct} | ❌ Errors: {wrong}\n"
            "🎯 Accuracy: {accuracy}%\n\n*Words to strengthen:*\n{weak_text}"
        ),
    },
    "fr": {
        "topic_prompt": "Choisissez un thème :",
        "topic_all": "🌐 Tous les mots",
        "review_empty": "Tout est révisé pour aujourd’hui. Vous pouvez commencer une nouvelle leçon.",
        "review_start_lesson": "▶️ Commencer une nouvelle leçon",
        "mirror_style_teacher": "Professeur",
        "mirror_style_conversation": "Conversation",
        "mirror_style_coach": "Coach",
        "mirror_style_brief": "Concis",
        "mirror_style_practice": "Pratique",
        "mirror_style_exam": "Examen",
        "mirror_depth_compact": "Court",
        "mirror_depth_balanced": "Équilibré",
        "mirror_depth_deep": "Approfondi",
        "mirror_level_adaptive": "Auto",
        "settings_text": (
            "⚙️ *Réglages*\n\nLangue : *{pack}*\nCartes par leçon : *{pace}*\n"
            "Style IA : *{style}*\n\nProfondeur : *{depth}* · niveau : *{level}*\n\n"
            "Choisissez une langue, un rythme ou un format de réponse :"
        ),
        "stats_weak_empty": "Aucun pour le moment",
        "stats_next_level": " ({remaining} avant le niveau {level})",
        "stats_text": (
            "📊 *Statistiques* ({pack})\n\n📈 *Niveau {level} · {title}* — {xp_line}\n"
            "🔥 Série : {streak} j (record : {streak_best})\n⭐ Aujourd’hui : +{today_xp} XP\n\n"
            "📚 Mots : {total} | Étudiés : {seen} | Maîtrisés : {learned}\n"
            "⏰ À réviser : {overdue}\n\n✅ Bonnes réponses : {correct} | ❌ Erreurs : {wrong}\n"
            "🎯 Précision : {accuracy}%\n\n*Mots à renforcer:*\n{weak_text}"
        ),
    },
    "de": {
        "topic_prompt": "Wähle ein Thema:",
        "topic_all": "🌐 Alle Wörter",
        "review_empty": "Für heute ist alles wiederholt. Du kannst eine neue Lektion starten.",
        "review_start_lesson": "▶️ Neue Lektion starten",
        "mirror_style_teacher": "Lehrer",
        "mirror_style_conversation": "Gespräch",
        "mirror_style_coach": "Coach",
        "mirror_style_brief": "Kurz",
        "mirror_style_practice": "Übung",
        "mirror_style_exam": "Prüfung",
        "mirror_depth_compact": "Kompakt",
        "mirror_depth_balanced": "Ausgewogen",
        "mirror_depth_deep": "Vertieft",
        "mirror_level_adaptive": "Auto",
        "settings_text": (
            "⚙️ *Einstellungen*\n\nSprache: *{pack}*\nKarten pro Lektion: *{pace}*\n"
            "KI-Stil: *{style}*\n\nTiefe: *{depth}* · Niveau: *{level}*\n\n"
            "Wähle Sprache, Tempo oder Antwortformat:"
        ),
        "stats_weak_empty": "Derzeit keine",
        "stats_next_level": " ({remaining} bis Stufe {level})",
        "stats_text": (
            "📊 *Statistik* ({pack})\n\n📈 *Stufe {level} · {title}* — {xp_line}\n"
            "🔥 Serie: {streak} Tage (Rekord: {streak_best})\n⭐ Heute: +{today_xp} XP\n\n"
            "📚 Wörter: {total} | Gelernt: {seen} | Beherrscht: {learned}\n"
            "⏰ Zu wiederholen: {overdue}\n\n✅ Richtig: {correct} | ❌ Fehler: {wrong}\n"
            "🎯 Genauigkeit: {accuracy}%\n\n*Zu stärkende Wörter:*\n{weak_text}"
        ),
    },
    "ja": {
        "topic_prompt": "トピックを選んでください：",
        "topic_all": "🌐 すべての単語",
        "review_empty": "今日の復習はすべて完了しました。新しいレッスンを始められます。",
        "review_start_lesson": "▶️ 新しいレッスンを始める",
        "mirror_style_teacher": "先生",
        "mirror_style_conversation": "会話",
        "mirror_style_coach": "コーチ",
        "mirror_style_brief": "簡潔",
        "mirror_style_practice": "練習",
        "mirror_style_exam": "試験",
        "mirror_depth_compact": "短め",
        "mirror_depth_balanced": "標準",
        "mirror_depth_deep": "詳しく",
        "mirror_level_adaptive": "自動",
        "settings_text": (
            "⚙️ *設定*\n\n言語：*{pack}*\n1レッスンのカード：*{pace}*\n"
            "AIスタイル：*{style}*\n\n詳しさ：*{depth}*・レベル：*{level}*\n\n"
            "言語、ペース、回答形式を選んでください："
        ),
        "stats_weak_empty": "今のところありません",
        "stats_next_level": "（レベル{level}まであと{remaining}）",
        "stats_text": (
            "📊 *統計*（{pack}）\n\n📈 *レベル{level}・{title}* — {xp_line}\n"
            "🔥 連続：{streak}日（最高：{streak_best}）\n⭐ 今日：+{today_xp} XP\n\n"
            "📚 単語：{total}｜学習済み：{seen}｜習得：{learned}\n"
            "⏰ 復習予定：{overdue}\n\n✅ 正解：{correct}｜❌ 間違い：{wrong}\n"
            "🎯 正答率：{accuracy}%\n\n*強化する単語：*\n{weak_text}"
        ),
    },
    "ar": {
        "topic_prompt": "اختر موضوعاً:",
        "topic_all": "🌐 كل الكلمات",
        "review_empty": "اكتملت مراجعة اليوم. يمكنك بدء درس جديد.",
        "review_start_lesson": "▶️ ابدأ درساً جديداً",
        "mirror_style_teacher": "معلّم",
        "mirror_style_conversation": "محادثة",
        "mirror_style_coach": "مدرّب",
        "mirror_style_brief": "موجز",
        "mirror_style_practice": "تدريب",
        "mirror_style_exam": "اختبار",
        "mirror_depth_compact": "قصير",
        "mirror_depth_balanced": "متوازن",
        "mirror_depth_deep": "متعمّق",
        "mirror_level_adaptive": "تلقائي",
        "settings_text": (
            "⚙️ *الإعدادات*\n\nاللغة: *{pack}*\nالبطاقات في الدرس: *{pace}*\n"
            "أسلوب الذكاء الاصطناعي: *{style}*\n\nالتفصيل: *{depth}* · المستوى: *{level}*\n\n"
            "اختر اللغة أو الوتيرة أو تنسيق الإجابة:"
        ),
        "stats_weak_empty": "لا يوجد حالياً",
        "stats_next_level": " ({remaining} إلى المستوى {level})",
        "stats_text": (
            "📊 *الإحصاءات* ({pack})\n\n📈 *المستوى {level} · {title}* — {xp_line}\n"
            "🔥 السلسلة: {streak} يوم (الأفضل: {streak_best})\n⭐ اليوم: +{today_xp} XP\n\n"
            "📚 الكلمات: {total} | دُرست: {seen} | أُتقنت: {learned}\n"
            "⏰ للمراجعة: {overdue}\n\n✅ صحيحة: {correct} | ❌ أخطاء: {wrong}\n"
            "🎯 الدقة: {accuracy}%\n\n*كلمات تحتاج إلى تقوية:*\n{weak_text}"
        ),
    },
    "zh": {
        "topic_prompt": "选择一个主题：",
        "topic_all": "🌐 所有单词",
        "review_empty": "今天的复习已全部完成，可以开始新课程。",
        "review_start_lesson": "▶️ 开始新课程",
        "mirror_style_teacher": "老师",
        "mirror_style_conversation": "对话",
        "mirror_style_coach": "教练",
        "mirror_style_brief": "简洁",
        "mirror_style_practice": "练习",
        "mirror_style_exam": "考试",
        "mirror_depth_compact": "简短",
        "mirror_depth_balanced": "平衡",
        "mirror_depth_deep": "深入",
        "mirror_level_adaptive": "自动",
        "settings_text": (
            "⚙️ *设置*\n\n语言：*{pack}*\n每课卡片：*{pace}*\n"
            "AI 风格：*{style}*\n\n详细程度：*{depth}* · 等级：*{level}*\n\n"
            "请选择语言、节奏或回答格式："
        ),
        "stats_weak_empty": "目前没有",
        "stats_next_level": "（距离等级 {level} 还差 {remaining}）",
        "stats_text": (
            "📊 *统计*（{pack}）\n\n📈 *等级 {level} · {title}* — {xp_line}\n"
            "🔥 连续学习：{streak} 天（纪录：{streak_best}）\n⭐ 今天：+{today_xp} XP\n\n"
            "📚 单词：{total} | 已学习：{seen} | 已掌握：{learned}\n"
            "⏰ 待复习：{overdue}\n\n✅ 正确：{correct} | ❌ 错误：{wrong}\n"
            "🎯 准确率：{accuracy}%\n\n*需要加强的单词：*\n{weak_text}"
        ),
    },
    "ru": {
        "topic_prompt": "Выбери тему:",
        "topic_all": "🌐 Все слова",
        "review_empty": "На сегодня всё повторено. Можно начать новый урок.",
        "review_start_lesson": "▶️ Начать новый урок",
        "mirror_style_teacher": "Преподаватель",
        "mirror_style_conversation": "Собеседник",
        "mirror_style_coach": "Коуч",
        "mirror_style_brief": "Кратко",
        "mirror_style_practice": "Практика",
        "mirror_style_exam": "Экзамен",
        "mirror_depth_compact": "Кратко",
        "mirror_depth_balanced": "Баланс",
        "mirror_depth_deep": "Глубоко",
        "mirror_level_adaptive": "Авто",
        "settings_text": (
            "⚙️ *Настройки*\n\nЯзык: *{pack}*\nКарточек в уроке: *{pace}*\n"
            "Стиль AI: *{style}*\n\nГлубина: *{depth}* · уровень: *{level}*\n\n"
            "Выбери язык, ритм или формат ответа:"
        ),
        "stats_weak_empty": "Пока нет",
        "stats_next_level": " ({remaining} до уровня {level})",
        "stats_text": (
            "📊 *Статистика* ({pack})\n\n📈 *Уровень {level} · {title}* — {xp_line}\n"
            "🔥 Серия: {streak} дн. (рекорд: {streak_best})\n⭐ Сегодня: +{today_xp} XP\n\n"
            "📚 Слов: {total} | Изучено: {seen} | Выучено: {learned}\n"
            "⏰ На повторение: {overdue}\n\n✅ Правильных: {correct} | ❌ Ошибок: {wrong}\n"
            "🎯 Точность: {accuracy}%\n\n*Слабые слова:*\n{weak_text}"
        ),
    },
    "es": {
        "topic_prompt": "Elige un tema:",
        "topic_all": "🌐 Todas las palabras",
        "review_empty": "Ya está todo repasado por hoy. Puedes empezar una lección nueva.",
        "review_start_lesson": "▶️ Empezar una lección nueva",
        "mirror_style_teacher": "Profesor",
        "mirror_style_conversation": "Conversación",
        "mirror_style_coach": "Entrenador",
        "mirror_style_brief": "Conciso",
        "mirror_style_practice": "Práctica",
        "mirror_style_exam": "Examen",
        "mirror_depth_compact": "Corto",
        "mirror_depth_balanced": "Equilibrado",
        "mirror_depth_deep": "Profundo",
        "mirror_level_adaptive": "Auto",
        "settings_text": (
            "⚙️ *Ajustes*\n\nIdioma: *{pack}*\nTarjetas por lección: *{pace}*\n"
            "Estilo de IA: *{style}*\n\nProfundidad: *{depth}* · nivel: *{level}*\n\n"
            "Elige un idioma, ritmo o formato de respuesta:"
        ),
        "stats_weak_empty": "Ninguna por ahora",
        "stats_next_level": " ({remaining} para el nivel {level})",
        "stats_text": (
            "📊 *Estadísticas* ({pack})\n\n📈 *Nivel {level} · {title}* — {xp_line}\n"
            "🔥 Racha: {streak} días (récord: {streak_best})\n⭐ Hoy: +{today_xp} XP\n\n"
            "📚 Palabras: {total} | Estudiadas: {seen} | Dominadas: {learned}\n"
            "⏰ Para repasar: {overdue}\n\n✅ Correctas: {correct} | ❌ Errores: {wrong}\n"
            "🎯 Precisión: {accuracy}%\n\n*Palabras por reforzar:*\n{weak_text}"
        ),
    },
}

_TOPIC_NAMES = {
    "en": ("Greetings", "Communication", "People & family", "Food & drink", "Home", "Travel", "Time & numbers", "Work & study", "Business & finance", "Health & body", "Nature & science", "Technology", "Actions", "Descriptions & emotions", "General"),
    "fr": ("Salutations", "Communication", "Personnes et famille", "Alimentation et boissons", "Maison", "Voyages", "Temps et nombres", "Travail et études", "Affaires et finances", "Santé et corps", "Nature et sciences", "Technologie", "Actions", "Descriptions et émotions", "Divers"),
    "de": ("Begrüßungen", "Kommunikation", "Menschen und Familie", "Essen und Trinken", "Zuhause", "Reisen", "Zeit und Zahlen", "Arbeit und Lernen", "Geschäft und Finanzen", "Gesundheit und Körper", "Natur und Wissenschaft", "Technologie", "Handlungen", "Beschreibungen und Gefühle", "Allgemein"),
    "ja": ("あいさつ", "コミュニケーション", "人と家族", "食べ物と飲み物", "家と暮らし", "旅行", "時間と数字", "仕事と学習", "ビジネスと金融", "健康と身体", "自然と科学", "テクノロジー", "動作", "説明と感情", "その他"),
    "ar": ("التحيات", "التواصل", "الناس والعائلة", "الطعام والشراب", "المنزل", "السفر", "الوقت والأرقام", "العمل والدراسة", "الأعمال والمال", "الصحة والجسم", "الطبيعة والعلوم", "التكنولوجيا", "الأفعال", "الأوصاف والمشاعر", "عام"),
    "zh": ("问候", "交流", "人物与家庭", "饮食", "家居生活", "旅行", "时间与数字", "工作与学习", "商业与金融", "健康与身体", "自然与科学", "科技", "动作", "描述与情感", "其他"),
    "ru": ("Приветствия", "Общение", "Люди и семья", "Еда и напитки", "Дом и быт", "Места и поездки", "Время и числа", "Работа и учёба", "Бизнес и финансы", "Здоровье и тело", "Природа и наука", "Технологии", "Действия", "Описания и эмоции", "Разное"),
    "es": ("Saludos", "Comunicación", "Personas y familia", "Comida y bebida", "Hogar", "Viajes", "Tiempo y números", "Trabajo y estudio", "Negocios y finanzas", "Salud y cuerpo", "Naturaleza y ciencia", "Tecnología", "Acciones", "Descripciones y emociones", "General"),
}
_TOPIC_IDS = ("greetings", "communication", "people", "food", "home", "travel", "time", "work", "business", "health", "nature", "technology", "actions", "descriptions", "general")
_TOPIC_ICONS = ("👋", "💬", "👥", "🍽", "🏠", "🧭", "🕒", "📚", "💼", "🩺", "🌿", "💻", "🏃", "🎨", "📦")

_LEVEL_NAMES = {
    "en": ("Beginner", "Learner", "Student", "Expert", "Linguist", "Polyglot", "Sage", "Master", "Legend"),
    "fr": ("Débutant", "Apprenti", "Étudiant", "Expert", "Linguiste", "Polyglotte", "Sage", "Maître", "Légende"),
    "de": ("Anfänger", "Lernender", "Student", "Kenner", "Linguist", "Polyglott", "Weiser", "Meister", "Legende"),
    "ja": ("初心者", "学習者", "学生", "上級者", "言語学者", "多言語話者", "賢者", "達人", "伝説"),
    "ar": ("مبتدئ", "متعلّم", "طالب", "خبير", "لغوي", "متعدد اللغات", "حكيم", "محترف", "أسطورة"),
    "zh": ("初学者", "学习者", "学生", "专家", "语言学家", "多语者", "智者", "大师", "传奇"),
    "ru": ("Новичок", "Ученик", "Студент", "Знаток", "Лингвист", "Полиглот", "Мудрец", "Мастер", "Легенда"),
    "es": ("Principiante", "Aprendiz", "Estudiante", "Experto", "Lingüista", "Políglota", "Sabio", "Maestro", "Leyenda"),
}

_EXTRA_MIRROR_STYLES = {
    "en": ("Coach", "Exam"),
    "fr": ("Coach", "Examen"),
    "de": ("Coach", "Prüfung"),
    "ja": ("コーチ", "試験"),
    "ar": ("مدرّب", "اختبار"),
    "zh": ("教练", "考试"),
    "ru": ("Коуч", "Экзамен"),
    "es": ("Entrenador", "Examen"),
}

for _locale, _messages in _HOME_SURFACE_COPY.items():
    _messages["mirror_style_coach"], _messages["mirror_style_exam"] = (
        _EXTRA_MIRROR_STYLES[_locale]
    )
    for _topic_id, _icon, _name in zip(
        _TOPIC_IDS, _TOPIC_ICONS, _TOPIC_NAMES[_locale]
    ):
        _messages[f"topic_{_topic_id}"] = f"{_icon} {_name}"
    for _level, _name in enumerate(_LEVEL_NAMES[_locale], 1):
        _messages[f"stats_level_title_{_level}"] = _name
    _CATALOG[_locale].update(_messages)

_LEARNING_BLOCK_COPY: dict[str, dict[str, str]] = {
    "en": {
        "block_intro": "📖 *{topic}*\nMemorize {count} words:\n\n{study}",
        "block_quiz_mode": "Quiz · 4 choices",
        "block_written_mode": "Written",
        "block_ai_tutor": "AI tutor",
        "block_voice_practice": "🎤 Pronounce 10 words",
        "block_topics_study": "Topics 📚",
        "block_quiz_prompt": "Choose the translation:",
        "block_written_prompt": "Write the translation:",
        "block_your_answer": "Your answer: _{answer}_",
        "block_summary_result": "📊 *Result: {correct}/{total}*",
        "block_summary_errors": "❌ Errors:",
        "block_summary_perfect": "🎉 No errors!",
        "block_summary_xp": "⭐ +{earned} XP for the lesson | Total: {total} XP",
        "block_summary_level": "📈 Level {level} · {title}",
        "block_summary_next": " ({remaining} XP to the next level)",
        "block_summary_streak": "🔥 Streak: {streak} days",
        "block_retry_errors": "🔄 Review errors",
        "block_pronunciation": "🗣 Pronunciation",
        "block_phrases": "💬 Phrases",
        "block_another_lesson": "▶️ Another lesson",
        "block_topics": "📚 Topics",
        "block_settings": "⚙️ Settings",
        "block_next": "➡️ Next block",
    },
    "fr": {
        "block_intro": "📖 *{topic}*\nMémorisez {count} mots :\n\n{study}",
        "block_quiz_mode": "Quiz · 4 choix",
        "block_written_mode": "Par écrit",
        "block_ai_tutor": "Tuteur IA",
        "block_voice_practice": "🎤 Prononcer 10 mots",
        "block_topics_study": "Thèmes 📚",
        "block_quiz_prompt": "Choisissez la traduction :",
        "block_written_prompt": "Écrivez la traduction :",
        "block_your_answer": "Votre réponse : _{answer}_",
        "block_summary_result": "📊 *Résultat : {correct}/{total}*",
        "block_summary_errors": "❌ Erreurs :",
        "block_summary_perfect": "🎉 Aucune erreur !",
        "block_summary_xp": "⭐ +{earned} XP pour la leçon | Total : {total} XP",
        "block_summary_level": "📈 Niveau {level} · {title}",
        "block_summary_next": " ({remaining} XP avant le niveau suivant)",
        "block_summary_streak": "🔥 Série : {streak} j",
        "block_retry_errors": "🔄 Revoir les erreurs",
        "block_pronunciation": "🗣 Prononciation",
        "block_phrases": "💬 Phrases",
        "block_another_lesson": "▶️ Encore une leçon",
        "block_topics": "📚 Thèmes",
        "block_settings": "⚙️ Réglages",
        "block_next": "➡️ Bloc suivant",
    },
    "de": {
        "block_intro": "📖 *{topic}*\nPräge dir {count} Wörter ein:\n\n{study}",
        "block_quiz_mode": "Quiz · 4 Antworten",
        "block_written_mode": "Schriftlich",
        "block_ai_tutor": "KI-Tutor",
        "block_voice_practice": "🎤 10 Wörter aussprechen",
        "block_topics_study": "Themen 📚",
        "block_quiz_prompt": "Wähle die Übersetzung:",
        "block_written_prompt": "Schreibe die Übersetzung:",
        "block_your_answer": "Deine Antwort: _{answer}_",
        "block_summary_result": "📊 *Ergebnis: {correct}/{total}*",
        "block_summary_errors": "❌ Fehler:",
        "block_summary_perfect": "🎉 Fehlerfrei!",
        "block_summary_xp": "⭐ +{earned} XP für die Lektion | Gesamt: {total} XP",
        "block_summary_level": "📈 Stufe {level} · {title}",
        "block_summary_next": " ({remaining} XP bis zur nächsten Stufe)",
        "block_summary_streak": "🔥 Serie: {streak} Tage",
        "block_retry_errors": "🔄 Fehler wiederholen",
        "block_pronunciation": "🗣 Aussprache",
        "block_phrases": "💬 Sätze",
        "block_another_lesson": "▶️ Noch eine Lektion",
        "block_topics": "📚 Themen",
        "block_settings": "⚙️ Einstellungen",
        "block_next": "➡️ Nächster Block",
    },
    "ja": {
        "block_intro": "📖 *{topic}*\n{count}語を覚えましょう：\n\n{study}",
        "block_quiz_mode": "クイズ · 4択",
        "block_written_mode": "入力",
        "block_ai_tutor": "AIチューター",
        "block_voice_practice": "🎤 10語を発音",
        "block_topics_study": "トピック 📚",
        "block_quiz_prompt": "訳を選んでください：",
        "block_written_prompt": "訳を入力してください：",
        "block_your_answer": "あなたの答え：_{answer}_",
        "block_summary_result": "📊 *結果：{correct}/{total}*",
        "block_summary_errors": "❌ 間違い：",
        "block_summary_perfect": "🎉 全問正解！",
        "block_summary_xp": "⭐ レッスン +{earned} XP｜合計：{total} XP",
        "block_summary_level": "📈 レベル {level} · {title}",
        "block_summary_next": "（次のレベルまで {remaining} XP）",
        "block_summary_streak": "🔥 連続：{streak}日",
        "block_retry_errors": "🔄 間違いを復習",
        "block_pronunciation": "🗣 発音",
        "block_phrases": "💬 フレーズ",
        "block_another_lesson": "▶️ もう一度レッスン",
        "block_topics": "📚 トピック",
        "block_settings": "⚙️ 設定",
        "block_next": "➡️ 次のブロック",
    },
    "ar": {
        "block_intro": "📖 *{topic}*\nاحفظ {count} كلمات:\n\n{study}",
        "block_quiz_mode": "اختبار · 4 خيارات",
        "block_written_mode": "كتابة",
        "block_ai_tutor": "معلّم AI",
        "block_voice_practice": "🎤 انطق 10 كلمات",
        "block_topics_study": "الموضوعات 📚",
        "block_quiz_prompt": "اختر الترجمة:",
        "block_written_prompt": "اكتب الترجمة:",
        "block_your_answer": "إجابتك: _{answer}_",
        "block_summary_result": "📊 *النتيجة: {correct}/{total}*",
        "block_summary_errors": "❌ الأخطاء:",
        "block_summary_perfect": "🎉 بلا أخطاء!",
        "block_summary_xp": "⭐ +{earned} XP للدرس | المجموع: {total} XP",
        "block_summary_level": "📈 المستوى {level} · {title}",
        "block_summary_next": " ({remaining} XP إلى المستوى التالي)",
        "block_summary_streak": "🔥 السلسلة: {streak} يوم",
        "block_retry_errors": "🔄 راجع الأخطاء",
        "block_pronunciation": "🗣 النطق",
        "block_phrases": "💬 العبارات",
        "block_another_lesson": "▶️ درس آخر",
        "block_topics": "📚 الموضوعات",
        "block_settings": "⚙️ الإعدادات",
        "block_next": "➡️ المجموعة التالية",
    },
    "zh": {
        "block_intro": "📖 *{topic}*\n请记住 {count} 个单词：\n\n{study}",
        "block_quiz_mode": "测验 · 4 个选项",
        "block_written_mode": "书写",
        "block_ai_tutor": "AI 导师",
        "block_voice_practice": "🎤 朗读 10 个单词",
        "block_topics_study": "主题 📚",
        "block_quiz_prompt": "选择翻译：",
        "block_written_prompt": "输入翻译：",
        "block_your_answer": "你的答案：_{answer}_",
        "block_summary_result": "📊 *结果：{correct}/{total}*",
        "block_summary_errors": "❌ 错误：",
        "block_summary_perfect": "🎉 全部正确！",
        "block_summary_xp": "⭐ 本课 +{earned} XP | 总计：{total} XP",
        "block_summary_level": "📈 等级 {level} · {title}",
        "block_summary_next": "（距离下一级还差 {remaining} XP）",
        "block_summary_streak": "🔥 连续学习：{streak} 天",
        "block_retry_errors": "🔄 复习错题",
        "block_pronunciation": "🗣 发音",
        "block_phrases": "💬 短语",
        "block_another_lesson": "▶️ 再上一课",
        "block_topics": "📚 主题",
        "block_settings": "⚙️ 设置",
        "block_next": "➡️ 下一组",
    },
    "ru": {
        "block_intro": "📖 *{topic}*\nЗапомни {count} слов:\n\n{study}",
        "block_quiz_mode": "Тест · 4 варианта",
        "block_written_mode": "Письменно",
        "block_ai_tutor": "AI-репетитор",
        "block_voice_practice": "🎤 Произнести 10 слов",
        "block_topics_study": "Темы 📚",
        "block_quiz_prompt": "Выбери перевод:",
        "block_written_prompt": "Напиши перевод:",
        "block_your_answer": "Твой ответ: _{answer}_",
        "block_summary_result": "📊 *Результат: {correct}/{total}*",
        "block_summary_errors": "❌ Ошибки:",
        "block_summary_perfect": "🎉 Без ошибок!",
        "block_summary_xp": "⭐ +{earned} XP за урок | Всего: {total} XP",
        "block_summary_level": "📈 Уровень {level} · {title}",
        "block_summary_next": " ({remaining} XP до следующего)",
        "block_summary_streak": "🔥 Серия: {streak} дн.",
        "block_retry_errors": "🔄 Повторить ошибки",
        "block_pronunciation": "🗣 Произношение",
        "block_phrases": "💬 Фразы",
        "block_another_lesson": "▶️ Ещё урок",
        "block_topics": "📚 Темы",
        "block_settings": "⚙️ Настройки",
        "block_next": "➡️ Следующий блок",
    },
    "es": {
        "block_intro": "📖 *{topic}*\nMemoriza {count} palabras:\n\n{study}",
        "block_quiz_mode": "Test · 4 opciones",
        "block_written_mode": "Por escrito",
        "block_ai_tutor": "Tutor de IA",
        "block_voice_practice": "🎤 Pronunciar 10 palabras",
        "block_topics_study": "Temas 📚",
        "block_quiz_prompt": "Elige la traducción:",
        "block_written_prompt": "Escribe la traducción:",
        "block_your_answer": "Tu respuesta: _{answer}_",
        "block_summary_result": "📊 *Resultado: {correct}/{total}*",
        "block_summary_errors": "❌ Errores:",
        "block_summary_perfect": "🎉 ¡Sin errores!",
        "block_summary_xp": "⭐ +{earned} XP por la lección | Total: {total} XP",
        "block_summary_level": "📈 Nivel {level} · {title}",
        "block_summary_next": " ({remaining} XP hasta el siguiente nivel)",
        "block_summary_streak": "🔥 Racha: {streak} días",
        "block_retry_errors": "🔄 Repasar errores",
        "block_pronunciation": "🗣 Pronunciación",
        "block_phrases": "💬 Frases",
        "block_another_lesson": "▶️ Otra lección",
        "block_topics": "📚 Temas",
        "block_settings": "⚙️ Ajustes",
        "block_next": "➡️ Siguiente bloque",
    },
}

for _locale, _messages in _LEARNING_BLOCK_COPY.items():
    _CATALOG[_locale].update(_messages)

_LANGUAGE_NAMES: dict[str, dict[str, str]] = {
    "en": {"en": "English", "fr": "French", "de": "German", "ja": "Japanese", "ar": "Arabic", "zh": "Chinese", "ru": "Russian", "es": "Spanish"},
    "fr": {"en": "l'anglais", "fr": "le français", "de": "l'allemand", "ja": "le japonais", "ar": "l'arabe", "zh": "le chinois", "ru": "le russe", "es": "l'espagnol"},
    "de": {"en": "Englisch", "fr": "Französisch", "de": "Deutsch", "ja": "Japanisch", "ar": "Arabisch", "zh": "Chinesisch", "ru": "Russisch", "es": "Spanisch"},
    "ja": {"en": "英語", "fr": "フランス語", "de": "ドイツ語", "ja": "日本語", "ar": "アラビア語", "zh": "中国語", "ru": "ロシア語", "es": "スペイン語"},
    "ar": {"en": "الإنجليزية", "fr": "الفرنسية", "de": "الألمانية", "ja": "اليابانية", "ar": "العربية", "zh": "الصينية", "ru": "الروسية", "es": "الإسبانية"},
    "zh": {"en": "英语", "fr": "法语", "de": "德语", "ja": "日语", "ar": "阿拉伯语", "zh": "中文", "ru": "俄语", "es": "西班牙语"},
    "ru": {"en": "английский", "fr": "французский", "de": "немецкий", "ja": "японский", "ar": "арабский", "zh": "китайский", "ru": "русский", "es": "испанский"},
    "es": {"en": "inglés", "fr": "francés", "de": "alemán", "ja": "japonés", "ar": "árabe", "zh": "chino", "ru": "ruso", "es": "español"},
}

_RESPONSE_LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "ar": "Arabic",
    "zh": "Simplified Chinese",
    "ru": "Russian",
    "es": "Spanish",
}

_USER_SURFACE_COPY = {
    "en": {
        "command_start": "Today's lesson",
        "command_learn": "Choose a topic",
        "command_lang": "Change language",
        "command_stats": "My progress",
        "command_ai": "AI tutor",
        "command_privacy": "Data and privacy",
        "command_help": "Help",
        "voice_prompt_pronunciation": "Pronunciation",
        "voice_prompt_conversation": "Phrases",
        "voice_prompt_focus": "Key word: {target} {transcription}",
        "voice_prompt_pronunciation_instruction": "Say only this word in one voice message.",
        "voice_prompt_conversation_instruction": "Say the whole phrase in one voice message.",
        "voice_prompt_feedback": "I will recognize your speech, suggest a correction and give you the next task.",
        "voice_prompt_evaluation": "The recognized text is checked, not your accent.",
        "privacy_overview": (
            "MY DICTIONARY privacy\n\nLearning history, product events and AI "
            "requests are deleted according to limited retention periods. You can "
            "erase your learning data immediately. Payment and audit records are "
            "kept for refunds, reconciliation and fraud prevention. Access will be "
            "blocked after deletion.\n\n{ai_consent}\n{mirror_memory}"
        ),
        "privacy_ai_granted": "AI consent: granted.",
        "privacy_ai_missing": "AI consent: not granted.",
        "privacy_mirror_enabled": "Mirror context: up to 20 recent messages, retained for {days} days.",
        "privacy_mirror_disabled": "Long-term Mirror context: disabled.",
        "privacy_delete_learning": "Delete my learning data",
        "privacy_voice_revoke": "Revoke voice-processing consent",
        "privacy_voice_missing": "Voice-processing consent not granted",
        "privacy_ai_revoke": "AI consent granted — revoke",
        "privacy_ai_missing_action": "AI consent not granted",
        "billing_disabled": "Purchasing AI credits is not available right now.",
    },
    "fr": {
        "command_start": "Leçon du jour",
        "command_learn": "Choisir un thème",
        "command_lang": "Changer de langue",
        "command_stats": "Ma progression",
        "command_ai": "Tuteur IA",
        "command_privacy": "Données et confidentialité",
        "command_help": "Aide",
        "voice_prompt_pronunciation": "Prononciation",
        "voice_prompt_conversation": "Phrases",
        "voice_prompt_focus": "Mot-clé : {target} {transcription}",
        "voice_prompt_pronunciation_instruction": "Prononcez uniquement ce mot dans un message vocal.",
        "voice_prompt_conversation_instruction": "Prononcez toute la phrase dans un message vocal.",
        "voice_prompt_feedback": "Je reconnaîtrai votre voix, proposerai une correction et donnerai l’exercice suivant.",
        "voice_prompt_evaluation": "Le texte reconnu est évalué, pas votre accent.",
        "privacy_overview": (
            "Confidentialité MY DICTIONARY\n\nL’historique d’apprentissage, les "
            "événements produit et les requêtes IA sont supprimés selon des durées "
            "de conservation limitées. Vous pouvez supprimer immédiatement vos "
            "données d’apprentissage. Les données de paiement et d’audit sont "
            "conservées pour les remboursements, les contrôles et la prévention de "
            "la fraude. L’accès sera bloqué après la suppression.\n\n"
            "{ai_consent}\n{mirror_memory}"
        ),
        "privacy_ai_granted": "Consentement IA : accordé.",
        "privacy_ai_missing": "Consentement IA : non accordé.",
        "privacy_mirror_enabled": "Contexte Mirror : jusqu’à 20 messages récents, conservés {days} jours.",
        "privacy_mirror_disabled": "Contexte Mirror à long terme : désactivé.",
        "privacy_delete_learning": "Supprimer mes données d’apprentissage",
        "privacy_voice_revoke": "Retirer le consentement au traitement vocal",
        "privacy_voice_missing": "Consentement au traitement vocal non accordé",
        "privacy_ai_revoke": "Consentement IA accordé — retirer",
        "privacy_ai_missing_action": "Consentement IA non accordé",
        "billing_disabled": "L’achat de crédits IA n’est pas disponible pour le moment.",
    },
    "de": {
        "command_start": "Heutige Lektion",
        "command_learn": "Thema auswählen",
        "command_lang": "Sprache wechseln",
        "command_stats": "Mein Fortschritt",
        "command_ai": "KI-Tutor",
        "command_privacy": "Daten und Datenschutz",
        "command_help": "Hilfe",
        "voice_prompt_pronunciation": "Aussprache",
        "voice_prompt_conversation": "Sätze",
        "voice_prompt_focus": "Schlüsselwort: {target} {transcription}",
        "voice_prompt_pronunciation_instruction": "Sprich nur dieses Wort in einer Sprachnachricht.",
        "voice_prompt_conversation_instruction": "Sprich den ganzen Satz in einer Sprachnachricht.",
        "voice_prompt_feedback": "Ich erkenne deine Sprache, schlage eine Korrektur vor und gebe die nächste Aufgabe.",
        "voice_prompt_evaluation": "Geprüft wird der erkannte Text, nicht dein Akzent.",
        "privacy_overview": (
            "Datenschutz bei MY DICTIONARY\n\nLernverlauf, Produktereignisse und "
            "KI-Anfragen werden nach begrenzten Aufbewahrungsfristen gelöscht. Du "
            "kannst deine Lerndaten sofort löschen. Zahlungs- und Prüfdatensätze "
            "bleiben für Rückerstattungen, Abgleich und Betrugsschutz erhalten. "
            "Nach der Löschung wird der Zugang gesperrt.\n\n{ai_consent}\n{mirror_memory}"
        ),
        "privacy_ai_granted": "KI-Einwilligung: erteilt.",
        "privacy_ai_missing": "KI-Einwilligung: nicht erteilt.",
        "privacy_mirror_enabled": "Mirror-Kontext: bis zu 20 letzte Nachrichten, {days} Tage gespeichert.",
        "privacy_mirror_disabled": "Langfristiger Mirror-Kontext: deaktiviert.",
        "privacy_delete_learning": "Meine Lerndaten löschen",
        "privacy_voice_revoke": "Einwilligung zur Sprachverarbeitung widerrufen",
        "privacy_voice_missing": "Einwilligung zur Sprachverarbeitung nicht erteilt",
        "privacy_ai_revoke": "KI-Einwilligung erteilt — widerrufen",
        "privacy_ai_missing_action": "KI-Einwilligung nicht erteilt",
        "billing_disabled": "Der Kauf von KI-Credits ist derzeit nicht verfügbar.",
    },
    "ja": {
        "command_start": "今日のレッスン",
        "command_learn": "テーマを選ぶ",
        "command_lang": "言語を変更",
        "command_stats": "学習の進捗",
        "command_ai": "AIチューター",
        "command_privacy": "データとプライバシー",
        "command_help": "ヘルプ",
        "voice_prompt_pronunciation": "発音",
        "voice_prompt_conversation": "フレーズ",
        "voice_prompt_focus": "キーワード：{target} {transcription}",
        "voice_prompt_pronunciation_instruction": "この単語だけを音声メッセージで発音してください。",
        "voice_prompt_conversation_instruction": "フレーズ全体を音声メッセージで発音してください。",
        "voice_prompt_feedback": "音声を認識し、修正案を示して次の課題へ進みます。",
        "voice_prompt_evaluation": "アクセントではなく、認識されたテキストを確認します。",
        "privacy_overview": (
            "MY DICTIONARYのプライバシー\n\n学習履歴、製品イベント、AIリクエストは、"
            "定められた保存期間に従って削除されます。学習データはすぐに削除できます。"
            "返金、照合、不正防止のため、支払い記録と監査記録は保持されます。削除後は"
            "アクセスが停止されます。\n\n{ai_consent}\n{mirror_memory}"
        ),
        "privacy_ai_granted": "AI同意：同意済み。",
        "privacy_ai_missing": "AI同意：未同意。",
        "privacy_mirror_enabled": "Mirrorコンテキスト：直近20件まで、{days}日間保存。",
        "privacy_mirror_disabled": "Mirrorの長期コンテキスト：無効。",
        "privacy_delete_learning": "学習データを削除",
        "privacy_voice_revoke": "音声処理への同意を取り消す",
        "privacy_voice_missing": "音声処理への同意はありません",
        "privacy_ai_revoke": "AI同意済み — 取り消す",
        "privacy_ai_missing_action": "AI同意はありません",
        "billing_disabled": "現在、AIクレジットは購入できません。",
    },
    "ar": {
        "command_start": "درس اليوم",
        "command_learn": "اختيار موضوع",
        "command_lang": "تغيير اللغة",
        "command_stats": "تقدمي",
        "command_ai": "مدرّس AI",
        "command_privacy": "البيانات والخصوصية",
        "command_help": "مساعدة",
        "voice_prompt_pronunciation": "النطق",
        "voice_prompt_conversation": "العبارات",
        "voice_prompt_focus": "الكلمة الأساسية: {target} {transcription}",
        "voice_prompt_pronunciation_instruction": "انطق هذه الكلمة فقط في رسالة صوتية.",
        "voice_prompt_conversation_instruction": "انطق العبارة كاملة في رسالة صوتية.",
        "voice_prompt_feedback": "سأتعرّف على كلامك وأقترح تصحيحاً ثم أرسل المهمة التالية.",
        "voice_prompt_evaluation": "يُفحص النص المتعرّف عليه، وليس لهجتك.",
        "privacy_overview": (
            "خصوصية MY DICTIONARY\n\nيتم حذف سجل التعلم وأحداث المنتج وطلبات AI "
            "وفق مدد حفظ محدودة. يمكنك حذف بيانات التعلم فوراً. تُحفظ سجلات الدفع "
            "والتدقيق لأغراض الاسترداد والمطابقة ومنع الاحتيال. سيتم حظر الوصول بعد "
            "الحذف.\n\n{ai_consent}\n{mirror_memory}"
        ),
        "privacy_ai_granted": "موافقة AI: ممنوحة.",
        "privacy_ai_missing": "موافقة AI: غير ممنوحة.",
        "privacy_mirror_enabled": "سياق Mirror: حتى 20 رسالة أخيرة، محفوظة لمدة {days} أيام.",
        "privacy_mirror_disabled": "سياق Mirror طويل المدى: معطّل.",
        "privacy_delete_learning": "حذف بيانات تعلمي",
        "privacy_voice_revoke": "سحب موافقة معالجة الصوت",
        "privacy_voice_missing": "لم تُمنح موافقة معالجة الصوت",
        "privacy_ai_revoke": "موافقة AI ممنوحة — سحبها",
        "privacy_ai_missing_action": "موافقة AI غير ممنوحة",
        "billing_disabled": "شراء أرصدة AI غير متاح حالياً.",
    },
    "zh": {
        "command_start": "今日课程",
        "command_learn": "选择主题",
        "command_lang": "更改语言",
        "command_stats": "我的进度",
        "command_ai": "AI 导师",
        "command_privacy": "数据与隐私",
        "command_help": "帮助",
        "voice_prompt_pronunciation": "发音",
        "voice_prompt_conversation": "短语",
        "voice_prompt_focus": "关键词：{target} {transcription}",
        "voice_prompt_pronunciation_instruction": "请只用一条语音消息读出这个单词。",
        "voice_prompt_conversation_instruction": "请用一条语音消息读出整句。",
        "voice_prompt_feedback": "我会识别语音、给出纠正建议并发送下一项练习。",
        "voice_prompt_evaluation": "检查的是识别出的文本，而不是你的口音。",
        "privacy_overview": (
            "MY DICTIONARY 隐私\n\n学习记录、产品事件和 AI 请求会按有限的保留期"
            "删除。你可以立即删除学习数据。付款和审计记录会保留，用于退款、核对和"
            "防止欺诈。删除后访问权限将被禁用。\n\n{ai_consent}\n{mirror_memory}"
        ),
        "privacy_ai_granted": "AI 同意：已授权。",
        "privacy_ai_missing": "AI 同意：未授权。",
        "privacy_mirror_enabled": "Mirror 上下文：最多保留最近 20 条消息，保存 {days} 天。",
        "privacy_mirror_disabled": "Mirror 长期上下文：已关闭。",
        "privacy_delete_learning": "删除我的学习数据",
        "privacy_voice_revoke": "撤回语音处理同意",
        "privacy_voice_missing": "未授权语音处理",
        "privacy_ai_revoke": "已授权 AI — 撤回",
        "privacy_ai_missing_action": "未授权 AI",
        "billing_disabled": "目前无法购买 AI 点数。",
    },
    "ru": {
        "command_start": "Урок на сегодня",
        "command_learn": "Выбрать тему",
        "command_lang": "Сменить язык",
        "command_stats": "Мой прогресс",
        "command_ai": "AI-репетитор",
        "command_privacy": "Данные и приватность",
        "command_help": "Помощь",
        "voice_prompt_pronunciation": "Произношение",
        "voice_prompt_conversation": "Фразы",
        "voice_prompt_focus": "Ключевое слово: {target} {transcription}",
        "voice_prompt_pronunciation_instruction": "Скажи только это слово одним голосовым.",
        "voice_prompt_conversation_instruction": "Скажи всю фразу одним голосовым.",
        "voice_prompt_feedback": "Я распознаю речь, подскажу исправление и сам дам следующее задание.",
        "voice_prompt_evaluation": "Проверяется распознанный текст, а не акцент.",
        "privacy_overview": (
            "Приватность MY DICTIONARY\n\nУчебная история, события продукта и "
            "AI-запросы удаляются по ограниченным срокам хранения. Ты можешь "
            "стереть свои учебные данные сразу. Платёжные и аудиторские записи "
            "сохраняются для возвратов, сверки и защиты от мошенничества. После "
            "удаления доступ будет заблокирован.\n\n{ai_consent}\n{mirror_memory}"
        ),
        "privacy_ai_granted": "AI-согласие: принято.",
        "privacy_ai_missing": "AI-согласие: не выдано.",
        "privacy_mirror_enabled": "Контекст Mirror: до 20 последних реплик, хранение {days} дней.",
        "privacy_mirror_disabled": "Долговременный контекст Mirror: выключен.",
        "privacy_delete_learning": "Удалить мои учебные данные",
        "privacy_voice_revoke": "Отозвать согласие на обработку голоса",
        "privacy_voice_missing": "Согласие на обработку голоса не выдано",
        "privacy_ai_revoke": "AI-согласие принято — отозвать",
        "privacy_ai_missing_action": "AI-согласие не выдано",
        "billing_disabled": "Покупка AI-кредитов пока недоступна.",
    },
    "es": {
        "command_start": "Lección de hoy",
        "command_learn": "Elegir tema",
        "command_lang": "Cambiar idioma",
        "command_stats": "Mi progreso",
        "command_ai": "Tutor de IA",
        "command_privacy": "Datos y privacidad",
        "command_help": "Ayuda",
        "voice_prompt_pronunciation": "Pronunciación",
        "voice_prompt_conversation": "Frases",
        "voice_prompt_focus": "Palabra clave: {target} {transcription}",
        "voice_prompt_pronunciation_instruction": "Pronuncia solo esta palabra en un mensaje de voz.",
        "voice_prompt_conversation_instruction": "Pronuncia la frase completa en un mensaje de voz.",
        "voice_prompt_feedback": "Reconoceré tu voz, sugeriré una corrección y enviaré la siguiente tarea.",
        "voice_prompt_evaluation": "Se comprueba el texto reconocido, no tu acento.",
        "privacy_overview": (
            "Privacidad de MY DICTIONARY\n\nEl historial de aprendizaje, los eventos "
            "del producto y las solicitudes de IA se eliminan según periodos de "
            "conservación limitados. Puedes borrar tus datos de aprendizaje de "
            "inmediato. Los registros de pago y auditoría se conservan para "
            "reembolsos, conciliación y prevención del fraude. El acceso se "
            "bloqueará después del borrado.\n\n{ai_consent}\n{mirror_memory}"
        ),
        "privacy_ai_granted": "Consentimiento de IA: concedido.",
        "privacy_ai_missing": "Consentimiento de IA: no concedido.",
        "privacy_mirror_enabled": "Contexto de Mirror: hasta 20 mensajes recientes, conservados {days} días.",
        "privacy_mirror_disabled": "Contexto de Mirror a largo plazo: desactivado.",
        "privacy_delete_learning": "Eliminar mis datos de aprendizaje",
        "privacy_voice_revoke": "Revocar el consentimiento de procesamiento de voz",
        "privacy_voice_missing": "Consentimiento de procesamiento de voz no concedido",
        "privacy_ai_revoke": "Consentimiento de IA concedido — revocar",
        "privacy_ai_missing_action": "Consentimiento de IA no concedido",
        "billing_disabled": "La compra de créditos de IA no está disponible ahora.",
    },
}

for _locale, _messages in _USER_SURFACE_COPY.items():
    _CATALOG[_locale].update(_messages)

_MINIAPP_TELEGRAM_COPY = {
    "en": {"command_app": "Open app", "miniapp_open": "Open MY DICTIONARY", "miniapp_private_only": "Open /app in a private chat with the bot.", "miniapp_disabled": "The app menu is not available right now."},
    "fr": {"command_app": "Ouvrir l’app", "miniapp_open": "Ouvrir MY DICTIONARY", "miniapp_private_only": "Ouvrez /app dans une conversation privée avec le bot.", "miniapp_disabled": "Le menu de l’application n’est pas disponible pour le moment."},
    "de": {"command_app": "App öffnen", "miniapp_open": "MY DICTIONARY öffnen", "miniapp_private_only": "Öffne /app in einem privaten Chat mit dem Bot.", "miniapp_disabled": "Das App-Menü ist derzeit nicht verfügbar."},
    "ja": {"command_app": "アプリを開く", "miniapp_open": "MY DICTIONARYを開く", "miniapp_private_only": "ボットとのプライベートチャットで /app を開いてください。", "miniapp_disabled": "アプリメニューは現在利用できません。"},
    "ar": {"command_app": "فتح التطبيق", "miniapp_open": "فتح MY DICTIONARY", "miniapp_private_only": "افتح /app في محادثة خاصة مع البوت.", "miniapp_disabled": "قائمة التطبيق غير متاحة حالياً."},
    "zh": {"command_app": "打开应用", "miniapp_open": "打开 MY DICTIONARY", "miniapp_private_only": "请在与机器人的私聊中打开 /app。", "miniapp_disabled": "应用菜单暂时不可用。"},
    "ru": {"command_app": "Открыть приложение", "miniapp_open": "Открыть MY DICTIONARY", "miniapp_private_only": "Откройте /app в личном чате с ботом.", "miniapp_disabled": "Меню приложения сейчас недоступно."},
    "es": {"command_app": "Abrir la app", "miniapp_open": "Abrir MY DICTIONARY", "miniapp_private_only": "Abre /app en un chat privado con el bot.", "miniapp_disabled": "El menú de la aplicación no está disponible ahora."},
}

for _locale, _messages in _MINIAPP_TELEGRAM_COPY.items():
    _CATALOG[_locale].update(_messages)

_TELEGRAM_INVITE_COPY = {
    "en": {
        "command_invite": "Invite friends",
        "invite_offer": "Invite friends to learn with MY DICTIONARY. You earn 5 AI credits for each friend who completes onboarding, for up to 10 friends. 🎁",
        "invite_continue": "Continue",
        "invite_share_text": "Learn vocabulary with me in MY DICTIONARY!",
        "invite_unavailable": "Invitations are not available right now.",
    },
    "fr": {
        "command_invite": "Inviter des amis",
        "invite_offer": "Invitez des amis à apprendre avec MY DICTIONARY. Vous gagnez 5 crédits IA pour chaque ami qui termine sa configuration, dans la limite de 10 amis. 🎁",
        "invite_continue": "Continuer",
        "invite_share_text": "Apprenez du vocabulaire avec moi dans MY DICTIONARY !",
        "invite_unavailable": "Les invitations ne sont pas disponibles pour le moment.",
    },
    "de": {
        "command_invite": "Freunde einladen",
        "invite_offer": "Lade Freunde ein, mit MY DICTIONARY zu lernen. Du erhältst 5 KI-Credits, nachdem jeder Freund die Einrichtung abgeschlossen hat, für bis zu 10 Freunde. 🎁",
        "invite_continue": "Weiter",
        "invite_share_text": "Lerne mit mir Vokabeln in MY DICTIONARY!",
        "invite_unavailable": "Einladungen sind derzeit nicht verfügbar.",
    },
    "ja": {
        "command_invite": "友達を招待",
        "invite_offer": "MY DICTIONARYに友達を招待しましょう。友達がオンボーディングを完了すると、あなたは5 AIクレジットを獲得できます。報酬は最大10人までです。🎁",
        "invite_continue": "続ける",
        "invite_share_text": "MY DICTIONARYで一緒に単語を学ぼう！",
        "invite_unavailable": "現在、招待は利用できません。",
    },
    "ar": {
        "command_invite": "دعوة الأصدقاء",
        "invite_offer": "ادعُ أصدقاءك للتعلّم مع MY DICTIONARY. تحصل على 5 أرصدة AI بعد إكمال كل صديق للإعداد، لما يصل إلى 10 أصدقاء. 🎁",
        "invite_continue": "متابعة",
        "invite_share_text": "تعلّم المفردات معي في MY DICTIONARY!",
        "invite_unavailable": "الدعوات غير متاحة حالياً.",
    },
    "zh": {
        "command_invite": "邀请好友",
        "invite_offer": "邀请好友一起使用 MY DICTIONARY 学习。每位好友完成新手设置后，你将获得 5 个 AI 点数，最多计算 10 位好友。🎁",
        "invite_continue": "继续",
        "invite_share_text": "和我一起在 MY DICTIONARY 学单词吧！",
        "invite_unavailable": "邀请功能暂时不可用。",
    },
    "ru": {
        "command_invite": "Пригласить друзей",
        "invite_offer": "Пригласите друзей учиться в MY DICTIONARY. Когда друг завершит настройку, вы получите 5 AI-кредитов. Награда доступна максимум за 10 друзей. 🎁",
        "invite_continue": "Продолжить",
        "invite_share_text": "Давай учить слова вместе в MY DICTIONARY!",
        "invite_unavailable": "Приглашения сейчас недоступны.",
    },
    "es": {
        "command_invite": "Invitar amigos",
        "invite_offer": "Invita a tus amigos a aprender con MY DICTIONARY. Obtienes 5 créditos de IA por cada amigo que completa la configuración, hasta un máximo de 10 amigos. 🎁",
        "invite_continue": "Continuar",
        "invite_share_text": "¡Aprende vocabulario conmigo en MY DICTIONARY!",
        "invite_unavailable": "Las invitaciones no están disponibles ahora.",
    },
}

for _locale, _messages in _TELEGRAM_INVITE_COPY.items():
    _CATALOG[_locale].update(_messages)

_USER_SURFACE_CYCLE2_COPY = {
    "en": {
        "privacy_voice_status": "Consent can be granted when you start /voice.",
        "privacy_consent_revoked": "Consent revoked.",
        "privacy_voice_revoked": "Voice-processing consent was revoked. The active voice session was stopped. Records changed: {changed}.",
        "privacy_ai_status": "Consent can be granted when you start /ai.",
        "privacy_ai_revoked": "AI-processing consent was revoked. No new AI requests will be sent until you consent again. Records changed: {changed}.",
        "privacy_delete_prompt": "Delete the learning profile, progress, analytics and AI history? These data cannot be restored.",
        "privacy_confirm_delete": "Confirm deletion",
        "privacy_cancel": "Cancel",
        "privacy_deletion_cancelled": "Deletion cancelled.",
        "privacy_data_unchanged": "Learning data were not changed.",
        "privacy_unknown_action": "Unknown action.",
        "privacy_data_deleted": "Data deleted.",
        "privacy_deletion_complete": "Learning data were deleted. Only the required payment and audit trail remains. Operation reference: {reference}.",
        "ai_processing_consent": "AI-processing consent\n\n{notice}\n\nVersion: {version}",
        "ai_consent_accept": "Accept and continue",
        "ai_consent_cancel": "Cancel",
        "ai_usage_stats": "AI usage\n\nAvailable credits: {available}\nReserved: {reserved}\nUsed: {spent}\nRequests: {completed} completed, {failed} refunded",
        "mirror_feedback_helpful": "Helpful",
        "mirror_feedback_unhelpful": "Not helpful",
        "mirror_feedback_unavailable": "Rating unavailable.",
        "mirror_feedback_thanks": "Thank you",
        "mirror_feedback_recorded": "Rating already recorded",
        "mirror_response_choose": "Choose a response format: /response text, /response voice or /response both.",
        "mirror_response_saved": "Mirror response format: {mode}.",
        "mirror_feedback_question": "Was this response helpful?",
        "voice_entry_pronunciation": "🎤 Pronounce 10 words",
        "voice_entry_phrases": "💬 Block phrases",
        "voice_entry_translation": "🌐 Translate a voice message",
        "voice_entry_disabled": "Voice features are currently disabled.",
        "voice_entry": "🎙 Voice messages\n\nSend a voice message with a question and AI will recognize the speech and answer in context.\n\nFor pronunciation, choose a practice below. One voice message means one word. After checking, I will show the next one.",
        "voice_consent": "Voice-processing consent\n\n{notice}\n\nVersion: {version}",
        "voice_consent_accept_continue": "Accept and continue",
        "voice_consent_accept_start": "Accept and start",
        "voice_consent_cancel": "Cancel",
        "voice_feedback_exact": "✅ Correct. Moving to the next word.",
        "voice_feedback_close": "🟡 Close. Check the spelling above; moving on.",
        "voice_feedback_retry": "🔁 Try the same word again.",
        "voice_feedback_recognized": "Recognized: {value}",
        "voice_feedback_meaning": "Meaning: {value}",
        "voice_feedback_phrase": "Phrase: {value}",
        "voice_feedback_focus": "Key word: {value}",
        "voice_feedback_focus_transcription": "Word transcription: {value}",
        "voice_feedback_word": "Word: {value}",
        "voice_feedback_transcription": "Transcription: {value}",
        "voice_feedback_other_word": "This sounds like another word in the block: {target} — {meaning}.",
        "voice_feedback_text_notice": "This compares recognized text; it is not an acoustic assessment of your accent.",
        "voice_feedback_credits": "AI credits: {credits}",
    },
    "fr": {
        "privacy_voice_status": "Le consentement peut être accordé au lancement de /voice.",
        "privacy_consent_revoked": "Consentement révoqué.",
        "privacy_voice_revoked": "Le consentement au traitement vocal a été révoqué. La session vocale active a été arrêtée. Enregistrements modifiés : {changed}.",
        "privacy_ai_status": "Le consentement peut être accordé au lancement de /ai.",
        "privacy_ai_revoked": "Le consentement au traitement par l’IA a été révoqué. Aucune nouvelle requête IA ne sera envoyée avant un nouveau consentement. Enregistrements modifiés : {changed}.",
        "privacy_delete_prompt": "Supprimer le profil d’apprentissage, la progression, les analyses et l’historique IA ? Ces données ne pourront pas être restaurées.",
        "privacy_confirm_delete": "Confirmer la suppression",
        "privacy_cancel": "Annuler",
        "privacy_deletion_cancelled": "Suppression annulée.",
        "privacy_data_unchanged": "Les données d’apprentissage n’ont pas été modifiées.",
        "privacy_unknown_action": "Action inconnue.",
        "privacy_data_deleted": "Données supprimées.",
        "privacy_deletion_complete": "Les données d’apprentissage ont été supprimées. Seules les traces de paiement et d’audit obligatoires sont conservées. Référence de l’opération : {reference}.",
        "ai_processing_consent": "Consentement au traitement par l’IA\n\n{notice}\n\nVersion : {version}",
        "ai_consent_accept": "Accepter et continuer",
        "ai_consent_cancel": "Annuler",
        "ai_usage_stats": "Utilisation de l’IA\n\nCrédits disponibles : {available}\nRéservés : {reserved}\nUtilisés : {spent}\nRequêtes : {completed} réussies, {failed} remboursée",
        "mirror_feedback_helpful": "Utile",
        "mirror_feedback_unhelpful": "Pas utile",
        "mirror_feedback_unavailable": "Évaluation indisponible.",
        "mirror_feedback_thanks": "Merci",
        "mirror_feedback_recorded": "Évaluation déjà enregistrée",
        "mirror_response_choose": "Choisissez le format : /response text, /response voice ou /response both.",
        "mirror_response_saved": "Format des réponses Mirror : {mode}.",
        "mirror_feedback_question": "Cette réponse était-elle utile ?",
        "voice_entry_pronunciation": "🎤 Prononcer 10 mots",
        "voice_entry_phrases": "💬 Phrases du bloc",
        "voice_entry_translation": "🌐 Traduire un message vocal",
        "voice_entry_disabled": "Les fonctions vocales sont désactivées pour le moment.",
        "voice_entry": "🎙 Messages vocaux\n\nEnvoyez simplement un message vocal avec une question : l’IA reconnaîtra la parole et répondra selon le contexte.\n\nPour la prononciation, choisissez un exercice ci-dessous. Un message vocal correspond à un mot. Après vérification, le mot suivant apparaîtra.",
        "voice_consent": "Consentement au traitement vocal\n\n{notice}\n\nVersion : {version}",
        "voice_consent_accept_continue": "Accepter et continuer",
        "voice_consent_accept_start": "Accepter et commencer",
        "voice_consent_cancel": "Annuler",
        "voice_feedback_exact": "✅ Correct. Passage au mot suivant.",
        "voice_feedback_close": "🟡 Presque. Vérifiez l’orthographe ci-dessus ; continuons.",
        "voice_feedback_retry": "🔁 Essayez encore une fois le même mot.",
        "voice_feedback_recognized": "Reconnu : {value}",
        "voice_feedback_meaning": "Sens : {value}",
        "voice_feedback_phrase": "Phrase : {value}",
        "voice_feedback_focus": "Mot-clé : {value}",
        "voice_feedback_focus_transcription": "Transcription du mot : {value}",
        "voice_feedback_word": "Mot : {value}",
        "voice_feedback_transcription": "Transcription : {value}",
        "voice_feedback_other_word": "Cela ressemble à un autre mot du bloc : {target} — {meaning}.",
        "voice_feedback_text_notice": "Cette comparaison porte sur le texte reconnu, pas sur une évaluation acoustique de votre accent.",
        "voice_feedback_credits": "Crédits IA : {credits}",
    },
    "ru": {
        "privacy_voice_status": "Согласие можно выдать при запуске /voice.",
        "privacy_consent_revoked": "Согласие отозвано.",
        "privacy_voice_revoked": "Согласие на обработку голоса отозвано. Активная голосовая сессия остановлена. Изменено записей: {changed}.",
        "privacy_ai_status": "Согласие можно выдать при запуске /ai.",
        "privacy_ai_revoked": "Согласие на обработку AI отозвано. Новые AI-запросы не будут отправлены до повторного согласия. Изменено записей: {changed}.",
        "privacy_delete_prompt": "Удалить учебный профиль, прогресс, аналитику и историю AI? Восстановить эти данные будет нельзя.",
        "privacy_confirm_delete": "Подтвердить удаление",
        "privacy_cancel": "Отмена",
        "privacy_deletion_cancelled": "Удаление отменено.",
        "privacy_data_unchanged": "Учебные данные не изменены.",
        "privacy_unknown_action": "Неизвестное действие.",
        "privacy_data_deleted": "Данные удалены.",
        "privacy_deletion_complete": "Учебные данные удалены. Сохранён только обязательный платёжный и аудиторский след. Номер операции: {reference}.",
        "ai_processing_consent": "Согласие на обработку AI\n\n{notice}\n\nВерсия: {version}",
        "ai_consent_accept": "Согласен и продолжить",
        "ai_consent_cancel": "Отмена",
        "ai_usage_stats": "AI-использование\n\nДоступно кредитов: {available}\nЗарезервировано: {reserved}\nИспользовано: {spent}\nЗапросы: {completed} успешно, {failed} с возвратом",
        "mirror_feedback_helpful": "Полезно",
        "mirror_feedback_unhelpful": "Не помогло",
        "mirror_feedback_unavailable": "Оценка недоступна.",
        "mirror_feedback_thanks": "Спасибо",
        "mirror_feedback_recorded": "Оценка уже учтена",
        "mirror_response_choose": "Выбери формат ответа: /response text, /response voice или /response both.",
        "mirror_response_saved": "Формат ответов Mirror: {mode}.",
        "mirror_feedback_question": "Ответ был полезен?",
        "voice_entry_pronunciation": "🎤 Произнести 10 слов",
        "voice_entry_phrases": "💬 Фразы по блоку",
        "voice_entry_translation": "🌐 Перевести голосовое",
        "voice_entry_disabled": "Голосовые функции пока выключены.",
        "voice_entry": "🎙 Голосовые сообщения\n\nПросто отправь голосовое с вопросом — AI распознает речь и ответит по контексту.\n\nДля произношения выбери тренировку ниже. Одно голосовое — одно слово. После проверки я сам покажу следующее.",
        "voice_consent": "Согласие на обработку голоса\n\n{notice}\n\nВерсия: {version}",
        "voice_consent_accept_continue": "Согласен и продолжить",
        "voice_consent_accept_start": "Согласен и начать",
        "voice_consent_cancel": "Отмена",
        "voice_feedback_exact": "✅ Верно. Перехожу к следующему слову.",
        "voice_feedback_close": "🟡 Близко. Сверь написание выше; продолжаем.",
        "voice_feedback_retry": "🔁 Попробуй это же слово ещё раз.",
        "voice_feedback_recognized": "Распознано: {value}",
        "voice_feedback_meaning": "Значение: {value}",
        "voice_feedback_phrase": "Фраза: {value}",
        "voice_feedback_focus": "Ключевое слово: {value}",
        "voice_feedback_focus_transcription": "Транскрипция слова: {value}",
        "voice_feedback_word": "Слово: {value}",
        "voice_feedback_transcription": "Транскрипция: {value}",
        "voice_feedback_other_word": "Похоже на другое слово блока: {target} — {meaning}.",
        "voice_feedback_text_notice": "Это сравнение текста распознавания, а не акустическая оценка акцента.",
        "voice_feedback_credits": "AI-кредиты: {credits}",
    },
    "de": {
        "privacy_voice_status": "Die Einwilligung kann beim Start von /voice erteilt werden.",
        "privacy_consent_revoked": "Einwilligung widerrufen.",
        "privacy_voice_revoked": "Die Einwilligung zur Sprachverarbeitung wurde widerrufen. Die aktive Sprachsitzung wurde beendet. Geänderte Datensätze: {changed}.",
        "privacy_ai_status": "Die Einwilligung kann beim Start von /ai erteilt werden.",
        "privacy_ai_revoked": "Die Einwilligung zur KI-Verarbeitung wurde widerrufen. Bis zu einer neuen Einwilligung werden keine KI-Anfragen gesendet. Geänderte Datensätze: {changed}.",
        "privacy_delete_prompt": "Lernprofil, Fortschritt, Analysen und KI-Verlauf löschen? Diese Daten können nicht wiederhergestellt werden.",
        "privacy_confirm_delete": "Löschung bestätigen",
        "privacy_cancel": "Abbrechen",
        "privacy_deletion_cancelled": "Löschung abgebrochen.",
        "privacy_data_unchanged": "Die Lerndaten wurden nicht geändert.",
        "privacy_unknown_action": "Unbekannte Aktion.",
        "privacy_data_deleted": "Daten gelöscht.",
        "privacy_deletion_complete": "Die Lerndaten wurden gelöscht. Nur der erforderliche Zahlungs- und Prüfpfad bleibt erhalten. Vorgangsnummer: {reference}.",
        "ai_processing_consent": "Einwilligung zur KI-Verarbeitung\n\n{notice}\n\nVersion: {version}",
        "ai_consent_accept": "Akzeptieren und fortfahren",
        "ai_consent_cancel": "Abbrechen",
        "ai_usage_stats": "KI-Nutzung\n\nVerfügbare Credits: {available}\nReserviert: {reserved}\nVerwendet: {spent}\nAnfragen: {completed} erfolgreich, {failed} erstattet",
        "mirror_feedback_helpful": "Hilfreich",
        "mirror_feedback_unhelpful": "Nicht hilfreich",
        "mirror_feedback_unavailable": "Bewertung nicht verfügbar.",
        "mirror_feedback_thanks": "Danke",
        "mirror_feedback_recorded": "Bewertung bereits erfasst",
        "mirror_response_choose": "Wähle das Antwortformat: /response text, /response voice oder /response both.",
        "mirror_response_saved": "Mirror-Antwortformat: {mode}.",
        "mirror_feedback_question": "War diese Antwort hilfreich?",
        "voice_entry_pronunciation": "🎤 10 Wörter aussprechen",
        "voice_entry_phrases": "💬 Sätze aus dem Block",
        "voice_entry_translation": "🌐 Sprachnachricht übersetzen",
        "voice_entry_disabled": "Sprachfunktionen sind derzeit deaktiviert.",
        "voice_entry": "🎙 Sprachnachrichten\n\nSende eine Sprachnachricht mit einer Frage. Die KI erkennt die Sprache und antwortet im Kontext.\n\nWähle unten eine Ausspracheübung. Eine Sprachnachricht entspricht einem Wort. Nach der Prüfung erscheint das nächste.",
        "voice_consent": "Einwilligung zur Sprachverarbeitung\n\n{notice}\n\nVersion: {version}",
        "voice_consent_accept_continue": "Akzeptieren und fortfahren",
        "voice_consent_accept_start": "Akzeptieren und starten",
        "voice_consent_cancel": "Abbrechen",
        "voice_feedback_exact": "✅ Richtig. Weiter zum nächsten Wort.",
        "voice_feedback_close": "🟡 Fast. Prüfe die Schreibweise oben; weiter geht’s.",
        "voice_feedback_retry": "🔁 Versuche dasselbe Wort noch einmal.",
        "voice_feedback_recognized": "Erkannt: {value}",
        "voice_feedback_meaning": "Bedeutung: {value}",
        "voice_feedback_phrase": "Satz: {value}",
        "voice_feedback_focus": "Schlüsselwort: {value}",
        "voice_feedback_focus_transcription": "Worttranskription: {value}",
        "voice_feedback_word": "Wort: {value}",
        "voice_feedback_transcription": "Transkription: {value}",
        "voice_feedback_other_word": "Das klingt nach einem anderen Wort im Block: {target} — {meaning}.",
        "voice_feedback_text_notice": "Verglichen wird der erkannte Text, nicht dein Akzent.",
        "voice_feedback_credits": "KI-Credits: {credits}",
    },
    "es": {
        "privacy_voice_status": "El consentimiento puede darse al iniciar /voice.",
        "privacy_consent_revoked": "Consentimiento revocado.",
        "privacy_voice_revoked": "Se revocó el consentimiento para procesar voz. La sesión de voz activa se detuvo. Registros modificados: {changed}.",
        "privacy_ai_status": "El consentimiento puede darse al iniciar /ai.",
        "privacy_ai_revoked": "Se revocó el consentimiento para procesar IA. No se enviarán nuevas solicitudes de IA hasta un nuevo consentimiento. Registros modificados: {changed}.",
        "privacy_delete_prompt": "¿Eliminar el perfil de aprendizaje, el progreso, las analíticas y el historial de IA? Estos datos no se podrán recuperar.",
        "privacy_confirm_delete": "Confirmar eliminación",
        "privacy_cancel": "Cancelar",
        "privacy_deletion_cancelled": "Eliminación cancelada.",
        "privacy_data_unchanged": "Los datos de aprendizaje no se modificaron.",
        "privacy_unknown_action": "Acción desconocida.",
        "privacy_data_deleted": "Datos eliminados.",
        "privacy_deletion_complete": "Los datos de aprendizaje se eliminaron. Solo se conserva el registro obligatorio de pagos y auditoría. Referencia de operación: {reference}.",
        "ai_processing_consent": "Consentimiento para el tratamiento por IA\n\n{notice}\n\nVersión: {version}",
        "ai_consent_accept": "Aceptar y continuar",
        "ai_consent_cancel": "Cancelar",
        "ai_usage_stats": "Uso de IA\n\nCréditos disponibles: {available}\nReservados: {reserved}\nUsados: {spent}\nSolicitudes: {completed} correctas, {failed} reembolsadas",
        "mirror_feedback_helpful": "Útil",
        "mirror_feedback_unhelpful": "No útil",
        "mirror_feedback_unavailable": "Valoración no disponible.",
        "mirror_feedback_thanks": "Gracias",
        "mirror_feedback_recorded": "Valoración ya registrada",
        "mirror_response_choose": "Elige el formato: /response text, /response voice o /response both.",
        "mirror_response_saved": "Formato de respuestas de Mirror: {mode}.",
        "mirror_feedback_question": "¿Fue útil esta respuesta?",
        "voice_entry_pronunciation": "🎤 Pronunciar 10 palabras",
        "voice_entry_phrases": "💬 Frases del bloque",
        "voice_entry_translation": "🌐 Traducir un mensaje de voz",
        "voice_entry_disabled": "Las funciones de voz están desactivadas por ahora.",
        "voice_entry": "🎙 Mensajes de voz\n\nEnvía un mensaje de voz con una pregunta: la IA reconocerá el habla y responderá según el contexto.\n\nPara practicar la pronunciación, elige un ejercicio. Un mensaje de voz corresponde a una palabra. Tras comprobarla, aparecerá la siguiente.",
        "voice_consent": "Consentimiento para procesar voz\n\n{notice}\n\nVersión: {version}",
        "voice_consent_accept_continue": "Aceptar y continuar",
        "voice_consent_accept_start": "Aceptar y empezar",
        "voice_consent_cancel": "Cancelar",
        "voice_feedback_exact": "✅ Correcto. Pasamos a la siguiente palabra.",
        "voice_feedback_close": "🟡 Cerca. Revisa la ortografía; continuamos.",
        "voice_feedback_retry": "🔁 Intenta la misma palabra otra vez.",
        "voice_feedback_recognized": "Reconocido: {value}",
        "voice_feedback_meaning": "Significado: {value}",
        "voice_feedback_phrase": "Frase: {value}",
        "voice_feedback_focus": "Palabra clave: {value}",
        "voice_feedback_focus_transcription": "Transcripción de la palabra: {value}",
        "voice_feedback_word": "Palabra: {value}",
        "voice_feedback_transcription": "Transcripción: {value}",
        "voice_feedback_other_word": "Parece otra palabra del bloque: {target} — {meaning}.",
        "voice_feedback_text_notice": "Se compara el texto reconocido, no se evalúa acústicamente tu acento.",
        "voice_feedback_credits": "Créditos de IA: {credits}",
    },
    "ja": {
        "privacy_voice_status": "/voice の開始時に同意できます。",
        "privacy_consent_revoked": "同意を取り消しました。",
        "privacy_voice_revoked": "音声処理への同意を取り消し、進行中の音声セッションを停止しました。変更された記録：{changed}。",
        "privacy_ai_status": "/ai の開始時に同意できます。",
        "privacy_ai_revoked": "AI処理への同意を取り消しました。再同意するまで新しいAIリクエストは送信されません。変更された記録：{changed}。",
        "privacy_delete_prompt": "学習プロフィール、進捗、分析、AI履歴を削除しますか？これらのデータは復元できません。",
        "privacy_confirm_delete": "削除を確認",
        "privacy_cancel": "キャンセル",
        "privacy_deletion_cancelled": "削除をキャンセルしました。",
        "privacy_data_unchanged": "学習データは変更されていません。",
        "privacy_unknown_action": "不明な操作です。",
        "privacy_data_deleted": "データを削除しました。",
        "privacy_deletion_complete": "学習データを削除しました。必須の支払い・監査記録のみ保持されます。操作番号：{reference}。",
        "ai_processing_consent": "AI処理への同意\n\n{notice}\n\nバージョン：{version}",
        "ai_consent_accept": "同意して続ける",
        "ai_consent_cancel": "キャンセル",
        "ai_usage_stats": "AI利用状況\n\n利用可能なクレジット：{available}\n予約済み：{reserved}\n使用済み：{spent}\nリクエスト：成功 {completed}、返却 {failed}",
        "mirror_feedback_helpful": "役に立った",
        "mirror_feedback_unhelpful": "役に立たなかった",
        "mirror_feedback_unavailable": "評価できません。",
        "mirror_feedback_thanks": "ありがとうございます",
        "mirror_feedback_recorded": "評価は記録済みです",
        "mirror_response_choose": "回答形式を選んでください：/response text、/response voice、/response both。",
        "mirror_response_saved": "Mirrorの回答形式：{mode}。",
        "mirror_feedback_question": "この回答は役に立ちましたか？",
        "voice_entry_pronunciation": "🎤 10語を発音",
        "voice_entry_phrases": "💬 ブロックのフレーズ",
        "voice_entry_translation": "🌐 音声メッセージを翻訳",
        "voice_entry_disabled": "音声機能は現在無効です。",
        "voice_entry": "🎙 音声メッセージ\n\n質問を音声で送ると、AIが音声を認識して文脈に沿って回答します。\n\n発音練習は下から選んでください。音声1件につき単語1つです。確認後、次の単語を表示します。",
        "voice_consent": "音声処理への同意\n\n{notice}\n\nバージョン：{version}",
        "voice_consent_accept_continue": "同意して続ける",
        "voice_consent_accept_start": "同意して開始",
        "voice_consent_cancel": "キャンセル",
        "voice_feedback_exact": "✅ 正解です。次の単語へ進みます。",
        "voice_feedback_close": "🟡 惜しいです。上の綴りを確認して続けましょう。",
        "voice_feedback_retry": "🔁 同じ単語をもう一度試してください。",
        "voice_feedback_recognized": "認識結果：{value}",
        "voice_feedback_meaning": "意味：{value}",
        "voice_feedback_phrase": "フレーズ：{value}",
        "voice_feedback_focus": "キーワード：{value}",
        "voice_feedback_focus_transcription": "単語の転写：{value}",
        "voice_feedback_word": "単語：{value}",
        "voice_feedback_transcription": "転写：{value}",
        "voice_feedback_other_word": "ブロック内の別の単語に似ています：{target} — {meaning}。",
        "voice_feedback_text_notice": "これは認識テキストの比較で、アクセントの音響評価ではありません。",
        "voice_feedback_credits": "AIクレジット：{credits}",
    },
    "zh": {
        "privacy_voice_status": "可在启动 /voice 时授权。",
        "privacy_consent_revoked": "已撤回授权。",
        "privacy_voice_revoked": "已撤回语音处理授权，并停止当前语音会话。修改记录数：{changed}。",
        "privacy_ai_status": "可在启动 /ai 时授权。",
        "privacy_ai_revoked": "已撤回 AI 处理授权。在再次授权前不会发送新的 AI 请求。修改记录数：{changed}。",
        "privacy_delete_prompt": "删除学习档案、进度、分析和 AI 历史记录？这些数据无法恢复。",
        "privacy_confirm_delete": "确认删除",
        "privacy_cancel": "取消",
        "privacy_deletion_cancelled": "已取消删除。",
        "privacy_data_unchanged": "学习数据未更改。",
        "privacy_unknown_action": "未知操作。",
        "privacy_data_deleted": "数据已删除。",
        "privacy_deletion_complete": "学习数据已删除，仅保留必要的付款和审计记录。操作编号：{reference}。",
        "ai_processing_consent": "AI 处理授权\n\n{notice}\n\n版本：{version}",
        "ai_consent_accept": "同意并继续",
        "ai_consent_cancel": "取消",
        "ai_usage_stats": "AI 使用情况\n\n可用点数：{available}\n已预留：{reserved}\n已使用：{spent}\n请求：成功 {completed}，退回 {failed}",
        "mirror_feedback_helpful": "有帮助",
        "mirror_feedback_unhelpful": "没有帮助",
        "mirror_feedback_unavailable": "暂时无法评分。",
        "mirror_feedback_thanks": "谢谢",
        "mirror_feedback_recorded": "评分已记录",
        "mirror_response_choose": "请选择回复格式：/response text、/response voice 或 /response both。",
        "mirror_response_saved": "Mirror 回复格式：{mode}。",
        "mirror_feedback_question": "这个回复有帮助吗？",
        "voice_entry_pronunciation": "🎤 朗读 10 个单词",
        "voice_entry_phrases": "💬 本组短语",
        "voice_entry_translation": "🌐 翻译语音消息",
        "voice_entry_disabled": "语音功能目前已关闭。",
        "voice_entry": "🎙 语音消息\n\n发送包含问题的语音消息，AI 会识别语音并结合上下文回答。\n\n若要练习发音，请在下方选择练习。每条语音对应一个单词，检查后会显示下一个。",
        "voice_consent": "语音处理授权\n\n{notice}\n\n版本：{version}",
        "voice_consent_accept_continue": "同意并继续",
        "voice_consent_accept_start": "同意并开始",
        "voice_consent_cancel": "取消",
        "voice_feedback_exact": "✅ 正确，进入下一个单词。",
        "voice_feedback_close": "🟡 很接近，请核对上方拼写后继续。",
        "voice_feedback_retry": "🔁 请再试一次这个单词。",
        "voice_feedback_recognized": "识别结果：{value}",
        "voice_feedback_meaning": "含义：{value}",
        "voice_feedback_phrase": "短语：{value}",
        "voice_feedback_focus": "关键词：{value}",
        "voice_feedback_focus_transcription": "单词转写：{value}",
        "voice_feedback_word": "单词：{value}",
        "voice_feedback_transcription": "转写：{value}",
        "voice_feedback_other_word": "听起来像本组中的另一个单词：{target} — {meaning}。",
        "voice_feedback_text_notice": "这里比较的是识别文本，不是对口音的声学评估。",
        "voice_feedback_credits": "AI 点数：{credits}",
    },
    "ar": {
        "privacy_voice_status": "يمكن منح الموافقة عند بدء /voice.",
        "privacy_consent_revoked": "تم سحب الموافقة.",
        "privacy_voice_revoked": "تم سحب موافقة معالجة الصوت وإيقاف الجلسة الصوتية النشطة. السجلات المعدلة: {changed}.",
        "privacy_ai_status": "يمكن منح الموافقة عند بدء /ai.",
        "privacy_ai_revoked": "تم سحب موافقة معالجة AI. لن تُرسل طلبات AI جديدة حتى الموافقة مجدداً. السجلات المعدلة: {changed}.",
        "privacy_delete_prompt": "هل تريد حذف ملف التعلم والتقدم والتحليلات وسجل AI؟ لا يمكن استعادة هذه البيانات.",
        "privacy_confirm_delete": "تأكيد الحذف",
        "privacy_cancel": "إلغاء",
        "privacy_deletion_cancelled": "تم إلغاء الحذف.",
        "privacy_data_unchanged": "لم تتغير بيانات التعلم.",
        "privacy_unknown_action": "إجراء غير معروف.",
        "privacy_data_deleted": "تم حذف البيانات.",
        "privacy_deletion_complete": "تم حذف بيانات التعلم. بقي فقط سجل الدفع والتدقيق الإلزامي. مرجع العملية: {reference}.",
        "ai_processing_consent": "الموافقة على معالجة AI\n\n{notice}\n\nالإصدار: {version}",
        "ai_consent_accept": "موافقة ومتابعة",
        "ai_consent_cancel": "إلغاء",
        "ai_usage_stats": "استخدام AI\n\nالأرصدة المتاحة: {available}\nالمحجوزة: {reserved}\nالمستخدمة: {spent}\nالطلبات: {completed} ناجحة، {failed} مستردة",
        "mirror_feedback_helpful": "مفيد",
        "mirror_feedback_unhelpful": "غير مفيد",
        "mirror_feedback_unavailable": "التقييم غير متاح.",
        "mirror_feedback_thanks": "شكراً",
        "mirror_feedback_recorded": "تم تسجيل التقييم مسبقاً",
        "mirror_response_choose": "اختر صيغة الرد: /response text أو /response voice أو /response both.",
        "mirror_response_saved": "صيغة ردود Mirror: {mode}.",
        "mirror_feedback_question": "هل كان هذا الرد مفيداً؟",
        "voice_entry_pronunciation": "🎤 نطق 10 كلمات",
        "voice_entry_phrases": "💬 عبارات المجموعة",
        "voice_entry_translation": "🌐 ترجمة رسالة صوتية",
        "voice_entry_disabled": "الميزات الصوتية معطلة حالياً.",
        "voice_entry": "🎙 الرسائل الصوتية\n\nأرسل سؤالاً صوتياً وسيتعرّف AI على الكلام ويجيب وفق السياق.\n\nلتدريب النطق اختر تمريناً أدناه. كل رسالة صوتية لكلمة واحدة، وبعد الفحص تظهر الكلمة التالية.",
        "voice_consent": "الموافقة على معالجة الصوت\n\n{notice}\n\nالإصدار: {version}",
        "voice_consent_accept_continue": "موافقة ومتابعة",
        "voice_consent_accept_start": "موافقة وبدء",
        "voice_consent_cancel": "إلغاء",
        "voice_feedback_exact": "✅ صحيح. ننتقل إلى الكلمة التالية.",
        "voice_feedback_close": "🟡 قريب. راجع الكتابة أعلاه ثم نتابع.",
        "voice_feedback_retry": "🔁 جرّب الكلمة نفسها مرة أخرى.",
        "voice_feedback_recognized": "تم التعرّف: {value}",
        "voice_feedback_meaning": "المعنى: {value}",
        "voice_feedback_phrase": "العبارة: {value}",
        "voice_feedback_focus": "الكلمة الأساسية: {value}",
        "voice_feedback_focus_transcription": "نسخ الكلمة: {value}",
        "voice_feedback_word": "الكلمة: {value}",
        "voice_feedback_transcription": "النسخ: {value}",
        "voice_feedback_other_word": "يبدو ككلمة أخرى في المجموعة: {target} — {meaning}.",
        "voice_feedback_text_notice": "هذه مقارنة للنص المتعرّف عليه وليست تقييماً صوتياً للهجة.",
        "voice_feedback_credits": "أرصدة AI: {credits}",
    },
}

for _locale, _messages in _USER_SURFACE_CYCLE2_COPY.items():
    _CATALOG[_locale].update(_messages)

_USER_SURFACE_CYCLE3_COPY = {
    "en": {
        "bot_help": "MY DICTIONARY\n\n/start — today's lesson and main menu\n/learn — choose a language and topic\n/stats — view progress\n/lang — change language\n/ai — AI tutor, credits and voice\n/privacy — data and privacy\n/help — help\n\nIn a lesson, tap “Show meaning”, then rate the word. The bot will save the answer and schedule the next review.",
        "billing_terms_accept": "I accept and want to start immediately",
        "billing_terms_instruction": "By tapping the button, you confirm that you have read and accept the terms.",
        "billing_terms_disabled": "Purchasing AI credits is currently disabled.",
        "billing_seller": "Seller: {value}",
        "billing_address": "Address: {value}",
        "billing_email": "Email: {value}",
        "billing_phone": "Phone: {value}",
        "billing_support_contact": "Payment support: {value}",
        "billing_seller_missing": "Seller details have not been published yet.",
        "billing_terms_consent": "I accept the terms and request that the digital service begin immediately after payment. I understand that the right of withdrawal may be lost after the service has been fully provided where allowed by law.",
        "billing_terms_text": "AI credit purchase terms\n\n{terms}\n\n{seller}\n\nVersion: {version}\n{consent}\n\n{instruction}",
        "billing_products_empty": "AI credit packs have not been published yet.",
        "billing_products_test": "Telegram Stars test environment. Choose a test AI credit pack:",
        "billing_products_choose": "Choose an AI credit pack:",
        "billing_support_text": "Payment support\n\nContact: {contact}\nSeller: {seller}\nEmail: {email}\nPhone: {phone}",
        "billing_payments_disabled": "Payments are currently disabled.",
        "billing_subscriptions_empty": "There are no active Stars subscriptions.",
        "legacy_streak_bonus": "+{bonus} streak bonus",
        "legacy_level": "[Level {level} · {title}]",
        "legacy_language_picker": "Current pack: *{pack}*\n\nChoose a language:",
        "legacy_quiz_prompt": "Choose the correct translation:",
        "legacy_correct": "✅ Correct!",
        "legacy_wrong": "❌ Wrong!",
        "legacy_next": "Next ➡️",
        "legacy_type_prompt": "Type the translation:",
        "legacy_your_answer": "Your answer: _{answer}_",
        "legacy_flash_known": "✅ Great!",
        "legacy_flash_retry": "🔁 We will review it again!",
        "legacy_smart_prompt": "Choose the translation:",
        "legacy_poll_translation": "translation?",
        "pilot_access_approved_notification": "Your free MY DICTIONARY pilot access is open. Send /start, choose a language and begin your first block.",
    },
    "fr": {
        "bot_help": "MY DICTIONARY\n\n/start — leçon du jour et menu principal\n/learn — choisir une langue et un thème\n/stats — voir la progression\n/lang — changer de langue\n/ai — tuteur IA, crédits et voix\n/privacy — données et confidentialité\n/help — aide\n\nPendant une leçon, appuyez sur « Afficher le sens », puis évaluez le mot. Le bot enregistrera la réponse et planifiera la prochaine révision.",
        "billing_terms_accept": "J’accepte et je souhaite commencer immédiatement",
        "billing_terms_instruction": "En appuyant sur le bouton, vous confirmez avoir lu et accepté les conditions.",
        "billing_terms_disabled": "L’achat de crédits IA est désactivé pour le moment.",
        "billing_seller": "Vendeur : {value}",
        "billing_address": "Adresse : {value}",
        "billing_email": "E-mail : {value}",
        "billing_phone": "Téléphone : {value}",
        "billing_support_contact": "Assistance paiements : {value}",
        "billing_seller_missing": "Les coordonnées du vendeur ne sont pas encore publiées.",
        "billing_terms_consent": "J’accepte les conditions et demande que le service numérique commence immédiatement après le paiement. Je comprends que le droit de rétractation peut être perdu après la fourniture complète du service dans les cas prévus par la loi.",
        "billing_terms_text": "Conditions d’achat des crédits IA\n\n{terms}\n\n{seller}\n\nVersion : {version}\n{consent}\n\n{instruction}",
        "billing_products_empty": "Aucun pack de crédits IA n’est encore publié.",
        "billing_products_test": "Environnement de test Telegram Stars. Choisissez un pack test de crédits IA :",
        "billing_products_choose": "Choisissez un pack de crédits IA :",
        "billing_support_text": "Assistance pour les paiements\n\nContact : {contact}\nVendeur : {seller}\nE-mail : {email}\nTéléphone : {phone}",
        "billing_payments_disabled": "Les paiements sont désactivés pour le moment.",
        "billing_subscriptions_empty": "Aucun abonnement Stars actif.",
        "legacy_streak_bonus": "+{bonus} pour la série",
        "legacy_level": "[Niveau {level} · {title}]",
        "legacy_language_picker": "Pack actuel : *{pack}*\n\nChoisissez une langue :",
        "legacy_quiz_prompt": "Choisissez la bonne traduction :",
        "legacy_correct": "✅ Correct !",
        "legacy_wrong": "❌ Erreur !",
        "legacy_next": "Suivant ➡️",
        "legacy_type_prompt": "Écrivez la traduction :",
        "legacy_your_answer": "Votre réponse : _{answer}_",
        "legacy_flash_known": "✅ Excellent !",
        "legacy_flash_retry": "🔁 Nous le reverrons !",
        "legacy_smart_prompt": "Choisissez la traduction :",
        "legacy_poll_translation": "traduction ?",
        "pilot_access_approved_notification": "Votre accès au pilote gratuit MY DICTIONARY est ouvert. Envoyez /start, choisissez une langue et commencez votre premier bloc.",
    },
    "ru": {
        "bot_help": "MY DICTIONARY\n\n/start — урок на сегодня и главное меню\n/learn — выбрать язык и тему\n/stats — посмотреть прогресс\n/lang — сменить язык\n/ai — AI-репетитор, кредиты и голос\n/privacy — данные и приватность\n/help — помощь\n\nВ уроке нажми «Показать значение», затем оцени слово. Бот сохранит ответ и назначит следующее повторение.",
        "billing_terms_accept": "Принимаю и начать сразу",
        "billing_terms_instruction": "Нажимая кнопку, ты подтверждаешь, что прочитал и принимаешь условия.",
        "billing_terms_disabled": "Покупка AI-кредитов сейчас выключена.",
        "billing_seller": "Продавец: {value}",
        "billing_address": "Адрес: {value}",
        "billing_email": "Email: {value}",
        "billing_phone": "Телефон: {value}",
        "billing_support_contact": "Поддержка платежей: {value}",
        "billing_seller_missing": "Реквизиты продавца ещё не опубликованы.",
        "billing_terms_consent": "Я принимаю условия и прошу начать оказание цифровой услуги сразу после оплаты. Я понимаю, что после полного предоставления услуги право на отказ может быть утрачено в предусмотренных законом случаях.",
        "billing_terms_text": "Условия покупки AI-кредитов\n\n{terms}\n\n{seller}\n\nВерсия: {version}\n{consent}\n\n{instruction}",
        "billing_products_empty": "Пакеты AI-кредитов пока не опубликованы.",
        "billing_products_test": "Тестовая среда Telegram Stars. Выбери тестовый пакет AI-кредитов:",
        "billing_products_choose": "Выбери пакет AI-кредитов:",
        "billing_support_text": "Поддержка по платежам\n\nКонтакт: {contact}\nПродавец: {seller}\nEmail: {email}\nТелефон: {phone}",
        "billing_payments_disabled": "Платежи пока выключены.",
        "billing_subscriptions_empty": "Активных Stars-подписок пока нет.",
        "legacy_streak_bonus": "+{bonus} за серию",
        "legacy_level": "[Уровень {level} · {title}]",
        "legacy_language_picker": "Текущий набор: *{pack}*\n\nВыбери язык:",
        "legacy_quiz_prompt": "Выбери правильный перевод:",
        "legacy_correct": "✅ Правильно!",
        "legacy_wrong": "❌ Ошибка!",
        "legacy_next": "Дальше ➡️",
        "legacy_type_prompt": "Напиши перевод по-русски:",
        "legacy_your_answer": "Твой ответ: _{answer}_",
        "legacy_flash_known": "✅ Отлично!",
        "legacy_flash_retry": "🔁 Ещё повторим!",
        "legacy_smart_prompt": "Выбери перевод:",
        "legacy_poll_translation": "перевод?",
        "pilot_access_approved_notification": "Доступ к бесплатному пилоту MY DICTIONARY открыт. Отправь /start, выбери язык и начни первый блок.",
    },
    "de": {
        "bot_help": "MY DICTIONARY\n\n/start — heutige Lektion und Hauptmenü\n/learn — Sprache und Thema wählen\n/stats — Fortschritt anzeigen\n/lang — Sprache wechseln\n/ai — KI-Tutor, Credits und Sprache\n/privacy — Daten und Datenschutz\n/help — Hilfe\n\nTippe in einer Lektion auf „Bedeutung anzeigen“ und bewerte danach das Wort. Der Bot speichert die Antwort und plant die nächste Wiederholung.",
        "billing_terms_accept": "Ich akzeptiere und möchte sofort beginnen",
        "billing_terms_instruction": "Mit der Schaltfläche bestätigst du, dass du die Bedingungen gelesen hast und akzeptierst.",
        "billing_terms_disabled": "Der Kauf von KI-Credits ist derzeit deaktiviert.",
        "billing_seller": "Verkäufer: {value}",
        "billing_address": "Adresse: {value}",
        "billing_email": "E-Mail: {value}",
        "billing_phone": "Telefon: {value}",
        "billing_support_contact": "Zahlungssupport: {value}",
        "billing_seller_missing": "Die Verkäuferangaben sind noch nicht veröffentlicht.",
        "billing_terms_consent": "Ich akzeptiere die Bedingungen und bitte darum, die digitale Dienstleistung direkt nach der Zahlung zu beginnen. Mir ist bewusst, dass das Widerrufsrecht nach vollständiger Erbringung im gesetzlich zulässigen Rahmen entfallen kann.",
        "billing_terms_text": "Bedingungen für den Kauf von KI-Credits\n\n{terms}\n\n{seller}\n\nVersion: {version}\n{consent}\n\n{instruction}",
        "billing_products_empty": "Es wurden noch keine KI-Credit-Pakete veröffentlicht.",
        "billing_products_test": "Telegram-Stars-Testumgebung. Wähle ein Testpaket:",
        "billing_products_choose": "Wähle ein KI-Credit-Paket:",
        "billing_support_text": "Zahlungssupport\n\nKontakt: {contact}\nVerkäufer: {seller}\nE-Mail: {email}\nTelefon: {phone}",
        "billing_payments_disabled": "Zahlungen sind derzeit deaktiviert.",
        "billing_subscriptions_empty": "Keine aktiven Stars-Abonnements.",
        "legacy_streak_bonus": "+{bonus} Serienbonus",
        "legacy_level": "[Stufe {level} · {title}]",
        "legacy_language_picker": "Aktuelles Paket: *{pack}*\n\nWähle eine Sprache:",
        "legacy_quiz_prompt": "Wähle die richtige Übersetzung:",
        "legacy_correct": "✅ Richtig!",
        "legacy_wrong": "❌ Falsch!",
        "legacy_next": "Weiter ➡️",
        "legacy_type_prompt": "Schreibe die Übersetzung:",
        "legacy_your_answer": "Deine Antwort: _{answer}_",
        "legacy_flash_known": "✅ Sehr gut!",
        "legacy_flash_retry": "🔁 Das wiederholen wir!",
        "legacy_smart_prompt": "Wähle die Übersetzung:",
        "legacy_poll_translation": "Übersetzung?",
        "pilot_access_approved_notification": "Dein Zugang zum kostenlosen MY DICTIONARY-Pilotprojekt ist freigeschaltet. Sende /start, wähle eine Sprache und beginne deinen ersten Block.",
    },
    "es": {
        "bot_help": "MY DICTIONARY\n\n/start — lección de hoy y menú principal\n/learn — elegir idioma y tema\n/stats — ver el progreso\n/lang — cambiar de idioma\n/ai — tutor de IA, créditos y voz\n/privacy — datos y privacidad\n/help — ayuda\n\nEn una lección, pulsa «Mostrar significado» y valora la palabra. El bot guardará la respuesta y programará el próximo repaso.",
        "billing_terms_accept": "Acepto y quiero empezar inmediatamente",
        "billing_terms_instruction": "Al pulsar el botón, confirmas que has leído y aceptas las condiciones.",
        "billing_terms_disabled": "La compra de créditos de IA está desactivada ahora.",
        "billing_seller": "Vendedor: {value}",
        "billing_address": "Dirección: {value}",
        "billing_email": "Correo: {value}",
        "billing_phone": "Teléfono: {value}",
        "billing_support_contact": "Soporte de pagos: {value}",
        "billing_seller_missing": "Los datos del vendedor aún no se han publicado.",
        "billing_terms_consent": "Acepto las condiciones y solicito que el servicio digital comience inmediatamente después del pago. Entiendo que el derecho de desistimiento puede perderse tras la prestación completa cuando lo permita la ley.",
        "billing_terms_text": "Condiciones de compra de créditos de IA\n\n{terms}\n\n{seller}\n\nVersión: {version}\n{consent}\n\n{instruction}",
        "billing_products_empty": "Aún no se han publicado paquetes de créditos de IA.",
        "billing_products_test": "Entorno de prueba de Telegram Stars. Elige un paquete de prueba:",
        "billing_products_choose": "Elige un paquete de créditos de IA:",
        "billing_support_text": "Soporte de pagos\n\nContacto: {contact}\nVendedor: {seller}\nCorreo: {email}\nTeléfono: {phone}",
        "billing_payments_disabled": "Los pagos están desactivados ahora.",
        "billing_subscriptions_empty": "No hay suscripciones Stars activas.",
        "legacy_streak_bonus": "+{bonus} por la racha",
        "legacy_level": "[Nivel {level} · {title}]",
        "legacy_language_picker": "Paquete actual: *{pack}*\n\nElige un idioma:",
        "legacy_quiz_prompt": "Elige la traducción correcta:",
        "legacy_correct": "✅ ¡Correcto!",
        "legacy_wrong": "❌ ¡Error!",
        "legacy_next": "Siguiente ➡️",
        "legacy_type_prompt": "Escribe la traducción:",
        "legacy_your_answer": "Tu respuesta: _{answer}_",
        "legacy_flash_known": "✅ ¡Muy bien!",
        "legacy_flash_retry": "🔁 ¡La repasaremos!",
        "legacy_smart_prompt": "Elige la traducción:",
        "legacy_poll_translation": "¿traducción?",
        "pilot_access_approved_notification": "Tu acceso al piloto gratuito de MY DICTIONARY está abierto. Envía /start, elige un idioma y comienza tu primer bloque.",
    },
    "ja": {
        "bot_help": "MY DICTIONARY\n\n/start — 今日のレッスンとメインメニュー\n/learn — 言語とテーマを選択\n/stats — 進捗を表示\n/lang — 言語を変更\n/ai — AIチューター、クレジット、音声\n/privacy — データとプライバシー\n/help — ヘルプ\n\nレッスンでは「意味を表示」を押してから単語を評価してください。回答が保存され、次の復習が設定されます。",
        "billing_terms_accept": "同意してすぐに開始する",
        "billing_terms_instruction": "ボタンを押すと、条件を読み同意したことを確認します。",
        "billing_terms_disabled": "AIクレジットの購入は現在無効です。",
        "billing_seller": "販売者：{value}",
        "billing_address": "住所：{value}",
        "billing_email": "メール：{value}",
        "billing_phone": "電話：{value}",
        "billing_support_contact": "支払いサポート：{value}",
        "billing_seller_missing": "販売者情報はまだ公開されていません。",
        "billing_terms_consent": "条件に同意し、支払い直後にデジタルサービスを開始するよう依頼します。法令で認められる場合、サービス完了後に撤回権を失うことを理解しています。",
        "billing_terms_text": "AIクレジット購入条件\n\n{terms}\n\n{seller}\n\nバージョン：{version}\n{consent}\n\n{instruction}",
        "billing_products_empty": "AIクレジットパックはまだ公開されていません。",
        "billing_products_test": "Telegram Starsテスト環境です。テストパックを選んでください：",
        "billing_products_choose": "AIクレジットパックを選んでください：",
        "billing_support_text": "支払いサポート\n\n連絡先：{contact}\n販売者：{seller}\nメール：{email}\n電話：{phone}",
        "billing_payments_disabled": "支払いは現在無効です。",
        "billing_subscriptions_empty": "有効なStarsサブスクリプションはありません。",
        "legacy_streak_bonus": "+{bonus} 連続ボーナス",
        "legacy_level": "[レベル {level} · {title}]",
        "legacy_language_picker": "現在のパック：*{pack}*\n\n言語を選んでください：",
        "legacy_quiz_prompt": "正しい訳を選んでください：",
        "legacy_correct": "✅ 正解！",
        "legacy_wrong": "❌ 不正解！",
        "legacy_next": "次へ ➡️",
        "legacy_type_prompt": "訳を入力してください：",
        "legacy_your_answer": "あなたの回答：_{answer}_",
        "legacy_flash_known": "✅ よくできました！",
        "legacy_flash_retry": "🔁 また復習しましょう！",
        "legacy_smart_prompt": "訳を選んでください：",
        "legacy_poll_translation": "訳は？",
        "pilot_access_approved_notification": "MY DICTIONARYの無料パイロットへのアクセスが有効になりました。/start を送り、言語を選んで最初のブロックを始めてください。",
    },
    "zh": {
        "bot_help": "MY DICTIONARY\n\n/start — 今日课程和主菜单\n/learn — 选择语言和主题\n/stats — 查看进度\n/lang — 更改语言\n/ai — AI 导师、点数和语音\n/privacy — 数据与隐私\n/help — 帮助\n\n在课程中点击“显示释义”，然后评价这个单词。机器人会保存答案并安排下一次复习。",
        "billing_terms_accept": "我同意并希望立即开始",
        "billing_terms_instruction": "点击按钮即表示你已阅读并接受相关条款。",
        "billing_terms_disabled": "AI 点数购买目前已关闭。",
        "billing_seller": "销售方：{value}",
        "billing_address": "地址：{value}",
        "billing_email": "邮箱：{value}",
        "billing_phone": "电话：{value}",
        "billing_support_contact": "付款支持：{value}",
        "billing_seller_missing": "销售方信息尚未公布。",
        "billing_terms_consent": "我接受条款，并请求在付款后立即开始提供数字服务。我理解，在法律允许的情况下，服务全部提供后可能失去撤回权。",
        "billing_terms_text": "AI 点数购买条款\n\n{terms}\n\n{seller}\n\n版本：{version}\n{consent}\n\n{instruction}",
        "billing_products_empty": "AI 点数包尚未发布。",
        "billing_products_test": "Telegram Stars 测试环境。请选择测试点数包：",
        "billing_products_choose": "请选择 AI 点数包：",
        "billing_support_text": "付款支持\n\n联系方式：{contact}\n销售方：{seller}\n邮箱：{email}\n电话：{phone}",
        "billing_payments_disabled": "付款目前已关闭。",
        "billing_subscriptions_empty": "没有有效的 Stars 订阅。",
        "legacy_streak_bonus": "+{bonus} 连续学习奖励",
        "legacy_level": "[等级 {level} · {title}]",
        "legacy_language_picker": "当前词包：*{pack}*\n\n请选择语言：",
        "legacy_quiz_prompt": "请选择正确翻译：",
        "legacy_correct": "✅ 正确！",
        "legacy_wrong": "❌ 错误！",
        "legacy_next": "下一个 ➡️",
        "legacy_type_prompt": "请输入翻译：",
        "legacy_your_answer": "你的回答：_{answer}_",
        "legacy_flash_known": "✅ 很好！",
        "legacy_flash_retry": "🔁 我们会再次复习！",
        "legacy_smart_prompt": "请选择翻译：",
        "legacy_poll_translation": "翻译？",
        "pilot_access_approved_notification": "你的 MY DICTIONARY 免费试用权限已开通。发送 /start，选择语言并开始第一组学习。",
    },
    "ar": {
        "bot_help": "MY DICTIONARY\n\n/start — درس اليوم والقائمة الرئيسية\n/learn — اختيار اللغة والموضوع\n/stats — عرض التقدم\n/lang — تغيير اللغة\n/ai — مدرّس AI والأرصدة والصوت\n/privacy — البيانات والخصوصية\n/help — المساعدة\n\nفي الدرس اضغط «إظهار المعنى» ثم قيّم الكلمة. سيحفظ البوت الإجابة ويحدد المراجعة التالية.",
        "billing_terms_accept": "أوافق وأرغب في البدء فوراً",
        "billing_terms_instruction": "بالضغط على الزر تؤكد أنك قرأت الشروط وتوافق عليها.",
        "billing_terms_disabled": "شراء أرصدة AI معطّل حالياً.",
        "billing_seller": "البائع: {value}",
        "billing_address": "العنوان: {value}",
        "billing_email": "البريد: {value}",
        "billing_phone": "الهاتف: {value}",
        "billing_support_contact": "دعم الدفع: {value}",
        "billing_seller_missing": "لم تُنشر بيانات البائع بعد.",
        "billing_terms_consent": "أوافق على الشروط وأطلب بدء الخدمة الرقمية مباشرة بعد الدفع. أفهم أن حق الانسحاب قد يسقط بعد تقديم الخدمة بالكامل حيث يسمح القانون.",
        "billing_terms_text": "شروط شراء أرصدة AI\n\n{terms}\n\n{seller}\n\nالإصدار: {version}\n{consent}\n\n{instruction}",
        "billing_products_empty": "لم تُنشر باقات أرصدة AI بعد.",
        "billing_products_test": "بيئة اختبار Telegram Stars. اختر باقة اختبار:",
        "billing_products_choose": "اختر باقة أرصدة AI:",
        "billing_support_text": "دعم الدفع\n\nالتواصل: {contact}\nالبائع: {seller}\nالبريد: {email}\nالهاتف: {phone}",
        "billing_payments_disabled": "المدفوعات معطّلة حالياً.",
        "billing_subscriptions_empty": "لا توجد اشتراكات Stars نشطة.",
        "legacy_streak_bonus": "+{bonus} مكافأة السلسلة",
        "legacy_level": "[المستوى {level} · {title}]",
        "legacy_language_picker": "الباقة الحالية: *{pack}*\n\nاختر لغة:",
        "legacy_quiz_prompt": "اختر الترجمة الصحيحة:",
        "legacy_correct": "✅ صحيح!",
        "legacy_wrong": "❌ خطأ!",
        "legacy_next": "التالي ➡️",
        "legacy_type_prompt": "اكتب الترجمة:",
        "legacy_your_answer": "إجابتك: _{answer}_",
        "legacy_flash_known": "✅ ممتاز!",
        "legacy_flash_retry": "🔁 سنراجعها مرة أخرى!",
        "legacy_smart_prompt": "اختر الترجمة:",
        "legacy_poll_translation": "الترجمة؟",
        "pilot_access_approved_notification": "تم فتح وصولك إلى اختبار MY DICTIONARY المجاني. أرسل /start واختر لغة وابدأ مجموعتك الأولى.",
    },
}

for _locale, _messages in _USER_SURFACE_CYCLE3_COPY.items():
    _CATALOG[_locale].update(_messages)

_USER_SURFACE_CYCLE4_EN = {
    "start_about_text": (
        "How learning works\n\n"
        "1. Tap “Today's lesson”.\n"
        "2. Recall the meaning and reveal the card.\n"
        "3. Mark “I know” or “I don't know”.\n"
        "4. The bot saves the answer and schedules the next review."
    ),
    "start_about_button": "▶️ Start lesson",
    "settings_stale": "This setting has expired.",
    "settings_pace_saved": "Pace saved",
    "settings_style_saved": "Style: {style}",
    "settings_depth_saved": "Depth: {depth}",
    "settings_level_saved": "Level: {level}",
    "settings_unavailable": "This setting is unavailable.",
    "voice_practice_disabled": "Voice practice is currently disabled.",
    "voice_need_block": "Choose a topic and create a 10-word block with /learn first.",
    "voice_block_stale": "This block has expired. Choose a topic and create a new block with /learn.",
    "voice_practice_cancelled": "Voice practice cancelled.",
    "voice_request_stale": "This request has expired. Start /voice again.",
    "consent_saved": "Consent saved.",
    "voice_consent_resend": "Ready. Send the voice message again and I will recognize it and reply in context.",
    "voice_translation_disabled": "Voice translation is currently disabled.",
    "voice_translation_consent": "Consent for recognition and translation\n\n{notice}\n\nVersion: {version}",
    "consent_accept": "Accept",
    "consent_cancel": "Cancel",
    "voice_translation_instruction": "Send a voice message. Russian speech will be translated into the active language, and other speech into Russian.",
    "voice_translation_cancelled": "Translation cancelled.",
    "voice_translation_send": "Send a voice message for recognition and translation.",
    "voice_stop_active": "Voice session stopped. Transcript: /voice_transcript.",
    "voice_stop_inactive": "There is no active voice session.",
    "voice_sessions_empty": "There are no voice sessions yet.",
    "voice_transcript_header": "Voice session transcript · {pack}",
    "voice_transcript_status": "Status: {status}",
    "voice_transcript_missing_word": "word from the block",
    "voice_transcript_recognized": "   Recognized: {value}",
    "voice_transcript_result": "   Result: {value}",
    "voice_transcript_empty": "No saved turns remain, or their retention period has expired.",
    "voice_translation_source_ru": "🇷🇺 Source phrase: {value}",
    "voice_translation_translation": "🇷🇺 Translation: {value}",
    "voice_translation_missing": "🇷🇺 No translation was returned",
    "voice_translation_source": "{flag} Source phrase: {value}",
    "voice_translation_latin": "Latin script: {value}",
    "voice_translation_detected": "Detected language: {value}.",
    "voice_translation_unknown": "unknown",
    "voice_block_complete": "✅ Voice block complete. All 10 words were checked.",
    "voice_access_unavailable": "Voice features are currently unavailable.",
    "voice_invalid": "Voice message rejected: duration or size is outside the allowed limits.",
    "ai_credit_recovery_error": "Could not confirm the AI credit refund. Check /ai_stats.",
    "voice_safe_error": "Could not process the voice message safely. No AI credit was charged.",
    "voice_practice_unavailable": "Voice practice is temporarily unavailable.",
    "voice_practice_unavailable_no_charge": "Voice practice is temporarily unavailable. No AI credit was charged.",
    "voice_translation_consent_required": "Current consent for recognition and translation is required. Start /voice.",
    "ai_credit_state_error": "Could not confirm the AI credit state. Check /ai_stats.",
    "voice_translation_safe_error": "Could not process the voice message safely. The text was not saved.",
    "voice_ai_disabled": "Voice AI is currently disabled.",
    "ai_disabled": "The AI tutor is currently disabled.",
    "ai_unavailable": "The AI tutor is temporarily unavailable.",
    "voice_transcription_failed": "Could not recognize the voice message. No AI credit was charged.",
    "voice_ai_unavailable_no_charge": "Voice AI is temporarily unavailable. No AI credit was charged.",
    "ai_need_block": "Choose a topic and create a block with /learn first.",
    "ai_safe_error": "Could not prepare a safe answer. No AI credit was charged.",
    "ai_unavailable_no_charge": "The AI tutor is temporarily unavailable. No AI credit was charged.",
    "mirror_voice_unavailable": "A voice response is currently unavailable.",
    "mirror_question_unrecognized": "Could not recognize the question.",
    "ai_request_cancelled": "AI request cancelled.",
    "ai_request_stale": "This request has expired. Start /ai again.",
    "ai_voice_resend": "Ready. Send the voice message again and AI will answer from its content.",
    "ai_default_question": "Explain the main connections between the words in this block.",
    "billing_disabled_callback": "Buying AI credits is currently disabled.",
    "billing_terms_accepted": "Terms accepted.",
    "billing_product_unavailable": "This package is currently unavailable.",
    "billing_credit_label": "{credits} AI credits",
    "billing_precheckout_error": "Could not confirm the price. Create a new invoice with /buy.",
    "billing_payment_review": "Payment received, but the credit grant needs review. Send /paysupport.",
    "billing_payment_success": "Payment confirmed. {credits} AI credits added.\nAvailable: {available}.",
    "billing_test_payment_success": "Test payment confirmed. {credits} AI credits added.\nAvailable: {available}.",
    "billing_payment_already": "This payment has already been recorded. Available: {available}.",
    "billing_subscription_restore": "Resume",
    "billing_subscription_cancel": "Disable auto-renewal",
    "billing_subscription_text": "Stars subscription\nStatus: {status}\nPaid through: {period_end}",
    "billing_subscription_failed": "Could not update the subscription.",
    "billing_subscription_updated": "Subscription setting updated.",
    "billing_autorenew_disabled": "Auto-renewal is disabled until the end of the paid period.",
    "billing_autorenew_enabled": "Subscription auto-renewal is enabled again.",
    "legacy_pack_activated": "Pack *{pack}* activated ({count} words)",
    "learning_no_words": "This pack has no available words yet.",
    "topic_stale": "This topic selection has expired. Send /learn.",
    "topic_empty": "This topic has no words yet.",
}

_USER_SURFACE_CYCLE4_COPY = {
    "en": _USER_SURFACE_CYCLE4_EN,
    "fr": {
        **_USER_SURFACE_CYCLE4_EN,
        "start_about_text": (
            "Comment se déroule l’apprentissage\n\n"
            "1. Appuyez sur « Leçon du jour ».\n"
            "2. Rappelez-vous le sens puis affichez la carte.\n"
            "3. Indiquez « Je sais » ou « Je ne sais pas ».\n"
            "4. Le bot enregistre la réponse et programme la révision."
        ),
        "start_about_button": "▶️ Commencer la leçon",
        "settings_stale": "Ce réglage a expiré.",
        "settings_pace_saved": "Rythme enregistré",
        "settings_style_saved": "Style : {style}",
        "settings_depth_saved": "Profondeur : {depth}",
        "settings_level_saved": "Niveau : {level}",
        "settings_unavailable": "Ce réglage n’est pas disponible.",
        "voice_practice_disabled": "La pratique vocale est désactivée pour le moment.",
        "voice_need_block": "Choisissez d’abord un thème et créez un bloc de 10 mots avec /learn.",
        "voice_block_stale": "Ce bloc a expiré. Choisissez un thème et créez un nouveau bloc avec /learn.",
        "voice_practice_cancelled": "Pratique vocale annulée.",
        "voice_request_stale": "Cette demande a expiré. Relancez /voice.",
        "consent_saved": "Consentement enregistré.",
        "voice_consent_resend": "C’est prêt. Renvoyez le message vocal : je le reconnaîtrai et répondrai selon le contexte.",
        "voice_translation_disabled": "La traduction vocale est désactivée pour le moment.",
        "voice_translation_consent": "Consentement à la reconnaissance et à la traduction\n\n{notice}\n\nVersion : {version}",
        "consent_accept": "Accepter",
        "consent_cancel": "Annuler",
        "voice_translation_instruction": "Envoyez un message vocal. Le russe sera traduit vers la langue active, et les autres langues vers le russe.",
        "voice_translation_cancelled": "Traduction annulée.",
        "voice_translation_send": "Envoyez un message vocal à reconnaître et à traduire.",
        "voice_stop_active": "Session vocale arrêtée. Transcription : /voice_transcript.",
        "voice_stop_inactive": "Aucune session vocale active.",
        "voice_sessions_empty": "Aucune session vocale pour le moment.",
        "voice_transcript_header": "Transcription de la session vocale · {pack}",
        "voice_transcript_status": "Statut : {status}",
        "voice_transcript_missing_word": "mot du bloc",
        "voice_transcript_recognized": "   Reconnu : {value}",
        "voice_transcript_result": "   Résultat : {value}",
        "voice_transcript_empty": "Aucune réplique enregistrée, ou leur durée de conservation a expiré.",
        "voice_translation_source_ru": "🇷🇺 Phrase source : {value}",
        "voice_translation_translation": "🇷🇺 Traduction : {value}",
        "voice_translation_missing": "🇷🇺 Aucune traduction reçue",
        "voice_translation_source": "{flag} Phrase source : {value}",
        "voice_translation_latin": "En alphabet latin : {value}",
        "voice_translation_detected": "Langue détectée : {value}.",
        "voice_translation_unknown": "inconnue",
        "voice_block_complete": "✅ Bloc vocal terminé. Les 10 mots ont été vérifiés.",
        "voice_access_unavailable": "Les fonctions vocales sont indisponibles pour le moment.",
        "voice_invalid": "Message vocal refusé : durée ou taille hors limites.",
        "ai_credit_recovery_error": "Impossible de confirmer le remboursement du crédit IA. Vérifiez /ai_stats.",
        "voice_safe_error": "Impossible de traiter le message vocal en toute sécurité. Aucun crédit IA n’a été débité.",
        "voice_practice_unavailable": "La pratique vocale est temporairement indisponible.",
        "voice_practice_unavailable_no_charge": "La pratique vocale est temporairement indisponible. Aucun crédit IA n’a été débité.",
        "voice_translation_consent_required": "Un consentement à jour pour la reconnaissance et la traduction est requis. Lancez /voice.",
        "ai_credit_state_error": "Impossible de confirmer l’état des crédits IA. Vérifiez /ai_stats.",
        "voice_translation_safe_error": "Impossible de traiter le message vocal en toute sécurité. Le texte n’a pas été enregistré.",
        "voice_ai_disabled": "L’IA vocale est désactivée pour le moment.",
        "ai_disabled": "Le tuteur IA est désactivé pour le moment.",
        "ai_unavailable": "Le tuteur IA est temporairement indisponible.",
        "voice_transcription_failed": "Impossible de reconnaître le message vocal. Aucun crédit IA n’a été débité.",
        "voice_ai_unavailable_no_charge": "L’IA vocale est temporairement indisponible. Aucun crédit IA n’a été débité.",
        "ai_need_block": "Choisissez d’abord un thème et créez un bloc avec /learn.",
        "ai_safe_error": "Impossible de préparer une réponse sûre. Aucun crédit IA n’a été débité.",
        "ai_unavailable_no_charge": "Le tuteur IA est temporairement indisponible. Aucun crédit IA n’a été débité.",
        "mirror_voice_unavailable": "La réponse vocale est indisponible pour le moment.",
        "mirror_question_unrecognized": "Impossible de reconnaître la question.",
        "ai_request_cancelled": "Demande IA annulée.",
        "ai_request_stale": "Cette demande a expiré. Relancez /ai.",
        "ai_voice_resend": "C’est prêt. Renvoyez le message vocal : l’IA répondra selon son contenu.",
        "ai_default_question": "Explique les liens principaux entre les mots de ce bloc.",
        "billing_disabled_callback": "L’achat de crédits IA est désactivé pour le moment.",
        "billing_terms_accepted": "Conditions acceptées.",
        "billing_product_unavailable": "Ce pack est actuellement indisponible.",
        "billing_credit_label": "{credits} crédits IA",
        "billing_precheckout_error": "Impossible de confirmer le prix. Créez une nouvelle facture avec /buy.",
        "billing_payment_review": "Paiement reçu, mais l’ajout des crédits doit être vérifié. Envoyez /paysupport.",
        "billing_payment_success": "Paiement confirmé. {credits} crédits IA ajoutés.\nDisponibles : {available}.",
        "billing_test_payment_success": "Paiement test confirmé. {credits} crédits IA ajoutés.\nDisponibles : {available}.",
        "billing_payment_already": "Ce paiement est déjà enregistré. Disponibles : {available}.",
        "billing_subscription_restore": "Réactiver",
        "billing_subscription_cancel": "Désactiver le renouvellement automatique",
        "billing_subscription_text": "Abonnement Stars\nStatut : {status}\nPayé jusqu’au : {period_end}",
        "billing_subscription_failed": "Impossible de modifier l’abonnement.",
        "billing_subscription_updated": "Paramètre d’abonnement mis à jour.",
        "billing_autorenew_disabled": "Le renouvellement automatique est désactivé jusqu’à la fin de la période payée.",
        "billing_autorenew_enabled": "Le renouvellement automatique de l’abonnement est réactivé.",
        "legacy_pack_activated": "Pack *{pack}* activé ({count} mots)",
        "learning_no_words": "Ce pack ne contient encore aucun mot disponible.",
        "topic_stale": "Cette sélection de thème a expiré. Envoyez /learn.",
        "topic_empty": "Ce thème ne contient encore aucun mot.",
    },
    "ru": {
        **_USER_SURFACE_CYCLE4_EN,
        "start_about_text": (
            "Как проходит обучение\n\n"
            "1. Нажми «Урок на сегодня».\n"
            "2. Вспомни значение слова и открой карточку.\n"
            "3. Отметь «Знаю» или «Не знаю».\n"
            "4. Бот сохранит ответ и сам назначит повторение."
        ),
        "start_about_button": "▶️ Начать урок",
        "settings_stale": "Настройка устарела.",
        "settings_pace_saved": "Ритм сохранён",
        "settings_style_saved": "Стиль: {style}",
        "settings_depth_saved": "Глубина: {depth}",
        "settings_level_saved": "Уровень: {level}",
        "settings_unavailable": "Настройка недоступна.",
        "voice_practice_disabled": "Голосовой тренажёр пока выключен.",
        "voice_need_block": "Сначала выбери тему и создай блок из 10 слов через /learn.",
        "voice_block_stale": "Блок устарел. Выбери тему и создай новый блок через /learn.",
        "voice_practice_cancelled": "Голосовая практика отменена.",
        "voice_request_stale": "Запрос устарел. Запусти /voice снова.",
        "consent_saved": "Согласие сохранено.",
        "voice_consent_resend": "Готово. Отправь голосовое ещё раз — я распознаю его и отвечу по контексту.",
        "voice_translation_disabled": "Перевод голосовых пока выключен.",
        "voice_translation_consent": "Согласие на распознавание и перевод\n\n{notice}\n\nВерсия: {version}",
        "consent_accept": "Согласен",
        "consent_cancel": "Отмена",
        "voice_translation_instruction": "Отправь голосовое. Русская речь будет переведена на активный язык, а речь на другом языке — на русский.",
        "voice_translation_cancelled": "Перевод отменён.",
        "voice_translation_send": "Отправь голосовое для распознавания и перевода.",
        "voice_stop_active": "Голосовая сессия остановлена. Транскрипт: /voice_transcript.",
        "voice_stop_inactive": "Активной голосовой сессии нет.",
        "voice_sessions_empty": "Голосовых сессий пока нет.",
        "voice_transcript_header": "Транскрипт голосовой сессии · {pack}",
        "voice_transcript_status": "Статус: {status}",
        "voice_transcript_missing_word": "слово из блока",
        "voice_transcript_recognized": "   Распознано: {value}",
        "voice_transcript_result": "   Результат: {value}",
        "voice_transcript_empty": "Сохранённых реплик нет или срок хранения истёк.",
        "voice_translation_source_ru": "🇷🇺 Исходная фраза: {value}",
        "voice_translation_translation": "🇷🇺 Перевод: {value}",
        "voice_translation_missing": "🇷🇺 Перевод не получен",
        "voice_translation_source": "{flag} Исходная фраза: {value}",
        "voice_translation_latin": "Латиницей: {value}",
        "voice_translation_detected": "Распознан язык: {value}.",
        "voice_translation_unknown": "не определён",
        "voice_block_complete": "✅ Голосовой блок завершён. Все 10 слов проверены.",
        "voice_access_unavailable": "Голосовые функции сейчас недоступны.",
        "voice_invalid": "Голосовое не принято: длительность или размер вне допустимого лимита.",
        "ai_credit_recovery_error": "Не удалось подтвердить возврат AI-кредита. Проверь /ai_stats.",
        "voice_safe_error": "Не удалось безопасно обработать голосовое. AI-кредит не списан.",
        "voice_practice_unavailable": "Голосовой тренажёр временно недоступен.",
        "voice_practice_unavailable_no_charge": "Голосовой тренажёр временно недоступен. AI-кредит не списан.",
        "voice_translation_consent_required": "Нужно актуальное согласие на распознавание и перевод. Запусти /voice.",
        "ai_credit_state_error": "Не удалось подтвердить состояние AI-кредитов. Проверь /ai_stats.",
        "voice_translation_safe_error": "Не удалось безопасно обработать голосовое. Текст не сохранён.",
        "voice_ai_disabled": "Голосовой AI пока выключен.",
        "ai_disabled": "AI-репетитор пока выключен.",
        "ai_unavailable": "AI-репетитор временно недоступен.",
        "voice_transcription_failed": "Не удалось распознать голосовое. AI-кредит не списан.",
        "voice_ai_unavailable_no_charge": "Голосовой AI временно недоступен. AI-кредит не списан.",
        "ai_need_block": "Сначала выбери тему и создай блок через /learn.",
        "ai_safe_error": "Не удалось подготовить безопасный ответ. AI-кредит не списан.",
        "ai_unavailable_no_charge": "AI-репетитор временно недоступен. AI-кредит не списан.",
        "mirror_voice_unavailable": "Голосовой ответ сейчас недоступен.",
        "mirror_question_unrecognized": "Не удалось распознать вопрос.",
        "ai_request_cancelled": "AI-запрос отменён.",
        "ai_request_stale": "Запрос устарел. Запусти /ai снова.",
        "ai_voice_resend": "Готово. Отправь голосовое ещё раз — AI ответит по его содержанию.",
        "ai_default_question": "Объясни главные связи между словами этого блока.",
        "billing_disabled_callback": "Покупка AI-кредитов пока выключена.",
        "billing_terms_accepted": "Условия приняты.",
        "billing_product_unavailable": "Этот пакет сейчас недоступен.",
        "billing_credit_label": "{credits} AI-кредитов",
        "billing_precheckout_error": "Не удалось подтвердить цену. Создай новый счёт через /buy.",
        "billing_payment_review": "Платёж получен, но начисление требует проверки. Напиши /paysupport.",
        "billing_payment_success": "Оплата подтверждена. Начислено {credits} AI-кредитов.\nДоступно: {available}.",
        "billing_test_payment_success": "Тестовая оплата подтверждена. Начислено {credits} AI-кредитов.\nДоступно: {available}.",
        "billing_payment_already": "Этот платёж уже учтён. Доступно: {available}.",
        "billing_subscription_restore": "Возобновить",
        "billing_subscription_cancel": "Отключить автопродление",
        "billing_subscription_text": "Stars-подписка\nСтатус: {status}\nОплачено до: {period_end}",
        "billing_subscription_failed": "Не удалось изменить подписку.",
        "billing_subscription_updated": "Настройка подписки обновлена.",
        "billing_autorenew_disabled": "Автопродление отключено до конца оплаченного периода.",
        "billing_autorenew_enabled": "Автопродление подписки снова включено.",
        "legacy_pack_activated": "Подключён набор *{pack}* ({count} слов)",
        "learning_no_words": "В этом наборе пока нет доступных слов.",
        "topic_stale": "Выбор темы устарел. Отправь /learn.",
        "topic_empty": "В этой теме пока нет слов.",
    },
}

_USER_SURFACE_CYCLE4_COPY.update({
    "de": {
        "start_about_text": (
            "So funktioniert das Lernen\n\n"
            "1. Tippe auf „Heutige Lektion“.\n"
            "2. Erinnere dich an die Bedeutung und decke die Karte auf.\n"
            "3. Markiere „Weiß ich“ oder „Weiß ich nicht“.\n"
            "4. Der Bot speichert die Antwort und plant die nächste Wiederholung."
        ),
        "start_about_button": "▶️ Lektion starten",
        "settings_stale": "Diese Einstellung ist abgelaufen.",
        "settings_pace_saved": "Tempo gespeichert",
        "settings_style_saved": "Stil: {style}",
        "settings_depth_saved": "Tiefe: {depth}",
        "settings_level_saved": "Niveau: {level}",
        "settings_unavailable": "Diese Einstellung ist nicht verfügbar.",
        "voice_practice_disabled": "Das Sprachtraining ist derzeit deaktiviert.",
        "voice_need_block": "Wähle zuerst ein Thema und erstelle mit /learn einen Block mit 10 Wörtern.",
        "voice_block_stale": "Dieser Block ist abgelaufen. Wähle ein Thema und erstelle mit /learn einen neuen Block.",
        "voice_practice_cancelled": "Sprachtraining abgebrochen.",
        "voice_request_stale": "Diese Anfrage ist abgelaufen. Starte /voice erneut.",
        "consent_saved": "Einwilligung gespeichert.",
        "voice_consent_resend": "Fertig. Sende die Sprachnachricht erneut; ich erkenne sie und antworte im Kontext.",
        "voice_translation_disabled": "Die Sprachübersetzung ist derzeit deaktiviert.",
        "voice_translation_consent": "Einwilligung zur Erkennung und Übersetzung\n\n{notice}\n\nVersion: {version}",
        "consent_accept": "Zustimmen",
        "consent_cancel": "Abbrechen",
        "voice_translation_instruction": "Sende eine Sprachnachricht. Russisch wird in die aktive Sprache übersetzt, andere Sprachen ins Russische.",
        "voice_translation_cancelled": "Übersetzung abgebrochen.",
        "voice_translation_send": "Sende eine Sprachnachricht zur Erkennung und Übersetzung.",
        "voice_stop_active": "Sprachsitzung beendet. Transkript: /voice_transcript.",
        "voice_stop_inactive": "Es gibt keine aktive Sprachsitzung.",
        "voice_sessions_empty": "Es gibt noch keine Sprachsitzungen.",
        "voice_transcript_header": "Transkript der Sprachsitzung · {pack}",
        "voice_transcript_status": "Status: {status}",
        "voice_transcript_missing_word": "Wort aus dem Block",
        "voice_transcript_recognized": "   Erkannt: {value}",
        "voice_transcript_result": "   Ergebnis: {value}",
        "voice_transcript_empty": "Es sind keine gespeicherten Beiträge vorhanden oder ihre Aufbewahrungsfrist ist abgelaufen.",
        "voice_translation_source_ru": "🇷🇺 Ausgangssatz: {value}",
        "voice_translation_translation": "🇷🇺 Übersetzung: {value}",
        "voice_translation_missing": "🇷🇺 Keine Übersetzung erhalten",
        "voice_translation_source": "{flag} Ausgangssatz: {value}",
        "voice_translation_latin": "Lateinische Schrift: {value}",
        "voice_translation_detected": "Erkannte Sprache: {value}.",
        "voice_translation_unknown": "unbekannt",
        "voice_block_complete": "✅ Sprachblock abgeschlossen. Alle 10 Wörter wurden geprüft.",
        "voice_access_unavailable": "Sprachfunktionen sind derzeit nicht verfügbar.",
        "voice_invalid": "Sprachnachricht abgelehnt: Dauer oder Größe liegt außerhalb der erlaubten Grenzen.",
        "ai_credit_recovery_error": "Die Erstattung des AI-Guthabens konnte nicht bestätigt werden. Prüfe /ai_stats.",
        "voice_safe_error": "Die Sprachnachricht konnte nicht sicher verarbeitet werden. Es wurde kein AI-Guthaben abgezogen.",
        "voice_practice_unavailable": "Das Sprachtraining ist vorübergehend nicht verfügbar.",
        "voice_practice_unavailable_no_charge": "Das Sprachtraining ist vorübergehend nicht verfügbar. Es wurde kein AI-Guthaben abgezogen.",
        "voice_translation_consent_required": "Eine aktuelle Einwilligung zur Erkennung und Übersetzung ist erforderlich. Starte /voice.",
        "ai_credit_state_error": "Der Stand des AI-Guthabens konnte nicht bestätigt werden. Prüfe /ai_stats.",
        "voice_translation_safe_error": "Die Sprachnachricht konnte nicht sicher verarbeitet werden. Der Text wurde nicht gespeichert.",
        "voice_ai_disabled": "Sprach-AI ist derzeit deaktiviert.",
        "ai_disabled": "Der AI-Tutor ist derzeit deaktiviert.",
        "ai_unavailable": "Der AI-Tutor ist vorübergehend nicht verfügbar.",
        "voice_transcription_failed": "Die Sprachnachricht konnte nicht erkannt werden. Es wurde kein AI-Guthaben abgezogen.",
        "voice_ai_unavailable_no_charge": "Sprach-AI ist vorübergehend nicht verfügbar. Es wurde kein AI-Guthaben abgezogen.",
        "ai_need_block": "Wähle zuerst ein Thema und erstelle mit /learn einen Block.",
        "ai_safe_error": "Eine sichere Antwort konnte nicht erstellt werden. Es wurde kein AI-Guthaben abgezogen.",
        "ai_unavailable_no_charge": "Der AI-Tutor ist vorübergehend nicht verfügbar. Es wurde kein AI-Guthaben abgezogen.",
        "mirror_voice_unavailable": "Eine Sprachantwort ist derzeit nicht verfügbar.",
        "mirror_question_unrecognized": "Die Frage konnte nicht erkannt werden.",
        "ai_request_cancelled": "AI-Anfrage abgebrochen.",
        "ai_request_stale": "Diese Anfrage ist abgelaufen. Starte /ai erneut.",
        "ai_voice_resend": "Fertig. Sende die Sprachnachricht erneut; die AI antwortet anhand ihres Inhalts.",
        "ai_default_question": "Erkläre die wichtigsten Zusammenhänge zwischen den Wörtern in diesem Block.",
        "billing_disabled_callback": "Der Kauf von AI-Guthaben ist derzeit deaktiviert.",
        "billing_terms_accepted": "Bedingungen akzeptiert.",
        "billing_product_unavailable": "Dieses Paket ist derzeit nicht verfügbar.",
        "billing_credit_label": "{credits} AI-Guthaben",
        "billing_precheckout_error": "Der Preis konnte nicht bestätigt werden. Erstelle mit /buy eine neue Rechnung.",
        "billing_payment_review": "Die Zahlung ist eingegangen, aber die Gutschrift muss geprüft werden. Sende /paysupport.",
        "billing_payment_success": "Zahlung bestätigt. {credits} AI-Guthaben hinzugefügt.\nVerfügbar: {available}.",
        "billing_test_payment_success": "Testzahlung bestätigt. {credits} AI-Guthaben hinzugefügt.\nVerfügbar: {available}.",
        "billing_payment_already": "Diese Zahlung wurde bereits erfasst. Verfügbar: {available}.",
        "billing_subscription_restore": "Fortsetzen",
        "billing_subscription_cancel": "Automatische Verlängerung deaktivieren",
        "billing_subscription_text": "Stars-Abonnement\nStatus: {status}\nBezahlt bis: {period_end}",
        "billing_subscription_failed": "Das Abonnement konnte nicht geändert werden.",
        "billing_subscription_updated": "Abonnementeinstellung aktualisiert.",
        "billing_autorenew_disabled": "Die automatische Verlängerung ist bis zum Ende des bezahlten Zeitraums deaktiviert.",
        "billing_autorenew_enabled": "Die automatische Verlängerung des Abonnements ist wieder aktiviert.",
        "legacy_pack_activated": "Paket *{pack}* aktiviert ({count} Wörter)",
        "learning_no_words": "Dieses Paket enthält noch keine verfügbaren Wörter.",
        "topic_stale": "Diese Themenauswahl ist abgelaufen. Sende /learn.",
        "topic_empty": "Dieses Thema enthält noch keine Wörter.",
    },
    "es": {
        "start_about_text": (
            "Cómo funciona el aprendizaje\n\n"
            "1. Pulsa «Lección de hoy».\n"
            "2. Recuerda el significado y muestra la tarjeta.\n"
            "3. Marca «Lo sé» o «No lo sé».\n"
            "4. El bot guarda la respuesta y programa el siguiente repaso."
        ),
        "start_about_button": "▶️ Empezar lección",
        "settings_stale": "Este ajuste ha caducado.",
        "settings_pace_saved": "Ritmo guardado",
        "settings_style_saved": "Estilo: {style}",
        "settings_depth_saved": "Profundidad: {depth}",
        "settings_level_saved": "Nivel: {level}",
        "settings_unavailable": "Este ajuste no está disponible.",
        "voice_practice_disabled": "La práctica de voz está desactivada por ahora.",
        "voice_need_block": "Elige primero un tema y crea un bloque de 10 palabras con /learn.",
        "voice_block_stale": "Este bloque ha caducado. Elige un tema y crea otro bloque con /learn.",
        "voice_practice_cancelled": "Práctica de voz cancelada.",
        "voice_request_stale": "Esta solicitud ha caducado. Inicia /voice de nuevo.",
        "consent_saved": "Consentimiento guardado.",
        "voice_consent_resend": "Listo. Envía de nuevo el mensaje de voz; lo reconoceré y responderé según el contexto.",
        "voice_translation_disabled": "La traducción de voz está desactivada por ahora.",
        "voice_translation_consent": "Consentimiento para reconocimiento y traducción\n\n{notice}\n\nVersión: {version}",
        "consent_accept": "Aceptar",
        "consent_cancel": "Cancelar",
        "voice_translation_instruction": "Envía un mensaje de voz. El ruso se traducirá al idioma activo y los demás idiomas al ruso.",
        "voice_translation_cancelled": "Traducción cancelada.",
        "voice_translation_send": "Envía un mensaje de voz para reconocerlo y traducirlo.",
        "voice_stop_active": "Sesión de voz detenida. Transcripción: /voice_transcript.",
        "voice_stop_inactive": "No hay ninguna sesión de voz activa.",
        "voice_sessions_empty": "Todavía no hay sesiones de voz.",
        "voice_transcript_header": "Transcripción de la sesión de voz · {pack}",
        "voice_transcript_status": "Estado: {status}",
        "voice_transcript_missing_word": "palabra del bloque",
        "voice_transcript_recognized": "   Reconocido: {value}",
        "voice_transcript_result": "   Resultado: {value}",
        "voice_transcript_empty": "No quedan intervenciones guardadas o su periodo de conservación ha caducado.",
        "voice_translation_source_ru": "🇷🇺 Frase original: {value}",
        "voice_translation_translation": "🇷🇺 Traducción: {value}",
        "voice_translation_missing": "🇷🇺 No se obtuvo ninguna traducción",
        "voice_translation_source": "{flag} Frase original: {value}",
        "voice_translation_latin": "Alfabeto latino: {value}",
        "voice_translation_detected": "Idioma detectado: {value}.",
        "voice_translation_unknown": "desconocido",
        "voice_block_complete": "✅ Bloque de voz terminado. Se comprobaron las 10 palabras.",
        "voice_access_unavailable": "Las funciones de voz no están disponibles por ahora.",
        "voice_invalid": "Mensaje de voz rechazado: la duración o el tamaño superan los límites permitidos.",
        "ai_credit_recovery_error": "No se pudo confirmar la devolución del crédito de IA. Consulta /ai_stats.",
        "voice_safe_error": "No se pudo procesar el mensaje de voz de forma segura. No se cobró ningún crédito de IA.",
        "voice_practice_unavailable": "La práctica de voz no está disponible temporalmente.",
        "voice_practice_unavailable_no_charge": "La práctica de voz no está disponible temporalmente. No se cobró ningún crédito de IA.",
        "voice_translation_consent_required": "Se necesita un consentimiento vigente para reconocer y traducir. Inicia /voice.",
        "ai_credit_state_error": "No se pudo confirmar el estado de los créditos de IA. Consulta /ai_stats.",
        "voice_translation_safe_error": "No se pudo procesar el mensaje de voz de forma segura. El texto no se guardó.",
        "voice_ai_disabled": "La IA de voz está desactivada por ahora.",
        "ai_disabled": "El tutor de IA está desactivado por ahora.",
        "ai_unavailable": "El tutor de IA no está disponible temporalmente.",
        "voice_transcription_failed": "No se pudo reconocer el mensaje de voz. No se cobró ningún crédito de IA.",
        "voice_ai_unavailable_no_charge": "La IA de voz no está disponible temporalmente. No se cobró ningún crédito de IA.",
        "ai_need_block": "Elige primero un tema y crea un bloque con /learn.",
        "ai_safe_error": "No se pudo preparar una respuesta segura. No se cobró ningún crédito de IA.",
        "ai_unavailable_no_charge": "El tutor de IA no está disponible temporalmente. No se cobró ningún crédito de IA.",
        "mirror_voice_unavailable": "La respuesta de voz no está disponible por ahora.",
        "mirror_question_unrecognized": "No se pudo reconocer la pregunta.",
        "ai_request_cancelled": "Solicitud de IA cancelada.",
        "ai_request_stale": "Esta solicitud ha caducado. Inicia /ai de nuevo.",
        "ai_voice_resend": "Listo. Envía de nuevo el mensaje de voz; la IA responderá según su contenido.",
        "ai_default_question": "Explica las conexiones principales entre las palabras de este bloque.",
        "billing_disabled_callback": "La compra de créditos de IA está desactivada por ahora.",
        "billing_terms_accepted": "Condiciones aceptadas.",
        "billing_product_unavailable": "Este paquete no está disponible por ahora.",
        "billing_credit_label": "{credits} créditos de IA",
        "billing_precheckout_error": "No se pudo confirmar el precio. Crea una factura nueva con /buy.",
        "billing_payment_review": "Se recibió el pago, pero la asignación de créditos debe revisarse. Envía /paysupport.",
        "billing_payment_success": "Pago confirmado. Se añadieron {credits} créditos de IA.\nDisponibles: {available}.",
        "billing_test_payment_success": "Pago de prueba confirmado. Se añadieron {credits} créditos de IA.\nDisponibles: {available}.",
        "billing_payment_already": "Este pago ya se registró. Disponibles: {available}.",
        "billing_subscription_restore": "Reanudar",
        "billing_subscription_cancel": "Desactivar la renovación automática",
        "billing_subscription_text": "Suscripción de Stars\nEstado: {status}\nPagada hasta: {period_end}",
        "billing_subscription_failed": "No se pudo modificar la suscripción.",
        "billing_subscription_updated": "Ajuste de suscripción actualizado.",
        "billing_autorenew_disabled": "La renovación automática está desactivada hasta que termine el periodo pagado.",
        "billing_autorenew_enabled": "La renovación automática de la suscripción está activa de nuevo.",
        "legacy_pack_activated": "Paquete *{pack}* activado ({count} palabras)",
        "learning_no_words": "Este paquete aún no tiene palabras disponibles.",
        "topic_stale": "Esta selección de tema ha caducado. Envía /learn.",
        "topic_empty": "Este tema aún no tiene palabras.",
    },
})

_USER_SURFACE_CYCLE4_COPY.update({
    "ja": {
        "start_about_text": (
            "学習の進め方\n\n"
            "1. 「今日のレッスン」をタップします。\n"
            "2. 意味を思い出してカードを開きます。\n"
            "3. 「わかる」または「わからない」を選びます。\n"
            "4. Botが回答を保存し、次の復習を設定します。"
        ),
        "start_about_button": "▶️ レッスンを始める",
        "settings_stale": "この設定は期限切れです。",
        "settings_pace_saved": "ペースを保存しました",
        "settings_style_saved": "スタイル：{style}",
        "settings_depth_saved": "詳しさ：{depth}",
        "settings_level_saved": "レベル：{level}",
        "settings_unavailable": "この設定は利用できません。",
        "voice_practice_disabled": "音声練習は現在無効です。",
        "voice_need_block": "先にトピックを選び、/learn で10語のブロックを作成してください。",
        "voice_block_stale": "このブロックは期限切れです。トピックを選び、/learn で新しいブロックを作成してください。",
        "voice_practice_cancelled": "音声練習をキャンセルしました。",
        "voice_request_stale": "このリクエストは期限切れです。/voice をもう一度開始してください。",
        "consent_saved": "同意を保存しました。",
        "voice_consent_resend": "準備できました。音声メッセージをもう一度送ると、認識して文脈に沿って回答します。",
        "voice_translation_disabled": "音声翻訳は現在無効です。",
        "voice_translation_consent": "音声認識と翻訳への同意\n\n{notice}\n\nバージョン：{version}",
        "consent_accept": "同意する",
        "consent_cancel": "キャンセル",
        "voice_translation_instruction": "音声メッセージを送ってください。ロシア語は学習中の言語へ、それ以外の言語はロシア語へ翻訳されます。",
        "voice_translation_cancelled": "翻訳をキャンセルしました。",
        "voice_translation_send": "認識と翻訳を行う音声メッセージを送ってください。",
        "voice_stop_active": "音声セッションを停止しました。文字起こし：/voice_transcript。",
        "voice_stop_inactive": "進行中の音声セッションはありません。",
        "voice_sessions_empty": "音声セッションはまだありません。",
        "voice_transcript_header": "音声セッションの文字起こし · {pack}",
        "voice_transcript_status": "状態：{status}",
        "voice_transcript_missing_word": "ブロック内の単語",
        "voice_transcript_recognized": "   認識結果：{value}",
        "voice_transcript_result": "   判定：{value}",
        "voice_transcript_empty": "保存された発話がないか、保存期間が終了しています。",
        "voice_translation_source_ru": "🇷🇺 元のフレーズ：{value}",
        "voice_translation_translation": "🇷🇺 翻訳：{value}",
        "voice_translation_missing": "🇷🇺 翻訳結果がありません",
        "voice_translation_source": "{flag} 元のフレーズ：{value}",
        "voice_translation_latin": "ラテン文字：{value}",
        "voice_translation_detected": "検出言語：{value}。",
        "voice_translation_unknown": "不明",
        "voice_block_complete": "✅ 音声ブロックが完了しました。10語すべてを確認しました。",
        "voice_access_unavailable": "音声機能は現在利用できません。",
        "voice_invalid": "音声メッセージを受け付けられません：長さまたはサイズが上限外です。",
        "ai_credit_recovery_error": "AIクレジットの返却を確認できませんでした。/ai_stats を確認してください。",
        "voice_safe_error": "音声メッセージを安全に処理できませんでした。AIクレジットは消費されていません。",
        "voice_practice_unavailable": "音声練習は一時的に利用できません。",
        "voice_practice_unavailable_no_charge": "音声練習は一時的に利用できません。AIクレジットは消費されていません。",
        "voice_translation_consent_required": "音声認識と翻訳への最新の同意が必要です。/voice を開始してください。",
        "ai_credit_state_error": "AIクレジットの状態を確認できませんでした。/ai_stats を確認してください。",
        "voice_translation_safe_error": "音声メッセージを安全に処理できませんでした。テキストは保存されていません。",
        "voice_ai_disabled": "音声AIは現在無効です。",
        "ai_disabled": "AIチューターは現在無効です。",
        "ai_unavailable": "AIチューターは一時的に利用できません。",
        "voice_transcription_failed": "音声メッセージを認識できませんでした。AIクレジットは消費されていません。",
        "voice_ai_unavailable_no_charge": "音声AIは一時的に利用できません。AIクレジットは消費されていません。",
        "ai_need_block": "先にトピックを選び、/learn でブロックを作成してください。",
        "ai_safe_error": "安全な回答を作成できませんでした。AIクレジットは消費されていません。",
        "ai_unavailable_no_charge": "AIチューターは一時的に利用できません。AIクレジットは消費されていません。",
        "mirror_voice_unavailable": "音声回答は現在利用できません。",
        "mirror_question_unrecognized": "質問を認識できませんでした。",
        "ai_request_cancelled": "AIリクエストをキャンセルしました。",
        "ai_request_stale": "このリクエストは期限切れです。/ai をもう一度開始してください。",
        "ai_voice_resend": "準備できました。音声メッセージをもう一度送ると、AIが内容に沿って回答します。",
        "ai_default_question": "このブロックの単語どうしの主なつながりを説明してください。",
        "billing_disabled_callback": "AIクレジットの購入は現在無効です。",
        "billing_terms_accepted": "利用条件に同意しました。",
        "billing_product_unavailable": "このパッケージは現在利用できません。",
        "billing_credit_label": "AIクレジット {credits}",
        "billing_precheckout_error": "価格を確認できませんでした。/buy で新しい請求を作成してください。",
        "billing_payment_review": "支払いを受け取りましたが、クレジット付与の確認が必要です。/paysupport を送信してください。",
        "billing_payment_success": "支払いを確認しました。AIクレジットを{credits}追加しました。\n利用可能：{available}。",
        "billing_test_payment_success": "テスト支払いを確認しました。AIクレジットを{credits}追加しました。\n利用可能：{available}。",
        "billing_payment_already": "この支払いはすでに記録されています。利用可能：{available}。",
        "billing_subscription_restore": "再開",
        "billing_subscription_cancel": "自動更新を無効にする",
        "billing_subscription_text": "Starsサブスクリプション\n状態：{status}\n支払済み期間：{period_end}まで",
        "billing_subscription_failed": "サブスクリプションを変更できませんでした。",
        "billing_subscription_updated": "サブスクリプション設定を更新しました。",
        "billing_autorenew_disabled": "自動更新は支払済み期間の終了まで無効です。",
        "billing_autorenew_enabled": "サブスクリプションの自動更新を再び有効にしました。",
        "legacy_pack_activated": "パック *{pack}* を有効にしました（{count}語）",
        "learning_no_words": "このパックには利用できる単語がまだありません。",
        "topic_stale": "このトピック選択は期限切れです。/learn を送信してください。",
        "topic_empty": "このトピックには単語がまだありません。",
    },
    "zh": {
        "start_about_text": (
            "学习方式\n\n"
            "1. 点击“今日课程”。\n"
            "2. 先回想词义，再显示卡片。\n"
            "3. 选择“会”或“不会”。\n"
            "4. 机器人会保存答案并安排下次复习。"
        ),
        "start_about_button": "▶️ 开始课程",
        "settings_stale": "此设置已过期。",
        "settings_pace_saved": "学习节奏已保存",
        "settings_style_saved": "风格：{style}",
        "settings_depth_saved": "详细程度：{depth}",
        "settings_level_saved": "级别：{level}",
        "settings_unavailable": "此设置不可用。",
        "voice_practice_disabled": "语音练习目前已关闭。",
        "voice_need_block": "请先选择主题，并通过 /learn 创建一个10词学习组。",
        "voice_block_stale": "此学习组已过期。请选择主题并通过 /learn 创建新学习组。",
        "voice_practice_cancelled": "语音练习已取消。",
        "voice_request_stale": "此请求已过期，请重新启动 /voice。",
        "consent_saved": "同意已保存。",
        "voice_consent_resend": "已准备好。请再次发送语音消息，我会识别并结合上下文回答。",
        "voice_translation_disabled": "语音翻译目前已关闭。",
        "voice_translation_consent": "语音识别与翻译同意\n\n{notice}\n\n版本：{version}",
        "consent_accept": "同意",
        "consent_cancel": "取消",
        "voice_translation_instruction": "请发送语音消息。俄语会被翻译成当前学习语言，其他语言会被翻译成俄语。",
        "voice_translation_cancelled": "翻译已取消。",
        "voice_translation_send": "请发送需要识别和翻译的语音消息。",
        "voice_stop_active": "语音会话已停止。转写：/voice_transcript。",
        "voice_stop_inactive": "当前没有进行中的语音会话。",
        "voice_sessions_empty": "目前还没有语音会话。",
        "voice_transcript_header": "语音会话转写 · {pack}",
        "voice_transcript_status": "状态：{status}",
        "voice_transcript_missing_word": "学习组中的单词",
        "voice_transcript_recognized": "   识别内容：{value}",
        "voice_transcript_result": "   结果：{value}",
        "voice_transcript_empty": "没有已保存的发言，或其保留期限已结束。",
        "voice_translation_source_ru": "🇷🇺 原句：{value}",
        "voice_translation_translation": "🇷🇺 翻译：{value}",
        "voice_translation_missing": "🇷🇺 未获得翻译",
        "voice_translation_source": "{flag} 原句：{value}",
        "voice_translation_latin": "拉丁字母：{value}",
        "voice_translation_detected": "识别语言：{value}。",
        "voice_translation_unknown": "未知",
        "voice_block_complete": "✅ 语音学习组已完成，10个单词均已检查。",
        "voice_access_unavailable": "语音功能目前不可用。",
        "voice_invalid": "语音消息被拒绝：时长或大小超出允许范围。",
        "ai_credit_recovery_error": "无法确认 AI 点数退还，请查看 /ai_stats。",
        "voice_safe_error": "无法安全处理语音消息，未扣除 AI 点数。",
        "voice_practice_unavailable": "语音练习暂时不可用。",
        "voice_practice_unavailable_no_charge": "语音练习暂时不可用，未扣除 AI 点数。",
        "voice_translation_consent_required": "需要最新的语音识别与翻译同意，请启动 /voice。",
        "ai_credit_state_error": "无法确认 AI 点数状态，请查看 /ai_stats。",
        "voice_translation_safe_error": "无法安全处理语音消息，文本未保存。",
        "voice_ai_disabled": "语音 AI 目前已关闭。",
        "ai_disabled": "AI 导师目前已关闭。",
        "ai_unavailable": "AI 导师暂时不可用。",
        "voice_transcription_failed": "无法识别语音消息，未扣除 AI 点数。",
        "voice_ai_unavailable_no_charge": "语音 AI 暂时不可用，未扣除 AI 点数。",
        "ai_need_block": "请先选择主题，并通过 /learn 创建学习组。",
        "ai_safe_error": "无法生成安全回答，未扣除 AI 点数。",
        "ai_unavailable_no_charge": "AI 导师暂时不可用，未扣除 AI 点数。",
        "mirror_voice_unavailable": "语音回答目前不可用。",
        "mirror_question_unrecognized": "无法识别问题。",
        "ai_request_cancelled": "AI 请求已取消。",
        "ai_request_stale": "此请求已过期，请重新启动 /ai。",
        "ai_voice_resend": "已准备好。请再次发送语音消息，AI 会根据其内容回答。",
        "ai_default_question": "请解释这个学习组中各单词之间的主要联系。",
        "billing_disabled_callback": "购买 AI 点数目前已关闭。",
        "billing_terms_accepted": "条款已接受。",
        "billing_product_unavailable": "此套餐目前不可用。",
        "billing_credit_label": "{credits} AI 点数",
        "billing_precheckout_error": "无法确认价格，请通过 /buy 创建新账单。",
        "billing_payment_review": "已收到付款，但点数发放需要审核。请发送 /paysupport。",
        "billing_payment_success": "付款已确认，已添加 {credits} AI 点数。\n可用：{available}。",
        "billing_test_payment_success": "测试付款已确认，已添加 {credits} AI 点数。\n可用：{available}。",
        "billing_payment_already": "此付款已记录。可用：{available}。",
        "billing_subscription_restore": "恢复",
        "billing_subscription_cancel": "关闭自动续订",
        "billing_subscription_text": "Stars 订阅\n状态：{status}\n已付至：{period_end}",
        "billing_subscription_failed": "无法修改订阅。",
        "billing_subscription_updated": "订阅设置已更新。",
        "billing_autorenew_disabled": "自动续订已关闭，直至已付费周期结束。",
        "billing_autorenew_enabled": "订阅自动续订已重新开启。",
        "legacy_pack_activated": "词包 *{pack}* 已启用（{count}词）",
        "learning_no_words": "此词包目前还没有可用单词。",
        "topic_stale": "此主题选择已过期，请发送 /learn。",
        "topic_empty": "此主题目前还没有单词。",
    },
})

_USER_SURFACE_CYCLE4_COPY.update({
    "ar": {
        "start_about_text": (
            "كيف يجري التعلّم\n\n"
            "1. اضغط «درس اليوم».\n"
            "2. حاول تذكّر المعنى ثم اكشف البطاقة.\n"
            "3. اختر «أعرف» أو «لا أعرف».\n"
            "4. يحفظ البوت الإجابة ويحدد موعد المراجعة التالية."
        ),
        "start_about_button": "▶️ ابدأ الدرس",
        "settings_stale": "انتهت صلاحية هذا الإعداد.",
        "settings_pace_saved": "تم حفظ الوتيرة",
        "settings_style_saved": "الأسلوب: {style}",
        "settings_depth_saved": "التفصيل: {depth}",
        "settings_level_saved": "المستوى: {level}",
        "settings_unavailable": "هذا الإعداد غير متاح.",
        "voice_practice_disabled": "التدريب الصوتي معطّل حالياً.",
        "voice_need_block": "اختر موضوعاً أولاً وأنشئ مجموعة من 10 كلمات عبر /learn.",
        "voice_block_stale": "انتهت صلاحية هذه المجموعة. اختر موضوعاً وأنشئ مجموعة جديدة عبر /learn.",
        "voice_practice_cancelled": "تم إلغاء التدريب الصوتي.",
        "voice_request_stale": "انتهت صلاحية هذا الطلب. شغّل /voice من جديد.",
        "consent_saved": "تم حفظ الموافقة.",
        "voice_consent_resend": "تم. أرسل الرسالة الصوتية مرة أخرى وسأتعرّف عليها وأجيب وفق السياق.",
        "voice_translation_disabled": "الترجمة الصوتية معطّلة حالياً.",
        "voice_translation_consent": "الموافقة على التعرّف والترجمة\n\n{notice}\n\nالإصدار: {version}",
        "consent_accept": "أوافق",
        "consent_cancel": "إلغاء",
        "voice_translation_instruction": "أرسل رسالة صوتية. ستُترجم الروسية إلى اللغة النشطة، وتُترجم اللغات الأخرى إلى الروسية.",
        "voice_translation_cancelled": "تم إلغاء الترجمة.",
        "voice_translation_send": "أرسل رسالة صوتية للتعرّف عليها وترجمتها.",
        "voice_stop_active": "تم إيقاف الجلسة الصوتية. النص: /voice_transcript.",
        "voice_stop_inactive": "لا توجد جلسة صوتية نشطة.",
        "voice_sessions_empty": "لا توجد جلسات صوتية بعد.",
        "voice_transcript_header": "نص الجلسة الصوتية · {pack}",
        "voice_transcript_status": "الحالة: {status}",
        "voice_transcript_missing_word": "كلمة من المجموعة",
        "voice_transcript_recognized": "   النص المتعرّف عليه: {value}",
        "voice_transcript_result": "   النتيجة: {value}",
        "voice_transcript_empty": "لا توجد مقاطع محفوظة، أو انتهت مدة الاحتفاظ بها.",
        "voice_translation_source_ru": "🇷🇺 العبارة الأصلية: {value}",
        "voice_translation_translation": "🇷🇺 الترجمة: {value}",
        "voice_translation_missing": "🇷🇺 لم تُستلم ترجمة",
        "voice_translation_source": "{flag} العبارة الأصلية: {value}",
        "voice_translation_latin": "بالأحرف اللاتينية: {value}",
        "voice_translation_detected": "اللغة المتعرّف عليها: {value}.",
        "voice_translation_unknown": "غير معروفة",
        "voice_block_complete": "✅ اكتملت المجموعة الصوتية. تم فحص الكلمات العشر.",
        "voice_access_unavailable": "الميزات الصوتية غير متاحة حالياً.",
        "voice_invalid": "رُفضت الرسالة الصوتية: المدة أو الحجم خارج الحدود المسموح بها.",
        "ai_credit_recovery_error": "تعذر تأكيد إعادة رصيد AI. راجع /ai_stats.",
        "voice_safe_error": "تعذرت معالجة الرسالة الصوتية بأمان. لم يُخصم أي رصيد AI.",
        "voice_practice_unavailable": "التدريب الصوتي غير متاح مؤقتاً.",
        "voice_practice_unavailable_no_charge": "التدريب الصوتي غير متاح مؤقتاً. لم يُخصم أي رصيد AI.",
        "voice_translation_consent_required": "تلزم موافقة حالية على التعرّف والترجمة. شغّل /voice.",
        "ai_credit_state_error": "تعذر تأكيد حالة أرصدة AI. راجع /ai_stats.",
        "voice_translation_safe_error": "تعذرت معالجة الرسالة الصوتية بأمان. لم يُحفظ النص.",
        "voice_ai_disabled": "ميزة AI الصوتية معطّلة حالياً.",
        "ai_disabled": "مدرّس AI معطّل حالياً.",
        "ai_unavailable": "مدرّس AI غير متاح مؤقتاً.",
        "voice_transcription_failed": "تعذر التعرّف على الرسالة الصوتية. لم يُخصم أي رصيد AI.",
        "voice_ai_unavailable_no_charge": "ميزة AI الصوتية غير متاحة مؤقتاً. لم يُخصم أي رصيد AI.",
        "ai_need_block": "اختر موضوعاً أولاً وأنشئ مجموعة عبر /learn.",
        "ai_safe_error": "تعذر إعداد إجابة آمنة. لم يُخصم أي رصيد AI.",
        "ai_unavailable_no_charge": "مدرّس AI غير متاح مؤقتاً. لم يُخصم أي رصيد AI.",
        "mirror_voice_unavailable": "الإجابة الصوتية غير متاحة حالياً.",
        "mirror_question_unrecognized": "تعذر التعرّف على السؤال.",
        "ai_request_cancelled": "تم إلغاء طلب AI.",
        "ai_request_stale": "انتهت صلاحية هذا الطلب. شغّل /ai من جديد.",
        "ai_voice_resend": "تم. أرسل الرسالة الصوتية مرة أخرى وسيجيب AI وفق محتواها.",
        "ai_default_question": "اشرح الروابط الأساسية بين كلمات هذه المجموعة.",
        "billing_disabled_callback": "شراء أرصدة AI معطّل حالياً.",
        "billing_terms_accepted": "تم قبول الشروط.",
        "billing_product_unavailable": "هذه الحزمة غير متاحة حالياً.",
        "billing_credit_label": "{credits} من أرصدة AI",
        "billing_precheckout_error": "تعذر تأكيد السعر. أنشئ فاتورة جديدة عبر /buy.",
        "billing_payment_review": "تم استلام الدفعة، لكن إضافة الرصيد تحتاج إلى مراجعة. أرسل /paysupport.",
        "billing_payment_success": "تم تأكيد الدفع وإضافة {credits} من أرصدة AI.\nالمتاح: {available}.",
        "billing_test_payment_success": "تم تأكيد دفعة الاختبار وإضافة {credits} من أرصدة AI.\nالمتاح: {available}.",
        "billing_payment_already": "سبق تسجيل هذه الدفعة. المتاح: {available}.",
        "billing_subscription_restore": "استئناف",
        "billing_subscription_cancel": "إيقاف التجديد التلقائي",
        "billing_subscription_text": "اشتراك Stars\nالحالة: {status}\nمدفوع حتى: {period_end}",
        "billing_subscription_failed": "تعذر تعديل الاشتراك.",
        "billing_subscription_updated": "تم تحديث إعداد الاشتراك.",
        "billing_autorenew_disabled": "التجديد التلقائي معطّل حتى نهاية الفترة المدفوعة.",
        "billing_autorenew_enabled": "تم تفعيل التجديد التلقائي للاشتراك من جديد.",
        "legacy_pack_activated": "تم تفعيل حزمة *{pack}* ({count} كلمة)",
        "learning_no_words": "لا تحتوي هذه الحزمة على كلمات متاحة بعد.",
        "topic_stale": "انتهت صلاحية اختيار الموضوع. أرسل /learn.",
        "topic_empty": "لا توجد كلمات في هذا الموضوع بعد.",
    },
})

# Every supported interface locale has dedicated cycle-4 copy. Unknown
# Telegram locales are normalized to English before catalog lookup.
if set(_USER_SURFACE_CYCLE4_COPY) != set(INTERFACE_LOCALES):
    raise ValueError("Cycle-4 interface catalog is incomplete")

for _locale, _messages in _USER_SURFACE_CYCLE4_COPY.items():
    _CATALOG[_locale].update(_messages)

_PRODUCTION_STARS_CANARY_COPY = {
    "en": "Canary payment confirmed and refunded in full.",
    "fr": "Le paiement canari est confirmé et intégralement remboursé.",
    "de": "Die Canary-Zahlung wurde bestätigt und vollständig erstattet.",
    "ja": "Canary決済を確認し、全額返金しました。",
    "ar": "تم تأكيد دفعة الاختبار المحدود وردّها بالكامل.",
    "zh": "Canary 付款已确认并全额退款。",
    "ru": "Canary-платёж подтверждён и полностью возвращён.",
    "es": "El pago canario se confirmó y se reembolsó por completo.",
}

for _locale, _message in _PRODUCTION_STARS_CANARY_COPY.items():
    _CATALOG[_locale]["billing_canary_refund_success"] = _message

_BILLING_PRODUCT_COPY: dict[str, dict[str, tuple[str, str]]] = {
    "en": {
        "ai-mini": ("Mini", "{credits} AI credits to try the tutor"),
        "ai-starter": ("Starter", "{credits} AI credits for tutor requests"),
        "ai-value": ("Value", "{credits} AI credits for regular practice"),
        "ai-monthly": ("Monthly", "{credits} AI credits every 30 days"),
    },
    "fr": {
        "ai-mini": ("Mini", "{credits} crédits IA pour découvrir le tuteur"),
        "ai-starter": (
            "Découverte",
            "{credits} crédits IA pour les demandes au tuteur",
        ),
        "ai-value": (
            "Avantage",
            "{credits} crédits IA pour la pratique régulière",
        ),
        "ai-monthly": ("Mensuel", "{credits} crédits IA tous les 30 jours"),
    },
    "de": {
        "ai-mini": (
            "Mini",
            "{credits} KI-Credits, um den Tutor kennenzulernen",
        ),
        "ai-starter": (
            "Einstieg",
            "{credits} KI-Credits für Anfragen an den Tutor",
        ),
        "ai-value": (
            "Vorteil",
            "{credits} KI-Credits für regelmäßiges Üben",
        ),
        "ai-monthly": ("Monatlich", "{credits} KI-Credits alle 30 Tage"),
    },
    "ja": {
        "ai-mini": ("ミニ", "{credits} AIクレジットでチューターを試す"),
        "ai-starter": (
            "スターター",
            "{credits} AIクレジットでチューターへの質問",
        ),
        "ai-value": ("お得", "{credits} AIクレジットで定期的な練習"),
        "ai-monthly": ("月額", "{credits} AIクレジットを30日ごとに付与"),
    },
    "ar": {
        "ai-mini": ("مصغّرة", "{credits} رصيد AI لتجربة المدرّس"),
        "ai-starter": ("بداية", "{credits} رصيد AI لطلبات المدرّس"),
        "ai-value": ("موفّرة", "{credits} رصيد AI للتدريب المنتظم"),
        "ai-monthly": ("شهرية", "{credits} رصيد AI كل 30 يومًا"),
    },
    "zh": {
        "ai-mini": ("迷你", "{credits} AI 点数，用于体验导师"),
        "ai-starter": ("入门", "{credits} AI 点数，用于向导师提问"),
        "ai-value": ("超值", "{credits} AI 点数，用于定期练习"),
        "ai-monthly": ("每月", "每 30 天获得 {credits} AI 点数"),
    },
    "ru": {
        "ai-mini": (
            "Мини",
            "{credits} AI-кредитов для знакомства с репетитором",
        ),
        "ai-starter": (
            "Старт",
            "{credits} AI-кредитов для запросов к репетитору",
        ),
        "ai-value": (
            "Выгодно",
            "{credits} AI-кредитов для регулярной практики",
        ),
        "ai-monthly": ("Месяц", "{credits} AI-кредитов каждые 30 дней"),
    },
    "es": {
        "ai-mini": ("Mini", "{credits} créditos de IA para probar el tutor"),
        "ai-starter": (
            "Inicio",
            "{credits} créditos de IA para consultas al tutor",
        ),
        "ai-value": (
            "Ahorro",
            "{credits} créditos de IA para la práctica habitual",
        ),
        "ai-monthly": ("Mensual", "{credits} créditos de IA cada 30 días"),
    },
}

_BILLING_PRODUCT_IDS = frozenset(
    {"ai-mini", "ai-starter", "ai-value", "ai-monthly"}
)
if set(_BILLING_PRODUCT_COPY) != set(INTERFACE_LOCALES) or any(
    set(products) != set(_BILLING_PRODUCT_IDS)
    for products in _BILLING_PRODUCT_COPY.values()
):
    raise ValueError("Billing product localization catalog is incomplete")

_SERVICE_COPY = {
    "en": {
        "access_waitlist": "Your free pilot request is registered. After approval, open /start again.",
        "access_blocked": "Access to MY DICTIONARY is blocked. Contact support.",
        "access_pending": "Pilot access is still awaiting approval. Check again with /start.",
        "access_closed": "MY DICTIONARY is currently available only to closed-test participants.",
        "rate_limited": "Too many actions in a row. Try again in {seconds} sec.",
        "mirror_unavailable": "Mirror is not available for this account right now.",
        "onboarding_required": "Complete setup with /start first.",
        "ai_consent_required": "An up-to-date AI-processing consent is required. Open /ai.",
        "ai_no_credits": "You have no AI credits left. Check your balance with /ai_stats.",
        "ai_paywall": "Your AI credits are empty. Balance: {balance}.",
        "ai_buy_credits": "Buy credits",
        "ai_continue_question": "Continue question",
        "ai_resume_expired": "That question has expired. Send it again.",
        "ai_unavailable_no_charge": "The AI tutor is temporarily unavailable. No AI credit was charged.",
        "ai_thinking_fast": "⚡ Preparing a quick answer…",
        "ai_thinking_deep": "🧠 Thinking through your learning question…",
        "ai_thinking_continuation": "💭 Continuing from our recent conversation…",
        "ai_failure": "I could not prepare a verified answer. No learning answer was invented.",
    },
    "fr": {
        "access_waitlist": "Votre demande pour le pilote gratuit est enregistrée. Après validation, ouvrez de nouveau /start.",
        "access_blocked": "L'accès à MY DICTIONARY est bloqué. Contactez l'assistance.",
        "access_pending": "L'accès au pilote attend encore une validation. Vérifiez avec /start.",
        "access_closed": "MY DICTIONARY est actuellement réservé aux participants du test fermé.",
        "rate_limited": "Trop d'actions successives. Réessayez dans {seconds} s.",
        "mirror_unavailable": "Mirror n'est pas disponible pour ce compte actuellement.",
        "onboarding_required": "Terminez d'abord la configuration avec /start.",
        "ai_consent_required": "Un consentement AI à jour est requis. Ouvrez /ai.",
        "ai_no_credits": "Vous n'avez plus de crédits AI. Consultez /ai_stats.",
        "ai_paywall": "Vos crédits AI sont épuisés. Solde : {balance}.",
        "ai_buy_credits": "Acheter des crédits",
        "ai_continue_question": "Continuer la question",
        "ai_resume_expired": "Cette question a expiré. Envoyez-la de nouveau.",
        "ai_unavailable_no_charge": "Le tuteur IA est temporairement indisponible. Aucun crédit IA n’a été débité.",
        "ai_thinking_fast": "⚡ Je prépare une réponse rapide…",
        "ai_thinking_deep": "🧠 J’analyse ta question d’apprentissage…",
        "ai_thinking_continuation": "💭 Je poursuis notre conversation récente…",
        "ai_failure": "Je n'ai pas pu préparer une réponse vérifiée. Aucune réponse n'a été inventée.",
    },
    "de": {
        "access_waitlist": "Deine Anfrage für den kostenlosen Pilot ist registriert. Öffne nach der Freigabe erneut /start.",
        "access_blocked": "Der Zugang zu MY DICTIONARY ist gesperrt. Kontaktiere den Support.",
        "access_pending": "Der Pilotzugang wartet noch auf Freigabe. Prüfe ihn mit /start.",
        "access_closed": "MY DICTIONARY ist derzeit nur für geschlossene Testteilnehmer verfügbar.",
        "rate_limited": "Zu viele Aktionen nacheinander. Versuche es in {seconds} Sek. erneut.",
        "mirror_unavailable": "Mirror ist für dieses Konto derzeit nicht verfügbar.",
        "onboarding_required": "Schließe zuerst die Einrichtung mit /start ab.",
        "ai_consent_required": "Eine aktuelle AI-Einwilligung ist erforderlich. Öffne /ai.",
        "ai_no_credits": "Deine AI-Credits sind aufgebraucht. Prüfe /ai_stats.",
        "ai_paywall": "Deine AI-Credits sind aufgebraucht. Guthaben: {balance}.",
        "ai_buy_credits": "Credits kaufen",
        "ai_continue_question": "Frage fortsetzen",
        "ai_resume_expired": "Diese Frage ist abgelaufen. Sende sie erneut.",
        "ai_unavailable_no_charge": "Der AI-Tutor ist vorübergehend nicht verfügbar. Es wurde kein AI-Guthaben abgezogen.",
        "ai_thinking_fast": "⚡ Ich bereite eine kurze Antwort vor…",
        "ai_thinking_deep": "🧠 Ich durchdenke deine Lernfrage…",
        "ai_thinking_continuation": "💭 Ich knüpfe an unser letztes Gespräch an…",
        "ai_failure": "Ich konnte keine verifizierte Antwort erstellen. Es wurde nichts erfunden.",
    },
    "ja": {
        "access_waitlist": "無料パイロットへの申請を受け付けました。承認後、もう一度 /start を開いてください。",
        "access_blocked": "MY DICTIONARYへのアクセスは停止されています。サポートに連絡してください。",
        "access_pending": "パイロット参加は承認待ちです。/start で確認できます。",
        "access_closed": "現在、MY DICTIONARYはクローズドテスト参加者のみ利用できます。",
        "rate_limited": "操作が多すぎます。{seconds}秒後にもう一度お試しください。",
        "mirror_unavailable": "現在、このアカウントではMirrorを利用できません。",
        "onboarding_required": "先に /start で設定を完了してください。",
        "ai_consent_required": "最新のAI処理同意が必要です。/ai を開いてください。",
        "ai_no_credits": "AIクレジットがありません。/ai_stats で残高を確認してください。",
        "ai_paywall": "AIクレジットがありません。残高：{balance}。",
        "ai_buy_credits": "クレジットを購入",
        "ai_continue_question": "質問を続ける",
        "ai_resume_expired": "この質問は期限切れです。もう一度送信してください。",
        "ai_unavailable_no_charge": "AIチューターは一時的に利用できません。AIクレジットは消費されていません。",
        "ai_thinking_fast": "⚡ 短い回答を準備中…",
        "ai_thinking_deep": "🧠 学習の質問をじっくり考えています…",
        "ai_thinking_continuation": "💭 最近の会話から続けます…",
        "ai_failure": "確認済みの回答を準備できませんでした。推測の回答は表示していません。",
    },
    "ar": {
        "access_waitlist": "تم تسجيل طلبك للنسخة التجريبية المجانية. بعد الموافقة افتح /start مجدداً.",
        "access_blocked": "الوصول إلى MY DICTIONARY محظور. تواصل مع الدعم.",
        "access_pending": "الوصول التجريبي ما زال بانتظار الموافقة. تحقّق عبر /start.",
        "access_closed": "MY DICTIONARY متاح حالياً للمشاركين في الاختبار المغلق فقط.",
        "rate_limited": "إجراءات كثيرة متتالية. حاول بعد {seconds} ثانية.",
        "mirror_unavailable": "Mirror غير متاح لهذا الحساب حالياً.",
        "onboarding_required": "أكمل الإعداد عبر /start أولاً.",
        "ai_consent_required": "يلزم قبول أحدث شروط معالجة AI. افتح /ai.",
        "ai_no_credits": "نفدت أرصدة AI. تحقّق من الرصيد عبر /ai_stats.",
        "ai_paywall": "نفدت أرصدة AI. الرصيد: {balance}.",
        "ai_buy_credits": "شراء أرصدة",
        "ai_continue_question": "متابعة السؤال",
        "ai_resume_expired": "انتهت صلاحية هذا السؤال. أرسله مرة أخرى.",
        "ai_unavailable_no_charge": "مدرّس AI غير متاح مؤقتاً. لم يُخصم أي رصيد AI.",
        "ai_thinking_fast": "⚡ أجهّز إجابة سريعة…",
        "ai_thinking_deep": "🧠 أحلّل سؤالك التعليمي…",
        "ai_thinking_continuation": "💭 أكمل من حوارنا الأخير…",
        "ai_failure": "تعذر إعداد إجابة موثوقة، لذلك لم يتم اختلاق إجابة تعليمية.",
    },
    "zh": {
        "access_waitlist": "免费试用申请已登记。批准后请再次打开 /start。",
        "access_blocked": "MY DICTIONARY 访问已被阻止，请联系支持。",
        "access_pending": "试用访问仍在等待批准，可通过 /start 查看。",
        "access_closed": "MY DICTIONARY 目前仅对封闭测试参与者开放。",
        "rate_limited": "连续操作过多，请在 {seconds} 秒后重试。",
        "mirror_unavailable": "此账户目前无法使用 Mirror。",
        "onboarding_required": "请先通过 /start 完成设置。",
        "ai_consent_required": "需要同意最新的 AI 处理条款，请打开 /ai。",
        "ai_no_credits": "AI 点数已用完，请通过 /ai_stats 查看余额。",
        "ai_paywall": "AI 点数已用完。余额：{balance}。",
        "ai_buy_credits": "购买点数",
        "ai_continue_question": "继续提问",
        "ai_resume_expired": "该问题已过期，请重新发送。",
        "ai_unavailable_no_charge": "AI 导师暂时不可用，未扣除 AI 点数。",
        "ai_thinking_fast": "⚡ 正在准备简短回答…",
        "ai_thinking_deep": "🧠 正在思考你的学习问题…",
        "ai_thinking_continuation": "💭 正在继续我们最近的对话…",
        "ai_failure": "无法生成经过验证的回答，因此没有提供猜测性学习答案。",
    },
    "ru": {
        "access_waitlist": "Заявка на бесплатный пилот принята. После одобрения открой /start ещё раз.",
        "access_blocked": "Доступ к MY DICTIONARY заблокирован. Обратись в поддержку.",
        "access_pending": "Доступ к пилоту ещё не одобрен. Проверь статус через /start.",
        "access_closed": "MY DICTIONARY пока доступен только участникам закрытого тестирования.",
        "rate_limited": "Слишком много действий подряд. Попробуй снова через {seconds} сек.",
        "mirror_unavailable": "Доступ к Mirror сейчас недоступен.",
        "onboarding_required": "Сначала заверши настройку через /start.",
        "ai_consent_required": "Для AI-ответа нужно актуальное согласие через /ai.",
        "ai_no_credits": "AI-кредиты закончились. Проверь баланс через /ai_stats.",
        "ai_paywall": "AI-кредиты закончились. Баланс: {balance}.",
        "ai_buy_credits": "Купить кредиты",
        "ai_continue_question": "Продолжить вопрос",
        "ai_resume_expired": "Этот вопрос устарел. Отправь его ещё раз.",
        "ai_unavailable_no_charge": "AI-репетитор временно недоступен. AI-кредит не списан.",
        "ai_thinking_fast": "⚡ Готовлю короткий ответ…",
        "ai_thinking_deep": "🧠 Продумываю твой учебный вопрос…",
        "ai_thinking_continuation": "💭 Продолжаю наш недавний диалог…",
        "ai_failure": "Не удалось подготовить проверенный ответ. Учебный ответ не был придуман.",
    },
    "es": {
        "access_waitlist": "Tu solicitud para el piloto gratuito está registrada. Tras la aprobación, abre /start de nuevo.",
        "access_blocked": "El acceso a MY DICTIONARY está bloqueado. Contacta con soporte.",
        "access_pending": "El acceso piloto sigue pendiente. Compruébalo con /start.",
        "access_closed": "MY DICTIONARY está disponible por ahora solo para participantes de la prueba cerrada.",
        "rate_limited": "Demasiadas acciones seguidas. Inténtalo en {seconds} s.",
        "mirror_unavailable": "Mirror no está disponible para esta cuenta ahora.",
        "onboarding_required": "Completa primero la configuración con /start.",
        "ai_consent_required": "Se requiere un consentimiento AI actualizado. Abre /ai.",
        "ai_no_credits": "No quedan créditos AI. Consulta el saldo con /ai_stats.",
        "ai_paywall": "Tus créditos AI se han agotado. Saldo: {balance}.",
        "ai_buy_credits": "Comprar créditos",
        "ai_continue_question": "Continuar pregunta",
        "ai_resume_expired": "Esta pregunta ha caducado. Envíala de nuevo.",
        "ai_unavailable_no_charge": "El tutor de IA no está disponible temporalmente. No se cobró ningún crédito de IA.",
        "ai_thinking_fast": "⚡ Preparo una respuesta rápida…",
        "ai_thinking_deep": "🧠 Analizo tu pregunta de aprendizaje…",
        "ai_thinking_continuation": "💭 Continúo nuestra conversación reciente…",
        "ai_failure": "No pude preparar una respuesta verificada. No se inventó una respuesta educativa.",
    },
}

for _locale, _messages in _SERVICE_COPY.items():
    _CATALOG[_locale].update(_messages)


_AI_TUTOR_ACTION_COPY = {
    "en": {
        "ai_tutor_menu_intro": (
            "AI Tutor uses your current lesson and progress. Choose a short "
            "analysis or ask one question. An AI credit is used only when an "
            "answer is generated."
        ),
        "ai_tutor_action_vocabulary": "📚 Vocabulary",
        "ai_tutor_action_mistakes": "🎯 Mistakes",
        "ai_tutor_action_progress": "📊 Progress",
        "ai_tutor_action_ask": "💬 Ask Tutor",
        "ai_tutor_ask_prompt": (
            "Send one question about this lesson or your progress. I’ll answer briefly."
        ),
        "ai_tutor_question_vocabulary": (
            "Analyze my current lesson and progress. In at most two short bullets, "
            "name the most useful pattern in my known or weak vocabulary and give "
            "one next step. If the data is missing, say so; do not invent facts."
        ),
        "ai_tutor_question_mistakes": (
            "Analyze my current lesson and recorded progress. In at most two short "
            "bullets, name my main observed error pattern and give one next step. "
            "If no mistakes are recorded, say so; do not invent facts."
        ),
        "ai_tutor_question_progress": (
            "Analyze my learning progress. In at most two short bullets, separate "
            "measured facts from one next step. If progress data is missing, say so; "
            "do not invent facts."
        ),
        "ai_tutor_pending_stale": (
            "That Tutor question has expired. Your message will be handled normally."
        ),
    },
    "fr": {
        "ai_tutor_menu_intro": (
            "Le tuteur IA utilise votre leçon et vos progrès actuels. Choisissez "
            "une analyse courte ou posez une question. Un crédit IA n’est utilisé "
            "que lorsqu’une réponse est générée."
        ),
        "ai_tutor_action_vocabulary": "📚 Vocabulaire",
        "ai_tutor_action_mistakes": "🎯 Erreurs",
        "ai_tutor_action_progress": "📊 Progrès",
        "ai_tutor_action_ask": "💬 Poser une question",
        "ai_tutor_ask_prompt": (
            "Envoyez une question sur cette leçon ou vos progrès. Je répondrai brièvement."
        ),
        "ai_tutor_question_vocabulary": (
            "Analyse ma leçon et mes progrès actuels. En deux points courts maximum, "
            "indique le schéma le plus utile dans mon vocabulaire connu ou fragile, "
            "puis une prochaine étape. Si les données manquent, dis-le sans rien inventer."
        ),
        "ai_tutor_question_mistakes": (
            "Analyse ma leçon et mes progrès enregistrés. En deux points courts maximum, "
            "indique mon principal type d’erreur observé, puis une prochaine étape. "
            "Si aucune erreur n’est enregistrée, dis-le sans rien inventer."
        ),
        "ai_tutor_question_progress": (
            "Analyse mes progrès. En deux points courts maximum, sépare les faits "
            "mesurés d’une prochaine étape. Si les données manquent, dis-le sans rien inventer."
        ),
        "ai_tutor_pending_stale": (
            "Cette question au tuteur a expiré. Votre message sera traité normalement."
        ),
    },
    "de": {
        "ai_tutor_menu_intro": (
            "Der KI-Tutor nutzt deine aktuelle Lektion und deinen Fortschritt. "
            "Wähle eine kurze Analyse oder stelle eine Frage. Ein KI-Guthaben wird "
            "nur verbraucht, wenn eine Antwort erzeugt wird."
        ),
        "ai_tutor_action_vocabulary": "📚 Wortschatz",
        "ai_tutor_action_mistakes": "🎯 Fehler",
        "ai_tutor_action_progress": "📊 Fortschritt",
        "ai_tutor_action_ask": "💬 Tutor fragen",
        "ai_tutor_ask_prompt": (
            "Sende eine Frage zu dieser Lektion oder deinem Fortschritt. Ich antworte kurz."
        ),
        "ai_tutor_question_vocabulary": (
            "Analysiere meine aktuelle Lektion und meinen Fortschritt. Nenne in höchstens "
            "zwei kurzen Punkten das nützlichste Muster in meinem bekannten oder schwachen "
            "Wortschatz und einen nächsten Schritt. Fehlende Daten nicht erfinden."
        ),
        "ai_tutor_question_mistakes": (
            "Analysiere meine aktuelle Lektion und den erfassten Fortschritt. Nenne in "
            "höchstens zwei kurzen Punkten mein wichtigstes beobachtetes Fehlermuster und "
            "einen nächsten Schritt. Wenn keine Fehler erfasst sind, sage es."
        ),
        "ai_tutor_question_progress": (
            "Analysiere meinen Lernfortschritt. Trenne in höchstens zwei kurzen Punkten "
            "gemessene Fakten von einem nächsten Schritt. Fehlende Daten nicht erfinden."
        ),
        "ai_tutor_pending_stale": (
            "Diese Tutor-Frage ist abgelaufen. Deine Nachricht wird normal verarbeitet."
        ),
    },
    "ja": {
        "ai_tutor_menu_intro": (
            "AIチューターは現在のレッスンと進捗を使います。短い分析を選ぶか、質問を1つ送ってください。"
            "AIクレジットは回答が生成されたときだけ使われます。"
        ),
        "ai_tutor_action_vocabulary": "📚 単語を分析",
        "ai_tutor_action_mistakes": "🎯 間違いを分析",
        "ai_tutor_action_progress": "📊 進捗を分析",
        "ai_tutor_action_ask": "💬 質問する",
        "ai_tutor_ask_prompt": (
            "このレッスンや進捗について質問を1つ送ってください。短く答えます。"
        ),
        "ai_tutor_question_vocabulary": (
            "現在のレッスンと進捗を分析し、覚えた単語または苦手な単語の最も役立つ傾向と次の一歩を、"
            "短い2項目以内で示してください。データがなければそう伝え、推測しないでください。"
        ),
        "ai_tutor_question_mistakes": (
            "現在のレッスンと記録済みの進捗を分析し、主な間違いの傾向と次の一歩を短い2項目以内で"
            "示してください。間違いの記録がなければそう伝え、推測しないでください。"
        ),
        "ai_tutor_question_progress": (
            "学習進捗を分析し、測定済みの事実と次の一歩を短い2項目以内で分けて示してください。"
            "データがなければそう伝え、推測しないでください。"
        ),
        "ai_tutor_pending_stale": (
            "チューターへの質問は期限切れです。このメッセージは通常どおり処理されます。"
        ),
    },
    "ar": {
        "ai_tutor_menu_intro": (
            "يستخدم مدرس الذكاء الاصطناعي درسك الحالي وتقدمك. اختر تحليلاً قصيراً أو اطرح "
            "سؤالاً واحداً. يُستخدم رصيد AI فقط عند إنشاء إجابة."
        ),
        "ai_tutor_action_vocabulary": "📚 المفردات",
        "ai_tutor_action_mistakes": "🎯 الأخطاء",
        "ai_tutor_action_progress": "📊 التقدم",
        "ai_tutor_action_ask": "💬 اسأل المدرس",
        "ai_tutor_ask_prompt": (
            "أرسل سؤالاً واحداً عن هذا الدرس أو تقدمك. سأجيب باختصار."
        ),
        "ai_tutor_question_vocabulary": (
            "حلل درسي الحالي وتقدمي. في نقطتين قصيرتين كحد أقصى، اذكر أهم نمط في "
            "مفرداتي المعروفة أو الضعيفة وخطوة تالية واحدة. إذا غابت البيانات فاذكر ذلك ولا تخترع حقائق."
        ),
        "ai_tutor_question_mistakes": (
            "حلل درسي الحالي والتقدم المسجل. في نقطتين قصيرتين كحد أقصى، اذكر نمط الخطأ "
            "الرئيسي الملحوظ وخطوة تالية واحدة. إذا لم تُسجل أخطاء فاذكر ذلك ولا تخترع حقائق."
        ),
        "ai_tutor_question_progress": (
            "حلل تقدمي في التعلم. في نقطتين قصيرتين كحد أقصى، افصل الحقائق المقاسة عن "
            "خطوة تالية واحدة. إذا غابت البيانات فاذكر ذلك ولا تخترع حقائق."
        ),
        "ai_tutor_pending_stale": (
            "انتهت مهلة سؤال المدرس. ستُعالج رسالتك بالطريقة المعتادة."
        ),
    },
    "zh": {
        "ai_tutor_menu_intro": (
            "AI 导师会参考你当前的课程和进度。请选择一项简短分析，或发送一个问题。"
            "只有生成 AI 回答时才会使用一个点数。"
        ),
        "ai_tutor_action_vocabulary": "📚 分析词汇",
        "ai_tutor_action_mistakes": "🎯 分析错误",
        "ai_tutor_action_progress": "📊 分析进度",
        "ai_tutor_action_ask": "💬 提问",
        "ai_tutor_ask_prompt": (
            "请发送一个关于本课或学习进度的问题。我会简短回答。"
        ),
        "ai_tutor_question_vocabulary": (
            "分析我当前的课程和进度。最多用两个简短要点，指出已掌握或薄弱词汇中最有用的规律，"
            "并给出一个下一步。缺少数据时请明确说明，不要编造。"
        ),
        "ai_tutor_question_mistakes": (
            "分析我当前的课程和已记录进度。最多用两个简短要点，指出主要的已观察错误规律，"
            "并给出一个下一步。若没有错误记录，请明确说明，不要编造。"
        ),
        "ai_tutor_question_progress": (
            "分析我的学习进度。最多用两个简短要点，将已测量事实与一个下一步分开。"
            "缺少数据时请明确说明，不要编造。"
        ),
        "ai_tutor_pending_stale": (
            "该导师提问已过期。你的消息将按普通消息处理。"
        ),
    },
    "ru": {
        "ai_tutor_menu_intro": (
            "AI-тьютор учитывает текущий урок и твой прогресс. Выбери короткий "
            "анализ или задай один вопрос. AI-кредит списывается только при создании ответа."
        ),
        "ai_tutor_action_vocabulary": "📚 Словарь",
        "ai_tutor_action_mistakes": "🎯 Ошибки",
        "ai_tutor_action_progress": "📊 Прогресс",
        "ai_tutor_action_ask": "💬 Спросить тьютора",
        "ai_tutor_ask_prompt": (
            "Отправь один вопрос об этом уроке или своём прогрессе. Я отвечу кратко."
        ),
        "ai_tutor_question_vocabulary": (
            "Проанализируй мой текущий урок и прогресс. Не более чем в двух коротких "
            "пунктах назови самый полезный паттерн в знакомых или слабых словах и один "
            "следующий шаг. Если данных нет, скажи об этом и ничего не выдумывай."
        ),
        "ai_tutor_question_mistakes": (
            "Проанализируй мой текущий урок и сохранённый прогресс. Не более чем в двух "
            "коротких пунктах назови главный замеченный тип ошибки и один следующий шаг. "
            "Если ошибок не записано, скажи об этом и ничего не выдумывай."
        ),
        "ai_tutor_question_progress": (
            "Проанализируй мой прогресс в обучении. Не более чем в двух коротких пунктах "
            "отдели измеренные факты от одного следующего шага. Если данных нет, скажи "
            "об этом и ничего не выдумывай."
        ),
        "ai_tutor_pending_stale": (
            "Вопрос тьютору устарел. Сообщение будет обработано в обычном режиме."
        ),
    },
    "es": {
        "ai_tutor_menu_intro": (
            "El tutor de IA usa tu lección y progreso actuales. Elige un análisis "
            "breve o haz una pregunta. Solo se usa un crédito de IA al generar una respuesta."
        ),
        "ai_tutor_action_vocabulary": "📚 Vocabulario",
        "ai_tutor_action_mistakes": "🎯 Errores",
        "ai_tutor_action_progress": "📊 Progreso",
        "ai_tutor_action_ask": "💬 Preguntar",
        "ai_tutor_ask_prompt": (
            "Envía una pregunta sobre esta lección o tu progreso. Responderé brevemente."
        ),
        "ai_tutor_question_vocabulary": (
            "Analiza mi lección y progreso actuales. En dos puntos breves como máximo, "
            "indica el patrón más útil de mi vocabulario conocido o débil y un siguiente "
            "paso. Si faltan datos, dilo sin inventar hechos."
        ),
        "ai_tutor_question_mistakes": (
            "Analiza mi lección y progreso registrados. En dos puntos breves como máximo, "
            "indica mi principal patrón de error observado y un siguiente paso. Si no hay "
            "errores registrados, dilo sin inventar hechos."
        ),
        "ai_tutor_question_progress": (
            "Analiza mi progreso de aprendizaje. En dos puntos breves como máximo, separa "
            "los hechos medidos de un siguiente paso. Si faltan datos, dilo sin inventar hechos."
        ),
        "ai_tutor_pending_stale": (
            "Esa pregunta al tutor ha caducado. Tu mensaje se procesará con normalidad."
        ),
    },
}

for _locale, _messages in _AI_TUTOR_ACTION_COPY.items():
    _CATALOG[_locale].update(_messages)


_AI_TUTOR_ECONOMICS_COPY = {
    "en": {
        "ai_tutor_economics_intro": "✨ AI Tutor — chat and credit packs",
        "ai_tutor_economics_balance": "Balance: {balance} AI credits.",
        "ai_tutor_economics_balance_unavailable": "Balance is temporarily unavailable.",
        "ai_tutor_economics_policy": (
            "One successfully generated AI answer costs 1 AI credit. "
            "A failed or rejected answer costs 0."
        ),
        "ai_tutor_economics_purchase_unavailable": "Credit purchases are currently unavailable.",
        "ai_tutor_action_start_lesson": "📚 Start a lesson",
        "ai_tutor_general_ask_prompt": (
            "You can chat freely with Tutor about language learning or your progress. "
            "Write any question, or choose an example below."
        ),
        "ai_tutor_starter_today": "🗓️ Today's summary",
        "ai_tutor_starter_today_question": (
            "Give me a brief summary of my learning today. Mention what I practiced, "
            "what improved, and one next step. If today's data is missing, say so and "
            "do not invent facts."
        ),
        "ai_tutor_starter_review": "🎯 What to review",
        "ai_tutor_starter_review_question": (
            "Based only on my saved progress, what should I review next? Give me up to "
            "three short priorities. If data is missing, say so and do not invent facts."
        ),
        "ai_tutor_starter_quiz": "🧠 Quick quiz",
        "ai_tutor_starter_quiz_question": (
            "Give me one short quiz question based on my current learning context, then "
            "wait for my answer. If context is missing, say so and do not invent facts."
        ),
    },
    "fr": {
        "ai_tutor_economics_intro": "✨ Tuteur IA — discussion et packs de crédits",
        "ai_tutor_economics_balance": "Solde : {balance} crédits IA.",
        "ai_tutor_economics_balance_unavailable": "Le solde est temporairement indisponible.",
        "ai_tutor_economics_policy": (
            "Une réponse IA générée avec succès coûte 1 crédit IA. "
            "Une réponse échouée ou rejetée coûte 0."
        ),
        "ai_tutor_economics_purchase_unavailable": "L’achat de crédits est actuellement indisponible.",
        "ai_tutor_action_start_lesson": "📚 Commencer une leçon",
        "ai_tutor_general_ask_prompt": (
            "Vous pouvez discuter librement avec le tuteur de votre apprentissage ou de "
            "vos progrès. Écrivez votre question ou choisissez un exemple ci-dessous."
        ),
        "ai_tutor_starter_today": "🗓️ Résumé du jour",
        "ai_tutor_starter_today_question": (
            "Donne-moi un bref résumé de mon apprentissage aujourd’hui. Indique ce que "
            "j’ai travaillé, ce qui s’est amélioré et une prochaine étape. Si les données "
            "du jour manquent, dis-le sans rien inventer."
        ),
        "ai_tutor_starter_review": "🎯 À réviser",
        "ai_tutor_starter_review_question": (
            "D’après mes progrès enregistrés uniquement, que dois-je réviser ensuite ? "
            "Donne au maximum trois priorités courtes. Si les données manquent, dis-le "
            "sans rien inventer."
        ),
        "ai_tutor_starter_quiz": "🧠 Quiz rapide",
        "ai_tutor_starter_quiz_question": (
            "Pose-moi une courte question de quiz à partir de mon apprentissage actuel, "
            "puis attends ma réponse. Si le contexte manque, dis-le sans rien inventer."
        ),
    },
    "de": {
        "ai_tutor_economics_intro": "✨ KI-Tutor — Chat und Guthabenpakete",
        "ai_tutor_economics_balance": "Guthaben: {balance} KI-Credits.",
        "ai_tutor_economics_balance_unavailable": "Das Guthaben ist vorübergehend nicht verfügbar.",
        "ai_tutor_economics_policy": (
            "Eine erfolgreich erzeugte KI-Antwort kostet 1 KI-Credit. "
            "Eine fehlgeschlagene oder abgelehnte Antwort kostet 0."
        ),
        "ai_tutor_economics_purchase_unavailable": "Der Kauf von Credits ist derzeit nicht verfügbar.",
        "ai_tutor_action_start_lesson": "📚 Lektion starten",
        "ai_tutor_general_ask_prompt": (
            "Du kannst frei mit dem Tutor über dein Sprachenlernen oder deinen Fortschritt "
            "sprechen. Schreibe eine Frage oder wähle unten ein Beispiel."
        ),
        "ai_tutor_starter_today": "🗓️ Tagesrückblick",
        "ai_tutor_starter_today_question": (
            "Gib mir eine kurze Zusammenfassung meines heutigen Lernens. Nenne, was ich "
            "geübt habe, was sich verbessert hat und einen nächsten Schritt. Wenn heutige "
            "Daten fehlen, sage es und erfinde nichts."
        ),
        "ai_tutor_starter_review": "🎯 Was wiederholen?",
        "ai_tutor_starter_review_question": (
            "Was sollte ich anhand meines gespeicherten Fortschritts als Nächstes "
            "wiederholen? Nenne höchstens drei kurze Prioritäten. Fehlende Daten nicht erfinden."
        ),
        "ai_tutor_starter_quiz": "🧠 Kurzes Quiz",
        "ai_tutor_starter_quiz_question": (
            "Stelle mir eine kurze Quizfrage aus meinem aktuellen Lernkontext und warte "
            "dann auf meine Antwort. Wenn Kontext fehlt, sage es und erfinde nichts."
        ),
    },
    "ja": {
        "ai_tutor_economics_intro": "✨ AIチューター — チャットとクレジットパック",
        "ai_tutor_economics_balance": "残高：AIクレジット {balance}。",
        "ai_tutor_economics_balance_unavailable": "残高は一時的に確認できません。",
        "ai_tutor_economics_policy": (
            "正常に生成されたAI回答1件につきAIクレジットを1使用します。"
            "失敗または拒否された回答は0です。"
        ),
        "ai_tutor_economics_purchase_unavailable": "現在、クレジットは購入できません。",
        "ai_tutor_action_start_lesson": "📚 レッスンを始める",
        "ai_tutor_general_ask_prompt": (
            "語学学習や進捗について、チューターと自由に話せます。質問を書くか、下の例を選んでください。"
        ),
        "ai_tutor_starter_today": "🗓️ 今日のまとめ",
        "ai_tutor_starter_today_question": (
            "今日の学習を短くまとめてください。練習したこと、上達したこと、次の一歩を示してください。"
            "今日のデータがなければそう伝え、推測しないでください。"
        ),
        "ai_tutor_starter_review": "🎯 次に復習すること",
        "ai_tutor_starter_review_question": (
            "保存された進捗だけを使い、次に何を復習すべきか短い3項目以内で教えてください。"
            "データがなければそう伝え、推測しないでください。"
        ),
        "ai_tutor_starter_quiz": "🧠 ミニクイズ",
        "ai_tutor_starter_quiz_question": (
            "現在の学習内容から短いクイズを1問出し、私の答えを待ってください。"
            "内容がなければそう伝え、推測しないでください。"
        ),
    },
    "ar": {
        "ai_tutor_economics_intro": "✨ مدرس AI — المحادثة وباقات الرصيد",
        "ai_tutor_economics_balance": "الرصيد: {balance} من أرصدة AI.",
        "ai_tutor_economics_balance_unavailable": "الرصيد غير متاح مؤقتاً.",
        "ai_tutor_economics_policy": (
            "تكلّف كل إجابة AI تُنشأ بنجاح رصيد AI واحداً. "
            "الإجابة الفاشلة أو المرفوضة تكلّف صفراً."
        ),
        "ai_tutor_economics_purchase_unavailable": "شراء الرصيد غير متاح حالياً.",
        "ai_tutor_action_start_lesson": "📚 ابدأ درساً",
        "ai_tutor_general_ask_prompt": (
            "يمكنك التحدث بحرية مع المدرس عن تعلم اللغة أو تقدمك. اكتب أي سؤال أو اختر مثالاً أدناه."
        ),
        "ai_tutor_starter_today": "🗓️ ملخص اليوم",
        "ai_tutor_starter_today_question": (
            "أعطني ملخصاً قصيراً لتعلمي اليوم: ما الذي تدربت عليه، وما الذي تحسن، وخطوة تالية واحدة. "
            "إذا لم تتوفر بيانات اليوم فاذكر ذلك ولا تخترع حقائق."
        ),
        "ai_tutor_starter_review": "🎯 ماذا أراجع؟",
        "ai_tutor_starter_review_question": (
            "استناداً فقط إلى تقدمي المحفوظ، ماذا أراجع بعد ذلك؟ أعطني ثلاث أولويات قصيرة كحد أقصى. "
            "إذا غابت البيانات فاذكر ذلك ولا تخترع حقائق."
        ),
        "ai_tutor_starter_quiz": "🧠 اختبار سريع",
        "ai_tutor_starter_quiz_question": (
            "اطرح علي سؤال اختبار قصيراً من سياق تعلمي الحالي ثم انتظر إجابتي. "
            "إذا غاب السياق فاذكر ذلك ولا تخترع حقائق."
        ),
    },
    "zh": {
        "ai_tutor_economics_intro": "✨ AI 导师 — 对话与点数包",
        "ai_tutor_economics_balance": "余额：{balance} 个 AI 点数。",
        "ai_tutor_economics_balance_unavailable": "暂时无法查看余额。",
        "ai_tutor_economics_policy": (
            "每个成功生成的 AI 回答消耗 1 个 AI 点数。"
            "生成失败或被拒绝的回答消耗 0 个。"
        ),
        "ai_tutor_economics_purchase_unavailable": "目前无法购买点数。",
        "ai_tutor_action_start_lesson": "📚 开始课程",
        "ai_tutor_general_ask_prompt": (
            "你可以自由地与导师聊语言学习或学习进度。输入任何问题，或选择下面的示例。"
        ),
        "ai_tutor_starter_today": "🗓️ 今日总结",
        "ai_tutor_starter_today_question": (
            "请简短总结我今天的学习：练习了什么、哪些方面有进步，以及下一步。"
            "如果没有今天的数据，请明确说明，不要编造。"
        ),
        "ai_tutor_starter_review": "🎯 接下来复习什么",
        "ai_tutor_starter_review_question": (
            "只根据已保存的进度，我接下来应该复习什么？最多给出三个简短重点。"
            "如果缺少数据，请明确说明，不要编造。"
        ),
        "ai_tutor_starter_quiz": "🧠 快速测验",
        "ai_tutor_starter_quiz_question": (
            "根据我当前的学习内容出一道简短测验题，然后等待我的回答。"
            "如果缺少上下文，请明确说明，不要编造。"
        ),
    },
    "ru": {
        "ai_tutor_economics_intro": "✨ AI-тьютор — чат и пакеты кредитов",
        "ai_tutor_economics_balance": "Баланс: {balance} AI-кредитов.",
        "ai_tutor_economics_balance_unavailable": "Баланс временно недоступен.",
        "ai_tutor_economics_policy": (
            "Один успешно созданный AI-ответ стоит 1 AI-кредит. "
            "Неудачный или отклонённый ответ стоит 0."
        ),
        "ai_tutor_economics_purchase_unavailable": "Покупка кредитов сейчас недоступна.",
        "ai_tutor_action_start_lesson": "📚 Начать урок",
        "ai_tutor_general_ask_prompt": (
            "С тьютором можно свободно общаться об изучении языка и своём прогрессе. "
            "Напиши любой вопрос или выбери готовый пример ниже."
        ),
        "ai_tutor_starter_today": "🗓️ Итог за сегодня",
        "ai_tutor_starter_today_question": (
            "Дай краткое резюме моего обучения за сегодня: что я практиковал, что "
            "улучшилось и какой следующий шаг. Если данных за сегодня нет, скажи об "
            "этом и ничего не выдумывай."
        ),
        "ai_tutor_starter_review": "🎯 Что повторить",
        "ai_tutor_starter_review_question": (
            "Только по моему сохранённому прогрессу скажи, что повторить дальше. Дай до "
            "трёх коротких приоритетов. Если данных нет, скажи об этом и ничего не выдумывай."
        ),
        "ai_tutor_starter_quiz": "🧠 Короткий квиз",
        "ai_tutor_starter_quiz_question": (
            "Задай мне один короткий вопрос по текущему учебному контексту и дождись "
            "моего ответа. Если контекста нет, скажи об этом и ничего не выдумывай."
        ),
    },
    "es": {
        "ai_tutor_economics_intro": "✨ Tutor de IA — chat y paquetes de créditos",
        "ai_tutor_economics_balance": "Saldo: {balance} créditos de IA.",
        "ai_tutor_economics_balance_unavailable": "El saldo no está disponible temporalmente.",
        "ai_tutor_economics_policy": (
            "Una respuesta de IA generada correctamente cuesta 1 crédito de IA. "
            "Una respuesta fallida o rechazada cuesta 0."
        ),
        "ai_tutor_economics_purchase_unavailable": "La compra de créditos no está disponible ahora.",
        "ai_tutor_action_start_lesson": "📚 Empezar una lección",
        "ai_tutor_general_ask_prompt": (
            "Puedes hablar libremente con el tutor sobre idiomas o tu progreso. "
            "Escribe cualquier pregunta o elige un ejemplo de abajo."
        ),
        "ai_tutor_starter_today": "🗓️ Resumen de hoy",
        "ai_tutor_starter_today_question": (
            "Dame un resumen breve de mi aprendizaje de hoy: qué practiqué, qué mejoró "
            "y un siguiente paso. Si faltan datos de hoy, dilo sin inventar hechos."
        ),
        "ai_tutor_starter_review": "🎯 Qué repasar",
        "ai_tutor_starter_review_question": (
            "Basándote solo en mi progreso guardado, ¿qué debo repasar ahora? Dame hasta "
            "tres prioridades breves. Si faltan datos, dilo sin inventar hechos."
        ),
        "ai_tutor_starter_quiz": "🧠 Quiz rápido",
        "ai_tutor_starter_quiz_question": (
            "Hazme una pregunta corta de quiz basada en mi aprendizaje actual y espera "
            "mi respuesta. Si falta contexto, dilo sin inventar hechos."
        ),
    },
}

for _locale, _messages in _AI_TUTOR_ECONOMICS_COPY.items():
    _CATALOG[_locale].update(_messages)


_ZERKALO_COMMUNICATION_COPY = {
    "en": {
        "mirror_progress_facts": "Accuracy {accuracy}% · {tracked} words · {due} due · {streak}-day streak.",
        "mirror_progress_focus_weak": "Focus now: review “{term}”.",
        "mirror_progress_focus_due": "Focus now: complete {due} due reviews.",
        "mirror_progress_no_history": "There is not enough learning history yet.",
        "mirror_progress_focus_starter": "Start one short five-word lesson.",
    },
    "fr": {
        "mirror_progress_facts": "Précision {accuracy} % · {tracked} mots · {due} à réviser · série de {streak} jours.",
        "mirror_progress_focus_weak": "Priorité : révisez « {term} ».",
        "mirror_progress_focus_due": "Priorité : terminez les {due} révisions prévues.",
        "mirror_progress_no_history": "Il n’y a pas encore assez d’historique d’apprentissage.",
        "mirror_progress_focus_starter": "Commencez une courte leçon de cinq mots.",
    },
    "de": {
        "mirror_progress_facts": "Genauigkeit {accuracy} % · {tracked} Wörter · {due} fällig · Serie: {streak} Tage.",
        "mirror_progress_focus_weak": "Fokus jetzt: „{term}“ wiederholen.",
        "mirror_progress_focus_due": "Fokus jetzt: {due} fällige Wiederholungen abschließen.",
        "mirror_progress_no_history": "Es gibt noch nicht genug Lernverlauf.",
        "mirror_progress_focus_starter": "Starte eine kurze Lektion mit fünf Wörtern.",
    },
    "ja": {
        "mirror_progress_facts": "正答率 {accuracy}%・学習語 {tracked}・復習 {due}・連続 {streak}日。",
        "mirror_progress_focus_weak": "今の重点：「{term}」を復習しましょう。",
        "mirror_progress_focus_due": "今の重点：期限の来た復習を {due} 件終えましょう。",
        "mirror_progress_no_history": "学習履歴はまだ十分にありません。",
        "mirror_progress_focus_starter": "5語の短いレッスンを始めましょう。",
    },
    "ar": {
        "mirror_progress_facts": "الدقة {accuracy}% · الكلمات {tracked} · للمراجعة {due} · السلسلة {streak} أيام.",
        "mirror_progress_focus_weak": "التركيز الآن: راجع «{term}».",
        "mirror_progress_focus_due": "التركيز الآن: أكمل {due} مراجعات مستحقة.",
        "mirror_progress_no_history": "لا يوجد سجل تعلم كافٍ بعد.",
        "mirror_progress_focus_starter": "ابدأ درساً قصيراً من خمس كلمات.",
    },
    "zh": {
        "mirror_progress_facts": "正确率 {accuracy}% · 已学 {tracked} 词 · 待复习 {due} · 连续 {streak} 天。",
        "mirror_progress_focus_weak": "当前重点：复习“{term}”。",
        "mirror_progress_focus_due": "当前重点：完成 {due} 项到期复习。",
        "mirror_progress_no_history": "目前还没有足够的学习记录。",
        "mirror_progress_focus_starter": "先开始一节五词短课。",
    },
    "ru": {
        "mirror_progress_facts": "Точность {accuracy}% · слов {tracked} · к повторению {due} · серия {streak} дн.",
        "mirror_progress_focus_weak": "Сейчас фокус: повтори «{term}».",
        "mirror_progress_focus_due": "Сейчас фокус: пройди {due} запланированных повторения.",
        "mirror_progress_no_history": "Данных об обучении пока недостаточно.",
        "mirror_progress_focus_starter": "Начни короткий урок из пяти слов.",
    },
    "es": {
        "mirror_progress_facts": "Precisión {accuracy}% · {tracked} palabras · {due} pendientes · racha de {streak} días.",
        "mirror_progress_focus_weak": "Enfócate ahora en repasar «{term}».",
        "mirror_progress_focus_due": "Enfócate ahora en completar {due} repasos pendientes.",
        "mirror_progress_no_history": "Todavía no hay suficiente historial de aprendizaje.",
        "mirror_progress_focus_starter": "Empieza una lección corta de cinco palabras.",
    },
}

for _locale, _messages in _ZERKALO_COMMUNICATION_COPY.items():
    _CATALOG[_locale].update(_messages)


_AI_RESPONSE_EXPERIENCE_COPY = {
    "en": {
        "mirror_capability_greeting": (
            "👋 Hi! I’m ready to help with your language learning.\n\n"
            "💡 Ask about a word, lesson, mistakes, or your progress."
        ),
    },
    "fr": {
        "mirror_capability_greeting": (
            "👋 Bonjour ! Je suis prêt à vous aider dans votre apprentissage.\n\n"
            "💡 Posez une question sur un mot, une leçon, vos erreurs ou vos progrès."
        ),
    },
    "de": {
        "mirror_capability_greeting": (
            "👋 Hallo! Ich helfe dir gern beim Sprachenlernen.\n\n"
            "💡 Frag nach einem Wort, einer Lektion, deinen Fehlern oder deinem Fortschritt."
        ),
    },
    "ja": {
        "mirror_capability_greeting": (
            "👋 こんにちは！語学学習をお手伝いします。\n\n"
            "💡 単語、レッスン、間違い、進捗について質問してください。"
        ),
    },
    "ar": {
        "mirror_capability_greeting": (
            "👋 مرحباً! أنا مستعد لمساعدتك في تعلم اللغة.\n\n"
            "💡 اسأل عن كلمة أو درس أو أخطائك أو تقدمك."
        ),
    },
    "zh": {
        "mirror_capability_greeting": (
            "👋 你好！我可以帮助你学习语言。\n\n"
            "💡 可以问我单词、课程、错误或学习进度。"
        ),
    },
    "ru": {
        "mirror_capability_greeting": (
            "👋 Привет! Я готов помочь тебе с изучением языка.\n\n"
            "💡 Спроси о слове, уроке, ошибках или своём прогрессе."
        ),
    },
    "es": {
        "mirror_capability_greeting": (
            "👋 ¡Hola! Estoy listo para ayudarte a aprender idiomas.\n\n"
            "💡 Pregunta por una palabra, una lección, tus errores o tu progreso."
        ),
    },
}

for _locale, _messages in _AI_RESPONSE_EXPERIENCE_COPY.items():
    _CATALOG[_locale].update(_messages)


def normalize_locale(value: str | None, *, fallback: str = DEFAULT_INTERFACE_LOCALE) -> str:
    """Normalize Telegram language_code without guessing unsupported locales."""
    safe_fallback = fallback if fallback in INTERFACE_LOCALES else DEFAULT_INTERFACE_LOCALE
    candidate = str(value or "").strip().lower().replace("_", "-")
    if candidate.startswith("zh"):
        return "zh"
    language = candidate.split("-", 1)[0]
    return language if language in INTERFACE_LOCALES else safe_fallback


def require_interface_locale(value: str) -> str:
    """Normalize a declared locale and reject unsupported language codes."""
    candidate = str(value or "").strip().lower().replace("_", "-")
    language = "zh" if candidate.startswith("zh") else candidate.split("-", 1)[0]
    if language not in INTERFACE_LOCALES:
        raise ValueError("Unsupported interface locale")
    return language


def translate(key: str, locale: str | None, **values: Any) -> str:
    selected = normalize_locale(locale)
    try:
        template = _CATALOG[selected][key]
    except KeyError as exc:
        raise KeyError(f"Unknown localization key: {key}") from exc
    return template.format(**values)


def billing_product_display_copy(
    product_id: str,
    locale: str | None,
    *,
    title: str,
    description: str,
    credits: int,
) -> tuple[str, str]:
    """Localize known billing display copy without changing canonical data."""
    selected = normalize_locale(locale)
    product_copy = _BILLING_PRODUCT_COPY[selected].get(str(product_id))
    if product_copy is None or selected == "ru":
        return str(title), str(description)
    localized_title, localized_description = product_copy
    return localized_title, localized_description.format(credits=int(credits))


def language_name(language: str | None, locale: str | None) -> str:
    selected = normalize_locale(locale)
    code = str(language or "").strip().lower()
    return _LANGUAGE_NAMES[selected].get(code, code or _LANGUAGE_NAMES[selected]["en"])


def response_language_instruction(locale: str | None) -> str:
    selected = normalize_locale(locale)
    return (
        f"Respond only in {_RESPONSE_LANGUAGE_NAMES[selected]}. "
        "Keep words and examples from the learning language unchanged, then "
        "explain them in the response language."
    )


def catalog_is_complete() -> bool:
    reference = set(_CATALOG[DEFAULT_INTERFACE_LOCALE])
    formatter = Formatter()
    reference_fields = {
        key: {
            field_name
            for _, field_name, _, _ in formatter.parse(value)
            if field_name is not None
        }
        for key, value in _CATALOG[DEFAULT_INTERFACE_LOCALE].items()
    }
    return set(_CATALOG) == set(INTERFACE_LOCALES) and all(
        set(values) == reference
        and all(str(text).strip() for text in values.values())
        and all(
            {
                field_name
                for _, field_name, _, _ in formatter.parse(values[key])
                if field_name is not None
            }
            == reference_fields[key]
            for key in reference
        )
        for values in _CATALOG.values()
    )
