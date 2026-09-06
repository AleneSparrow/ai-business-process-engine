# Founder presence — Flywheel

Операторский пакет. Публичные тексты — английский. Этот индекс — русский.

**Источник правды — не этот репозиторий и не параллельная Google-таблица.**
Живая очередь автопоста:

https://tables.zapier.com/app/tables/01M1N9VBC7JMDFM9QSMKZNMQM8

Статусы: `Draft → Ready → Posted | Skip`. Копировать руками в LinkedIn **нельзя** —
скилл `flywheel linkedin autopost` / `flywheel x typefully autopost`.

| Документ | Зачем |
| --- | --- |
| [01-readiness-audit.md](01-readiness-audit.md) | Что было в репо до пакета |
| [02-strategy.md](02-strategy.md) | Две аудитории, Долина, маховик |
| [03-market-demand-2026-09.md](03-market-demand-2026-09.md) | Рамка спроса (не календарь постов) |
| [04-autopublish-control.md](04-autopublish-control.md) | Zapier Tables + гейт Ready |
| [05-content-calendar.md](05-content-calendar.md) | Живой календарь, без дублей Brand 1–5 |
| [06-post-queue.md](06-post-queue.md) | Только дыры founder-sv (короткие). Длинные LI-001…016 не постить |
| [07-shooting-scripts.md](07-shooting-scripts.md) | V-01…V-12, видео не через text Zap |
| [08-profile-setup.md](08-profile-setup.md) | Био; X = @AleneVorobei |
| [guardrails.yaml](guardrails.yaml) | Линтер |
| [content-control.csv](content-control.csv) | **Не live.** Срез длинных LI-001…016. Не импортировать в Zapier. |

Линтер: `python3 scripts/content_guard.py docs/marketing/founder-presence/06-post-queue.md`
