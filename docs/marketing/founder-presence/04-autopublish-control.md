# Автопубликация с жёстким контролем

Публикация без вашего имени в поле `approved_by` **запрещена**. Это не рекомендация.

## 1. Зачем автопост, если контроль жёсткий

Цель — не «ИИ постит за вас». Цель:

- вы снимаете и утверждаете пачкой раз в неделю;
- машина публикует в слоты, когда аудитория США онлайн;
- ни один черновик не выходит, пока линтер и вы не сказали да;
- каждую пятницу цифры возвращаются в таблицу, слабые столпы режутся.

Без гейта автопост в 2026 читается как slop и сжигает личный бренд, который
как раз нужно построить.

## 2. Машина состояний

```
DRAFT → LINT_PASS → APPROVED → SCHEDULED → PUBLISHED → MEASURED
              ↘ REJECTED
SCHEDULED → KILLED   (до времени слота)
```

Переходы:

| Из | В | Кто |
| --- | --- | --- |
| DRAFT | LINT_PASS | `scripts/content_guard.py` без ошибок |
| DRAFT / LINT_PASS | REJECTED | вы, одной пометкой |
| LINT_PASS | APPROVED | **только вы**, `approved_by = Alena Vorobei` и дата |
| APPROVED | SCHEDULED | Zapier / Buffer, слот из календаря |
| SCHEDULED | PUBLISHED | Zapier LinkedIn Create Share Update |
| SCHEDULED | KILLED | вы, до слота |
| PUBLISHED | MEASURED | ручной ввод метрик в пятницу, 15 минут |

Агент, подрядчик, «ассистент» **не имеют** права ставить APPROVED.

## 3. Что уже подключено в Zapier (не создавать аккаунты)

На момент сборки этого пакета:

- **LinkedIn** — личный профиль Alena Vorobei. Действие: Create Share Update.
- **Gmail** — дайджест на утверждение.
- **Google Sheets** — реестр очереди (контрольная плоскость).
- **Google Calendar** — слоты съёмки и публикации.

Не подключено, и агент это не включает за вас:

- X / Twitter (в каталоге Zapier как нативное приложение не найдено; кросспост —
  через Buffer, когда вы сами заведёте Buffer).
- YouTube, Instagram, TikTok — ручная загрузка из одной папки съёмки.
- Company LinkedIn Page — отдельное действие Create Company Update, только
  если будет company page. Пока не использовать.

## 4. Контрольная таблица

Живая таблица: [Flywheel Content Control](https://docs.google.com/spreadsheets/d/1MK0vr9eNFcV-CpiNITSPgtYq--ZnC7nOocoV_eIEk4M/edit)
(создана 4 сентября 2026, 26 черновиков, все `DRAFT`). Дубль в репозитории:
`content-control.csv`. Сортируйте по колонке `id`, если порядок строк съехал
при загрузке.

Колонки (они же в `content-control.csv` и в Google Sheet):

1. `id` — `LI-001`, `X-001`, `V-01`
2. `channel` — `linkedin` / `x` / `short_video` / `youtube`
3. `audience` — `scene` / `buyer` / `both`
4. `pillar` — `cycle` / `model` / `builder`
5. `title_internal` — для вас, не публикуется
6. `body` — финальный английский текст
7. `media` — имя файла или `none`
8. `status`
9. `lint` — `pass` / `fail` / `unchecked`
10. `approved_by`
11. `approved_at`
12. `scheduled_for` — ISO, America/Los_Angeles
13. `published_url`
14. `saves` `comments_icp` `inbound_yes` — пятничные метрики
15. `kill` — `FALSE` пока жив

Zapier-правило публикации (собираете в UI Zapier, агент запове не создаёт):

**Zap A — LinkedIn, только чистые ряды**

1. Trigger: Google Sheets → New or Updated Spreadsheet Row
2. Filter (обязателен, без него не включать Zap):
   - `status` exactly `APPROVED`
   - `approved_by` exactly `Alena Vorobei`
   - `lint` exactly `pass`
   - `kill` is not `TRUE`
   - `channel` is `linkedin`
   - `scheduled_for` ≤ now (или Scheduler + Lookup Row)
3. Action: LinkedIn → Create Share Update
   - Comment = `body`
   - Visible To = Anyone
   - URL только если в `body` нет уже ссылки и вы сознательно хотите OG
4. Action: Sheets → Update Row: `status = PUBLISHED`, записать URL если есть

**Zap B — утренний гейт, не публикация**

1. Trigger: Schedule, 08:00 America/Los_Angeles, пн–пт
2. Sheets: найти ряды `status = LINT_PASS`
3. Gmail: себе письмо «N постов ждут approve. Ничего не уйдёт без тебя.»
   Список id + первые 80 символов. Кнопок «опубликовать всё» в письме нет.

**Zap C — kill switch**

Если `kill = TRUE` и `status = SCHEDULED` — Update Row в `KILLED`, не постить.
Проверять тем же фильтром Zap A: kill не TRUE.

Пока Zap A не собран, публикация только руками из APPROVED. Это нормальный
режим недели 1: вы копируете текст в LinkedIn сами, ставите PUBLISHED.

## 5. Слоты (America/Los_Angeles)

| Канал | Дни | Время |
| --- | --- | --- |
| LinkedIn | вт, ср, чт, пт | 07:30 |
| X | пн–пт | 08:15 и опционально 16:30 |
| Short video | вт, пт | 11:00 (после нативной загрузки) |

Не публиковать пять постов в один час «чтобы догнать». Сцена видит дамп.

## 6. Линтер

```bash
python scripts/content_guard.py docs/marketing/founder-presence/06-post-queue.md
python scripts/content_guard.py --text-file /tmp/draft.md
```

Падает, если в тексте есть запрещённые якоря из `guardrails.yaml`: cold lead,
Atelier как имя продукта, intake assistant как самоназвание, выдуманный %,
«to payment», «for lawyers» как определение продукта, visa/green card как сюжет,
superlatives вроде disrupt/revolutionary.

Линтер не заменяет мозг. Он ловит рецидив старых документов.

## 7. Еженедельный разбор спроса (пятница, 20 минут)

Вписать в Sheet:

- какой `pillar` дал `inbound_yes`
- какой пост прокомментировал человек с US / founder / operator в headline
- что из Wave 1 outreach совпало по языку с комментариями

Решения только бинарные: столп жив / столп на паузу. Не «чуть поменять тон».

Раз в месяц перечитывать `03-market-demand-2026-09.md` и один новый открытый
обзор по AI receptionist / agents. Если рынок начал говорить вашим тезисом
без вас — усилить отличие (deterministic cycle), не громче повторять общее.

## 8. Чего система намеренно не делает

- Не генерирует и не постит новые тексты без новой очереди в репозитории.
- Не отвечает на комментарии. Комментарии — 15 минут вашего голоса в день.
  Автоответы убивают доказательство, что это вы.
- Не публикует видео. Видео слишком легко выложить не туда и не тем кропом.
  Ролики — ручная загрузка по сценарию `07`.
- Не трогает секреты, не логинится в новые сети, не создаёт аккаунты.
