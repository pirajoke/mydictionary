const assert = require("node:assert/strict");
const profile = require("../../mydictionary/static/dictionary-profile.js");

const now = Date.parse("2026-09-17T12:00:00Z");

{
  const activity = profile.sanitizeActivity({
    "2026-09-14": 1,
    "2026-09-15": 2,
    "2026-09-16": 3,
    "2026-09-17": 4,
    "2026-02-30": 7,
    private: 99,
    "2026-09-13": -4,
    "2026-09-12": 999999,
  });
  assert.deepEqual(activity, {
    "2026-09-12": 999,
    "2026-09-14": 1,
    "2026-09-15": 2,
    "2026-09-16": 3,
    "2026-09-17": 4,
  });
}

{
  const snapshot = profile.buildSnapshot({
    saved: {
      "en:ru:hello": {interval: 8, due: now + 86_400_000},
      "en:ru:school": {interval: 2, due: now - 1},
      "en:ru:book": {interval: 0, due: now + 120_000},
      "fr:ru:hello": {interval: 30, due: now - 1},
    },
    activity: {
      "2026-09-12": 1,
      "2026-09-14": 1,
      "2026-09-15": 2,
      "2026-09-16": 3,
      "2026-09-17": 4,
    },
    pairPrefix: "en:ru:",
    now,
  });
  assert.equal(snapshot.saved, 3);
  assert.equal(snapshot.learned, 1);
  assert.equal(snapshot.learning, 2);
  assert.equal(snapshot.due, 1);
  assert.equal(snapshot.studyDays, 5);
  assert.equal(snapshot.streak, 4);
  assert.equal(snapshot.progress, 33);
  assert.deepEqual(snapshot.week.map((day) => [day.date, day.count]), [
    ["2026-09-11", 0], ["2026-09-12", 1], ["2026-09-13", 0],
    ["2026-09-14", 1], ["2026-09-15", 2], ["2026-09-16", 3],
    ["2026-09-17", 4],
  ]);
  assert.equal(snapshot.week.at(-1).level, 4);
}

{
  const empty = profile.buildSnapshot({saved: {}, activity: {}, pairPrefix: "en:ru:", now});
  assert.deepEqual(
    {saved: empty.saved, learned: empty.learned, due: empty.due, studyDays: empty.studyDays, streak: empty.streak, progress: empty.progress},
    {saved: 0, learned: 0, due: 0, studyDays: 0, streak: 0, progress: 0},
  );
}

console.log(JSON.stringify({ok: true, checks: ["bounded activity", "pair metrics", "seven-day chart", "streak", "legacy empty state"]}));
