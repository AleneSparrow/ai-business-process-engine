# 20 технических постов: замкнутый цикл продаж (Flywheel)

Документ для агента, который публикует в LinkedIn и X (Twitter).
Собрано 4 сентября 2026 по факту инженерной работы: движок перестал быть CRM-intake и стал закрывать входящее обращение записью.

Язык постов — **английский** (рынок США). Этот бриф — на русском, чтобы агент не перепутал УТП.

---

## Роль агента

Опубликовать серию из 20 постов. Каждый номер = одна мысль, в двух длинах:

- **LinkedIn** — 1 пост, 800–1600 знаков, абзацы коротко, без эмодзи-стены, без «🚀».
- **X / Twitter** — 1 твит до ~260 знаков. Если мысль не влезает — указан **thread** из 2 твитов, публиковать пачкой.

Не сокращать серию, не менять порядок без причины: это пошаговый разбор той же работы.

Не смешивать платформы в одном черновике: копировать блок LinkedIn в LinkedIn, блок X в X.

---

## Что продаём (и чем это не является)

Flywheel — детерминированный движок **от входящего обращения до сделки**. Полная замена человеку, который сидит и обрабатывает лиды: квалификация, возражения, следующий шаг, запись. AI только переформулирует уже выбранный ход.

Не CRM. Не intake «сняли имя и передали человеку». Не лидогенерация (это продукт 2, позже). Не «продукт для юристов» — юрниша это вход на рынок, движок без отраслевых ветвлений.

Причина покупать: цикл доходит до записи / принятой сметы.
Детерминированность — доказательство, что это безопасно впустить, не заголовок.

---

## Запрещено в копи

- слова **cold lead / cold outreach / generate leads** как обещание этого продукта
- называть Flywheel **CRM**, **chatbot**, **intake assistant**, **Atelier**
- обещать **процент конверсии в клиента**, **to payment**, сбор денег с конечного клиента
- отраслевая лексика «для юристов / для HVAC» как суть продукта (вертикаль можно как *пример* входящего, не как нишу)
- выдуманные цены, скидки, гарантии в примерах диалога
- упоминание внутренних веток, PR, паролей, localhost
- «AI решает, что сказать»

Можно: inbound inquiry, booked time, next step, objection, Business DNA, engine, zero-config.

Хештеги — максимум 3, только в LinkedIn, в конце. На X лучше без них. Разрешённый набор: `#B2B` `#SaaS` `#salesops` — не больше. Не ставить `#legaltech` как главный тег.

Голос: первый человек, инженер/основатель, конкретика, без вдохновляющего тумана.

Каденс: 1 пост в день, LinkedIn утром US East, X в тот же день через 2–4 часа. Не публиковать все 20 сразу.

Визуал (если агент умеет прикладывать): скрин диалога или дашборда с BOOKED; не стоковые рукопожатия.

---

## Карта серии (что за чем)

| # | Технический шаг |
|---|-----------------|
| 1 | Находка: движок складывал лиды в папку, а не продавал |
| 2 | CRM ≠ замкнутый цикл |
| 3 | Zero-config по умолчанию держит время |
| 4 | Нет цены → закрытие = следующий шаг в календаре |
| 5 | `sales_playbook`: ход выбирает движок, не модель |
| 6 | Возражение: признать, потом close |
| 7 | Тон клиента не меняет ход |
| 8 | Follow-up не спрашивает «ещё интересно?» |
| 9 | «Дорого» на слотах — это возражение, не промах по кнопке |
| 10 | Два сервиса в каталоге → спросить, не эскалировать |
| 11 | Повседневные слова, не названия из каталога |
| 12 | Flywheel продаёт сам себя тем же циклом |
| 13 | 35 диалогов / 14 бизнесов — eval |
| 14 | Виджет, который не парсился |
| 15 | Дашборд прятал тестовые лиды |
| 16 | Человек только для safety |
| 17 | В `src/` нет ветвлений по индустрии |
| 18 | Вкладка CRM в Settings — исходящий пинг, не продукт |
| 19 | Живой Chrome: два BOOKED после возражения |
| 20 | Продукт 2 (генерация лидов) — потом; этот продукт закрывает входящих |

---

## Пост 1 — Движок складывал лиды

**LinkedIn**

We instrumented the engine and the number was ugly: a hundred-plus inbound conversations, almost none booked.

Not because the model was “bad at sales.” Because the default path after qualification was human review. The bot captured a name, a ZIP, a service — and filed it.

That is a CRM.

A person who processes inbound leads does not file the conversation. They hold a time.

So we changed the default. Zero-config onboarding now books a next step the moment the lead qualifies. Quote, handoff, and “wait for the team” are Settings, not the first run.

