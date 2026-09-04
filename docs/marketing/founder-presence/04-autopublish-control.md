# Автопубликация — живой контур Zapier

Копировать посты руками **нельзя**. Очередь и гейт — Zapier Tables.
Публикация без `status = Ready` **запрещена**.

## Источник правды

| Что | Где |
| --- | --- |
| Очередь | https://tables.zapier.com/app/tables/01M1N9VBC7JMDFM9QSMKZNMQM8 |
| Зеркало Sheets (не live) | https://docs.google.com/spreadsheets/d/1_lj_aaK38nbIF4bkjNxZJEsT6LobkFr-cBOBmRSWnm4/edit |
| Не использовать | таблица `Flywheel Content Control` / `1MK0vr9eNFcV-CpiNITSPgtYq--ZnC7nOocoV_eIEk4M` |
| Скилл LinkedIn | `flywheel linkedin autopost` |
| Скилл X | `flywheel x typefully autopost` (публикация); `flywheel x autopost` — короткий alias |
| Zap 378524885 | **OFF**, не включать, пока там Copilot/генерация |
| Typefully | подключен: social set `330124`, @AleneVorobei |

Поля таблицы: `publish_date`, `channel`, `audience`, `status`, `post_text`,
`cta_url`, `image_url`, `posted_url`, `notes`.

## Машина состояний

```
Draft → Ready → Posted
Draft → Skip
Ready → Skip   (kill до слота)
```

`founder-sv` Ready только после явного «делай» / Ready от Alena.
4 сентября 2026: FSV-02/04/05 и FSV-X02/X03 поставлены Ready; FSV-01 и
FSV-X01 — Skip (дубль живого интро); FSV-03 уже Posted. FSV-V01 остаётся Skip.

## Audience

| audience | Куда | Правило |
| --- | --- | --- |
| `brand` | личный LinkedIn + homepage CTA | автопост, если Ready и дата ≤ сейчас |
| `founder-sv` | тот же LinkedIn | авторство/сборка; Ready только вручную |
| `brand-sv` | X @AleneVorobei | Typefully |
| `wave1-lawyers` | `/lawyers` | не в бренд-фид, пока Alena явно не сказала |

Видео: `notes` содержит `BLOCK_AUTOPOST_UNTIL_VIDEO` или `status = Skip` —
text Zap не стреляет. Native video грузится руками, потом Posted + URL.

## Каналы, которые уже едут

- LinkedIn Create Share Update, аккаунт Alena Vorobei, visibility anyone.
- X через Typefully, social set `330124` (Alena Vorobei), @AleneVorobei.

Instagram / Facebook / Buffer — не трогать, пока нет connection.

## Линтер перед Ready

```bash
python3 scripts/content_guard.py --text-file /tmp/draft.md
```

Запрещено в `post_text`: cold lead, intake assistant как имя продукта,
выдуманный %, «to payment» как сбор денег, Pro/10 seats, продукт «для юристов».
