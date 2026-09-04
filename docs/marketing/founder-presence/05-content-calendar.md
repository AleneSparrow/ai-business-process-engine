# Календарь — живая очередь, без дублей

CTA по умолчанию: `https://ai-business-process-engine.vercel.app/`
Время слота: **09:00 America/Los_Angeles = 16:00 UTC**.

Brand 1–5 уже в таблице. Их не переписывать и не дублировать длинными LI-002/011/009.

## Уже в автопосте (не трогать)

| Когда (UTC) | Канал | Audience | Status | Что |
| --- | --- | --- | --- | --- |
| 2026-09-04 | linkedin | brand | Posted | Capture vs cycle (Brand 1). Live на профиле. |
| 2026-09-04 16:00 | x | brand-sv | Posted | Тот же тезис на @AleneVorobei |
| 2026-09-06 16:00 | linkedin | brand | Ready | Brand 2 — cycle |
| 2026-09-08 16:00 | linkedin | brand | Ready | Brand 3 — not lead gen |
| 2026-09-09 16:00 | linkedin | wave1-lawyers | Draft | не в бренд-фид |
| 2026-09-10 16:00 | linkedin | brand | Ready | Brand 4 — safety as note |
| 2026-09-11 16:00 | linkedin | wave1-lawyers | Draft | не в бренд-фид |
| 2026-09-12 16:00 | linkedin | brand | Ready | Brand 5 — zero-config / legal is the door |
| 2026-09-16 16:00 | linkedin | wave1-lawyers | Draft | не в бренд-фид |

## Дыры, закрытые в той же таблице (Draft, пока не Ready)

| Когда (UTC) | ID | Канал | Суть |
| --- | --- | --- | --- |
| 2026-09-14 16:00 | FSV-01 | linkedin | Я Alena, это мой движок |
| 2026-09-15 16:00 | FSV-X01 | x | то же, коротко |
| 2026-09-17 16:00 | FSV-X02 | x | idempotency |
| 2026-09-18 16:00 | FSV-02 | linkedin | модель не меняет стейт |
| 2026-09-21 16:00 | FSV-03 | linkedin | честно недоделано (деньги / live tenant) |
| 2026-09-22 16:00 | FSV-X03 | x | след раньше города |
| 2026-09-23 16:00 | FSV-04 | linkedin | DNA, не-legal тест |
| 2026-09-25 16:00 | FSV-05 | linkedin | design partner |
| 2026-09-28 16:00 | FSV-V01 | linkedin | Skip — native video V-01, не text Zap |

Чтобы FSV-01…05 ушли в LinkedIn: в таблице `status = Ready`. Не раньше.

## Съёмка

Один блок 90–120 мин / 14 дней. Сценарии — `07-shooting-scripts.md`.
Первый обязательный ролик — V-01 (лицо + имя). Без него founder-след дырявый,
даже если Brand 1–5 постятся.

## Engagement (не Zapier)

15 мин/день: комментарии на LinkedIn и X к US-фаундерам. Автоответы запрещены.
