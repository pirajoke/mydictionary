# Lexi: лист человеческой проверки немецкого пакета

Статус: ожидает проверки человеком. Ни одна запись ниже не считается согласованной.
Пакет подготовлен автоматически для удобства редактора; он не заменяет лингвистическую вычитку.

Источник: [draft PR #143](https://github.com/pirajoke/mydictionary/pull/143), коммит `ebdfb24d39563af77eb3a9da4f8c4b25ba644077`.
Извлечено 2026-09-15 из `words_de_basic.json` и `content/german_editorial.json` без изменения текста.
100 записей, 45 с дополнительными принимаемыми переводами, 10 глаголов с формами.

Редактор (владеющий немецким и русским): __________
Дата проверки: __________
Проверенный SHA: __________
Решение: ОЖИДАЕТ / НУЖНЫ ПРАВКИ / СОГЛАСОВАНО

Для каждой строки проверить естественность немецкого примера, точность русского перевода,
артикль/множественное число/формы, часть речи и границы принимаемых ответов.
В колонке «Решение и правка» вписать «ОК» либо точную замену и причину.
Весь пакет согласован только после решения по всем 100 строкам и подписи выше.
Изменённый SHA требует повторной проверки затронутых строк. Согласование редактора не является разрешением на merge или deploy.

Отдельно проверить сохранённые широкие соответствия: Hand — рука/кисть руки;
Vormittag — утро/первая половина дня; Straße — улица/дорога; Bahnhof — железнодорожный вокзал;
es tut mir leid — простите/мне жаль; Medizin — значение лекарства.
Пометка «meist Singular» описывает обычное употребление, а не отсутствие всех специальных множественных форм.
Исходные основные переводы, идентификаторы и IPA этим редакторским обновлением не менялись.
Этот лист не удостоверяет IPA и не содержит оценки CEFR.

| № / entry_id | Слово и основной перевод | Пример DE → RU | Часть речи и грамматика | Все принимаемые переводы | Решение и правка |
|---|---|---|---|---|---|
| 1 / hello | Hallo → привет | Hallo, ich bin Anna.<br>Привет, я Анна. | interjection | привет; здравствуй; здравствуйте | ОЖИДАЕТ |
| 2 / goodbye | auf Wiedersehen → до свидания | Auf Wiedersehen, bis morgen!<br>До свидания, до завтра! | phrase | до свидания | ОЖИДАЕТ |
| 3 / please | bitte → пожалуйста | Ein Glas Wasser, bitte.<br>Стакан воды, пожалуйста. | particle | пожалуйста | ОЖИДАЕТ |
| 4 / thank-you | danke → спасибо | Danke für deine Hilfe!<br>Спасибо за твою помощь! | interjection | спасибо; благодарю | ОЖИДАЕТ |
| 5 / yes | ja → да | Ja, ich komme morgen.<br>Да, я приду завтра. | particle | да | ОЖИДАЕТ |
| 6 / no | nein → нет | Nein, das ist mein Buch.<br>Нет, это моя книга. | particle | нет | ОЖИДАЕТ |
| 7 / excuse-me | entschuldigen Sie → извините | Entschuldigen Sie, wo ist der Bahnhof?<br>Извините, где вокзал? | phrase<br>Примечание: Вежливое обращение на Sie; также перед вопросом. | извините; простите | ОЖИДАЕТ |
| 8 / sorry | es tut mir leid → простите | Es tut mir leid, ich habe keine Zeit.<br>Мне жаль, у меня нет времени. | phrase<br>Примечание: Выражает сожаление или извинение: «мне жаль». | простите; мне жаль; сожалею | ОЖИДАЕТ |
| 9 / good-morning | guten Morgen → доброе утро | Guten Morgen, Frau Weber!<br>Доброе утро, госпожа Вебер! | phrase | доброе утро; с добрым утром | ОЖИДАЕТ |
| 10 / good-night | gute Nacht → спокойной ночи | Gute Nacht, schlaf gut!<br>Спокойной ночи, спи хорошо! | phrase | спокойной ночи; доброй ночи | ОЖИДАЕТ |
| 11 / person | Person → человек | Eine Person wartet vor der Tür.<br>Один человек ждёт перед дверью. | noun<br>Артикль: die<br>Мн. число: Personen<br>Примечание: Person — человек любого пола; грамматический род женский. | человек; персона | ОЖИДАЕТ |
| 12 / friend | Freund → друг | Mein Freund wohnt in Berlin.<br>Мой друг живёт в Берлине. | noun<br>Артикль: der<br>Мн. число: Freunde | друг; приятель | ОЖИДАЕТ |
| 13 / family | Familie → семья | Meine Familie isst zusammen.<br>Моя семья ест вместе. | noun<br>Артикль: die<br>Мн. число: Familien | семья | ОЖИДАЕТ |
| 14 / mother | Mutter → мать | Meine Mutter liest ein Buch.<br>Моя мама читает книгу. | noun<br>Артикль: die<br>Мн. число: Mütter | мать; мама | ОЖИДАЕТ |
| 15 / father | Vater → отец | Mein Vater trinkt Tee.<br>Мой папа пьёт чай. | noun<br>Артикль: der<br>Мн. число: Väter | отец; папа | ОЖИДАЕТ |
| 16 / child | Kind → ребёнок | Das Kind spielt im Zimmer.<br>Ребёнок играет в комнате. | noun<br>Артикль: das<br>Мн. число: Kinder | ребёнок; дитя | ОЖИДАЕТ |
| 17 / woman | Frau → женщина | Die Frau öffnet das Fenster.<br>Женщина открывает окно. | noun<br>Артикль: die<br>Мн. число: Frauen | женщина | ОЖИДАЕТ |
| 18 / man | Mann → мужчина | Der Mann wartet auf den Bus.<br>Мужчина ждёт автобус. | noun<br>Артикль: der<br>Мн. число: Männer | мужчина | ОЖИДАЕТ |
| 19 / name | Name → имя | Wie ist dein Name?<br>Как тебя зовут? | noun<br>Артикль: der<br>Мн. число: Namen<br>Примечание: Склонение: der Name, den Namen, des Namens. | имя | ОЖИДАЕТ |
| 20 / teacher | Lehrer → учитель | Der Lehrer erklärt die Frage.<br>Учитель объясняет вопрос. | noun<br>Артикль: der<br>Мн. число: Lehrer | учитель; преподаватель | ОЖИДАЕТ |
| 21 / water | Wasser → вода | Das Wasser im Glas ist kalt.<br>Вода в стакане холодная. | noun<br>Артикль: das<br>Мн. число: meist Singular<br>Примечание: Обычно вещественное значение; специальные формы множественного числа: Wasser, Wässer. | вода | ОЖИДАЕТ |
| 22 / food | Nahrung → еда | Der Körper braucht Nahrung.<br>Организму нужна пища. | noun<br>Артикль: die<br>Мн. число: meist Singular<br>Примечание: Обобщённое обозначение пищи; обычно единственное число. | еда; пища; питание | ОЖИДАЕТ |
| 23 / bread | Brot → хлеб | Ich kaufe frisches Brot.<br>Я покупаю свежий хлеб. | noun<br>Артикль: das<br>Мн. число: Brote | хлеб | ОЖИДАЕТ |
| 24 / milk | Milch → молоко | Die Milch steht im Kühlschrank.<br>Молоко стоит в холодильнике. | noun<br>Артикль: die<br>Мн. число: meist Singular<br>Примечание: Обычно вещественное значение; специальные формы множественного числа: Milche, Milchen. | молоко | ОЖИДАЕТ |
| 25 / coffee | Kaffee → кофе | Mein Kaffee ist noch heiß.<br>Мой кофе ещё горячий. | noun<br>Артикль: der<br>Мн. число: meist Singular<br>Примечание: В обычном значении напитка — единственное число; сорта: Kaffees. | кофе | ОЖИДАЕТ |
| 26 / tea | Tee → чай | Wir trinken Tee ohne Zucker.<br>Мы пьём чай без сахара. | noun<br>Артикль: der<br>Мн. число: Tees<br>Примечание: Вещество обычно в единственном числе; Tees — сорта чая. | чай | ОЖИДАЕТ |
| 27 / apple | Apfel → яблоко | Der Apfel liegt auf dem Tisch.<br>Яблоко лежит на столе. | noun<br>Артикль: der<br>Мн. число: Äpfel | яблоко | ОЖИДАЕТ |
| 28 / rice | Reis → рис | Heute koche ich Reis.<br>Сегодня я готовлю рис. | noun<br>Артикль: der<br>Мн. число: meist Singular<br>Примечание: Обычно вещественное значение, единственное число. | рис | ОЖИДАЕТ |
| 29 / meat | Fleisch → мясо | Ich esse heute kein Fleisch.<br>Сегодня я не ем мясо. | noun<br>Артикль: das<br>Мн. число: meist Singular<br>Примечание: Обычно вещественное значение, единственное число. | мясо | ОЖИДАЕТ |
| 30 / fish | Fisch → рыба | Der Fisch schwimmt im Wasser.<br>Рыба плавает в воде. | noun<br>Артикль: der<br>Мн. число: Fische | рыба | ОЖИДАЕТ |
| 31 / house | Haus → дом | Unser Haus hat eine blaue Tür.<br>У нашего дома синяя дверь. | noun<br>Артикль: das<br>Мн. число: Häuser | дом | ОЖИДАЕТ |
| 32 / room | Zimmer → комната | Mein Zimmer ist klein.<br>Моя комната маленькая. | noun<br>Артикль: das<br>Мн. число: Zimmer | комната | ОЖИДАЕТ |
| 33 / door | Tür → дверь | Bitte mach die Tür zu.<br>Пожалуйста, закрой дверь. | noun<br>Артикль: die<br>Мн. число: Türen | дверь | ОЖИДАЕТ |
| 34 / window | Fenster → окно | Das Fenster ist offen.<br>Окно открыто. | noun<br>Артикль: das<br>Мн. число: Fenster | окно | ОЖИДАЕТ |
| 35 / table | Tisch → стол | Das Buch liegt auf dem Tisch.<br>Книга лежит на столе. | noun<br>Артикль: der<br>Мн. число: Tische | стол | ОЖИДАЕТ |
| 36 / chair | Stuhl → стул | Hier ist ein freier Stuhl.<br>Здесь есть свободный стул. | noun<br>Артикль: der<br>Мн. число: Stühle | стул | ОЖИДАЕТ |
| 37 / bed | Bett → кровать | Das Kind liegt im Bett.<br>Ребёнок лежит в кровати. | noun<br>Артикль: das<br>Мн. число: Betten | кровать; постель | ОЖИДАЕТ |
| 38 / kitchen | Küche → кухня | Wir kochen in der Küche.<br>Мы готовим на кухне. | noun<br>Артикль: die<br>Мн. число: Küchen | кухня | ОЖИДАЕТ |
| 39 / bathroom | Badezimmer → ванная | Das Badezimmer ist neben der Küche.<br>Ванная комната рядом с кухней. | noun<br>Артикль: das<br>Мн. число: Badezimmer | ванная; ванная комната | ОЖИДАЕТ |
| 40 / key | Schlüssel → ключ | Mein Schlüssel liegt hier.<br>Мой ключ лежит здесь. | noun<br>Артикль: der<br>Мн. число: Schlüssel | ключ | ОЖИДАЕТ |
| 41 / road | Straße → дорога | Die Straße ist heute ruhig.<br>На улице сегодня тихо. | noun<br>Артикль: die<br>Мн. число: Straßen<br>Примечание: Straße — прежде всего улица или дорога с покрытием. | дорога; улица | ОЖИДАЕТ |
| 42 / station | Bahnhof → станция | Wir treffen uns am Bahnhof.<br>Мы встречаемся на вокзале. | noun<br>Артикль: der<br>Мн. число: Bahnhöfe<br>Примечание: Bahnhof — железнодорожный вокзал или станция. | станция; вокзал; железнодорожная станция | ОЖИДАЕТ |
| 43 / airport | Flughafen → аэропорт | Der Bus fährt zum Flughafen.<br>Автобус едет в аэропорт. | noun<br>Артикль: der<br>Мн. число: Flughäfen | аэропорт | ОЖИДАЕТ |
| 44 / hotel | Hotel → отель | Unser Hotel ist am Bahnhof.<br>Наш отель у вокзала. | noun<br>Артикль: das<br>Мн. число: Hotels | отель; гостиница | ОЖИДАЕТ |
| 45 / ticket | Fahrkarte → билет | Ich kaufe eine Fahrkarte nach Bonn.<br>Я покупаю билет до Бонна. | noun<br>Артикль: die<br>Мн. число: Fahrkarten | билет; проездной билет | ОЖИДАЕТ |
| 46 / car | Auto → автомобиль | Das Auto steht vor dem Haus.<br>Машина стоит перед домом. | noun<br>Артикль: das<br>Мн. число: Autos | автомобиль; машина; авто | ОЖИДАЕТ |
| 47 / train | Zug → поезд | Der Zug kommt in zehn Minuten.<br>Поезд прибудет через десять минут. | noun<br>Артикль: der<br>Мн. число: Züge | поезд | ОЖИДАЕТ |
| 48 / bus | Bus → автобус | Dieser Bus fährt ins Zentrum.<br>Этот автобус едет в центр. | noun<br>Артикль: der<br>Мн. число: Busse | автобус | ОЖИДАЕТ |
| 49 / city | Stadt → город | Diese Stadt hat einen großen Park.<br>В этом городе есть большой парк. | noun<br>Артикль: die<br>Мн. число: Städte | город | ОЖИДАЕТ |
| 50 / country | Land → страна | In welchem Land wohnst du?<br>В какой стране ты живёшь? | noun<br>Артикль: das<br>Мн. число: Länder | страна; государство | ОЖИДАЕТ |
| 51 / today | heute → сегодня | Heute bleibe ich zu Hause.<br>Сегодня я остаюсь дома. | adverb | сегодня | ОЖИДАЕТ |
| 52 / tomorrow | morgen → завтра | Morgen beginnt die Schule.<br>Завтра начинается учёба в школе. | adverb | завтра | ОЖИДАЕТ |
| 53 / yesterday | gestern → вчера | Gestern war ich im Büro.<br>Вчера я был в офисе. | adverb | вчера | ОЖИДАЕТ |
| 54 / now | jetzt → сейчас | Jetzt habe ich Zeit.<br>Сейчас у меня есть время. | adverb | сейчас; теперь | ОЖИДАЕТ |
| 55 / morning | Vormittag → утро | Am Vormittag arbeite ich im Büro.<br>В первой половине дня я работаю в офисе. | noun<br>Артикль: der<br>Мн. число: Vormittage<br>Примечание: Vormittag — время до полудня; не всё утро в широком смысле. | утро; первая половина дня | ОЖИДАЕТ |
| 56 / evening | Abend → вечер | Am Abend lese ich gern.<br>Вечером я люблю читать. | noun<br>Артикль: der<br>Мн. число: Abende | вечер | ОЖИДАЕТ |
| 57 / day | Tag → день | Ein Tag hat vierundzwanzig Stunden.<br>В сутках двадцать четыре часа. | noun<br>Артикль: der<br>Мн. число: Tage | день; сутки | ОЖИДАЕТ |
| 58 / week | Woche → неделя | Eine Woche hat sieben Tage.<br>В неделе семь дней. | noun<br>Артикль: die<br>Мн. число: Wochen | неделя | ОЖИДАЕТ |
| 59 / month | Monat → месяц | Nächsten Monat fahre ich nach Berlin.<br>В следующем месяце я еду в Берлин. | noun<br>Артикль: der<br>Мн. число: Monate | месяц | ОЖИДАЕТ |
| 60 / year | Jahr → год | Dieses Jahr lerne ich Deutsch.<br>В этом году я учу немецкий. | noun<br>Артикль: das<br>Мн. число: Jahre | год | ОЖИДАЕТ |
| 61 / work | Arbeit → работа | Meine Arbeit beginnt um neun Uhr.<br>Моя работа начинается в девять часов. | noun<br>Артикль: die<br>Мн. число: Arbeiten | работа; труд | ОЖИДАЕТ |
| 62 / school | Schule → школа | Die Schule ist neben dem Park.<br>Школа находится рядом с парком. | noun<br>Артикль: die<br>Мн. число: Schulen | школа | ОЖИДАЕТ |
| 63 / student | Student → студент | Der Student liest in der Bibliothek.<br>Студент читает в библиотеке. | noun<br>Артикль: der<br>Мн. число: Studenten<br>Примечание: Слабое склонение: der Student, den Studenten. | студент | ОЖИДАЕТ |
| 64 / book | Buch → книга | Das Buch ist neu.<br>Книга новая. | noun<br>Артикль: das<br>Мн. число: Bücher | книга; книжка | ОЖИДАЕТ |
| 65 / money | Geld → деньги | Ich habe Geld für die Fahrkarte.<br>У меня есть деньги на билет. | noun<br>Артикль: das<br>Мн. число: Gelder<br>Примечание: Обычно единственное число; Gelder — выделенные денежные средства. | деньги; денежные средства | ОЖИДАЕТ |
| 66 / shop | Geschäft → магазин | Das Geschäft öffnet um acht Uhr.<br>Магазин открывается в восемь часов. | noun<br>Артикль: das<br>Мн. число: Geschäfte | магазин; лавка | ОЖИДАЕТ |
| 67 / office | Büro → офис | Heute bin ich im Büro.<br>Сегодня я в офисе. | noun<br>Артикль: das<br>Мн. число: Büros | офис; контора | ОЖИДАЕТ |
| 68 / computer | Computer → компьютер | Mein Computer ist sehr schnell.<br>Мой компьютер очень быстрый. | noun<br>Артикль: der<br>Мн. число: Computer | компьютер | ОЖИДАЕТ |
| 69 / phone | Telefon → телефон | Das Telefon klingelt im Büro.<br>В офисе звонит телефон. | noun<br>Артикль: das<br>Мн. число: Telefone | телефон; телефонный аппарат | ОЖИДАЕТ |
| 70 / question | Frage → вопрос | Ich habe eine Frage zum Text.<br>У меня есть вопрос по тексту. | noun<br>Артикль: die<br>Мн. число: Fragen | вопрос | ОЖИДАЕТ |
| 71 / doctor | Arzt → врач | Der Arzt spricht mit dem Kind.<br>Врач разговаривает с ребёнком. | noun<br>Артикль: der<br>Мн. число: Ärzte | врач; доктор | ОЖИДАЕТ |
| 72 / hospital | Krankenhaus → больница | Das Krankenhaus ist in dieser Straße.<br>Больница находится на этой улице. | noun<br>Артикль: das<br>Мн. число: Krankenhäuser | больница | ОЖИДАЕТ |
| 73 / head | Kopf → голова | Mein Kopf tut weh.<br>У меня болит голова. | noun<br>Артикль: der<br>Мн. число: Köpfe | голова | ОЖИДАЕТ |
| 74 / hand | Hand → рука | Das Kind hält meine Hand.<br>Ребёнок держит меня за руку. | noun<br>Артикль: die<br>Мн. число: Hände<br>Примечание: Hand — кисть руки; вся рука — Arm. | рука; кисть; кисть руки | ОЖИДАЕТ |
| 75 / eye | Auge → глаз | Ihre Augen sind blau.<br>У неё голубые глаза. | noun<br>Артикль: das<br>Мн. число: Augen | глаз | ОЖИДАЕТ |
| 76 / heart | Herz → сердце | Mein Herz schlägt schnell.<br>Моё сердце быстро бьётся. | noun<br>Артикль: das<br>Мн. число: Herzen<br>Примечание: Склонение: das Herz, des Herzens, dem Herzen. | сердце | ОЖИДАЕТ |
| 77 / pain | Schmerz → боль | Ich habe Schmerzen im Rücken.<br>У меня болит спина. | noun<br>Артикль: der<br>Мн. число: Schmerzen | боль | ОЖИДАЕТ |
| 78 / medicine | Medizin → лекарство | Die Medizin steht im Schrank.<br>Лекарство стоит в шкафу. | noun<br>Артикль: die<br>Мн. число: Medizinen<br>Примечание: Здесь Medizin означает лекарство; другое значение — медицина. | лекарство; медикамент; лекарственное средство | ОЖИДАЕТ |
| 79 / tired | müde → уставший | Nach der Arbeit bin ich müde.<br>После работы я чувствую усталость. | adjective | уставший; усталый; утомлённый | ОЖИДАЕТ |
| 80 / healthy | gesund → здоровый | Das Kind ist wieder gesund.<br>Ребёнок снова здоров. | adjective | здоровый | ОЖИДАЕТ |
| 81 / go | gehen → идти | Ich gehe zu Fuß zur Schule.<br>Я иду в школу пешком. | verb<br>Наст. время: er geht<br>Претерит: er ging<br>Перфект: er ist gegangen | идти; ходить | ОЖИДАЕТ |
| 82 / come | kommen → приходить | Kommst du morgen zu uns?<br>Ты придёшь к нам завтра? | verb<br>Наст. время: er kommt<br>Претерит: er kam<br>Перфект: er ist gekommen | приходить; прибывать | ОЖИДАЕТ |
| 83 / eat | essen → есть | Wir essen zusammen in der Küche.<br>Мы едим вместе на кухне. | verb<br>Наст. время: er isst<br>Претерит: er aß<br>Перфект: er hat gegessen | есть; кушать | ОЖИДАЕТ |
| 84 / drink | trinken → пить | Ich trinke ein Glas Wasser.<br>Я пью стакан воды. | verb<br>Наст. время: er trinkt<br>Претерит: er trank<br>Перфект: er hat getrunken | пить | ОЖИДАЕТ |
| 85 / sleep | schlafen → спать | Das Kind schläft schon.<br>Ребёнок уже спит. | verb<br>Наст. время: er schläft<br>Претерит: er schlief<br>Перфект: er hat geschlafen | спать | ОЖИДАЕТ |
| 86 / read | lesen → читать | Sie liest jeden Abend ein Buch.<br>Она каждый вечер читает книгу. | verb<br>Наст. время: er liest<br>Претерит: er las<br>Перфект: er hat gelesen | читать | ОЖИДАЕТ |
| 87 / write | schreiben → писать | Ich schreibe meinen Namen.<br>Я пишу своё имя. | verb<br>Наст. время: er schreibt<br>Претерит: er schrieb<br>Перфект: er hat geschrieben | писать | ОЖИДАЕТ |
| 88 / speak | sprechen → говорить | Wir sprechen heute Deutsch.<br>Сегодня мы говорим по-немецки. | verb<br>Наст. время: er spricht<br>Претерит: er sprach<br>Перфект: er hat gesprochen | говорить; разговаривать | ОЖИДАЕТ |
| 89 / listen | zuhören → слушать | Ich höre dir zu.<br>Я тебя слушаю. | verb<br>Наст. время: er hört zu<br>Претерит: er hörte zu<br>Перфект: er hat zugehört<br>Примечание: Отделяемая приставка zu-; слушать кого-либо: в немецком Dativ (dir zuhören). | слушать; выслушивать | ОЖИДАЕТ |
| 90 / help | helfen → помогать | Kannst du mir bitte helfen?<br>Ты можешь мне помочь, пожалуйста? | verb<br>Наст. время: er hilft<br>Претерит: er half<br>Перфект: er hat geholfen<br>Примечание: Кому помогать: Dativ (mir helfen). | помогать; оказывать помощь | ОЖИДАЕТ |
| 91 / big | groß → большой | Das Zimmer ist groß und hell.<br>Комната большая и светлая. | adjective | большой; крупный | ОЖИДАЕТ |
| 92 / small | klein → маленький | Wir wohnen in einem kleinen Haus.<br>Мы живём в маленьком доме. | adjective | маленький; небольшой | ОЖИДАЕТ |
| 93 / good | gut → хороший | Das ist eine gute Idee.<br>Это хорошая идея. | adjective | хороший | ОЖИДАЕТ |
| 94 / bad | schlecht → плохой | Das Wetter ist heute schlecht.<br>Сегодня плохая погода. | adjective | плохой; дурной; скверный | ОЖИДАЕТ |
| 95 / new | neu → новый | Mein neues Fahrrad ist blau.<br>Мой новый велосипед синий. | adjective | новый | ОЖИДАЕТ |
| 96 / old | alt → старый | Das alte Haus steht am Fluss.<br>Старый дом стоит у реки. | adjective | старый | ОЖИДАЕТ |
| 97 / hot | heiß → горячий | Vorsicht, der Tee ist heiß!<br>Осторожно, чай горячий! | adjective | горячий; жаркий | ОЖИДАЕТ |
| 98 / cold | kalt → холодный | Das Wasser ist mir zu kalt.<br>Эта вода для меня слишком холодная. | adjective | холодный | ОЖИДАЕТ |
| 99 / happy | glücklich → счастливый | Ich bin glücklich, dass du hier bist.<br>Я счастлив, что ты здесь. | adjective | счастливый | ОЖИДАЕТ |
| 100 / sad | traurig → грустный | Sie ist traurig, weil ihr Freund geht.<br>Ей грустно, потому что её друг уходит. | adjective | грустный; печальный | ОЖИДАЕТ |