If your AI assistant is proud of a full contact record and an empty calendar, you did not automate sales. You automated a clipboard.

**X**

We measured it: 100+ inbound chats, almost no bookings. The engine was filing names, not holding times. That’s a CRM. We flipped the default: qualify → hold a calendar slot. Capture is not a sale.

---

## Пост 2 — Замкнутый цикл, не inbox

**LinkedIn**

Most “AI for leads” stops where the work starts.

Name. Phone. “A teammate will follow up.”

The person you are replacing does not stop there. They qualify, handle “I need to think about it,” pick a next step, and put it on the calendar.

That is the product: inbound inquiry → booked or quoted deal. Closed cycle. Full replacement for the processor, not a nicer inbox.

Lead generation is a different product, later. This one assumes the person already reached out. The job is to not lose them between the form and the appointment.

**X**

“We’ll follow up” is not a sales motion. The processor you replace qualifies, handles hesitation, and holds a time. That’s the cycle. Capture-and-handoff is an inbox with extra steps.

---

## Пост 3 — Zero-config = запись, не review

**LinkedIn**

Zero-config used to mean: every new service was `human_review`, booking off.

So a plumber who finished the wizard in ten minutes still did not get a booked job. The engine waited for Settings.

That is individual setup hiding inside a default.

The rule now: every service starts bookable, booking on. Without a price — which the engine must never invent — the close is a held time on hours derived from the ZIP codes the owner already typed.

If you want quotes or a human in the loop, you opt into that. You do not have to opt into selling.

**X**

Zero-config used to ship every service as “human review.” Wizard done, calendar empty. Default is now bookable. No invented prices. The close is a held time. Handoff is a setting, not the product.

---

## Пост 4 — Универсальный close без цены

**LinkedIn**

The engine is forbidden from inventing a dollar amount. That is not a style choice. A hallucinated price is a commitment the business never made.

So what is the close when there is no catalog price yet?

A next step that advances the deal: consult, visit, demo, call. Three real slots. Reply 1, 2, or 3.

That is an advance, not a handoff. The lead is not “warmed.” They are on the calendar.

If you cannot name a price, you can still name a time. A processor does this all day. The engine should too.

**X**

The engine must never invent a price. So the universal close is a next step on the calendar — consult, visit, demo, call. 1, 2, or 3. That’s an advance. Not “someone will reach out.”

---

## Пост 5 — Playbook выбирает ход, модель — нет

**LinkedIn**

We put the sales motion in a module the model cannot vote on.

Discover. Offer a commitment. Handle an objection. Trial-close. Nurture. Escalate for safety. Deal done.

The AI may rephrase an already-approved sentence. It does not pick the move, the price, or whether to escalate.

If the customer is irritated, the wording can get shorter. The move stays “hold a time.”

This is how you get objection handling and sales technique without letting a language model freelance policy. Determinism here is not the pitch. It is how the pitch stays true on turn twelve.

**X**

Sales moves are a playbook the model can’t vote on: discover, close, handle objection, nurture, safety. AI rephrases. It does not pick the path, the price, or the escalation. Tone can change wording. Not the move.

---

## Пост 6 — Возражение: признать, потом close

**LinkedIn**

“That’s too expensive” used to get a warm sentence and a dead end.

A processor does not end the turn on empathy. They acknowledge, then ask for the commitment already on the table.

Price → still hold a time (or accept the quote).
“I need to think” → hold the slot so it does not slip.
“I’ll ask my partner” → hold a time they can forward.

The acknowledgment can vary. The close cannot disappear.

If your bot is great at validating feelings and never asks for 1, 2, or 3, you built a therapist with a CRM export.

**X**

Empathy without a close is a dead end. “Too expensive” / “need to think” / “ask my partner” → acknowledge, then hold a time. The wording can vary. The ask cannot vanish.

---

## Пост 7 — Тон ≠ другой сценарий

**LinkedIn**

Irritated customers get shorter sentences. Anxious ones get calmer ones.

They do not get a different commercial path.

We encoded that as a test: same facts, different `customer_tone`, same sales move. Neutral and irritated both offer the commitment. Emergency still escalates — because safety is a fact, not a vibe.

If tone could reroute the deal, the model would be back in charge of policy. It is not.

Adapt the voice. Do not adapt the spine.

**X**

Irritated ≠ a different playbook. Shorter sentences, same close. Emergency still goes to a human — that’s a fact, not a mood. Tone adapters may reword. They may not reroute.

---

## Пост 8 — Follow-up — это повторный close

**LinkedIn**

A stalled qualified lead used to get: “Are you still interested?”

That is a CRM check-in. It also trains the customer that nothing is on the table.

Follow-up now re-asks the commitment that was already offered.

