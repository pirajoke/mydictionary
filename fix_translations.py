#!/usr/bin/env python3
"""Fix translation issues in words.json."""
import json
from pathlib import Path

WORDS_FILE = Path(__file__).parent / "words.json"
words = json.load(open(WORDS_FILE, encoding="utf-8"))

# === FIXES: (index, field, new_value) or "REMOVE" ===
fixes = {
    # Typos in Russian
    4:   {"ru": "пневмония"},                           # пневмони → пневмония
    19:  {"ru": "деятельность"},                        # деятельнсость → деятельность
    8:   {"ru": "лесной пожар"},                        # Лесных пожаров → лесной пожар
    12:  {"ru": "тщеславие"},                           # Суета → тщеславие (vanity = тщеславие, not суета)
    24:  "REMOVE",                                       # stabbornes → stabbornes (broken entry, duplicate of 23)
    34:  "REMOVE",                                       # Dipe → Падение (typo of Dip, duplicate-ish)
    39:  {"ru": "взгляд"},                              # Скользнуть → взгляд (glance = взгляд)
    42:  {"ru": "взаимосвязанный"},                     # взаимозависимый → взаимосвязанный
    51:  {"ru": "клянётся"},                            # Ругань → клянётся (swears = клянётся/ругается)
    70:  {"ru": "кран"},                                # Вентиль → кран (faucet = кран)
    71:  "REMOVE",                                       # Embarrasse → duplicate of 44 Embarrassed
    78:  {"ru": "раненый"},                             # Получившее ранение → раненый
    80:  {"ru": "преследуемый"},                        # Обеспокоенный → преследуемый (harassed)
    82:  {"ru": "поверхность"},                         # Поверхностный → поверхность (noun)
    89:  {"ru": "загул"},                               # Клещи → загул (bender = загул, not клещи)
    113: {"ru": "улизнуть"},                            # Улизнул. → улизнуть (remove period, infinitive)
    129: {"ru": "руководители"},                        # Выполнения → руководители (execs = executives)
    139: {"ru": "облажаться"},                          # Завинчивать → облажаться (screwed up)
    140: {"ru": "сравнительный"},                       # Тайным → сравнительный (comparative)
    150: {"ru": "локон", "en": "Curl"},                 # Curle → Curl (typo)
    151: {"ru": "передовой"},                           # Режущая кромка → передовой (cutting edge = передовой)
    153: {"ru": "чрезмерно используемый"},              # Злоупотреблявшее → чрезмерно используемый
    161: {"en": "Pressure"},                            # Pressue → Pressure (typo)
    163: {"ru": "труба"},                               # Трубный звук → труба (trumpet = труба)
    174: {"ru": "возбуждённый"},                        # Горн → возбуждённый (horny ≠ горн)
    178: {"ru": "попрошайничество"},                    # Нищенство → same as 179, keep but fix: beg = просить/умолять
    178: {"ru": "умолять"},                             # Beg = умолять
    201: {"ru": "ударившийся"},                         # Ударившегося → ударившийся
    209: {"en": "Betrayal"},                            # Betraile → Betrayal (typo)
    213: {"en": "Grateful"},                            # Greatful → Grateful (typo)
    214: {"ru": "аутсайдеры"},                          # Побежденная сторона → аутсайдеры
    219: {"ru": "площадки"},                            # Футбольных поля → площадки
    223: {"en": "Distraction", "ru": "отвлечение"},     # Destraction → Distraction, удаление → отвлечение
    236: {"ru": "вход"},                                # Вступление → вход (entry = вход primarily)
    252: {"ru": "бросил"},                              # Брошенная → бросил (threw = past tense of throw)
    255: {"en": "Persuasive"},                          # PErsuasive → Persuasive
    272: {"ru": "бесящий"},                             # Бесящей → бесящий
    278: {"ru": "ил"},                                  # Осадок → ил (silt = ил specifically)
    282: "REMOVE",                                       # Smoot → Олово (not a real word, probably Smooth typo)
    285: {"ru": "охранник"},                            # Гвардия → охранник (guard = охранник)
    312: {"ru": "особняк"},                             # Дом → особняк (mansion = особняк)
    314: {"ru": "непрочитанный"},                       # Несчитанный → непрочитанный
    326: {"ru": "вмешательство"},                       # Интервенция → вмешательство
    329: {"ru": "инфляция"},                            # Вздутие → инфляция (inflation = инфляция)
    336: {"en": "Parameters", "ru": "параметры"},       # Paraneters/Пункт → Parameters/параметры
    339: {"ru": "уменьшать"},                           # Сводить → уменьшать (reduce)
    343: {"en": "Insurance", "ru": "страхование"},      # Insurens → Insurance
    348: {"ru": "осуждающий"},                          # Поверхностный → осуждающий (judgmental)
    349: {"ru": "заколотый"},                           # Колотой → заколотый
    357: {"ru": "питательные вещества"},                # Питательность → питательные вещества
    366: {"ru": "отменять"},                            # уничтожать → отменять (undo = отменять)
    372: {"ru": "сознание"},                            # сознание OK but typo in en
    372: {"en": "consciousness"},                       # conciousness → consciousness
    381: {"ru": "возможность"},                         # перспектива → возможность (opportunity)
    387: {"ru": "застревание"},                         # скрутка → застревание (stranding)
    391: {"en": "jerk"},                                # jerk of → jerk (typo)
    395: {"ru": "когда-либо"},                          # всегда → когда-либо (ever ≠ always)
    396: {"ru": "вызов"},                               # OK actually
    403: {"en": "particularly"},                        # particulary → particularly (typo)
    413: {"ru": "под"},                                 # нижний → под (underneath = под/снизу)
    415: {"en": "self-aware", "ru": "самосознающий"},   # self aware → self-aware
    427: {"en": "all participants", "ru": "все участники"}, # participant → participants
    437: {"ru": "резко падать"},                        # грузило → резко падать (plummet = резко падать)
    439: {"ru": "зависимость"},                         # наркомания → зависимость (addiction = зависимость)
    440: {"ru": "тяга"},                                # стремление → тяга (craving = тяга)
    443: "REMOVE",                                       # iner → в (broken duplicate of 442 inner)
    451: {"ru": "признаваться"},                        # исповедоваться → признаваться (confess)
    453: {"en": "Committee", "ru": "комитет"},          # commite/СССР → Committee/комитет
    463: {"en": "Accountancy"},                         # accountacy → Accountancy (typo)
    466: {"en": "Summarize", "ru": "подводить итог"},   # summerize → Summarize
    469: {"en": "Concerning"},                          # concering → Concerning (typo)
    492: {"ru": "штрих-код"},                           # штрих → штрих-код (barcode)
    505: {"ru": "намазать клей"},                       # клей распространения → намазать клей
    528: {"ru": "шестерни"},                            # зубья → шестерни (gears = шестерни)
    530: {"ru": "мошеннический"},                       # мошенник → мошеннический (adj)
    541: {"en": "Immediately"},                         # immediatly → Immediately (typo)
    543: {"ru": "трюковый"},                            # трюк → трюковый (gimmicky = adj)
    545: {"ru": "предпосылка"},                         # помещение → предпосылка (premise = предпосылка mainly)
    587: {"ru": "пильзнер"},                            # Пльзеньский → пильзнер
    589: "REMOVE",                                       # varity → duplicate of 588 variety
    611: {"en": "Precious", "ru": "драгоценный"},       # Presious/Раз → Precious/драгоценный
    616: {"ru": "хлопья"},                              # Злаковый → хлопья (cereal commonly = хлопья)
    621: {"en": "Extend", "ru": "расширять"},           # Extand/Ми → Extend/расширять
    623: {"ru": "что угодно"},                          # все → что угодно (whatever)
    627: "REMOVE",                                       # Grit up → not a real phrase
    628: {"ru": "задница"},                             # Дофига → задница (wazoo = slang for butt)
    629: {"ru": "позволять себе"},                      # Давать → позволять себе (afford)
    630: {"ru": "антиутопический"},                     # Мрачный → антиутопический (dystopian)
    646: {"ru": "подача"},                              # Тангаж → подача (pitch in common usage)
    660: {"ru": "неправильно подобранный"},             # нужен → неправильно подобранный (miscast)

    # Full sentences to REMOVE (not vocabulary words)
    5:   "REMOVE",  # Comparison of the political system...
    10:  "REMOVE",  # I usually play much better
    202: "REMOVE",  # This is over
}

# Apply fixes
removed = 0
for idx in sorted(fixes.keys(), reverse=True):
    fix = fixes[idx]
    if fix == "REMOVE":
        en = words[idx]["en"]
        print(f"REMOVE [{idx}]: {en}")
        words.pop(idx)
        removed += 1
    else:
        old_en = words[idx]["en"]
        old_ru = words[idx]["ru"]
        for k, v in fix.items():
            words[idx][k] = v
        new_en = words[idx]["en"]
        new_ru = words[idx]["ru"]
        print(f"FIX [{idx}]: {old_en}→{new_en} | {old_ru}→{new_ru}")

# Save
with open(WORDS_FILE, "w", encoding="utf-8") as f:
    json.dump(words, f, ensure_ascii=False, indent=2)

print(f"\nApplied fixes. Removed {removed} entries. {len(words)} words remaining.")
