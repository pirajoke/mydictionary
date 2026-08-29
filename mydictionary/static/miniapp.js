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
  const hintedUser = webApp && webApp.initDataUnsafe && webApp.initDataUnsafe.user
    ? webApp.initDataUnsafe.user
    : null;
  const hintedLanguage = hintedUser
    ? hintedUser.language_code
    : "en";
  const hintedPhotoUrl = webApp && webApp.initDataUnsafe && webApp.initDataUnsafe.user
    ? webApp.initDataUnsafe.user.photo_url
    : "";
  const hintedBase = String(hintedLanguage || "en").toLowerCase().replace("_", "-").split("-", 1)[0];
  const hintedLocale = hintedBase.startsWith("zh") ? "zh" : (prebootstrapCopy[hintedBase] ? hintedBase : "en");
  document.documentElement.lang = hintedLocale;
  if (hintedLocale === "ar") document.documentElement.dir = "rtl";
  let payload = null;
  let calendarCursor = null;

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
  const summaryStat = (label, value, tone) => {
    const item = document.createElement("div");
    item.className = `summary-stat ${tone}`;
    item.setAttribute("role", "listitem");
    const number = document.createElement("b");
    const caption = document.createElement("span");
    text(number, value);
    text(caption, label);
    item.append(number, caption);
    return item;
  };

  function safeTelegramPhotoUrl(value) {
    try {
      const candidate = new URL(String(value || ""));
      const hostname = candidate.hostname.toLowerCase();
      const trustedRoots = ["t.me", "telegram.org", "telegram-cdn.org", "cdn-telegram.org", "telesco.pe"];
      const trusted = trustedRoots.some((root) => hostname === root || hostname.endsWith(`.${root}`));
      if (
        candidate.protocol !== "https:" || !trusted || candidate.username ||
        candidate.password || candidate.port || candidate.hash
      ) return "";
      return candidate.href;
    } catch (_) {
      return "";
    }
  }

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
    const main = document.createElement("div");
    main.className = "word-card-main";
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
    attempts.className = "word-attempts";
    text(attempts, `${copy.attempts_correct}: ${word.correct} · ${copy.attempts_wrong}: ${word.wrong}`);
    main.append(header, meaning);
    card.append(main, attempts);
    node("word-list").append(card);
  }

  function addSetting(list, label, value, state = "") {
    const row = document.createElement("div");
    row.className = `setting-row${state ? ` ${state}` : ""}`;
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    text(term, label);
    text(detail, value);
    row.append(term, detail);
    list.append(row);
  }

  function languageDisplayLabel(language) {
    return String(language.label || "").trim().replace(/\s*·\s*\d+\s*$/u, "");
  }

  function languageCard(language, copy) {
    const card = document.createElement("div");
    card.className = "language-card";
    card.dir = language.direction;
    const label = document.createElement("strong");
    label.dir = language.direction;
    text(label, languageDisplayLabel(language));
    const count = document.createElement("span");
    count.className = "language-count";
    text(count, language.word_count);
    card.append(label, count);
    if (language.current) {
      const current = document.createElement("span");
      current.className = "badge";
      text(current, copy.language_current);
      card.append(current);
    }
    return card;
  }

  function isoMonth(value) {
    return `${value.getUTCFullYear().toString().padStart(4, "0")}-${(value.getUTCMonth() + 1).toString().padStart(2, "0")}`;
  }

  function monthFromKey(value) {
    const matched = /^(\d{4})-(\d{2})$/.exec(String(value || ""));
    if (!matched) return null;
    const year = Number(matched[1]);
    const month = Number(matched[2]) - 1;
    if (year < 1970 || year > 2100 || month < 0 || month > 11) return null;
    return new Date(Date.UTC(year, month, 1));
  }

  function renderCalendar(calendar, copy, locale) {
    const today = /^\d{4}-\d{2}-\d{2}$/.test(String(calendar.today || "")) ? calendar.today : "";
    const maxMonth = monthFromKey(calendar.max_month) || new Date();
    const minMonth = monthFromKey(calendar.min_month) || maxMonth;
    if (!calendarCursor || calendarCursor < minMonth || calendarCursor > maxMonth) {
      calendarCursor = new Date(Date.UTC(maxMonth.getUTCFullYear(), maxMonth.getUTCMonth(), 1));
    }
    const activityDays = new Set(
      Array.isArray(calendar.activity_days)
        ? calendar.activity_days.filter((day) => /^\d{4}-\d{2}-\d{2}$/.test(String(day)))
        : []
    );
    const monthLabel = new Intl.DateTimeFormat(locale, {month: "long", year: "numeric", timeZone: "UTC"});
    const weekdayLabel = new Intl.DateTimeFormat(locale, {weekday: "narrow", timeZone: "UTC"});
    text(node("calendar-month"), monthLabel.format(calendarCursor));

    const grid = node("calendar-grid");
    grid.replaceChildren();
    const monday = new Date(Date.UTC(2026, 7, 3));
    for (let weekday = 0; weekday < 7; weekday += 1) {
      const label = document.createElement("span");
      label.className = "calendar-weekday";
      label.setAttribute("role", "columnheader");
      text(label, weekdayLabel.format(new Date(monday.getTime() + weekday * 86400000)));
      grid.append(label);
    }

    const leading = (calendarCursor.getUTCDay() + 6) % 7;
    const firstCell = new Date(Date.UTC(calendarCursor.getUTCFullYear(), calendarCursor.getUTCMonth(), 1 - leading));
    for (let index = 0; index < 42; index += 1) {
      const cellDate = new Date(firstCell.getTime() + index * 86400000);
      const day = `${cellDate.getUTCFullYear().toString().padStart(4, "0")}-${(cellDate.getUTCMonth() + 1).toString().padStart(2, "0")}-${cellDate.getUTCDate().toString().padStart(2, "0")}`;
      const cell = document.createElement("span");
      const inMonth = cellDate.getUTCMonth() === calendarCursor.getUTCMonth();
      const active = activityDays.has(day);
      cell.className = `calendar-day${inMonth ? "" : " outside"}${active ? " active" : ""}${day === today ? " today" : ""}`;
      cell.setAttribute("role", "gridcell");
      cell.setAttribute("aria-label", `${new Intl.DateTimeFormat(locale, {dateStyle: "long", timeZone: "UTC"}).format(cellDate)}${active ? ` · ${copy.calendar_active_day}` : ""}${day === today ? ` · ${copy.calendar_today}` : ""}`);
      if (day === today) cell.setAttribute("aria-current", "date");
      text(cell, cellDate.getUTCDate());
      grid.append(cell);
    }
    node("calendar-previous").disabled = isoMonth(calendarCursor) <= calendar.min_month;
    node("calendar-next").disabled = isoMonth(calendarCursor) >= calendar.max_month;
  }

  function moveCalendar(offset) {
    if (!payload || !calendarCursor) return;
    const next = new Date(Date.UTC(calendarCursor.getUTCFullYear(), calendarCursor.getUTCMonth() + offset, 1));
    if (isoMonth(next) < payload.progress.calendar.min_month || isoMonth(next) > payload.progress.calendar.max_month) return;
    calendarCursor = next;
    renderCalendar(payload.progress.calendar, payload.copy, payload.locale);
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
    const profile = data.profile;
    text(node("display-name"), profile.display_name);
    const currentLanguage = data.languages.find((language) => language.current);
    text(node("current-language"), currentLanguage ? currentLanguage.label : copy.setting_unknown);
    text(node("profile-language"), currentLanguage ? currentLanguage.label : copy.setting_unknown);
    text(node("profile-credit-balance"), profile.credits);
    const avatar = node("profile-photo");
    const avatarFallback = node("profile-avatar-fallback");
    const initials = String(profile.display_name || "?").trim().split(/\s+/).slice(0, 2).map((part) => part.slice(0, 1).toUpperCase()).join("") || "?";
    text(avatarFallback, initials);
    const avatarUrl = safeTelegramPhotoUrl(profile.avatar_url) || safeTelegramPhotoUrl(hintedPhotoUrl);
    if (avatarUrl) {
      avatar.src = avatarUrl;
      avatar.hidden = false;
      avatarFallback.hidden = true;
      avatar.addEventListener("error", () => {
        avatar.hidden = true;
        avatar.removeAttribute("src");
        avatarFallback.hidden = false;
      }, {once: true});
    } else {
      avatar.hidden = true;
      avatar.removeAttribute("src");
      avatarFallback.hidden = false;
    }

    const progress = data.progress;
    text(node("streak-count"), progress.streak);
    text(node("best-streak"), progress.best_streak);
    calendarCursor = null;
    renderCalendar(progress.calendar, copy, data.locale);
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
    node("word-summary").replaceChildren(
      summaryStat(copy.metric_tracked_words, progress.tracked_words, "tracked"),
      summaryStat(copy.metric_learned_words, data.words.filter((word) => word.learned).length, "learned"),
      summaryStat(copy.word_review, data.words.filter((word) => word.due).length, "due")
    );
    data.words.forEach((word) => addWord(word, copy));
    node("empty-words").hidden = data.words.length !== 0;

    text(node("wallet-available"), data.credits.available);
    node("credit-summary").replaceChildren(
      summaryStat(copy.credit_reserved, data.credits.reserved, "reserved"),
      summaryStat(copy.credit_spent, data.credits.spent, "spent")
    );
    text(node("credit-contract"), data.credits.contract);
    const products = node("product-list");
    products.replaceChildren();
    data.products.forEach((product) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "product-card";
      button.disabled = !data.features.stars_checkout;
      const productCopy = document.createElement("span");
      productCopy.className = "product-card-copy";
      const title = document.createElement("strong");
      const credits = document.createElement("small");
      text(title, product.title);
      text(credits, `${product.credits} ✦`);
      productCopy.append(title, credits);
      const price = document.createElement("span");
      price.className = "product-card-price";
      text(price, `${product.price_xtr} XTR`);
      button.append(productCopy, price);
      button.addEventListener("click", () => openAction("buy"));
      products.append(button);
    });
    node("checkout-disabled").hidden = data.features.stars_checkout;

    const currentLanguageCard = node("language-current");
    const languages = node("language-list");
    currentLanguageCard.replaceChildren();
    languages.replaceChildren();
    const selectedLanguage = data.languages.find((language) => language.current);
    if (selectedLanguage) currentLanguageCard.append(languageCard(selectedLanguage, copy));
    data.languages.filter((language) => !language.current).forEach((language) => {
      languages.append(languageCard(language, copy));
    });

    const learningSettings = node("settings-learning");
    const tutorSettings = node("settings-tutor");
    const featureSettings = node("settings-features");
    learningSettings.replaceChildren();
    tutorSettings.replaceChildren();
    featureSettings.replaceChildren();
    addSetting(learningSettings, copy.setting_daily_goal, data.settings.daily_goal);
    addSetting(learningSettings, copy.setting_meaning_language, data.settings.meaning_language);
    addSetting(learningSettings, copy.setting_learning_goal, data.settings.learning_goal);
    addSetting(tutorSettings, copy.setting_mirror_mode, data.settings.mirror_mode);
    addSetting(tutorSettings, copy.setting_mirror_style, data.settings.mirror_style);
    addSetting(tutorSettings, copy.setting_mirror_depth, data.settings.mirror_depth);
    addSetting(tutorSettings, copy.setting_mirror_level, data.settings.mirror_level);
    addSetting(featureSettings, copy.setting_ai, data.features.ai ? copy.feature_enabled : copy.feature_disabled, data.features.ai ? "enabled" : "disabled");
    addSetting(featureSettings, copy.setting_voice, data.features.voice ? copy.feature_enabled : copy.feature_disabled, data.features.voice ? "enabled" : "disabled");

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
  node("calendar-previous").addEventListener("click", () => moveCalendar(-1));
  node("calendar-next").addEventListener("click", () => moveCalendar(1));
  load();
})();
