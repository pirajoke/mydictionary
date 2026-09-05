"""Privacy-safe Telegram Mini App bootstrap helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
from http.client import HTTPSConnection
import json
import re
import time
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import select, text

from mydictionary.localization import (
    billing_product_display_copy,
    language_name,
    normalize_locale,
    translate,
)
from mydictionary.runtime_secrets import RuntimeSecretError, load_bot_token_file
from mydictionary.storage import AnalyticsEvent, User, UserProgress, vocabulary_id_for


INTERFACE_LOCALES = frozenset({"en", "fr", "de", "ja", "ar", "zh", "ru", "es"})
_BOT_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_MINIAPP_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,51}$")
_MAX_INIT_DATA_BYTES = 8192
_MAX_AVATAR_URL_BYTES = 512
_ACTIVITY_WINDOW_DAYS = 370
_ACTIVITY_EVENT_NAMES = frozenset(
    {
        "start_received",
        "onboarding_started",
        "onboarding_completed",
        "language_switched",
        "block_started",
        "block_mode_started",
        "word_audio_played",
        "block_completed",
    }
)


class MiniAppAuthenticationError(ValueError):
    """Raised when Telegram initData cannot be authenticated."""


class MiniAppConfigurationError(RuntimeError):
    """Raised when an enabled Mini App configuration is unsafe."""


class MiniAppAccessDenied(PermissionError):
    """Raised when the signed Telegram account is not an active learner."""


class TelegramCommandSyncError(RuntimeError):
    """Raised when a private command-menu update cannot be confirmed."""


def build_telegram_command_payload(
    *,
    ai_enabled: bool,
    miniapp_enabled: bool,
    locale: str | None,
) -> list[dict[str, str]]:
    """Build the shared bounded command menu for one saved interface locale."""
    selected_locale = normalize_locale(locale)
    commands = [
        ("continue", "start_daily"),
        ("review", "start_review"),
        ("learn", "command_learn"),
        ("stats", "command_stats"),
    ]
    if ai_enabled:
        commands.append(("ai", "command_ai"))
    if miniapp_enabled:
        commands.extend((("app", "command_app"), ("invite", "command_invite")))
    commands.extend((("privacy", "command_privacy"), ("help", "command_help")))
    return [
        {
            "command": command,
            "description": translate(copy_key, selected_locale)[:256],
        }
        for command, copy_key in commands
    ]


def sync_telegram_chat_commands(
    *,
    bot_token: str,
    user_id: int,
    locale: str,
    ai_enabled: bool,
    miniapp_enabled: bool,
    timeout: float = 3.0,
) -> None:
    """Apply one learner's saved locale to their private Telegram menu."""
    token = str(bot_token or "").strip()
    learner_id = int(user_id)
    if (
        learner_id <= 0
        or len(token) > 256
        or not re.fullmatch(r"\d{5,16}:[A-Za-z0-9_-]{20,128}", token)
    ):
        raise TelegramCommandSyncError("invalid Telegram command sync settings")
    payload = {
        "commands": build_telegram_command_payload(
            ai_enabled=ai_enabled,
            miniapp_enabled=miniapp_enabled,
            locale=locale,
        ),
        "scope": {"type": "chat", "chat_id": learner_id},
    }
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    connection = HTTPSConnection("api.telegram.org", timeout=max(1.0, float(timeout)))
    try:
        connection.request(
            "POST",
            f"/bot{token}/setMyCommands",
            body=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        response = connection.getresponse()
        response_body = response.read(4096)
        try:
            result = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TelegramCommandSyncError("invalid Telegram response") from exc
        if response.status != 200 or result.get("ok") is not True:
            raise TelegramCommandSyncError("Telegram command sync rejected")
    finally:
        connection.close()


def _safe_telegram_photo_url(value: object) -> str:
    candidate = str(value or "").strip()
    if not candidate or len(candidate.encode("utf-8")) > _MAX_AVATAR_URL_BYTES:
        return ""
    parsed = urlsplit(candidate)
    hostname = str(parsed.hostname or "").lower()
    trusted_host = (
        hostname == "t.me"
        or hostname == "telegram.org"
        or hostname.endswith(".telegram.org")
        or hostname == "telegram-cdn.org"
        or hostname.endswith(".telegram-cdn.org")
        or hostname == "cdn-telegram.org"
        or hostname.endswith(".cdn-telegram.org")
        or hostname == "telesco.pe"
        or hostname.endswith(".telesco.pe")
    )
    if (
        parsed.scheme != "https"
        or not trusted_host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or not parsed.path.startswith("/")
        or parsed.fragment
    ):
        return ""
    return candidate


def _enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"", "0", "false", "no", "off"}:
        return False
    raise MiniAppConfigurationError("MINIAPP_ENABLED must be a boolean")


@dataclass(frozen=True)
class MiniAppSettings:
    enabled: bool
    public_url: str = ""
    bot_username: str = ""
    auth_max_age_seconds: int = 300
    bot_token_file: str = ""
    bot_token: str = field(default="", repr=False)

    @classmethod
    def from_env(
        cls,
        values: Mapping[str, object],
        *,
        validate_token_file: bool = True,
    ) -> "MiniAppSettings":
        enabled = _enabled(values.get("MINIAPP_ENABLED", "false"))
        if not enabled:
            return cls(enabled=False)

        public_url = str(values.get("MINIAPP_PUBLIC_URL") or "").strip()
        parsed = urlsplit(public_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path != "/miniapp"
        ):
            raise MiniAppConfigurationError(
                "MINIAPP_PUBLIC_URL must be an HTTPS /miniapp URL"
            )

        bot_username = str(values.get("MINIAPP_BOT_USERNAME") or "").strip()
        if not _BOT_USERNAME_RE.fullmatch(bot_username):
            raise MiniAppConfigurationError("MINIAPP_BOT_USERNAME is invalid")

        try:
            auth_max_age_seconds = int(
                values.get("MINIAPP_AUTH_MAX_AGE_SECONDS") or 300
            )
        except (TypeError, ValueError) as exc:
            raise MiniAppConfigurationError(
                "MINIAPP_AUTH_MAX_AGE_SECONDS must be an integer"
            ) from exc
        if not 60 <= auth_max_age_seconds <= 900:
            raise MiniAppConfigurationError(
                "MINIAPP_AUTH_MAX_AGE_SECONDS must be between 60 and 900"
            )

        token_file = str(values.get("BOT_TOKEN_FILE") or "").strip()
        if not token_file:
            raise MiniAppConfigurationError(
                "BOT_TOKEN_FILE is required when the Mini App is enabled"
            )
        if str(values.get("BOT_TOKEN") or "").strip():
            raise MiniAppConfigurationError(
                "BOT_TOKEN cannot be combined with BOT_TOKEN_FILE"
            )
        token = ""
        if validate_token_file:
            try:
                loaded = load_bot_token_file(
                    {"BOT_TOKEN_FILE": token_file}
                )
            except RuntimeSecretError as exc:
                raise MiniAppConfigurationError(str(exc)) from exc
            token = loaded["BOT_TOKEN"]

        return cls(
            enabled=True,
            public_url=public_url,
            bot_username=bot_username,
            auth_max_age_seconds=auth_max_age_seconds,
            bot_token_file=token_file,
            bot_token=token,
        )


