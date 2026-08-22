"""Small, deterministic locale catalog for the Telegram product surface."""

from __future__ import annotations

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
        "ai_limit_reached": "The AI safety limit is active. Try again later.",
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
        "ai_limit_reached": "La limite de sécurité AI est active. Réessayez plus tard.",
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
        "ai_limit_reached": "Das AI-Sicherheitslimit ist aktiv. Versuche es später erneut.",
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
        "ai_limit_reached": "AIの安全上限に達しました。後でもう一度お試しください。",
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
        "ai_limit_reached": "حد أمان AI نشط. حاول لاحقاً.",
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
        "ai_limit_reached": "AI 安全限制已启用，请稍后再试。",
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
        "ai_limit_reached": "Сработал защитный лимит AI. Попробуй позже.",
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
        "ai_limit_reached": "El límite de seguridad de AI está activo. Inténtalo más tarde.",
        "ai_failure": "No pude preparar una respuesta verificada. No se inventó una respuesta educativa.",
    },
}

for _locale, _messages in _SERVICE_COPY.items():
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
    return set(_CATALOG) == set(INTERFACE_LOCALES) and all(
        set(values) == reference and all(str(text).strip() for text in values.values())
        for values in _CATALOG.values()
    )
