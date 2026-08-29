(() => {
  "use strict";
  const webApp = window.Telegram && window.Telegram.WebApp;
  const botUsername = document.body.dataset.botUsername || "";
  const prebootstrapCopy = {
    "en": {"loading": "Loading…", "error": "Something went wrong.", "retry": "Try again"},
    "fr": {"loading": "Chargement…", "error": "Un problème est survenu.", "retry": "Réessayer"},
    "de": {"loading": "Wird geladen…", "error": "Ein Fehler ist aufgetreten.", "retry": "Erneut versuchen"},
    "ja": {"loading": "読み込み中…", "error": "問題が発生しました。", "retry": "再試行"},
    "ar": {"loading": "جارٍ التحميل…", "error": "حدث خطأ.", "retry": "إعادة المحاولة"},
    "zh": {"loading": "加载中…", "error": "出现问题。", "retry": "重试"},
    "ru": {"loading": "Загрузка…", "error": "Что-то пошло не так.", "retry": "Повторить"},
    "es": {"loading": "Cargando…", "error": "Ha ocurrido un problema.", "retry": "Reintentar"}
  };
  const hintedLanguage = webApp && webApp.initDataUnsafe && webApp.initDataUnsafe.user
    ? webApp.initDataUnsafe.user.language_code
    : "en";
  const hintedBase = String(hintedLanguage || "en").toLowerCase().replace("_", "-").split("-", 1)[0];
  const hintedLocale = hintedBase.startsWith("zh") ? "zh" : (prebootstrapCopy[hintedBase] ? hintedBase : "en");
  document.documentElement.lang = hintedLocale;
  if (hintedLocale === "ar") document.documentElement.dir = "rtl";
  let payload = null;

  const node = (id) => document.getElementById(id);
  const text = (element, value) => { element.textContent = String(value ?? ""); };
  const metric = (label, value) => {
    const item = document.createElement("div");
    item.className = "metric";
    const number = document.createElement("b");
    const caption = document.createElement("span");
    text(number, value);
    text(caption, label);
    item.append(number, caption);
    return item;
  };

  function applyCopy(copy) {
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      const value = copy[element.dataset.i18n];
      if (value) text(element, value);
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
      const value = copy[element.dataset.i18nAriaLabel];
      if (value) element.setAttribute("aria-label", value);
    });
  }

  applyCopy(prebootstrapCopy[hintedLocale]);

  function actionLink(action) {
    if (!payload || !payload.actions[action] || !botUsername) return "";
    return `https://t.me/${botUsername}?start=${encodeURIComponent(payload.actions[action])}`;
  }

  function openAction(action) {
    if (action === "share") {
      const url = `https://t.me/${botUsername}`;
      if (webApp) webApp.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}`);
      return;
    }
    const url = actionLink(action);
    if (url && webApp) webApp.openTelegramLink(url);
  }

  function addWord(word, copy) {
    const card = document.createElement("article");
    card.className = "word-card";
    const header = document.createElement("header");
    const title = document.createElement("h2");
    text(title, word.target);
    header.append(title);
    if (word.due || word.learned) {
      const badge = document.createElement("span");
      badge.className = "badge";
      text(badge, word.due ? copy.word_review : copy.word_learned);
      header.append(badge);
    }
    const meaning = document.createElement("p");
    text(meaning, word.meaning);
    const attempts = document.createElement("small");
    text(attempts, `${copy.attempts_correct}: ${word.correct} · ${copy.attempts_wrong}: ${word.wrong}`);
    card.append(header, meaning, attempts);
    node("word-list").append(card);
  }

  function addSetting(list, label, value) {
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    text(term, label);
    text(detail, value);
    list.append(term, detail);
  }

  function render(data) {
    payload = data;
    const copy = data.copy;
    applyCopy(copy);
    document.querySelector(".bottom-nav").hidden = false;
    document.documentElement.lang = data.locale;
    if (data.direction === "rtl") {
      document.documentElement.dir = "rtl";
    } else {
      document.documentElement.dir = "ltr";
    }
    text(node("display-name"), data.profile.display_name);
    const currentLanguage = data.languages.find((language) => language.current);
    text(node("current-language"), currentLanguage ? currentLanguage.label : copy.setting_unknown);

    const progress = data.progress;
    node("profile-metrics").replaceChildren(
      metric(copy.metric_level, progress.level),
      metric(copy.metric_xp, progress.xp),
      metric(copy.metric_streak, progress.streak),
      metric(copy.metric_best_streak, progress.best_streak),
      metric(copy.metric_sessions, progress.sessions),
      metric(copy.metric_accuracy, `${progress.accuracy.correct}/${progress.accuracy.total}`),
      metric(copy.metric_today_xp, progress.today_xp),
      metric(copy.metric_daily_goal, data.profile.daily_word_goal),
      metric(copy.metric_tracked_words, progress.tracked_words),
      metric(copy.metric_learned_words, progress.learned_words),
      metric(copy.metric_ai_credits, data.credits.available)
    );

    node("word-list").replaceChildren();
    data.words.forEach((word) => addWord(word, copy));
    node("empty-words").hidden = data.words.length !== 0;

    node("credit-summary").replaceChildren(
      metric(copy.credit_available, data.credits.available),
      metric(copy.credit_reserved, data.credits.reserved),
      metric(copy.credit_spent, data.credits.spent)
    );
    text(node("credit-contract"), data.credits.contract);
    const products = node("product-list");
    products.replaceChildren();
    data.products.forEach((product) => {
      const button = document.createElement("button");
      button.type = "button";
      button.disabled = !data.features.stars_checkout;
      text(button, `${product.title} · ${product.credits} ✦ · ${product.price_xtr} XTR`);
      button.addEventListener("click", () => openAction("buy"));
      products.append(button);
    });
    node("checkout-disabled").hidden = data.features.stars_checkout;

    const languages = node("language-list");
    languages.replaceChildren();
    data.languages.forEach((language) => {
      const card = document.createElement("div");
      card.className = "language-card";
      card.dir = language.direction;
      const label = document.createElement("strong");
      label.dir = language.direction;
      text(label, language.label);
      const count = document.createElement("span");
      text(count, language.word_count);
      card.append(label, count);
      if (language.current) {
        const current = document.createElement("span");
        current.className = "badge";
        text(current, copy.language_current);
        card.append(current);
      }
      languages.append(card);
    });

    const settings = node("settings-list");
    settings.replaceChildren();
    addSetting(settings, copy.setting_daily_goal, data.settings.daily_goal);
    addSetting(settings, copy.setting_meaning_language, data.settings.meaning_language);
    addSetting(settings, copy.setting_learning_goal, data.settings.learning_goal);
    addSetting(settings, copy.setting_mirror_mode, data.settings.mirror_mode);
    addSetting(settings, copy.setting_mirror_style, data.settings.mirror_style);
    addSetting(settings, copy.setting_mirror_depth, data.settings.mirror_depth);
    addSetting(settings, copy.setting_mirror_level, data.settings.mirror_level);
    addSetting(settings, copy.setting_ai, data.features.ai ? copy.feature_enabled : copy.feature_disabled);
    addSetting(settings, copy.setting_voice, data.features.voice ? copy.feature_enabled : copy.feature_disabled);

    node("loading-state").hidden = true;
    node("error-state").hidden = true;
    node("app-content").hidden = false;
  }

  function showError() {
    node("loading-state").hidden = true;
    node("app-content").hidden = true;
    node("error-state").hidden = false;
  }

  async function load() {
    node("loading-state").hidden = false;
    node("error-state").hidden = true;
    try {
      if (!webApp || !webApp.initData) throw new Error("disabled");
      webApp.ready();
      webApp.expand();
      const response = await fetch("/miniapp/api/bootstrap", {
        headers: {"X-Telegram-Init-Data": webApp.initData},
        cache: "no-store",
        credentials: "omit"
      });
      if (!response.ok) throw new Error("error");
      render(await response.json());
    } catch (_) {
      showError();
    }
  }

  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  function activateTab(tab, focus = false) {
    tabs.forEach((candidate) => {
      const active = candidate === tab;
      candidate.setAttribute("aria-selected", String(active));
      candidate.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll("[data-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.panel !== tab.dataset.tab;
    });
    if (focus) tab.focus();
  }
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (event) => {
      const index = tabs.indexOf(tab);
      let target = null;
      const rtl = document.documentElement.dir === "rtl";
      if (event.key === "ArrowLeft") {
        const offset = rtl ? 1 : -1;
        target = tabs[(index + offset + tabs.length) % tabs.length];
      }
      if (event.key === "ArrowRight") {
        const offset = rtl ? -1 : 1;
        target = tabs[(index + offset + tabs.length) % tabs.length];
      }
      if (event.key === "Home") target = tabs[0];
      if (event.key === "End") target = tabs[tabs.length - 1];
      if (target) {
        event.preventDefault();
        activateTab(target, true);
      }
    });
  });
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => openAction(button.dataset.action));
  });
  node("retry-button").addEventListener("click", load);
  load();
})();