def verify_init_data(
    init_data: str,
    *,
    bot_token: str,
    now: int | float | None = None,
    max_age_seconds: int = 300,
) -> dict[str, Any]:
    """Verify Telegram Web App initData and return a minimal signed identity."""

    raw = str(init_data or "")
    if not raw or len(raw.encode("utf-8")) > _MAX_INIT_DATA_BYTES:
        raise MiniAppAuthenticationError("Invalid Telegram authentication")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise MiniAppAuthenticationError("Invalid Telegram authentication") from exc
    fields: dict[str, str] = {}
    for key, value in pairs:
        if not key or key in fields:
            raise MiniAppAuthenticationError("Invalid Telegram authentication")
        fields[key] = value
    supplied_hash = fields.pop("hash", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", supplied_hash):
        raise MiniAppAuthenticationError("Invalid Telegram authentication")
    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", str(bot_token).encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret, data_check.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied_hash.lower(), expected_hash):
        raise MiniAppAuthenticationError("Invalid Telegram authentication")

    try:
        auth_date = int(fields["auth_date"])
        observed_at = int(time.time() if now is None else now)
    except (KeyError, TypeError, ValueError) as exc:
        raise MiniAppAuthenticationError("Invalid Telegram authentication") from exc
    if auth_date > observed_at + 30 or observed_at - auth_date > int(max_age_seconds):
        raise MiniAppAuthenticationError("Invalid Telegram authentication")

    try:
        signed_user = json.loads(fields["user"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MiniAppAuthenticationError("Invalid Telegram authentication") from exc
    if not isinstance(signed_user, dict) or isinstance(signed_user.get("id"), bool):
        raise MiniAppAuthenticationError("Invalid Telegram authentication")
    try:
        user_id = int(signed_user["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MiniAppAuthenticationError("Invalid Telegram authentication") from exc
    if user_id <= 0:
        raise MiniAppAuthenticationError("Invalid Telegram authentication")
    first_name = str(signed_user.get("first_name") or "").strip()
    last_name = str(signed_user.get("last_name") or "").strip()
    display_name = " ".join(part for part in (first_name, last_name) if part)[:80]
    if not display_name:
        display_name = "Learner"
    language_code = str(signed_user.get("language_code") or "").strip()[:16]
    identity = {
        "user_id": user_id,
        "display_name": display_name,
        "language_code": language_code,
    }
    photo_url = _safe_telegram_photo_url(signed_user.get("photo_url"))
    if photo_url:
        identity["photo_url"] = photo_url
    return identity


def require_active_learner(store: Any, user_id: int) -> Mapping[str, Any]:
    profile = store.access_profile(int(user_id))
    privacy_status = profile.get("privacy_status") if isinstance(profile, Mapping) else None
    if privacy_status is None:
        session_factory = getattr(store, "Session", None)
        if callable(session_factory):
            with session_factory() as session:
                learner = session.get(User, int(user_id))
                privacy_status = (
                    learner.privacy_status if learner is not None else None
                )
    if (
        not isinstance(profile, Mapping)
        or profile.get("access_status") != "active"
        or privacy_status != "active"
    ):
        raise MiniAppAccessDenied("Mini App access denied")
    return profile


def miniapp_locale(value: str | None) -> str:
    return normalize_locale(value, fallback="en")


def miniapp_text_direction(locale: str | None) -> str:
    return "rtl" if miniapp_locale(locale) == "ar" else "ltr"


MINIAPP_COPY: dict[str, dict[str, str]] = {
    "en": {
        "loading": "Loading…", "error": "Something went wrong.", "retry": "Try again",
        "profile": "Profile", "words": "My words", "credits": "AI credits", "languages": "Languages", "settings": "Settings",
        "continue_lesson": "Continue lesson", "start_first_lesson": "Start first lesson", "first_lesson_hint": "3 minutes · your first lesson is ready", "daily_quest": "Daily quest", "ai_tutor": "AI Tutor", "share": "Share",
        "empty_words": "No tracked words yet. Start a lesson to add some.", "start_lesson": "Start a lesson",
        "change_language": "Change in Telegram", "open_settings": "Open settings", "privacy": "Privacy",
        "word_review": "Review", "word_learned": "Learned", "attempts_correct": "Correct", "attempts_wrong": "Wrong",
        "metric_level": "Level", "metric_xp": "XP", "metric_streak": "Streak", "metric_best_streak": "Best streak",
        "metric_sessions": "Sessions", "metric_accuracy": "Accuracy", "metric_today_xp": "Today’s XP",
        "metric_daily_goal": "Daily goal", "metric_tracked_words": "Tracked words", "metric_learned_words": "Learned words", "metric_ai_credits": "AI credits",
        "credit_available": "Available", "credit_reserved": "Reserved", "credit_spent": "Spent",
        "credit_contract": "One successful Tutor response costs one AI credit. Failed attempts cost nothing.",
        "checkout_disabled": "Purchases are not available right now.",
        "setting_daily_goal": "Daily goal", "setting_meaning_language": "Meaning language", "setting_learning_goal": "Learning goal",
        "setting_mirror_mode": "Mirror mode", "setting_mirror_style": "Mirror style", "setting_mirror_depth": "Response depth",
        "setting_mirror_level": "Learner level", "setting_ai": "AI Tutor", "setting_voice": "Voice practice", "setting_unknown": "Not set",
        "settings_group_learning": "Learning", "settings_group_tutor": "AI Tutor", "settings_group_features": "Features",
        "feature_enabled": "Available", "feature_disabled": "Unavailable", "language_current": "Current", "navigation_label": "Main navigation", "more_stats": "More stats",
        "streak_days": "days streak", "best_streak_short": "Best", "calendar_activity": "Learning activity", "calendar_today": "Today",
        "calendar_active_day": "Learning day", "previous_month": "Previous month", "next_month": "Next month", "share_profile": "Share profile",
    },
    "fr": {
        "loading": "Chargement…", "error": "Un problème est survenu.", "retry": "Réessayer",
        "profile": "Profil", "words": "Mes mots", "credits": "Crédits IA", "languages": "Langues", "settings": "Réglages",
        "continue_lesson": "Continuer la leçon", "start_first_lesson": "Commencer le premier cours", "first_lesson_hint": "3 minutes · votre premier cours est prêt", "daily_quest": "Mission du jour", "ai_tutor": "Tuteur IA", "share": "Partager",
        "empty_words": "Aucun mot suivi. Commencez une leçon pour en ajouter.", "start_lesson": "Commencer une leçon",
        "change_language": "Changer dans Telegram", "open_settings": "Ouvrir les réglages", "privacy": "Confidentialité",
        "word_review": "À réviser", "word_learned": "Appris", "attempts_correct": "Correct", "attempts_wrong": "Incorrectes",
        "metric_level": "Niveau", "metric_xp": "XP", "metric_streak": "Série", "metric_best_streak": "Meilleure série",
        "metric_sessions": "Sessions", "metric_accuracy": "Précision", "metric_today_xp": "XP du jour",
        "metric_daily_goal": "Objectif quotidien", "metric_tracked_words": "Mots suivis", "metric_learned_words": "Mots appris", "metric_ai_credits": "Crédits IA",
        "credit_available": "Disponibles", "credit_reserved": "Réservés", "credit_spent": "Utilisés",
        "credit_contract": "Une réponse réussie du tuteur coûte un crédit IA. Les tentatives échouées ne coûtent rien.",
        "checkout_disabled": "Les achats ne sont pas disponibles pour le moment.",
        "setting_daily_goal": "Objectif quotidien", "setting_meaning_language": "Langue des définitions", "setting_learning_goal": "Objectif d’apprentissage",
        "setting_mirror_mode": "Mode Mirror", "setting_mirror_style": "Style Mirror", "setting_mirror_depth": "Profondeur de réponse",
        "setting_mirror_level": "Niveau d’apprentissage", "setting_ai": "Tuteur IA", "setting_voice": "Pratique vocale", "setting_unknown": "Non défini",
        "settings_group_learning": "Apprentissage", "settings_group_tutor": "Tuteur IA", "settings_group_features": "Fonctionnalités",
        "feature_enabled": "Disponible", "feature_disabled": "Indisponible", "language_current": "Actuelle", "navigation_label": "Navigation principale", "more_stats": "Plus de statistiques",
        "streak_days": "jours de série", "best_streak_short": "Record", "calendar_activity": "Activité d’apprentissage", "calendar_today": "Aujourd’hui",
        "calendar_active_day": "Jour d’apprentissage", "previous_month": "Mois précédent", "next_month": "Mois suivant", "share_profile": "Partager le profil",
    },
    "de": {
        "loading": "Wird geladen…", "error": "Ein Fehler ist aufgetreten.", "retry": "Erneut versuchen",
        "profile": "Profil", "words": "Meine Wörter", "credits": "KI-Credits", "languages": "Sprachen", "settings": "Einstellungen",
        "continue_lesson": "Lektion fortsetzen", "start_first_lesson": "Erste Lektion starten", "first_lesson_hint": "3 Minuten · deine erste Lektion ist bereit", "daily_quest": "Tagesmission", "ai_tutor": "KI-Tutor", "share": "Teilen",
        "empty_words": "Noch keine Wörter gespeichert. Starte eine Lektion.", "start_lesson": "Lektion starten",
        "change_language": "In Telegram ändern", "open_settings": "Einstellungen öffnen", "privacy": "Datenschutz",
        "word_review": "Wiederholen", "word_learned": "Gelernt", "attempts_correct": "Richtig", "attempts_wrong": "Falsch",
        "metric_level": "Niveau", "metric_xp": "XP", "metric_streak": "Serie", "metric_best_streak": "Beste Serie",
        "metric_sessions": "Einheiten", "metric_accuracy": "Genauigkeit", "metric_today_xp": "Heutige XP",
        "metric_daily_goal": "Tagesziel", "metric_tracked_words": "Gespeicherte Wörter", "metric_learned_words": "Gelernte Wörter", "metric_ai_credits": "KI-Credits",
        "credit_available": "Verfügbar", "credit_reserved": "Reserviert", "credit_spent": "Verbraucht",
        "credit_contract": "Eine erfolgreiche Tutor-Antwort kostet einen KI-Credit. Fehlversuche kosten nichts.",
        "checkout_disabled": "Käufe sind derzeit nicht verfügbar.",
        "setting_daily_goal": "Tagesziel", "setting_meaning_language": "Erklärungssprache", "setting_learning_goal": "Lernziel",
        "setting_mirror_mode": "Mirror-Modus", "setting_mirror_style": "Mirror-Stil", "setting_mirror_depth": "Antworttiefe",
        "setting_mirror_level": "Lernniveau", "setting_ai": "KI-Tutor", "setting_voice": "Sprechübung", "setting_unknown": "Nicht festgelegt",
        "settings_group_learning": "Lernen", "settings_group_tutor": "KI-Tutor", "settings_group_features": "Funktionen",
        "feature_enabled": "Verfügbar", "feature_disabled": "Nicht verfügbar", "language_current": "Aktuell", "navigation_label": "Hauptnavigation", "more_stats": "Mehr Statistiken",
        "streak_days": "Tage in Folge", "best_streak_short": "Bestwert", "calendar_activity": "Lernaktivität", "calendar_today": "Heute",
        "calendar_active_day": "Lerntag", "previous_month": "Vorheriger Monat", "next_month": "Nächster Monat", "share_profile": "Profil teilen",
    },
    "ja": {
        "loading": "読み込み中…", "error": "問題が発生しました。", "retry": "再試行",
        "profile": "プロフィール", "words": "単語", "credits": "AIクレジット", "languages": "言語", "settings": "設定",
        "continue_lesson": "レッスンを続ける", "start_first_lesson": "最初のレッスンを始める", "first_lesson_hint": "3分 · 最初のレッスンの準備ができました", "daily_quest": "今日のミッション", "ai_tutor": "AIチューター", "share": "共有",
        "empty_words": "記録された単語はまだありません。レッスンを始めましょう。", "start_lesson": "レッスンを始める",
        "change_language": "Telegramで変更", "open_settings": "設定を開く", "privacy": "プライバシー",
        "word_review": "復習", "word_learned": "習得済み", "attempts_correct": "正解", "attempts_wrong": "不正解",
        "metric_level": "レベル", "metric_xp": "XP", "metric_streak": "連続日数", "metric_best_streak": "最長記録",
        "metric_sessions": "学習回数", "metric_accuracy": "正答率", "metric_today_xp": "今日のXP",
        "metric_daily_goal": "1日の目標", "metric_tracked_words": "記録単語", "metric_learned_words": "習得単語", "metric_ai_credits": "AIクレジット",
        "credit_available": "利用可能", "credit_reserved": "予約中", "credit_spent": "使用済み",
        "credit_contract": "チューターの回答が成功するとAIクレジットを1つ使います。失敗時は消費しません。",
        "checkout_disabled": "現在、購入は利用できません。",
        "setting_daily_goal": "1日の目標", "setting_meaning_language": "意味の言語", "setting_learning_goal": "学習目標",
        "setting_mirror_mode": "Mirrorモード", "setting_mirror_style": "Mirrorスタイル", "setting_mirror_depth": "回答の詳しさ",
        "setting_mirror_level": "学習レベル", "setting_ai": "AIチューター", "setting_voice": "音声練習", "setting_unknown": "未設定",
        "settings_group_learning": "学習", "settings_group_tutor": "AIチューター", "settings_group_features": "機能",
        "feature_enabled": "利用可能", "feature_disabled": "利用不可", "language_current": "現在", "navigation_label": "メインナビゲーション", "more_stats": "その他の統計",
        "streak_days": "日連続", "best_streak_short": "最高", "calendar_activity": "学習アクティビティ", "calendar_today": "今日",
        "calendar_active_day": "学習日", "previous_month": "前の月", "next_month": "次の月", "share_profile": "プロフィールを共有",
    },
    "ar": {
        "loading": "جارٍ التحميل…", "error": "حدث خطأ.", "retry": "إعادة المحاولة",
        "profile": "الملف", "words": "كلماتي", "credits": "رصيد AI", "languages": "اللغات", "settings": "الإعدادات",
        "continue_lesson": "متابعة الدرس", "start_first_lesson": "ابدأ الدرس الأول", "first_lesson_hint": "3 دقائق · درسك الأول جاهز", "daily_quest": "مهمة اليوم", "ai_tutor": "مدرّس AI", "share": "مشاركة",
        "empty_words": "لا توجد كلمات محفوظة بعد. ابدأ درساً.", "start_lesson": "بدء درس",
        "change_language": "التغيير في Telegram", "open_settings": "فتح الإعدادات", "privacy": "الخصوصية",
        "word_review": "مراجعة", "word_learned": "تم تعلمها", "attempts_correct": "صحيح", "attempts_wrong": "خاطئة",
        "metric_level": "المستوى", "metric_xp": "XP", "metric_streak": "السلسلة", "metric_best_streak": "أفضل سلسلة",
        "metric_sessions": "الجلسات", "metric_accuracy": "الدقة", "metric_today_xp": "XP اليوم",
        "metric_daily_goal": "الهدف اليومي", "metric_tracked_words": "الكلمات المحفوظة", "metric_learned_words": "الكلمات المتعلمة", "metric_ai_credits": "رصيد AI",
        "credit_available": "متاح", "credit_reserved": "محجوز", "credit_spent": "مستخدم",
        "credit_contract": "تكلّف إجابة المدرّس الناجحة رصيد AI واحداً. المحاولات الفاشلة مجانية.",
        "checkout_disabled": "الشراء غير متاح حالياً.",
        "setting_daily_goal": "الهدف اليومي", "setting_meaning_language": "لغة المعاني", "setting_learning_goal": "هدف التعلم",
        "setting_mirror_mode": "وضع Mirror", "setting_mirror_style": "أسلوب Mirror", "setting_mirror_depth": "تفصيل الإجابة",
        "setting_mirror_level": "مستوى المتعلم", "setting_ai": "مدرّس AI", "setting_voice": "تدريب صوتي", "setting_unknown": "غير محدد",
        "settings_group_learning": "التعلّم", "settings_group_tutor": "مدرّس AI", "settings_group_features": "الميزات",
        "feature_enabled": "متاح", "feature_disabled": "غير متاح", "language_current": "الحالية", "navigation_label": "التنقل الرئيسي", "more_stats": "إحصاءات إضافية",
        "streak_days": "أيام متتالية", "best_streak_short": "الأفضل", "calendar_activity": "نشاط التعلّم", "calendar_today": "اليوم",
        "calendar_active_day": "يوم تعلّم", "previous_month": "الشهر السابق", "next_month": "الشهر التالي", "share_profile": "مشاركة الملف",
    },
    "zh": {
        "loading": "加载中…", "error": "出现问题。", "retry": "重试",
        "profile": "个人资料", "words": "我的单词", "credits": "AI 点数", "languages": "语言", "settings": "设置",
        "continue_lesson": "继续课程", "start_first_lesson": "开始第一课", "first_lesson_hint": "3 分钟 · 第一课已准备好", "daily_quest": "今日任务", "ai_tutor": "AI 导师", "share": "分享",
        "empty_words": "还没有记录单词。开始课程即可添加。", "start_lesson": "开始课程",
        "change_language": "在 Telegram 中更改", "open_settings": "打开设置", "privacy": "隐私",
        "word_review": "复习", "word_learned": "已掌握", "attempts_correct": "正确", "attempts_wrong": "错误",
        "metric_level": "等级", "metric_xp": "XP", "metric_streak": "连续学习", "metric_best_streak": "最佳连续记录",
        "metric_sessions": "学习次数", "metric_accuracy": "正确率", "metric_today_xp": "今日 XP",
        "metric_daily_goal": "每日目标", "metric_tracked_words": "记录单词", "metric_learned_words": "已学单词", "metric_ai_credits": "AI 点数",
        "credit_available": "可用", "credit_reserved": "已预留", "credit_spent": "已使用",
        "credit_contract": "导师成功回答一次消耗一个 AI 点数；失败不扣点数。",
        "checkout_disabled": "暂时无法购买。",
        "setting_daily_goal": "每日目标", "setting_meaning_language": "释义语言", "setting_learning_goal": "学习目标",
        "setting_mirror_mode": "Mirror 模式", "setting_mirror_style": "Mirror 风格", "setting_mirror_depth": "回答深度",
        "setting_mirror_level": "学习等级", "setting_ai": "AI 导师", "setting_voice": "语音练习", "setting_unknown": "未设置",
        "settings_group_learning": "学习", "settings_group_tutor": "AI 导师", "settings_group_features": "功能",
        "feature_enabled": "可用", "feature_disabled": "不可用", "language_current": "当前", "navigation_label": "主导航", "more_stats": "更多统计",
        "streak_days": "天连续学习", "best_streak_short": "最佳", "calendar_activity": "学习记录", "calendar_today": "今天",
        "calendar_active_day": "学习日", "previous_month": "上个月", "next_month": "下个月", "share_profile": "分享个人资料",
    },
    "ru": {
        "loading": "Загрузка…", "error": "Что-то пошло не так.", "retry": "Повторить",
        "profile": "Профиль", "words": "Мои слова", "credits": "AI-кредиты", "languages": "Языки", "settings": "Настройки",
        "continue_lesson": "Продолжить урок", "start_first_lesson": "Начать первый урок", "first_lesson_hint": "3 минуты · первый урок уже готов", "daily_quest": "Задание дня", "ai_tutor": "AI-репетитор", "share": "Поделиться",
        "empty_words": "Пока нет отслеживаемых слов. Начните урок.", "start_lesson": "Начать урок",
        "change_language": "Сменить в Telegram", "open_settings": "Открыть настройки", "privacy": "Приватность",
        "word_review": "Повторить", "word_learned": "Изучено", "attempts_correct": "Верно", "attempts_wrong": "Неверно",
        "metric_level": "Уровень", "metric_xp": "XP", "metric_streak": "Серия", "metric_best_streak": "Лучшая серия",
        "metric_sessions": "Занятия", "metric_accuracy": "Точность", "metric_today_xp": "XP сегодня",
        "metric_daily_goal": "Цель на день", "metric_tracked_words": "Слова в работе", "metric_learned_words": "Изученные слова", "metric_ai_credits": "AI-кредиты",
        "credit_available": "Доступно", "credit_reserved": "Зарезервировано", "credit_spent": "Потрачено",
        "credit_contract": "Один успешный ответ репетитора стоит один AI-кредит. Неудачные попытки бесплатны.",
        "checkout_disabled": "Покупки сейчас недоступны.",
        "setting_daily_goal": "Цель на день", "setting_meaning_language": "Язык значений", "setting_learning_goal": "Цель обучения",
        "setting_mirror_mode": "Режим Mirror", "setting_mirror_style": "Стиль Mirror", "setting_mirror_depth": "Глубина ответа",
        "setting_mirror_level": "Уровень ученика", "setting_ai": "AI-репетитор", "setting_voice": "Голосовая практика", "setting_unknown": "Не задано",
        "settings_group_learning": "Обучение", "settings_group_tutor": "AI-репетитор", "settings_group_features": "Возможности",
        "feature_enabled": "Доступно", "feature_disabled": "Недоступно", "language_current": "Текущий", "navigation_label": "Основная навигация", "more_stats": "Ещё статистика",
        "streak_days": "дней подряд", "best_streak_short": "Рекорд", "calendar_activity": "Календарь занятий", "calendar_today": "Сегодня",
        "calendar_active_day": "Учебный день", "previous_month": "Предыдущий месяц", "next_month": "Следующий месяц", "share_profile": "Поделиться профилем",
    },
    "es": {
        "loading": "Cargando…", "error": "Ha ocurrido un problema.", "retry": "Reintentar",
        "profile": "Perfil", "words": "Mis palabras", "credits": "Créditos de IA", "languages": "Idiomas", "settings": "Ajustes",
        "continue_lesson": "Continuar la lección", "start_first_lesson": "Empezar la primera lección", "first_lesson_hint": "3 minutos · tu primera lección está lista", "daily_quest": "Misión del día", "ai_tutor": "Tutor de IA", "share": "Compartir",
        "empty_words": "Aún no hay palabras guardadas. Empieza una lección.", "start_lesson": "Empezar una lección",
        "change_language": "Cambiar en Telegram", "open_settings": "Abrir ajustes", "privacy": "Privacidad",
        "word_review": "Repasar", "word_learned": "Aprendida", "attempts_correct": "Correcto", "attempts_wrong": "Incorrectos",
        "metric_level": "Nivel", "metric_xp": "XP", "metric_streak": "Racha", "metric_best_streak": "Mejor racha",
        "metric_sessions": "Sesiones", "metric_accuracy": "Precisión", "metric_today_xp": "XP de hoy",
        "metric_daily_goal": "Objetivo diario", "metric_tracked_words": "Palabras guardadas", "metric_learned_words": "Palabras aprendidas", "metric_ai_credits": "Créditos de IA",
        "credit_available": "Disponibles", "credit_reserved": "Reservados", "credit_spent": "Gastados",
        "credit_contract": "Una respuesta correcta del tutor cuesta un crédito de IA. Los intentos fallidos no cuestan nada.",
        "checkout_disabled": "Las compras no están disponibles ahora.",
        "setting_daily_goal": "Objetivo diario", "setting_meaning_language": "Idioma de significados", "setting_learning_goal": "Objetivo de aprendizaje",
        "setting_mirror_mode": "Modo Mirror", "setting_mirror_style": "Estilo Mirror", "setting_mirror_depth": "Profundidad de respuesta",
        "setting_mirror_level": "Nivel del estudiante", "setting_ai": "Tutor de IA", "setting_voice": "Práctica de voz", "setting_unknown": "Sin definir",
        "settings_group_learning": "Aprendizaje", "settings_group_tutor": "Tutor de IA", "settings_group_features": "Funciones",
        "feature_enabled": "Disponible", "feature_disabled": "No disponible", "language_current": "Actual", "navigation_label": "Navegación principal", "more_stats": "Más estadísticas",
        "streak_days": "días de racha", "best_streak_short": "Récord", "calendar_activity": "Actividad de aprendizaje", "calendar_today": "Hoy",
        "calendar_active_day": "Día de estudio", "previous_month": "Mes anterior", "next_month": "Mes siguiente", "share_profile": "Compartir perfil",
    },
}

_LANGUAGE_SWITCH_COPY = {
    "en": ("Switching dictionary…", "Could not switch dictionary.", "Try again"),
    "fr": ("Changement de dictionnaire…", "Impossible de changer de dictionnaire.", "Réessayer"),
    "de": ("Wörterbuch wird gewechselt…", "Wörterbuch konnte nicht gewechselt werden.", "Erneut versuchen"),
    "ja": ("辞書を切り替えています…", "辞書を切り替えられませんでした。", "再試行"),
    "ar": ("جارٍ تبديل القاموس…", "تعذر تبديل القاموس.", "إعادة المحاولة"),
    "zh": ("正在切换词典…", "无法切换词典。", "重试"),
    "ru": ("Переключаю словарь…", "Не удалось переключить словарь.", "Повторить"),
    "es": ("Cambiando diccionario…", "No se pudo cambiar el diccionario.", "Reintentar"),
}
for _locale, (_pending, _error, _retry) in _LANGUAGE_SWITCH_COPY.items():
    MINIAPP_COPY[_locale].update(
        language_switch_pending=_pending,
        language_switch_error=_error,
        language_switch_retry=_retry,
    )

_INTERFACE_LANGUAGE_COPY = {
    "en": ("Bot language", "Changing bot language…", "Could not change bot language.", "Try again"),
    "fr": ("Langue du bot", "Changement de la langue du bot…", "Impossible de changer la langue du bot.", "Réessayer"),
    "de": ("Bot-Sprache", "Bot-Sprache wird geändert…", "Bot-Sprache konnte nicht geändert werden.", "Erneut versuchen"),
    "ja": ("ボットの言語", "ボットの言語を変更しています…", "ボットの言語を変更できませんでした。", "再試行"),
    "ar": ("لغة البوت", "جارٍ تغيير لغة البوت…", "تعذر تغيير لغة البوت.", "إعادة المحاولة"),
    "zh": ("机器人语言", "正在更改机器人语言…", "无法更改机器人语言。", "重试"),
    "ru": ("Язык бота", "Меняю язык бота…", "Не удалось изменить язык бота.", "Повторить"),
    "es": ("Idioma del bot", "Cambiando el idioma del bot…", "No se pudo cambiar el idioma del bot.", "Reintentar"),
}
for _locale, (_label, _pending, _error, _retry) in _INTERFACE_LANGUAGE_COPY.items():
    MINIAPP_COPY[_locale].update(
        setting_interface_language=_label,
        interface_language_pending=_pending,
        interface_language_error=_error,
        interface_language_retry=_retry,
    )

_SETTINGS_HUB_COPY = {
    "en": {
        "settings_credit_cta": "Manage AI credits",
        "settings_dictionary": "Dictionary",
        "settings_learning_plan": "Learning plan",
        "settings_tutor_preferences": "Tutor preferences",
        "settings_help": "How to use Lexi",
        "settings_group_support": "Support",
    },
    "fr": {
        "settings_credit_cta": "Gérer les crédits IA",
        "settings_dictionary": "Dictionnaire",
        "settings_learning_plan": "Plan d’apprentissage",
        "settings_tutor_preferences": "Préférences du tuteur",
        "settings_help": "Comment utiliser Lexi",
        "settings_group_support": "Aide",
    },
    "de": {
        "settings_credit_cta": "KI-Credits verwalten",
        "settings_dictionary": "Wörterbuch",
        "settings_learning_plan": "Lernplan",
        "settings_tutor_preferences": "Tutor-Einstellungen",
        "settings_help": "Lexi verwenden",
        "settings_group_support": "Hilfe",
    },
    "ja": {
        "settings_credit_cta": "AIクレジットを管理",
        "settings_dictionary": "辞書",
        "settings_learning_plan": "学習プラン",
        "settings_tutor_preferences": "チューター設定",
        "settings_help": "Lexiの使い方",
        "settings_group_support": "サポート",
    },
    "ar": {
        "settings_credit_cta": "إدارة رصيد AI",
        "settings_dictionary": "القاموس",
        "settings_learning_plan": "خطة التعلّم",
        "settings_tutor_preferences": "تفضيلات المدرّس",
        "settings_help": "كيفية استخدام Lexi",
        "settings_group_support": "الدعم",
    },
    "zh": {
        "settings_credit_cta": "管理 AI 点数",
        "settings_dictionary": "词典",
        "settings_learning_plan": "学习计划",
        "settings_tutor_preferences": "导师偏好",
        "settings_help": "如何使用 Lexi",
        "settings_group_support": "帮助",
    },
    "ru": {
        "settings_credit_cta": "Управление AI-кредитами",
        "settings_dictionary": "Словарь",
        "settings_learning_plan": "План обучения",
        "settings_tutor_preferences": "Настройки репетитора",
        "settings_help": "Как пользоваться Lexi",
        "settings_group_support": "Помощь",
    },
    "es": {
        "settings_credit_cta": "Gestionar créditos de IA",
        "settings_dictionary": "Diccionario",
        "settings_learning_plan": "Plan de aprendizaje",
        "settings_tutor_preferences": "Preferencias del tutor",
        "settings_help": "Cómo usar Lexi",
        "settings_group_support": "Ayuda",
    },
}
for _locale, _copy in _SETTINGS_HUB_COPY.items():
    MINIAPP_COPY[_locale].update(_copy)

_REFERRAL_COPY = {
    "en": {
        "referral_title": "Learn together, earn AI credits",
        "referral_body": "Invite a friend. When they finish setup, you earn 5 AI credits.",
        "referral_invited": "Invited",
        "referral_activated": "Activated",
        "referral_earned": "Credits earned",
        "referral_terms": "5 credits per activated friend · rewards for the first 10 friends",
        "referral_invite": "Invite friends",
        "referral_pending": "Creating your invite…",
        "referral_error": "Could not create the invite.",
        "referral_retry": "Try again",
        "referral_share_text": "Learn vocabulary with me in Lexi!",
    },
    "fr": {
        "referral_title": "Apprenez ensemble, gagnez des crédits IA",
        "referral_body": "Invitez un ami. Quand il termine la configuration, vous gagnez 5 crédits IA.",
        "referral_invited": "Invités",
        "referral_activated": "Activés",
        "referral_earned": "Crédits gagnés",
        "referral_terms": "5 crédits par ami activé · récompenses pour les 10 premiers amis",
        "referral_invite": "Inviter des amis",
        "referral_pending": "Création de votre invitation…",
        "referral_error": "Impossible de créer l’invitation.",
        "referral_retry": "Réessayer",
        "referral_share_text": "Apprenez du vocabulaire avec moi dans Lexi !",
    },
    "de": {
        "referral_title": "Gemeinsam lernen, KI-Credits verdienen",
        "referral_body": "Lade einen Freund ein. Nach der Einrichtung erhältst du 5 KI-Credits.",
        "referral_invited": "Eingeladen",
        "referral_activated": "Aktiviert",
        "referral_earned": "Credits verdient",
        "referral_terms": "5 Credits je aktiviertem Freund · Prämien für die ersten 10 Freunde",
        "referral_invite": "Freunde einladen",
        "referral_pending": "Einladung wird erstellt…",
        "referral_error": "Einladung konnte nicht erstellt werden.",
        "referral_retry": "Erneut versuchen",
        "referral_share_text": "Lerne mit mir Vokabeln in Lexi!",
    },
    "ja": {
        "referral_title": "一緒に学んでAIクレジットを獲得",
        "referral_body": "友達を招待。初期設定を完了すると、5 AIクレジットを獲得できます。",
        "referral_invited": "招待済み",
        "referral_activated": "利用開始",
        "referral_earned": "獲得クレジット",
        "referral_terms": "利用開始した友達1人につき5クレジット · 最初の10人まで",
        "referral_invite": "友達を招待",
        "referral_pending": "招待リンクを作成中…",
        "referral_error": "招待リンクを作成できませんでした。",
        "referral_retry": "再試行",
        "referral_share_text": "Lexiで一緒に単語を学ぼう！",
    },
    "ar": {
        "referral_title": "تعلّما معاً واكسب رصيد AI",
        "referral_body": "ادعُ صديقاً. عند إكمال الإعداد تحصل على 5 أرصدة AI.",
        "referral_invited": "المدعوون",
        "referral_activated": "المفعّلون",
        "referral_earned": "الرصيد المكتسب",
        "referral_terms": "5 أرصدة لكل صديق مفعّل · مكافآت لأول 10 أصدقاء",
        "referral_invite": "دعوة الأصدقاء",
        "referral_pending": "جارٍ إنشاء الدعوة…",
        "referral_error": "تعذر إنشاء الدعوة.",
        "referral_retry": "إعادة المحاولة",
        "referral_share_text": "تعلّم المفردات معي في Lexi!",
    },
    "zh": {
        "referral_title": "一起学习，赚取 AI 点数",
        "referral_body": "邀请好友。好友完成设置后，你将获得 5 个 AI 点数。",
        "referral_invited": "已邀请",
        "referral_activated": "已激活",
        "referral_earned": "已赚点数",
        "referral_terms": "每位激活好友 5 点 · 前 10 位好友可获奖励",
        "referral_invite": "邀请好友",
        "referral_pending": "正在创建邀请…",
        "referral_error": "无法创建邀请。",
        "referral_retry": "重试",
        "referral_share_text": "和我一起在 Lexi 学单词吧！",
    },
    "ru": {
        "referral_title": "Учитесь вместе — получайте AI-кредиты",
        "referral_body": "Пригласите друга. Когда он завершит настройку, вы получите 5 AI-кредитов.",
        "referral_invited": "Приглашено",
        "referral_activated": "Активировано",
        "referral_earned": "Получено кредитов",
        "referral_terms": "5 кредитов за активного друга · награды за первых 10 друзей",
        "referral_invite": "Пригласить друзей",
        "referral_pending": "Создаю приглашение…",
        "referral_error": "Не удалось создать приглашение.",
        "referral_retry": "Повторить",
        "referral_share_text": "Давай учить слова вместе в Lexi!",
    },
    "es": {
        "referral_title": "Aprendan juntos y ganen créditos de IA",
        "referral_body": "Invita a un amigo. Cuando complete la configuración, ganarás 5 créditos de IA.",
        "referral_invited": "Invitados",
        "referral_activated": "Activados",
        "referral_earned": "Créditos ganados",
        "referral_terms": "5 créditos por amigo activado · premios para los primeros 10 amigos",
        "referral_invite": "Invitar amigos",
        "referral_pending": "Creando tu invitación…",
        "referral_error": "No se pudo crear la invitación.",
        "referral_retry": "Reintentar",
        "referral_share_text": "¡Aprende vocabulario conmigo en Lexi!",
    },
}
for _locale, _copy in _REFERRAL_COPY.items():
    MINIAPP_COPY[_locale].update(_copy)

_SETTING_VALUE_COPY = {
    "en": {"basics": "Everyday basics", "travel": "Travel focus", "conversation": "Conversation practice", "work": "Work and study", "personal": "Personal growth", "text": "Text replies", "voice": "Voice replies", "both": "Text and voice", "teacher": "Teacher guidance", "coach": "Learning coach", "practice": "Practice partner", "brief": "Brief guidance", "exam": "Exam practice", "compact": "Compact detail", "balanced": "Balanced detail", "deep": "Detailed response", "adaptive": "Adaptive level"},
    "fr": {"basics": "Bases du quotidien", "travel": "Voyage", "conversation": "Conversation guidée", "work": "Travail et études", "personal": "Développement personnel", "text": "Texte", "voice": "Voix", "both": "Texte et voix", "teacher": "Professeur", "coach": "Coach pédagogique", "practice": "Entraînement", "brief": "Concis", "exam": "Examen", "compact": "Courte", "balanced": "Équilibrée", "deep": "Détaillée", "adaptive": "Adaptatif"},
    "de": {"basics": "Alltagsgrundlagen", "travel": "Reisen", "conversation": "Gespräch", "work": "Arbeit und Studium", "personal": "Persönliche Entwicklung", "text": "Textmodus", "voice": "Sprachmodus", "both": "Text und Sprache", "teacher": "Lehrkraft", "coach": "Lerncoach", "practice": "Übung", "brief": "Kurz", "exam": "Prüfung", "compact": "Kompakt", "balanced": "Ausgewogen", "deep": "Ausführlich", "adaptive": "Anpassbar"},
    "ja": {"basics": "日常の基礎", "travel": "旅行", "conversation": "会話練習", "work": "仕事と学習", "personal": "自分磨き", "text": "テキスト", "voice": "音声", "both": "テキストと音声", "teacher": "先生", "coach": "コーチ", "practice": "練習", "brief": "簡潔", "exam": "試験", "compact": "短め", "balanced": "標準", "deep": "詳しく", "adaptive": "自動調整"},
    "ar": {"basics": "أساسيات يومية", "travel": "السفر", "conversation": "المحادثة", "work": "العمل والدراسة", "personal": "التطور الشخصي", "text": "نصي", "voice": "صوتي", "both": "نص وصوت", "teacher": "معلّم", "coach": "مدرّب", "practice": "تدريب", "brief": "مختصر", "exam": "اختبار", "compact": "موجز", "balanced": "متوازن", "deep": "مفصل", "adaptive": "متكيف"},
    "zh": {"basics": "日常基础", "travel": "旅行", "conversation": "对话练习", "work": "工作与学习", "personal": "个人成长", "text": "文字", "voice": "语音", "both": "文字和语音", "teacher": "老师", "coach": "教练", "practice": "练习", "brief": "简洁", "exam": "考试", "compact": "精简", "balanced": "均衡", "deep": "详细", "adaptive": "自适应"},
    "ru": {"basics": "Базовая лексика", "travel": "Путешествия", "conversation": "Разговорная практика", "work": "Работа и учёба", "personal": "Личное развитие", "text": "Текст", "voice": "Голос", "both": "Текст и голос", "teacher": "Преподаватель", "coach": "Наставник", "practice": "Практика", "brief": "Кратко", "exam": "Экзамен", "compact": "Компактно", "balanced": "Сбалансированно", "deep": "Подробно", "adaptive": "Адаптивно"},
    "es": {"basics": "Bases cotidianas", "travel": "Viajes", "conversation": "Conversación guiada", "work": "Trabajo y estudio", "personal": "Crecimiento personal", "text": "Texto", "voice": "Voz", "both": "Texto y voz", "teacher": "Profesor", "coach": "Entrenador", "practice": "Práctica", "brief": "Breve", "exam": "Examen", "compact": "Compacta", "balanced": "Equilibrada", "deep": "Detallada", "adaptive": "Adaptativo"},
}


def _localized_setting_value(locale: str, value: object) -> str:
    key = str(value or "").strip().lower()
    if re.fullmatch(r"[abc][12]", key):
        return key.upper()
    return _SETTING_VALUE_COPY[locale].get(
        key, MINIAPP_COPY[locale]["setting_unknown"]
    )


def _bounded_text(value: object, maximum: int = 160) -> str:
    return str(value or "").strip()[:maximum]


def visible_credit_products(
    products: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    *,
    locale: str,
) -> list[dict[str, Any]]:
    visible = [
        row
        for row in products
        if row.get("status") == "active"
        and row.get("billing_mode") == "one_time"
        and _MINIAPP_PUBLIC_ID_RE.fullmatch(str(row.get("product_id") or ""))
    ]
    visible.sort(key=lambda row: (int(row.get("display_order") or 0), int(row.get("price_xtr") or 0)))
    result = []
    for row in visible[:12]:
        product_id = str(row.get("product_id") or "")
        title, description = billing_product_display_copy(
            str(row.get("product_id") or ""),
            locale,
            title=_bounded_text(row.get("title"), 80),
            description=_bounded_text(row.get("description"), 160),
            credits=max(0, int(row.get("credits") or 0)),
        )
        result.append(
            {
                "product_id": product_id,
                "title": _bounded_text(title, 80),
                "description": _bounded_text(description, 160),
                "credits": max(0, int(row.get("credits") or 0)),
                "price_xtr": max(0, int(row.get("price_xtr") or 0)),
                "billing_mode": "one_time",
                "deep_link_action": f"buy_{product_id}",
            }
        )
    return result


def _due(next_review: object) -> bool:
    if not next_review:
        return False
    if isinstance(next_review, datetime):
        observed = next_review.date()
    elif isinstance(next_review, date):
        observed = next_review
    else:
        try:
            observed = date.fromisoformat(str(next_review)[:10])
        except ValueError:
            return False
    return observed <= datetime.now(timezone.utc).date()


def _read_only_database_snapshot(
    store: Any,
    *,
    user_id: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    """Read the SQLAlchemy store without calling its ensure-backed getters."""

    session_factory = vars(store).get("Session")
    if not callable(session_factory):
        return None
    with session_factory() as session:
        learner = session.get(User, int(user_id))
        if learner is None:
            raise MiniAppAccessDenied("Mini App access denied")
        progress_row = session.get(UserProgress, int(user_id))
        mirror_row = session.execute(
            text(
                "SELECT interface_locale, mirror_response_mode, mirror_style, mirror_depth, mirror_level FROM users "
                "WHERE telegram_user_id = :user_id"
            ),
            {"user_id": int(user_id)},
        ).mappings().one()
        product = {
            "role": learner.role,
            "native_language": learner.native_language,
            "learning_goal": learner.learning_goal,
            "daily_word_goal": learner.daily_word_goal,
            "active_pack_id": progress_row.active_pack_id if progress_row else None,
            "active_lang": progress_row.active_lang if progress_row else "en",
            "mirror_style": str(mirror_row["mirror_style"] or "teacher"),
            "interface_locale": mirror_row["interface_locale"],
        }
        progress = {}
        if progress_row is not None:
            for field_name in (
                "total_correct",
                "total_wrong",
                "sessions",
                "xp",
                "level",
                "streak",
                "streak_best",
                "last_activity_date",
                "today_xp",
                "today_date",
                "active_lang",
                "active_pack_id",
            ):
                progress[field_name] = getattr(progress_row, field_name)
        preferences = {
            "mode": str(mirror_row["mirror_response_mode"] or "text"),
            "depth": str(mirror_row["mirror_depth"] or "balanced"),
            "level": str(mirror_row["mirror_level"] or "adaptive"),
        }
    return product, progress, preferences


def _read_only_activity_days(
    store: Any,
    *,
    user_id: int,
    observed_date: date,
    last_activity_date: object,
) -> list[str]:
    """Return a bounded, identity-free set of real learning days."""

    first_date = observed_date - timedelta(days=_ACTIVITY_WINDOW_DAYS - 1)
    activity_days: set[date] = set()
    try:
        canonical_day = date.fromisoformat(str(last_activity_date or "")[:10])
    except ValueError:
        canonical_day = None
    if canonical_day is not None and first_date <= canonical_day <= observed_date:
        activity_days.add(canonical_day)

    session_factory = vars(store).get("Session")
    if callable(session_factory):
        first_instant = datetime.combine(first_date, datetime.min.time(), timezone.utc)
        final_instant = datetime.combine(
            observed_date + timedelta(days=1), datetime.min.time(), timezone.utc
        )
        with session_factory() as session:
            rows = session.scalars(
                select(AnalyticsEvent.occurred_at).where(
                    AnalyticsEvent.telegram_user_id == int(user_id),
                    AnalyticsEvent.event_name.in_(_ACTIVITY_EVENT_NAMES),
                    AnalyticsEvent.occurred_at >= first_instant,
                    AnalyticsEvent.occurred_at < final_instant,
                )
            ).all()
        for occurred_at in rows:
            if isinstance(occurred_at, datetime):
                activity_day = occurred_at.date()
                if first_date <= activity_day <= observed_date:
                    activity_days.add(activity_day)
    return [activity_day.isoformat() for activity_day in sorted(activity_days)]


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def build_bootstrap(
    store: Any,
    *,
    user_id: int,
    display_name: str,
    locale: str,
    catalog: Any,
    products: list[Mapping[str, Any]],
    checkout_enabled: bool,
    ai_enabled: bool,
    voice_enabled: bool,
    avatar_url: str = "",
    initial_credits: int = 0,
    observed_date: date | None = None,
    active_pack_id_override: str | None = None,
    active_language_override: str | None = None,
    interface_locale_override: str | None = None,
) -> dict[str, Any]:
    access = require_active_learner(store, user_id)
    database_snapshot = _read_only_database_snapshot(
        store,
        user_id=int(user_id),
    )
    preferences: Mapping[str, Any] = {}
    if database_snapshot is not None:
        product, progress, preferences = database_snapshot
    else:
        product = store.product_profile(int(user_id))
        if not isinstance(product, Mapping):
            product = {}
        progress = store.load_profile(int(user_id), {})
        if not isinstance(progress, Mapping):
            progress = {}
    if active_pack_id_override is not None:
        product = dict(product)
        progress = dict(progress)
        product["active_pack_id"] = str(active_pack_id_override)
        progress["active_pack_id"] = str(active_pack_id_override)
        if active_language_override is not None:
            product["active_lang"] = str(active_language_override)
            progress["active_lang"] = str(active_language_override)
    active_language = _bounded_text(product.get("active_lang") or "en", 16)
    active_pack = catalog.get(str(product.get("active_pack_id") or ""))
    progress_namespace = (
        active_pack.storage_key if active_pack is not None else active_language
    )
    word_progress = store.load_word_progress(int(user_id), progress_namespace)
    if not isinstance(word_progress, Mapping):
        word_progress = {}

    words: list[dict[str, Any]] = []
    if active_pack is not None and active_pack.visible_to(str(access.get("role") or "learner")):
        for word in catalog.words(active_pack):
            state = word_progress.get(vocabulary_id_for(word))
            if not isinstance(state, Mapping):
                continue
            meaning_language = str(product.get("native_language") or "ru")
            if meaning_language == "ru":
                curated_meaning = word.get("meaning")
            else:
                aligned = catalog.meaning_entry(
                    word,
                    meaning_language=meaning_language,
                    target_pack=active_pack,
                    role=str(access.get("role") or "learner"),
                )
                curated_meaning = (
                    aligned.get("target") if isinstance(aligned, Mapping) else ""
                )
            correct = max(0, int(state.get("correct_count") or 0))
            wrong = max(0, int(state.get("wrong_count") or 0))
            words.append(
                {
                    "target": _bounded_text(word.get("target"), 120),
                    "meaning": _bounded_text(curated_meaning, 200),
                    "correct": correct,
                    "wrong": wrong,
                    "learned": bool(correct >= 3),
                    "due": _due(state.get("next_review")),
                }
            )
            if len(words) >= 60:
                break

    total_correct = max(0, int(progress.get("total_correct") or 0))
    total_wrong = max(0, int(progress.get("total_wrong") or 0))
    usage = store.ai_usage_summary(
        int(user_id), initial_credits=max(0, int(initial_credits))
    )
    if not isinstance(usage, Mapping):
        usage = {}
    referrals = {
        "invited": 0,
        "activated": 0,
        "earned_credits": 0,
        "reward_credits": 5,
        "reward_cap": 10,
    }
    referral_loader = getattr(store, "referral_summary", None)
    if callable(referral_loader):
        candidate = referral_loader(int(user_id))
        if isinstance(candidate, Mapping):
            referrals = {
                key: max(0, int(candidate.get(key) or 0))
                for key in referrals
            }
    if database_snapshot is None:
        preference_loader = getattr(store, "get_mirror_preferences", None)
        if callable(preference_loader):
            try:
                candidate = preference_loader(int(user_id))
            except (AttributeError, TypeError, ValueError):
                candidate = {}
            if isinstance(candidate, Mapping):
                preferences = candidate

    languages = []
    seen_languages: set[str] = set()
    role = str(access.get("role") or product.get("role") or "learner")
    meaning_language = str(product.get("native_language") or "ru")
    for pack in catalog.compatible_packs(meaning_language, role):
        if pack.target_language in seen_languages:
            continue
        seen_languages.add(pack.target_language)
        languages.append(
            {
                "language": _bounded_text(pack.target_language, 16),
                "flag": _bounded_text(pack.flag, 8),
                "label": _bounded_text(pack.label, 80),
                "direction": "rtl" if pack.direction == "rtl" else "ltr",
                "word_count": max(0, int(pack.entry_count)),
                "current": pack.pack_id == str(product.get("active_pack_id") or ""),
                "switch_value": pack.pack_id,
            }
        )

    selected_locale = miniapp_locale(
        interface_locale_override or product.get("interface_locale") or locale
    )
    copy = MINIAPP_COPY[selected_locale]
    tracked_count = len(word_progress)
    learned_count = sum(
        1
        for state in word_progress.values()
        if isinstance(state, Mapping)
        and int(state.get("correct_count") or 0) >= 3
    )
    today = observed_date or datetime.now(timezone.utc).date()
    raw_today_date = progress.get("today_date")
    try:
        progress_today = date.fromisoformat(str(raw_today_date)[:10])
    except (TypeError, ValueError):
        progress_today = None
    today_xp = (
        max(0, int(progress.get("today_xp") or 0))
        if progress_today == today
        else 0
    )
    activity_days = _read_only_activity_days(
        store,
        user_id=int(user_id),
        observed_date=today,
        last_activity_date=progress.get("last_activity_date"),
    )
    first_activity = date.fromisoformat(activity_days[0]) if activity_days else today
    calendar = {
        "today": today.isoformat(),
        "min_month": _month_key(first_activity),
        "max_month": _month_key(today),
        "activity_days": activity_days,
    }
    settings_values = {
        "learning_goal": _localized_setting_value(
            selected_locale, product.get("learning_goal")
        ),
        "mirror_mode": _localized_setting_value(
            selected_locale, preferences.get("mode")
        ),
        "mirror_style": _localized_setting_value(
            selected_locale, product.get("mirror_style")
        ),
        "mirror_depth": _localized_setting_value(
            selected_locale, preferences.get("depth")
        ),
        "mirror_level": _localized_setting_value(
            selected_locale, preferences.get("level")
        ),
    }
    profile_payload = {
        "display_name": _bounded_text(display_name, 80),
        "current_language": active_language,
        "meaning_language": _bounded_text(product.get("native_language"), 16),
        "learning_goal": _bounded_text(product.get("learning_goal"), 32),
        "daily_word_goal": max(0, int(product.get("daily_word_goal") or 0)),
        "credits": max(0, int(usage.get("available_credits") or 0)),
    }
    safe_avatar_url = _safe_telegram_photo_url(avatar_url)
    if safe_avatar_url:
        profile_payload["avatar_url"] = safe_avatar_url

    return {
        "locale": selected_locale,
        "direction": miniapp_text_direction(selected_locale),
        "copy": dict(copy),
        "profile": profile_payload,
        "progress": {
            "level": max(0, int(progress.get("level") or 0)),
            "xp": max(0, int(progress.get("xp") or 0)),
            "streak": max(0, int(progress.get("streak") or 0)),
            "best_streak": max(0, int(progress.get("streak_best") or 0)),
            "sessions": max(0, int(progress.get("sessions") or 0)),
            "today_xp": today_xp,
            "accuracy": {"correct": total_correct, "total": total_correct + total_wrong},
            "tracked_words": tracked_count,
            "learned_words": learned_count,
            "calendar": calendar,
        },
        "words": words,
        "credits": {
            "available": max(0, int(usage.get("available_credits") or 0)),
            "reserved": max(0, int(usage.get("reserved_credits") or 0)),
            "spent": max(0, int(usage.get("spent_credits") or 0)),
            "contract": copy["credit_contract"],
        },
        "referrals": referrals,
        "products": visible_credit_products(products, locale=selected_locale),
        "languages": languages[:16],
        "settings": {
            "daily_goal": max(0, int(product.get("daily_word_goal") or 0)),
            "meaning_language": language_name(
                _bounded_text(product.get("native_language"), 16),
                selected_locale,
            ),
            "interface_locale": selected_locale,
            **settings_values,
        },
        "interface_locales": [
            {
                "value": candidate,
                "label": language_name(candidate, selected_locale),
                "direction": "rtl" if candidate == "ar" else "ltr",
                "current": candidate == selected_locale,
            }
            for candidate in ("en", "fr", "de", "ja", "ar", "zh", "ru", "es")
        ],
        "features": {
            "ai": bool(ai_enabled),
            "voice": bool(voice_enabled),
            "stars_checkout": bool(checkout_enabled),
        },
        "actions": {
            "learn": "miniapp_learn",
            "continue": "miniapp_continue",
            "ai": "miniapp_ai",
            "buy": "miniapp_buy",
            "lang": "miniapp_lang",
            "settings": "miniapp_settings",
            "privacy": "miniapp_privacy",
            "help": "miniapp_help",
            "share": "share",
        },
    }
