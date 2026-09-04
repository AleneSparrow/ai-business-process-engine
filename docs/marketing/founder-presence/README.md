# Founder presence — Flywheel

Операторский пакет для Алёны Воробей. Публичные тексты — на английском.
Этот индекс — на русском.

**Вердикт одной строкой.** Продажная GTM-волна 1 (соло-юристы как *вход*) собрана.
Маркетинговая стратегия *основателя*, контент-план, доказательство авторства,
автопубликация и съёмка — до этого пакета **не были готовы**. Теперь они есть
как система. Публиковать можно только после вашего `APPROVED` в таблице контроля.

| Документ | Зачем |
| --- | --- |
| [01-readiness-audit.md](01-readiness-audit.md) | Что уже было и чего не хватало |
| [02-strategy.md](02-strategy.md) | Две аудитории, Долина, «продаёт сам себя» |
| [03-market-demand-2026-09.md](03-market-demand-2026-09.md) | Спрос сентября 2026, не снимок августа |
| [04-autopublish-control.md](04-autopublish-control.md) | Жёсткий контур: очередь → линт → вы → автопост |
| [05-content-calendar.md](05-content-calendar.md) | 8 недель, ритм, столпы |
| [06-post-queue.md](06-post-queue.md) | Готовые посты (LinkedIn / X), статус DRAFT |
| [07-shooting-scripts.md](07-shooting-scripts.md) | Сценарии и инструкция съёмки с вами в кадре |
| [08-profile-setup.md](08-profile-setup.md) | Био, шапка, что застолбить вручную |
| [guardrails.yaml](guardrails.yaml) | Запрещённые формулировки для линтера |
| [content-control.csv](content-control.csv) | Тот же реестр, что уходит в Google Sheet |

Линтер: `python scripts/content_guard.py docs/marketing/founder-presence/06-post-queue.md`

Живая очередь (все 26 постов, статус **DRAFT**, ничего не опубликовано):
[Flywheel Content Control](https://docs.google.com/spreadsheets/d/1MK0vr9eNFcV-CpiNITSPgtYq--ZnC7nOocoV_eIEk4M/edit)
в Google Sheets аккаунта Alena Vorobei. Чтобы выложить LI-001, поставьте
`approved_by = Alena Vorobei`, `status = APPROVED`. Пока Zap A не собран —
копируйте текст в LinkedIn руками.

Ни один пост **не публикуется агентом**. LinkedIn у Zapier подключён как
Alena Vorobei — это канал доставки *после* вашего явного approve, не кнопка
«выложить всё сейчас».
