(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("dictionary-data").textContent);
  const packs = data.packs;
  const $ = (id) => document.getElementById(id);
  const isFile = document.body.dataset.download === "true" || location.protocol === "file:";
  const storageKey = "lexi:dictionary:v1";
  const copy = {
    en: {
      title: "Your words, at hand.", intro: "Find a word. Save it. Remember it.", target: "Learning", native: "Translation", swap: "Swap languages", search_label: "Word or short phrase", placeholder: "Search either language", clear: "Clear", all: "Dictionary", saved: "Saved", practice: "Practise 5 words", practice_title: "A little practice", close: "Close practice", answer_label: "Write the translation", check: "Check", show: "Show answer", next: "Next word", online_hint: "For words and phrases outside this pack, use online translation.", translate: "Translate in Yandex ↗", provider_note: "Only this click sends your text to Yandex. Internet required.", offline_title: "Take your dictionary with you", offline_body: "Save these packs for local search and practice without internet.", save_offline: "Save on this device", download: "Download dictionary", export: "Export saved words · CSV", offline_limit: "Offline: included words and practice. AI, new translations and online audio need internet. Your device may clear browser storage.", how_open: "How to open offline", instructions: "Open this page in Safari or Chrome, save it on this device, then add it to your home screen. You can also download the HTML file and open it in a browser. Some phone file previews do not run interactive files.", local_note: "Saved words and practice stay in this browser. They do not sync with your Telegram progress.", interface: "Interface language", free: "Free starter dictionary", remove_offline: "Remove offline packs", online: "Local search · online", offline: "Local search · offline", file_ready: "Downloaded dictionary", cached: "Ready offline", pack: "{count} words in this pair · search and practice are free", results: "{count} results", truncated: "Showing {shown} of {count}. Refine your search.", save: "+ Save", unsave: "✓ Saved", no_match: "This word is not in the starter pack. Try a shorter spelling or translate it online.", no_saved: "Save words with “+ Save”. They will appear here for practice.", empty_filter: "No saved words match this search.", saving: "Saving dictionary…", save_success: "Dictionary saved. Open this page once in your browser; then it can reopen without internet. Saved words remain on this device.", save_error: "Could not save for offline use. Try again in Safari or Chrome, or download the HTML file.", removed: "Offline packs removed. Your saved words are still here.", storage_error: "Your browser cannot save changes. Search still works; export your saved words before closing.", correct: "Correct!", correction: "Correct translation:", complete: "Done for now. Come back tomorrow for another short practice.", score: "{correct} of {total} recalled without hints", position: "Word {index} of {total}", unsupported: "This language is not in the downloadable starter packs yet. An available language pair was selected. Other languages remain available in Telegram.", remind: "Due for another try", no_export: "Save a word first.", file_help: "This file already contains all starter packs. Open it in a browser without internet. Favourites saved in another browser are not copied into this file.", offline_provider: "New translations need internet. Your downloaded words still work.", recall: "Try to remember before revealing the answer.", copied: "Saved words exported."
    },
    ru: {
      title: "Слова всегда под рукой.", intro: "Найди перевод. Сохрани. Запомни.", target: "Изучаю", native: "Перевод", swap: "Поменять языки местами", search_label: "Слово или короткая фраза", placeholder: "Ищи на любом из двух языков", clear: "Очистить", all: "Словарь", saved: "Сохранено", practice: "Повторить 5 слов", practice_title: "Немного практики", close: "Закрыть практику", answer_label: "Напиши перевод", check: "Проверить", show: "Показать ответ", next: "Следующее слово", online_hint: "Слова и фразы за пределами набора можно перевести онлайн.", translate: "Перевести в Яндексе ↗", provider_note: "Только после нажатия текст отправится в Яндекс. Нужен интернет.", offline_title: "Возьми словарь с собой", offline_body: "Сохрани наборы для поиска и практики без интернета.", save_offline: "Сохранить на устройстве", download: "Скачать словарь", export: "Сохранённые слова · CSV", offline_limit: "Без сети: слова из наборов и практика. AI, новые переводы и онлайн-озвучка требуют интернета. Устройство может очистить кэш браузера.", how_open: "Как пользоваться без сети", instructions: "Открой страницу в Safari или Chrome, сохрани на устройстве и добавь на главный экран. Также можно скачать HTML-файл и открыть его в браузере. Некоторые приложения «Файлы» не запускают интерактивный просмотр.", local_note: "Слова и практика хранятся в этом браузере. Они не синхронизируются с прогрессом в Telegram.", interface: "Язык интерфейса", free: "Бесплатный базовый словарь", remove_offline: "Удалить офлайн-наборы", online: "Поиск на устройстве · онлайн", offline: "Поиск на устройстве · без сети", file_ready: "Скачанный словарь", cached: "Доступен без сети", pack: "{count} слов в этой паре · поиск и практика бесплатны", results: "Найдено: {count}", truncated: "Показано {shown} из {count}. Уточни запрос.", save: "+ Сохранить", unsave: "✓ Сохранено", no_match: "Этого слова пока нет в базовом наборе. Попробуй сократить запрос или переведи его онлайн.", no_saved: "Нажми «+ Сохранить» рядом со словом — оно появится здесь для повторения.", empty_filter: "Среди сохранённых слов совпадений нет.", saving: "Сохраняю словарь…", save_success: "Словарь сохранён. Один раз открой эту страницу в браузере — затем она откроется без сети. Сохранённые слова остаются на устройстве.", save_error: "Не получилось сохранить для офлайн-работы. Попробуй в Safari или Chrome либо скачай HTML-файл.", removed: "Офлайн-наборы удалены. Сохранённые слова остались.", storage_error: "Браузер не сохраняет изменения. Поиск работает; выгрузи слова перед закрытием.", correct: "Верно!", correction: "Правильный перевод:", complete: "На сегодня достаточно. Возвращайся завтра на короткое повторение.", score: "Без подсказок: {correct} из {total}", position: "Слово {index} из {total}", unsupported: "Этого языка пока нет в скачиваемых базовых наборах. Выбрана доступная языковая пара. Остальные языки доступны в Telegram.", remind: "Пора попробовать снова", no_export: "Сначала сохрани хотя бы одно слово.", file_help: "Все базовые наборы уже внутри файла. Открой его в браузере без интернета. Избранное из другого браузера в этот файл не переносится.", offline_provider: "Для новых переводов нужен интернет. Скачанные слова продолжают работать.", recall: "Попробуй вспомнить, прежде чем открыть ответ.", copied: "Сохранённые слова выгружены."
    },
    fr: {
      title: "Tes mots, à portée de main.", intro: "Trouve une traduction. Garde-la. Retiens-la.", target: "J’apprends", native: "Traduction", swap: "Inverser les langues", search_label: "Mot ou courte phrase", placeholder: "Chercher dans les deux langues", clear: "Effacer", all: "Dictionnaire", saved: "Enregistrés", practice: "Réviser 5 mots", practice_title: "Un peu de pratique", close: "Fermer", answer_label: "Écris la traduction", check: "Vérifier", show: "Voir la réponse", next: "Mot suivant", online_hint: "Pour les mots et phrases hors de ce pack, utilise la traduction en ligne.", translate: "Traduire avec Yandex ↗", provider_note: "Seul ce clic envoie le texte à Yandex. Internet nécessaire.", offline_title: "Emporte ton dictionnaire", offline_body: "Enregistre les packs pour chercher et pratiquer sans internet.", save_offline: "Enregistrer sur cet appareil", download: "Télécharger le dictionnaire", export: "Exporter mes mots · CSV", offline_limit: "Hors ligne : mots inclus et exercices. IA, nouvelles traductions et audio en ligne nécessitent internet. Le navigateur peut vider son stockage.", how_open: "Comment ouvrir hors ligne", instructions: "Ouvre cette page dans Safari ou Chrome, enregistre-la sur cet appareil et ajoute-la à l’écran d’accueil. Tu peux aussi télécharger le fichier HTML et l’ouvrir dans un navigateur. Certains aperçus de fichiers sur téléphone ne sont pas interactifs.", local_note: "Mots et exercices restent dans ce navigateur, sans synchronisation avec ta progression Telegram.", interface: "Langue de l’interface", free: "Dictionnaire de base gratuit", remove_offline: "Supprimer les packs hors ligne", online: "Recherche locale · en ligne", offline: "Recherche locale · hors ligne", file_ready: "Dictionnaire téléchargé", cached: "Disponible hors ligne", pack: "{count} mots dans cette paire · recherche et pratique gratuites", results: "{count} résultats", truncated: "{shown} sur {count} affichés. Affine ta recherche.", save: "+ Garder", unsave: "✓ Gardé", no_match: "Ce mot n’est pas encore dans le pack. Essaie une recherche plus courte ou traduis-le en ligne.", no_saved: "Appuie sur « + Garder » pour retrouver ici tes mots à réviser.", empty_filter: "Aucun mot enregistré ne correspond.", saving: "Enregistrement…", save_success: "Dictionnaire enregistré. Ouvre cette page une fois dans ton navigateur pour pouvoir la rouvrir sans internet.", save_error: "Impossible d’enregistrer hors ligne. Réessaie dans Safari ou Chrome, ou télécharge le fichier HTML.", removed: "Packs hors ligne supprimés. Tes mots sont conservés.", storage_error: "Le navigateur ne peut pas enregistrer les changements. Exporte tes mots avant de fermer.", correct: "Exact !", correction: "Traduction correcte :", complete: "C’est assez pour aujourd’hui. Reviens demain pour une courte révision.", score: "{correct} sur {total} sans indice", position: "Mot {index} sur {total}", unsupported: "Cette langue n’est pas encore téléchargeable. Une paire disponible a été sélectionnée. Les autres langues restent disponibles dans Telegram.", remind: "À réessayer", no_export: "Enregistre d’abord un mot.", file_help: "Tous les packs sont déjà dans ce fichier. Ouvre-le dans un navigateur sans internet. Les favoris d’un autre navigateur ne sont pas copiés ici.", offline_provider: "Les nouvelles traductions nécessitent internet. Les mots téléchargés fonctionnent toujours.", recall: "Essaie de te rappeler avant d’afficher la réponse.", copied: "Mots enregistrés exportés."
    }
  };
  let saved = {};
  let preferences = {};
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || "{}");
    if (stored.saved && typeof stored.saved === "object" && !Array.isArray(stored.saved)) {
      // Covers all 4,200 directional starter entries without truncating valid
      // favourites, while bounding deliberately malformed local storage.
      saved = Object.fromEntries(Object.entries(stored.saved).slice(0, 10000).filter(([key, value]) => /^[a-z]{2}:[a-z]{2}:[\w-]{1,100}$/.test(key) && value && typeof value === "object"));
    }
    preferences = Object.fromEntries(Object.entries(stored.preferences || {}).filter(([key,value]) => ["target","native","ui"].includes(key) && typeof value === "string" && /^[a-z]{2}$/.test(value)));
  } catch (_) { /* Local lookup also works when storage is unavailable. */ }
  const params = new URLSearchParams(location.search);
  const languageCodes = packs.map((pack) => pack.target_language);
  const requestedTarget = params.get("target") || (isFile && document.body.dataset.defaultTarget) || preferences.target || "en";
  let target = languageCodes.includes(requestedTarget) ? requestedTarget : "en";
  const requestedNative = params.get("native") || (isFile && document.body.dataset.defaultNative) || preferences.native || "ru";
  let native = languageCodes.includes(requestedNative) ? requestedNative : "ru";
  if (native === target) native = target === "ru" ? "en" : "ru";
  const requestedUi = (params.get("ui") || (isFile && document.body.dataset.defaultUi) || preferences.ui || navigator.language || "en").split("-")[0];
  let ui = Object.hasOwn(copy,requestedUi) ? requestedUi : "en";
  let view = "all";
  let offlineReady = false;
  let session = null;
  const normalized = (value) => String(value || "").normalize("NFKC").toLocaleLowerCase().replace(/\s+/g, " ").trim();
  const searchable = (value) => normalized(value).normalize("NFD").replace(/\p{M}/gu, "");
  const t = (key, values = {}) => Object.entries(values).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), copy[ui][key] || copy.en[key] || key);
  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify({saved, preferences: {target, native, ui}})); }
    catch (_) { $("offline-status").textContent = t("storage_error"); $("offline-status").className = "error"; }
  }
  function entries() {
    const pack = packs.find((item) => item.target_language === target);
    const meaningPack = packs.find((item) => item.target_language === native);
    const aligned = new Map(meaningPack.entries.map((entry) => [entry.entry_id, entry]));
    return pack.entries.flatMap((entry) => {
      const match = aligned.get(entry.entry_id);
      const meaning = native === "ru" ? entry.meaning : match?.target;
      if (!meaning) return [];
      return [{...entry, meaning, key: `${target}:${native}:${entry.entry_id}`, meanings: native === "ru" ? (entry.accepted_meanings || [meaning]) : [meaning], example: native === "ru" ? entry.example : (entry.example?.target ? {target: entry.example.target, meaning: ""} : null)}];
    });
  }
  function labelLanguage(code) {
    try { return new Intl.DisplayNames([ui], {type:"language"}).of(code); }
    catch (_) { return code.toUpperCase(); }
  }
  function setLanguageOptions() {
    for (const [id, selected] of [["target-language",target],["native-language",native]]) {
      $(id).replaceChildren(...languageCodes.map((code) => {
        const option = document.createElement("option"); option.value = code; option.textContent = labelLanguage(code); option.selected = code === selected; return option;
      }));
    }
    $("interface-language").replaceChildren(...[["en","English"],["ru","Русский"],["fr","Français"]].map(([code,label]) => { const option=document.createElement("option"); option.value=code; option.textContent=label; option.selected=code===ui; return option; }));
  }
  function connection() {
    $("connection-status").textContent = isFile ? t("file_ready") : offlineReady ? t("cached") : navigator.onLine ? t("online") : t("offline");
    $("connection-status").classList.toggle("ready", offlineReady || isFile);
  }
  function applyCopy() {
    document.documentElement.lang = ui;
    document.title = `Lexi · ${t("all")}`;
    document.querySelectorAll("[data-copy]").forEach((node) => {node.textContent = t(node.dataset.copy);});
    document.querySelectorAll("[data-label]").forEach((node) => {node.setAttribute("aria-label",t(node.dataset.label));});
    $("dictionary-query").placeholder = t("placeholder");
    $("target-language").setAttribute("aria-label",t("target"));
    $("native-language").setAttribute("aria-label",t("native"));
    $("interface-language").setAttribute("aria-label",t("interface"));
    document.querySelector(".view-switch").setAttribute("aria-label",t("all"));
    setLanguageOptions(); connection();
    if (!$("pair-notice").hidden) $("pair-notice").textContent = t("unsupported");
    $("download-dictionary").href = `/dictionary/download?${new URLSearchParams({target,native,ui})}`;
    $("download-dictionary").hidden = isFile;
    $("save-offline").hidden = isFile;
    if (isFile) $("offline-status").textContent = t("file_help");
  }
  function row(entry) {
    const item = document.createElement("article"); item.className="word-row";
    const content=document.createElement("div"); content.className="word-copy";
    for (const [className,value] of [["word-target",entry.target],["word-transcription",entry.transcription],["word-meaning",entry.meaning]]) {
      if (!value) continue;
      const line=document.createElement("p"); line.className=className; line.dir="auto"; line.textContent=value; content.append(line);
    }
    if (entry.example?.target) { const example=document.createElement("p"); example.className="word-example"; example.dir="auto"; example.textContent=[entry.example.target,entry.example.meaning].filter(Boolean).join(" — "); content.append(example); }
    const button=document.createElement("button"); button.type="button"; button.className="save-word";
    button.textContent=t(saved[entry.key] ? "unsave":"save"); button.setAttribute("aria-pressed",String(Boolean(saved[entry.key]))); button.setAttribute("aria-label",`${button.textContent}: ${entry.target}`);
    button.addEventListener("click",()=>{
      if (saved[entry.key]) delete saved[entry.key]; else saved[entry.key]={due:Date.now(),interval:0};
      persist(); render();
      const replacement=Array.from($("dictionary-results").querySelectorAll(".save-word")).find((candidate)=>candidate.getAttribute("aria-label")?.endsWith(`: ${entry.target}`));
      if (replacement) replacement.focus({preventScroll:true});
    });
    item.append(content,button); return item;
  }
  function render() {
    const all=entries(); const query=$("dictionary-query").value.trim(); const needle=searchable(query);
    const selected=all.filter((entry)=>saved[entry.key]);
    $("saved-count").textContent=selected.length;
    $("pack-note").textContent=t("pack",{count:all.length});
    $("view-all").setAttribute("aria-pressed",String(view==="all")); $("view-saved").setAttribute("aria-pressed",String(view==="saved"));
    const matches=(view==="saved" ? selected : all).map((entry)=>{
      const fields=[entry.target,...entry.meanings,entry.transcription].map(searchable);
      const rank=!needle ? 0 : fields.includes(needle) ? 0 : fields.some((field)=>field.startsWith(needle)) ? 1 : fields.some((field)=>field.includes(needle)) ? 2 : 9;
      return {entry,rank};
    }).filter((item)=>item.rank<9).sort((a,b)=>a.rank-b.rank).map((item)=>item.entry);
    const shown=matches.slice(0,50); $("dictionary-results").replaceChildren(...shown.map(row));
    $("result-status").textContent=matches.length>50?t("truncated",{shown:50,count:matches.length}):t("results",{count:matches.length});
    $("empty-results").hidden=matches.length>0;
    $("empty-copy").textContent=t(view==="saved" ? selected.length ? "empty_filter":"no_saved":"no_match");
    $("start-practice").disabled=all.length===0;
    $("online-translation").hidden=!query;
    const link=$("translate-link");
    link.hidden=!navigator.onLine;
    link.href=`https://translate.yandex.com/?${new URLSearchParams({source_lang:target,target_lang:native,text:query})}`;
    $("online-translation").querySelector("p").textContent=t(navigator.onLine?"online_hint":"offline_provider");
  }
  function closePractice(){session=null;$("practice-area").hidden=true;$("dictionary-results").hidden=false;render();}
  function changePair(){closePractice();$("pair-notice").hidden=true;$("dictionary-query").value="";persist();applyCopy();render();}
  $("target-language").addEventListener("change",()=>{const old=target;target=$("target-language").value;if(native===target) native=old;changePair();});
  $("native-language").addEventListener("change",()=>{const old=native;native=$("native-language").value;if(target===native) target=old;changePair();});
  $("swap-languages").addEventListener("click",()=>{[target,native]=[native,target];changePair();});
  $("interface-language").addEventListener("change",()=>{ui=$("interface-language").value;closePractice();persist();applyCopy();render();});
  $("dictionary-query").addEventListener("input",render);
  $("clear-query").addEventListener("click",()=>{$("dictionary-query").value="";render();$("dictionary-query").focus();});
  $("view-all").addEventListener("click",()=>{view="all";render();});
  $("view-saved").addEventListener("click",()=>{view="saved";render();});
  function practiceWord() {
    const entry=session.words[session.index];
    $("practice-position").textContent=t("position",{index:session.index+1,total:session.words.length});
    $("practice-question").textContent=entry.target;
    $("practice-input").value=""; $("practice-input").disabled=false;
    $("practice-form").hidden=false; $("check-answer").disabled=false;
    $("practice-feedback").textContent=t("recall"); $("practice-feedback").className="";
    $("show-answer").hidden=false; $("next-word").hidden=true;
    $("practice-input").focus({preventScroll:true}); session.answered=false;
  }
  $("start-practice").addEventListener("click",()=>{
    const all=entries();const chosen=all.filter((entry)=>saved[entry.key]);
    const pool=(chosen.length ? chosen : all).slice();
    if(chosen.length)pool.sort((a,b)=>(Number(saved[a.key]?.due)||0)-(Number(saved[b.key]?.due)||0));
    else for(let index=pool.length-1;index>0;index--){const other=Math.floor(Math.random()*(index+1));[pool[index],pool[other]]=[pool[other],pool[index]];}
    session={words:pool.slice(0,5),index:0,correct:0,answered:false};
    if(!session.words.length)return;
    $("practice-area").hidden=false;$("dictionary-results").hidden=true;$("online-translation").hidden=true;$("empty-results").hidden=true;practiceWord();$("practice-area").scrollIntoView({block:"nearest"});
  });
  function answer(reveal=false){
    if(!session||session.answered)return;
    const entry=session.words[session.index];const given=normalized($("practice-input").value);
    if(!reveal&&!given){$("practice-input").focus();return;}
    const correct=!reveal&&entry.meanings.some((meaning)=>normalized(meaning)===given);
    if(correct)session.correct++;
    session.answered=true;
    $("practice-feedback").textContent=`${t(correct?"correct":"correction")}\n${entry.meaning}`;
    $("practice-feedback").className=correct?"correct":"incorrect";
    $("practice-input").disabled=true;$("check-answer").disabled=true;$("show-answer").hidden=true;$("next-word").hidden=false;
    if(saved[entry.key]){const previous=Math.max(0,Math.min(30,Number(saved[entry.key].interval)||0));const interval=correct?Math.min(30,Math.max(1,previous*2)):0;saved[entry.key]={interval,due:Date.now()+(correct?interval*86400000:120000)};persist();}
  }
  $("practice-form").addEventListener("submit",(event)=>{event.preventDefault();answer();});
  $("show-answer").addEventListener("click",()=>answer(true));
  $("close-practice").addEventListener("click",closePractice);
  $("next-word").addEventListener("click",()=>{
    if(!session)return;
    session.index++;
    if(session.index<session.words.length){practiceWord();return;}
    $("practice-question").textContent=t("score",{correct:session.correct,total:session.words.length});
    $("practice-feedback").textContent=t("complete");$("practice-feedback").className="";
    $("practice-position").textContent="";$("practice-form").hidden=true;$("show-answer").hidden=true;$("next-word").hidden=true;session=null;$("dictionary-results").hidden=false;render();
  });
  function downloadCsv(){
    const all=entries().filter((entry)=>saved[entry.key]);
    if(!all.length){$("offline-status").textContent=t("no_export");return;}
    const cell=(value)=>{const string=String(value||"");const safe=/^[=+@\-\t\r\n]/.test(string)?`'${string}`:string;return `"${safe.replaceAll('"','""')}"`;};
    const csv="\ufeff"+[["Word","Translation","Transcription","Source language","Translation language"],...all.map((entry)=>[entry.target,entry.meaning,entry.transcription,target,native])].map((fields)=>fields.map(cell).join(",")).join("\r\n");
    const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));const link=document.createElement("a");link.href=url;link.download=`lexi-${target}-${native}.csv`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);$("offline-status").textContent=t("copied");
  }
  $("export-saved").addEventListener("click",downloadCsv);
  const offlineAssets=["/dictionary/","/static/dictionary.css","/static/dictionary.js","/dictionary/manifest.webmanifest"];
  const ownCache=(key)=>/^lexi-dictionary-[a-f0-9]{16}$/.test(key);
  async function inspectOffline(){
    if(isFile||!("caches" in window)||!("serviceWorker" in navigator))return;
    try{
      const registration=await navigator.serviceWorker.getRegistration("/dictionary/");offlineReady=false;
      if(registration?.active&&new URL(registration.scope).pathname==="/dictionary/"){
        for(const key of (await caches.keys()).filter(ownCache)){
          const cache=await caches.open(key);
          if((await Promise.all(offlineAssets.map((url)=>cache.match(url)))).every(Boolean)){offlineReady=true;break;}
        }
      }
      $("remove-offline").hidden=!offlineReady;connection();
    }catch(_){/* Offline saving is optional. */}
  }
  $("save-offline").addEventListener("click",async()=>{
    const button=$("save-offline");button.disabled=true;$("offline-status").textContent=t("saving");$("offline-status").className="";
    try{
      if(!navigator.onLine||!("serviceWorker" in navigator)||!window.isSecureContext)throw new Error("unsupported");
      const registration=await navigator.serviceWorker.register("/dictionary/sw.js",{scope:"/dictionary/"});
      await registration.update();
      await new Promise((resolve,reject)=>{
        const deadline=Date.now()+12000;
        const check=()=>{
          if(registration.active && !registration.installing && !registration.waiting){resolve();return;}
          if(Date.now()>deadline){reject(new Error("timeout"));return;}
          setTimeout(check,100);
        };check();
      });
      if(!registration.active)throw new Error("inactive");
      // An unregistered worker can still control this tab. Re-registering the
      // same worker may revive it without an install event, so refill explicitly.
      await new Promise((resolve,reject)=>{
        const channel=new MessageChannel();
        const timer=setTimeout(()=>{channel.port1.close();reject(new Error("cache_timeout"));},12000);
        channel.port1.onmessage=({data})=>{clearTimeout(timer);channel.port1.close();data?.ok?resolve():reject(new Error("cache_failed"));};
        registration.active.postMessage("SAVE_OFFLINE",[channel.port2]);
      });
      await inspectOffline();if(!offlineReady)throw new Error("not_cached");
      $("offline-status").textContent=t("save_success");
    }catch(_){$("offline-status").textContent=t("save_error");$("offline-status").className="error";}finally{button.disabled=false;}
  });
  $("remove-offline").addEventListener("click",async()=>{
    try{const registration=await navigator.serviceWorker.getRegistration("/dictionary/");if(registration&&new URL(registration.scope).pathname==="/dictionary/")await registration.unregister();for(const key of (await caches.keys()).filter(ownCache))await caches.delete(key);offlineReady=false;$("remove-offline").hidden=true;connection();$("offline-status").textContent=t("removed");}catch(_){$("offline-status").textContent=t("save_error");}
  });
  for(const event of ["online","offline"])window.addEventListener(event,()=>{connection();render();});
  applyCopy();render();
  if(requestedTarget!==target||!languageCodes.includes(requestedNative)){$("pair-notice").textContent=t("unsupported");$("pair-notice").hidden=false;}
  inspectOffline();
})();
