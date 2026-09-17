(function (root) {
  "use strict";

  const DAY_MS = 86_400_000;
  const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

  function validDateKey(value) {
    if (!DATE_PATTERN.test(value)) return false;
    const [year, month, day] = value.split("-").map(Number);
    const parsed = new Date(Date.UTC(year, month - 1, day));
    return parsed.getUTCFullYear() === year
      && parsed.getUTCMonth() === month - 1
      && parsed.getUTCDate() === day;
  }

  function sanitizeActivity(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const rows = Object.entries(value)
      .filter(([date]) => validDateKey(date))
      .map(([date, count]) => [date, Math.min(999, Math.max(0, Math.trunc(Number(count) || 0)))])
      .filter(([, count]) => count > 0)
      .sort(([left], [right]) => left.localeCompare(right))
      .slice(-400);
    return Object.fromEntries(rows);
  }

  function dateKey(value) {
    const date = new Date(value);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function shiftedDate(value, offset) {
    const date = new Date(value);
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() + offset);
    return date;
  }

  function buildSnapshot({saved = {}, activity = {}, pairPrefix = "", now = Date.now()} = {}) {
    const safeActivity = sanitizeActivity(activity);
    const rows = Object.entries(saved && typeof saved === "object" ? saved : {})
      .filter(([key, state]) => key.startsWith(pairPrefix) && state && typeof state === "object");
    const learned = rows.filter(([, state]) => Number(state.interval) >= 7).length;
    const due = rows.filter(([, state]) => Number.isFinite(Number(state.due)) && Number(state.due) <= now).length;
    const today = dateKey(now);
    const yesterday = dateKey(shiftedDate(now, -1));
    let cursor = safeActivity[today] ? new Date(now) : safeActivity[yesterday] ? shiftedDate(now, -1) : null;
    let streak = 0;
    while (cursor && safeActivity[dateKey(cursor)]) {
      streak += 1;
      cursor = shiftedDate(cursor, -1);
    }
    const week = Array.from({length: 7}, (_, index) => {
      const date = dateKey(shiftedDate(now, index - 6));
      return {date, count: safeActivity[date] || 0};
    });
    const peak = Math.max(1, ...week.map((day) => day.count));
    week.forEach((day) => { day.level = day.count ? Math.max(1, Math.ceil((day.count / peak) * 4)) : 0; });
    return {
      saved: rows.length,
      learned,
      learning: Math.max(0, rows.length - learned),
      due,
      studyDays: Object.keys(safeActivity).length,
      streak,
      progress: rows.length ? Math.round((learned / rows.length) * 100) : 0,
      week,
    };
  }

  const api = {
    sanitizeActivity,
    buildSnapshot,
  };

  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LexiDictionaryProfile = api;
})(typeof globalThis === "object" ? globalThis : this);