Qualified, no slot picked → I can still hold a time. Reply 1, 2, or 3.
Quoted, not accepted → the quote is still there. Reply accept, or tell us what to change.
Mid-questions → take the next detail and hold a time.

We also started nudging QUALIFIED and QUOTED, not only the early states. Silence after a slot offer is a stalled sale, not a closed file.

**X**

“Still interested?” is a CRM ping. Follow-up should re-ask the commitment already on the table: hold the slot, or accept the quote. Qualified-but-quiet is a stalled sale, not an archive.

---

## Пост 9 — «Дорого» на выборе времени

**LinkedIn**

Live path, not a thought experiment.

The engine had already offered three appointment times. The customer said “that’s too expensive for me.”

The slot picker treated it as a missed click: “Please reply with its option number.”

Technically true. Commercially illiterate. A processor hears a price flinch, not a UI error.

Fix: if the reply is an objection and not a slot, acknowledge it, keep the times, ask to hold one. No invented dollar amount — there isn’t one. Then they can still send 2 and book.

We watched this in Chrome the same day: objection, hold-a-time, option 2, BOOKED.

**X**

Customer saw three times and said “too expensive.” The picker answered “reply with 1, 2, or 3.” That’s a missed-click handler, not sales. Now: acknowledge, keep the slots, hold a time. No invented price. Then 2 → booked.

---

## Пост 10 — Два совпадения в каталоге

**LinkedIn**

If the customer’s words hit two services, the fallback used to set `requires_human`.

Ambiguous → get a person.

That is how a CRM protects a database. It is not how a processor works. A processor asks: furnace or toilet? Demo or trial?

Two catalog hits is now “which of these?” Safety and “promise me a return” still escalate. Guessing between plumbing and HVAC still does not.

Asking is a sales move (discover). Dumping the lead in a queue is filing.

**X**

Two services matched → we used to page a human. That’s filing. A processor asks “which one?” Ambiguity is discover, not escalation. Safety still escalates. Guessing still doesn’t.

---

## Пост 11 — Слова клиента, не ярлыки каталога

**LinkedIn**

Zero-config dies the first time a customer says “the house isn’t warming up” instead of “Heating & AC repair.”

The outage fallback cannot wait for a live model. It matches distinctive tokens from the owner’s own service names and descriptions — words that belong to one service, not shared filler like “repair.”

Furnace → HVAC. Kitchen sink backup → drain. “Laptop repair” on a home-services catalog → not offered, lost, not guessed.

If matching only works when the visitor recites your Settings labels, you do not have zero-config. You have a search box.

**X**

Customers don’t say your catalog name. They say “house isn’t warming up.” Fallback matching uses distinctive tokens from the owner’s descriptions — not shared words like “repair.” Guessing between services is forbidden.

---

## Пост 12 — Продукт продаёт себя тем же движком

**LinkedIn**

We said the engine should sell any business. Then we made it sell this one.

A visitor who writes “we lose people after the form, I want a live walkthrough to a booked time” is not a support ticket. They are a Flywheel lead. Same onboarding. Same bookable default. Same close: hold a demo time.

If the engine cannot book its own demo without a human processing the thread, it is not a replacement for that human. It is a demo environment.

Dogfooding is not a blog habit. It is a failing test when the self-serve path dead-ends.

**X**

If the engine can’t book its own demo, it isn’t replacing the person who processes leads. A “show me a walkthrough to a booked time” inbound is a lead. Same cycle. Hold the slot.

---

## Пост 13 — Eval: 35 диалогов, не слайд

**LinkedIn**

Claims get a matrix, not a metaphor.

35 multi-turn dialogues. 14 businesses. Home services, salon, auto, wealth (zero-config), pest, photo, SaaS — including Flywheel itself. Everyday wording, objections, emergencies, unsupported requests.

Deterministic fallback (the same path you get when the model is down): 35/35. Sales bar 98% met. No invented prices. Zero-config paths booked. Safety cases still went to a human.

“Works for any business” is not a positioning sentence until a non-legal vertical books. This is that check.

**X**

35 live dialogues, 14 businesses, including our own demo inbound. Deterministic path (model-down fallback): 35/35. No invented prices. Emergencies still human. “Any business” is a test matrix, not a slogan.

---

## Пост 14 — Виджет, который молчал

**LinkedIn**

The staff dashboard was empty. Conversations existed. The website widget would not start.

A one-line slip in the embed: a timezone helper had replaced the `restore()` function that rehydrates the chat. The file no longer parsed. Visitors saw a launcher that did nothing.

No model was involved. No prompt to tweak. A syntax hole in the last mile.

We added a check so a helper function cannot eat `restore()` again.

If the embed does not parse, your closed cycle is a server talking to itself.

**X**

