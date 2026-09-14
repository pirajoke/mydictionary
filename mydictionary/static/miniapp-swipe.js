(() => {
  "use strict";
  // A deliberately small controller; the server owns the queue and every score.
  const keys = ["title", "hint", "mix", "forgotten", "new", "start", "reveal", "hide", "again", "know", "undo", "retry", "speak", "keyboard", "loading", "saving", "error", "auth", "empty", "done", "restart", "stale", "wait", "language"];
  const translations = {
    en: ["Keep words in mind", "Your reviews and new words. One card at a time.", "Smart mix", "Review", "New", "Start swiping", "Show meaning", "Hide meaning", "← Again", "Know →", "Undo last answer", "Try again", "Listen", "Swipe left: again · right: know. Space: flip.", "Preparing your deck…", "Saving…", "Could not save. Your card stays here — try again.", "Reopen Lexi in Telegram to continue.", "No words in this mode yet. Try another mode or language.", "Session complete!\n{known} known · {again} to practise\n+{xp} XP", "Another session", "Progress changed. Start a fresh deck; saved answers are safe.", "Too many requests. Please wait and retry.", "Change language"],
    ru: ["Вернём слова в память", "Твои повторения и новые слова. По одной карточке.", "Умный микс", "Повторить", "Новые", "Начать свайпы", "Показать значение", "Скрыть значение", "← Ещё раз", "Знаю →", "Отменить ответ", "Повторить запрос", "Слушать", "Влево — ещё раз · вправо — знаю. Пробел — переворот.", "Собираю твою колоду…", "Сохраняю…", "Не удалось сохранить. Карточка на месте — повтори запрос.", "Открой Lexi заново в Telegram, чтобы продолжить.", "В этом режиме пока нет слов. Попробуй другой режим или язык.", "Урок завершён!\n{known} знаю · {again} на тренировку\n+{xp} XP", "Ещё один урок", "Прогресс изменился. Открой новую колоду; ответы сохранены.", "Слишком много запросов. Подожди и повтори.", "Сменить язык"],
    fr: ["Gardons les mots en mémoire", "Tes révisions et nouveaux mots. Une carte à la fois.", "Mix malin", "Réviser", "Nouveaux", "Commencer les cartes", "Voir le sens", "Masquer le sens", "← À revoir", "Je sais →", "Annuler la réponse", "Réessayer", "Écouter", "Gauche : à revoir · droite : je sais. Espace : retourner.", "Préparation des cartes…", "Enregistrement…", "Enregistrement impossible. La carte reste ici — réessaie.", "Rouvre Lexi dans Telegram pour continuer.", "Aucun mot dans ce mode. Essaie un autre mode ou une autre langue.", "Session terminée !\n{known} connus · {again} à travailler\n+{xp} XP", "Une autre session", "La progression a changé. Lance un nouveau jeu ; tes réponses sont enregistrées.", "Trop de demandes. Patiente et réessaie.", "Changer de langue"],
    de: ["Wörter im Kopf behalten", "Deine Wiederholungen und neue Wörter. Karte für Karte.", "Smarter Mix", "Wiederholen", "Neu", "Karten starten", "Bedeutung zeigen", "Bedeutung verbergen", "← Noch mal", "Gewusst →", "Antwort rückgängig", "Erneut versuchen", "Anhören", "Links: noch mal · rechts: gewusst. Leertaste: umdrehen.", "Deine Karten werden vorbereitet…", "Speichern…", "Speichern fehlgeschlagen. Die Karte bleibt hier — versuche es erneut.", "Öffne Lexi erneut in Telegram.", "Keine Wörter in diesem Modus. Wähle einen anderen Modus oder eine Sprache.", "Einheit abgeschlossen!\n{known} gewusst · {again} zum Üben\n+{xp} XP", "Weitere Einheit", "Der Fortschritt wurde geändert. Starte neue Karten; Antworten sind gespeichert.", "Zu viele Anfragen. Warte und versuche es erneut.", "Sprache wechseln"],
    es: ["Mantén las palabras en tu memoria", "Tus repasos y palabras nuevas. Una tarjeta cada vez.", "Mezcla inteligente", "Repasar", "Nuevas", "Empezar tarjetas", "Mostrar significado", "Ocultar significado", "← Otra vez", "Lo sé →", "Deshacer respuesta", "Reintentar", "Escuchar", "Izquierda: otra vez · derecha: lo sé. Espacio: girar.", "Preparando tus tarjetas…", "Guardando…", "No se pudo guardar. La tarjeta sigue aquí — reintenta.", "Vuelve a abrir Lexi en Telegram.", "No hay palabras en este modo. Prueba otro modo o idioma.", "¡Sesión completada!\n{known} conocidas · {again} para practicar\n+{xp} XP", "Otra sesión", "El progreso cambió. Empieza otra baraja; las respuestas están guardadas.", "Demasiadas solicitudes. Espera y reintenta.", "Cambiar idioma"],
    ja: ["単語を記憶に戻そう", "復習と新しい単語を、一枚ずつ。", "スマートミックス", "復習", "新しい単語", "カードを始める", "意味を表示", "意味を隠す", "← もう一度", "分かった →", "回答を取り消す", "再試行", "聞く", "左：もう一度 · 右：分かった。スペース：裏返す。", "カードを準備中…", "保存中…", "保存できませんでした。カードはそのままです。再試行してください。", "TelegramでLexiを開き直してください。", "このモードには単語がありません。別のモードや言語を選んでください。", "学習完了！\n{known} 単語を覚えた · {again} 単語を練習\n+{xp} XP", "もう一回", "学習状況が変わりました。新しいカードを始めてください。回答は保存されています。", "リクエストが多すぎます。しばらく待って再試行してください。", "言語を変更"],
    zh: ["让单词回到记忆中", "你的复习与新单词，一次一张卡。", "智能混合", "复习", "新单词", "开始刷卡", "显示词义", "隐藏词义", "← 再练一次", "记住了 →", "撤销回答", "重试", "听发音", "左滑：再练一次 · 右滑：记住了。空格：翻面。", "正在准备卡片…", "正在保存…", "保存失败，卡片仍在这里。请重试。", "请在Telegram中重新打开Lexi。", "此模式暂无单词，请尝试其他模式或语言。", "学习完成！\n{known} 已记住 · {again} 待练习\n+{xp} XP", "再学一轮", "学习进度已改变。请开始新一轮；回答已保存。", "请求过多，请稍后重试。", "切换语言"],
    ar: ["لنعيد الكلمات إلى الذاكرة", "مراجعاتك وكلماتك الجديدة، بطاقة واحدة كل مرة.", "مزيج ذكي", "مراجعة", "جديد", "ابدأ البطاقات", "أظهر المعنى", "أخفِ المعنى", "← مرة أخرى", "أعرفها →", "تراجع عن الإجابة", "حاول مجددًا", "استمع", "اسحب لليسار للتكرار ولليمين إن عرفتها. المسافة لقلب البطاقة.", "جارٍ إعداد البطاقات…", "جارٍ الحفظ…", "تعذر الحفظ. البطاقة باقية هنا، حاول مجددًا.", "أعد فتح Lexi في Telegram للمتابعة.", "لا توجد كلمات في هذا الوضع. جرّب وضعًا أو لغة أخرى.", "اكتملت الجلسة!\n{known} معروفة · {again} للتدريب\n+{xp} XP", "جلسة أخرى", "تغير التقدم. ابدأ بطاقات جديدة؛ إجاباتك محفوظة.", "طلبات كثيرة. انتظر ثم حاول مجددًا.", "تغيير اللغة"]
  };
  const copies = Object.fromEntries(Object.entries(translations).map(([locale, values]) => [locale, Object.fromEntries(keys.map((key, i) => [key, values[i]]))]));
  const additional = {
    en: ["Continue remaining cards", "Pause · answers saved", "Audio is unavailable. Try listening again.", "Mix", "Start practice"],
    ru: ["Продолжить оставшиеся карточки", "Пауза · ответы сохранены", "Звук недоступен. Попробуй послушать ещё раз.", "Смесь", "Начать занятие"],
    fr: ["Continuer les cartes restantes", "Pause · réponses enregistrées", "Audio indisponible. Réessaie de l’écouter.", "Mélange", "Commencer"],
    de: ["Verbleibende Karten fortsetzen", "Pause · Antworten gespeichert", "Audio nicht verfügbar. Versuche es erneut.", "Gemischt", "Übung starten"],
    es: ["Continuar tarjetas pendientes", "Pausa · respuestas guardadas", "Audio no disponible. Intenta escucharlo de nuevo.", "Mezcla", "Empezar práctica"],
    ja: ["残りのカードを続ける", "一時停止 · 回答は保存済み", "音声を再生できません。もう一度お試しください。", "ミックス", "練習を始める"],
    zh: ["继续剩余卡片", "暂停 · 回答已保存", "暂时无法播放，请重试。", "混合", "开始练习"],
    ar: ["تابع البطاقات المتبقية", "توقف مؤقت · الإجابات محفوظة", "الصوت غير متاح. حاول الاستماع مجددًا.", "مزيج", "ابدأ التدريب"]
  };
  Object.entries(additional).forEach(([locale, values]) => Object.assign(copies[locale], Object.fromEntries(["resume", "pause", "audio_error", "mix", "start"].map((key, index) => [key, values[index]]))));
  const plurals = {en: "plural", ru: "мн. ч.", fr: "pluriel", de: "Plural", es: "plural", ja: "複数", zh: "复数", ar: "الجمع"};
  Object.entries(plurals).forEach(([locale, label]) => { copies[locale].plural = label; });
  const root = document.getElementById("swipe-trainer");
  if (!root) return;
  const el = id => document.getElementById(`swipe-${id}`);
  const modes = Array.from(document.querySelectorAll("[data-swipe-mode]"));
  const setText = (id, value) => { if (el(id)) el(id).textContent = String(value ?? ""); };
  let copy = copies.en;
  let mode = "mix", deck = null, state = null, activePack = null;
  let busy = false, retryJob = null, fatal = false, revealed = false, drag = null;
  let sequence = 0, completed = null, overview = null, refreshJob = null;
  const webApp = () => window.Telegram && window.Telegram.WebApp;
  const authenticated = () => Boolean(webApp() && webApp().initData);
  const currentCard = () => deck && state && deck.cards.find(card => card.word_index === state.queue[0]);

  function clearSession() {
    deck = null; state = null; completed = null;
  }

  function draw() {
    const card = currentCard();
    const blocked = busy || Boolean(retryJob) || fatal || !authenticated();
    root.dataset.active = String(Boolean(card));
    root.setAttribute("aria-busy", String(busy));
    el("controls").hidden = !card;
    el("summary").hidden = !completed;
    el("start").hidden = Boolean(card) || busy || Boolean(retryJob);
    el("start").disabled = blocked;
    el("retry").hidden = !retryJob || busy || fatal;
    el("retry").disabled = busy;
    modes.forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.swipeMode === mode));
      const count = deck && deck.counts[button.dataset.swipeMode === "mix" ? "total" : button.dataset.swipeMode];
      button.textContent = copy[button.dataset.swipeMode] + (count === undefined || count === null ? "" : ` · ${count}`);
      button.disabled = blocked;
    });
    ["reveal", "again", "know", "speak"].forEach(id => { el(id).disabled = blocked || !card; });
    el("speak").disabled = el("speak").disabled || !(window.speechSynthesis && typeof SpeechSynthesisUtterance !== "undefined");
    el("undo").hidden = !state || !state.undo_operation_id;
    el("undo").disabled = blocked || !state || !state.undo_operation_id;
    if (el("resume")) {
      el("resume").hidden = Boolean(card) || Boolean(completed) || !overview?.resume;
      el("resume").disabled = blocked;
      setText("resume", copy.resume);
    }
    if (el("pause")) { el("pause").hidden = !card; el("pause").disabled = blocked; setText("pause", copy.pause); }
    setText("start", completed ? copy.restart : copy.start);
    setText("reveal", revealed ? copy.hide : copy.reveal);
    el("reveal").setAttribute("aria-expanded", String(revealed));
    el("meaning").hidden = !revealed;
    if (card) {
      el("card").dataset.kind = card.kind;
      setText("kind", copy[card.kind]);
      setText("target", card.target);
      setText("transcription", card.transcription);
      setText("meaning", card.meaning);
      const grammar = card.grammar || {};
      setText("grammar", grammar.article
        ? `${grammar.article} ${card.target} · ${copy.plural}: ${grammar.plural}${grammar.note ? ` · ${grammar.note}` : ""}`
        : Object.values(grammar).join(" · "));
      setText("example", card.example?.target || "");
      setText("example-meaning", card.example?.meaning || "");
      if (el("context")) el("context").hidden = !revealed || !(card.example?.target || Object.keys(grammar).length);
      const remaining = new Set(state.queue).size;
      const finished = deck.cards.length - remaining;
      setText("count", `${finished} / ${deck.cards.length}`);
      el("progress").max = deck.cards.length;
      el("progress").value = finished;
    }
    if (completed) setText("summary", copy.done.replace("{known}", completed.known).replace("{again}", completed.again).replace("{xp}", completed.earned_xp));
  }

  async function request(action, body) {
    if (!authenticated() || fatal) throw Object.assign(new Error("auth"), {status: 401});
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`/miniapp/api/swipe/${action}`, {
        method: "POST", headers: {"Content-Type": "application/json", "X-Telegram-Init-Data": webApp().initData},
        body: JSON.stringify(body), credentials: "omit", cache: "no-store", signal: controller.signal
      });
      if (!response.ok) throw Object.assign(new Error("request_failed"), {status: response.status});
      return await response.json();
    } finally { clearTimeout(timer); }
  }

  async function perform(action, body, accept) {
    if (busy || !authenticated() || fatal) return;
    const issued = sequence;
    busy = true;
    setText("status", ["deck", "resume"].includes(action) ? copy.loading : copy.saving);
    draw();
    let accepted = false;
    try {
      const result = await request(action, body);
      if (issued !== sequence) return;
      accept(result);
      retryJob = null;
      setText("status", ["deck", "resume"].includes(action) && !result.cards.length ? copy.empty : "");
      accepted = true;
    } catch (error) {
      if (issued !== sequence) return;
      if (error.status === 401 || error.status === 403) {
        fatal = true; retryJob = null; setText("status", copy.auth);
      } else if (error.status === 409 || error.status === 404 || error.status === 400) {
        clearSession(); retryJob = null; overview = null;
        setText("status", copy.stale);
      } else {
        // A lost response can still mean the transaction committed. Replay it.
        retryJob = {action, body, accept};
        setText("status", error.status === 429 ? copy.wait : copy.error);
      }
    } finally {
      if (issued === sequence) { busy = false; draw(); }
    }
    if (accepted && ["rate", "resume"].includes(action) && !state.queue.length && deck.session_id) await complete();
    if (accepted && ["deck", "resume", "undo"].includes(action) && currentCard()) el("card").focus?.();
  }

  function acceptDeck(result) {
    deck = result;
    mode = result.mode;
    state = {reviewed: 0, known: 0, again: 0, undo_operation_id: null, ...result};
    revealed = false; completed = null;
  }

  function publishOverview() {
    if (typeof CustomEvent !== "undefined") root.dispatchEvent?.(new CustomEvent("lexi:practice-status", {bubbles: true, detail: overview}));
  }

  async function refresh() {
    if (refreshJob) return refreshJob;
    if (fatal || !authenticated()) return null;
    const issued = sequence;
    const job = (async () => {
      try {
        const result = await request("status", {});
        if (issued !== sequence) return null;
        overview = result;
        if (!deck) deck = {counts: result.counts, cards: []};
        publishOverview(); draw();
        return result;
      } catch (error) {
        if (issued !== sequence) return null;
        if ([401, 403].includes(error.status)) { fatal = true; setText("status", copy.auth); }
        else setText("status", error.status === 409 ? copy.stale : copy.error);
        draw(); return null;
      }
    })();
    refreshJob = job;
    try { return await job; } finally { if (refreshJob === job) refreshJob = null; }
  }

  async function enter(requested = "auto") {
    if (busy || retryJob || fatal || !authenticated()) return;
    if (!["auto", "mix", "forgotten", "new"].includes(requested)) return;
    if (currentCard() && (requested === "auto" || requested === mode)) { draw(); el("card").focus?.(); return; }
    const issued = sequence;
    if (!overview && !await refresh()) return;
    if (issued !== sequence || busy || fatal) return;
    const resumable = overview?.resume;
    if (resumable && (requested === "auto" || requested === resumable.mode)) {
      return perform("resume", {session_id: resumable.session_id}, acceptDeck);
    }
    mode = requested === "auto" ? (overview.counts.forgotten > 0 ? "forgotten" : "new") : requested;
    return start();
  }

  function start() {
    if (busy || retryJob || fatal || !authenticated()) return;
    return perform("deck", {mode}, acceptDeck);
  }
  function choose() {
    if (busy || retryJob || fatal || !authenticated()) return;
    clearSession(); draw();
    return refresh();
  }
  function grade(knew) {
    const card = currentCard();
    if (!card || busy || retryJob || fatal) return;
    const operationId = window.crypto.randomUUID();
    return perform("rate", {session_id: deck.session_id, operation_id: operationId, word_index: card.word_index, knew}, result => {
      state = result; revealed = false;
      try {
        if (webApp().HapticFeedback) webApp().HapticFeedback.impactOccurred("light");
      } catch (_) { /* Optional feedback never affects a saved assessment. */ }
    });
  }
  function undo() {
    if (!state || !state.undo_operation_id || busy || retryJob) return;
    return perform("undo", {session_id: deck.session_id, operation_id: state.undo_operation_id}, result => {
      state = result; revealed = false; completed = null;
      root.dispatchEvent?.(new Event("lexi:practice-completed", {bubbles: true}));
    });
  }
  function complete() {
    return perform("complete", {session_id: deck.session_id}, result => {
      completed = result;
      if (overview) overview.resume = null;
      publishOverview();
      // Refresh neighboring progress without making another learner-data write.
      root.dispatchEvent?.(new Event("lexi:practice-completed", {bubbles: true}));
    });
  }
  function reveal() { if (currentCard() && !busy && !retryJob) { revealed = !revealed; draw(); } }
  function speak() {
    const card = currentCard();
    if (!card || !window.speechSynthesis || typeof SpeechSynthesisUtterance === "undefined") return;
    const utterance = new SpeechSynthesisUtterance(card.target);
    utterance.lang = deck.tts_locale;
    utterance.onerror = () => setText("status", copy.audio_error);
    window.speechSynthesis.cancel(); window.speechSynthesis.speak(utterance);
  }
  function resetDrag() {
    if (drag) { try { el("card").releasePointerCapture(drag.id); } catch (_) { /* Optional capture. */ } }
    drag = null; el("card").classList.remove("is-dragging");
    el("card").style.transform = "";
  }
  el("card").addEventListener("pointerdown", event => {
    if (busy || retryJob || fatal || !currentCard() || event.isPrimary === false || event.button > 0) return;
    if (event.target.closest("button, a, input, select, textarea, summary, details")) return;
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY, dx: 0, dy: 0};
    try { el("card").setPointerCapture(event.pointerId); } catch (_) { /* Optional capture. */ }
  });
  el("card").addEventListener("pointermove", event => {
    if (!drag || drag.id !== event.pointerId) return;
    drag.dx = event.clientX - drag.x; drag.dy = event.clientY - drag.y;
    if (Math.abs(drag.dy) > Math.abs(drag.dx) + 12) { resetDrag(); return; }
    if (Math.abs(drag.dx) > 8) {
      el("card").classList.add("is-dragging");
      const rotation = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : drag.dx / 22;
      el("card").style.transform = `translateX(${Math.max(-110, Math.min(110, drag.dx))}px) rotate(${rotation}deg)`;
    }
  });
  el("card").addEventListener("pointerup", event => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = drag.dx, dy = drag.dy; resetDrag();
    if (Math.abs(dx) >= 72 && Math.abs(dx) > Math.abs(dy)) return grade(dx > 0);
    if (Math.abs(dx) < 8 && Math.abs(dy) < 8) reveal();
  });
  el("card").addEventListener("pointercancel", resetDrag);
  el("card").addEventListener("lostpointercapture", resetDrag);
  el("card").addEventListener("keydown", event => {
    if (event.target !== el("card")) return;
    if ([" ", "Enter", "ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      return event.key === "ArrowLeft" ? grade(false) : event.key === "ArrowRight" ? grade(true) : reveal();
    }
  });
  el("start").addEventListener("click", start);
  el("resume")?.addEventListener("click", () => enter());
  el("pause")?.addEventListener("click", choose);
  el("reveal").addEventListener("click", reveal);
  el("speak").addEventListener("click", speak);
  el("again").addEventListener("click", () => grade(false));
  el("know").addEventListener("click", () => grade(true));
  el("undo").addEventListener("click", undo);
  el("retry").addEventListener("click", () => retryJob && perform(retryJob.action, retryJob.body, retryJob.accept));
  el("language")?.addEventListener("click", () => document.getElementById("tab-languages").click());
  modes.forEach(button => button.addEventListener("click", () => {
    if (busy || retryJob || fatal || button.dataset.swipeMode === mode) return;
    mode = button.dataset.swipeMode; clearSession();
    setText("status", ""); draw();
  }));
  window.addEventListener("pagehide", () => { if (window.speechSynthesis) window.speechSynthesis.cancel(); resetDrag(); });
  window.LexiSwipe = Object.freeze({configure(data) {
    const current = (data.languages || []).find(language => language.current);
    const nextPack = current ? current.switch_value : data.settings && data.settings.active_pack_id;
    if (nextPack !== activePack || data.privacy?.access_erased) {
      sequence += 1; busy = false; retryJob = null; overview = null; refreshJob = null; clearSession(); resetDrag();
    }
    activePack = nextPack;
    copy = copies[data.locale] || copies.en;
    fatal = !authenticated() || data.privacy?.access_erased === true;
    ["title", "hint", "again", "know", "undo", "retry", "speak"].forEach(id => setText(id, copy[id]));
    setText("keyboard-hint", copy.keyboard);
    setText("language", current ? `${current.label} ›` : copy.language);
    if (el("language")) el("language").setAttribute("aria-label", copy.language);
    if (fatal) setText("status", copy.auth);
    draw();
  }, refresh, enter, choose});
})();