Dashboard empty, widget dead. Not the model — `restore()` in the embed got overwritten and the file stopped parsing. Last-mile syntax. We now syntax-check the widget so a helper can’t eat the boot function again.

---

## Пост 15 — Обзор прятал лиды

**LinkedIn**

Second empty-dashboard bug, different layer.

New businesses run in test mode. Overview statistics respected “hide test data.” The lead list used the same flag.

So after a real widget conversation you still saw “No leads yet” — unless you found a checkbox meant for charts.

Operators do not debug query strings. They think the product ate the lead.

Fix: the list always includes test-mode cases. The checkbox only filters statistics. Proof of work stays visible. Vanity rates stay honest.

**X**

New businesses are test-mode. Overview hid those cases behind a stats checkbox, so the list said “No leads yet” after a live chat. List now always shows them. The checkbox is for rates, not for hiding the work.

---

## Пост 16 — Человек только для safety

**LinkedIn**

Human review is not the commercial default. It is the exception list.

Smoking breaker panel. “Guarantee me 20% and invest it now.” Owner explicitly sets a service back to handoff.

Everything else should advance: ask the missing question, offer times, handle the flinch, book.

If “needs a person” is how you finish qualification, you hired a language model to operate a ticket queue. The expensive part of the processor’s job — the close — is still on a human who was supposed to be freed.

**X**

Humans stay for safety and out-of-policy asks — not as the default after “qualified.” If qualification ends in a ticket, you automated a queue. The close is still on a person.

---

## Пост 17 — Ни одной отраслевой ветки в движке

**LinkedIn**

There is no industry fork in the engine. No legal glossary. No salon mode.

The same playbook booked a furnace repair and a product demo. Service names and descriptions come from onboarding. Distinctive tokens come from that text. Hours come from ZIP codes. The close is still a time.

Verticals are how you enter a market. They are not how you fork the product. We already made that mistake once.

“Any business” is a property of the code, or it is fiction. The test is a second vertical booking without a special case.

**X**

No industry fork in the engine. Furnace repair and a product demo use the same close: hold a time. Verticals are go-to-market. They are not forks of the product.

---

## Пост 18 — Вкладка CRM — это не CRM

**LinkedIn**

Settings has a tab labeled CRM.

It is not a CRM. It is an outbound HTTPS ping — Zapier, Make, the system you already have — when a conversation hits qualified or won. The URL is treated as a secret and never shown again.

Flywheel does not become the system of record because a webhook exists. The cycle still has to close inside the engine. The ping is a copy of a fact, after the fact.

If the tab were the product, we would have built an inbox. We built a close, then a doorbell.

**X**

Settings → CRM is an outbound webhook: ping Zapier/Make when a chat is qualified or won. It is not a CRM. The engine still has to book. The ping is a doorbell after the close.

---

## Пост 19 — Живой диалог, не отчёт

**LinkedIn**

A real browser, not a screenshot of a passing test.

New business. Onboarding only. Booking left on. No Settings visit.

Maya: furnace, ZIP, phone. Slots. “Too expensive.” Hold a time. Option 2. Booked — 9:30 a.m.

Jordan, same widget, same day: AC isn’t cooling. Same objection. Same ask. Option 2. Booked — 11:30 a.m.

Overview: booked 2, needs-you 0.

That is the replacement: the processor is not in the thread. The calendar is.

**X**

Fresh business, no Settings. Two inbound chats, both said “too expensive,” both booked a time the same morning. Overview: booked 2, needs you 0. That’s the processor, replaced.

---

## Пост 20 — Этот продукт закрывает. Следующий — находит.

**LinkedIn**

Two products. Easy to mash together. Fatal if you do.

This one takes someone who already reached out and walks them to a booked or quoted deal. That is the whole job.

Finding net-new people is a later product. We will not describe inbound visitors as “cold leads.” That phrase promises a machine we have not shipped.

How we will get our own customers: the same engine. A demo request is a lead. The cycle must hold a time. If we cannot sell Flywheel with Flywheel, we are not ready to sell it to anyone else.

Closed cycle first. Generation second. Never reversed in the copy.

**X**

This product closes inbound. Lead gen is product two, later. Don’t call an inbound chat a “cold lead.” And Flywheel has to sell itself the same way: demo request → hold a time. If we can’t, we don’t ship the pitch.

---

## Чеклист перед публикацией

1. В тексте нет cold lead / CRM-as-product / intake assistant / Atelier / «для юристов» как сути.
2. Нет выдуманной цены и нет % «лид → клиент».
3. LinkedIn и X скопированы из своего блока, не склеены.
4. Посты 1→20 по порядку; не начинать с комплаенса.
5. Если есть визуал — только реальный диалог/дашборд, не сток.
6. После публикации не править УТП «для охвата».

Конец документа.
