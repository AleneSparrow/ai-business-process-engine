# Flywheel Demand — источники и выводы

Исследование под продукт 2, 3 сентября 2026. Это синтез публичных рамок маркетинга и диджитал-маркетинга, применённый к границе Flywheel. Не юридическое заключение.

## 1. Что изучалось

| Тема | Зачем продукту 2 |
| --- | --- |
| STP (Segmentation → Targeting → Positioning) | Этапы сборки кампании |
| Jobs-to-be-done + Value Proposition Canvas | Из чего строить ЦА без отраслевых костылей |
| Positioning canvas (April Dunford) | Порядок: альтернативы → отличия → ценность → best-fit → категория |
| TOFU / MOFU / BOFU и HubSpot lifecycle | Учёт стадий, не обещание линейного пути |
| Content funnel 2026 + AI search | Какие брифы Attract должен собирать |
| Permission marketing + welcome-серии | Режим Loyalty вместо холодных рассылок |
| CAN-SPAM, TCPA, FTC substantiation, Endorsement Guides | Что архитектура запрещает по умолчанию |
| Карта инструментов 2026 (HubSpot, Jasper, Klaviyo, Apollo, Instantly, 11x) | Где ниша, где не конкурировать |

## 2. Стратегическая сборка

**STP** остаётся рабочей последовательностью 2026 года: сначала группы, потом выбор группы, потом место в голове этой группы. Targeting не равен «самому большому сегменту» — критерий: доступность, fit, готовность платить. Для zero-config Flywheel это означает *concentrated* targeting: один primary-сегмент из услуг и географии Business DNA, а не десять персон от агентства.

**Jobs-to-be-done / Value Proposition Canvas** (Christensen; Osterwalder et al.). Клиент «нанимает» услугу на работу, а не покупает фичи. Поэтому Marketing DNA хранит `jobs / pains / gains`, а не демографию «женщины 35–44». Демография может появиться позже как канал, не как определение ЦА.

**April Dunford, positioning canvas** (порядок важен):

1. Competitive alternatives — включая «сделают сами» и «наймут человека» (~40% B2B-сделок уходит в no-decision).
2. Unique attributes — только то, что реально следует из Business DNA или owner evidence.
3. Value + proof.
4. Best-fit customers.
5. Market category — последней, не первой.

Ошибка, которую продукт не должен автоматизировать: придумать категорию и слоган до того, как есть отличия. Билдер поэтому начинает с каталога услуг и альтернатив по умолчанию, а не с «мы disruptors».

## 3. Воронка привлечения

Классика TOFU/MOFU/BOFU и HubSpot lifecycle (Subscriber → Lead → MQL → SQL → Opportunity) полезна как **телеметрия**. Она плохо описывает реальное поведение 2026 года.

- Google / BCG (Think with Google, 2025): порядка **80%** потребителей не идут линейным путём. Поведение описывается как 4S: streaming, scrolling, searching, shopping — режимы, а не стадии.
- 6sense: в ~95% случаев покупатель берёт одного из четырёх вендоров, которые были на shortlist в день 1. Сравнение и proof нужны рано, не только «на дне воронки».
- AI-search (ChatGPT / Perplexity / AI Overviews): закрытый за формой контент не попадает в ответный слой. Attract по умолчанию **не гейтит** explainer/comparison. Форма уместна на интерактиве (калькулятор) или на подписке loyalty.

Вывод для состояний проспекта: skip-ahead — это фича, не баг. `UNKNOWN → INQUIRED` легален. Стадии нужны, чтобы понимать, какой бриф показать и когда уже нельзя слать nurture.

Содержимое брифов (синтез content-funnel практик):

| Стадия учёта | Формат | Задача |
| --- | --- | --- |
| aware | explainer | Работа (job), без продажи |
| engaged | comparison | Сами / штат / этот бизнес; честный «кому не подходит» |
| intent | next_step | Что будет после обращения — правда, потому что дальше включается process engine |

Метрики Attract: не vanity-reach, а inquiry и handoff в `NEW_LEAD`. Loyalty: opt-in, open/click, unsubscribe, inquiry с последовательности.

## 4. Loyalty, не cold

Seth Godin, *Permission Marketing*: право писать зарабатывается и удерживается полезностью. Welcome-серии 2026 года сходятся на одном каркасе: 4–6 писем за 7–14 дней, одно CTA на письмо, оффер не в первом письме.

Опора, которую кодирует `sequence_planner`:

1. t=0 — выполнить обещание opt-in  
2. t=48h — кто вы (позиция)  
3. t=96h — ценность по job  
4. t=168h — proof, только если есть evidence  
5. t=240h — мягкий inquire  

Это **не** конкуренция с Instantly/Smartlead/Apollo (холодный объём 10k–100k писем/день, reply 1–4%). Холодный канал противоречит и бренду Flywheel, и входу продукта 1 («человек обратился сам»), и TCPA/CAN-SPAM-риску для SMB без юридического штата.

Klaviyo-класс — retention для тех, кто уже купил. Demand заканчивается раньше: на обращении. После `WON` реактивация — зона process engine (`REACTIVATION`), не Demand.

## 5. Комплаенс, который нельзя «добавить потом»

**CAN-SPAM (FTC).** Любое коммерческое email, включая B2B. Честный From/subject, физический почтовый адрес, рабочий unsubscribe, обработка opt-out ≤ 10 рабочих дней. Штраф до **$53,088** за каждое письмо (индексация FTC, 2025). Demand жёстче закона: loyalty не стартует без opt-in и без адреса в DNA.

**TCPA.** SMS — не CAN-SPAM. Маркетинговые тексты требуют prior express written consent, STOP, немедленный revoke «любым разумным способом». Штатные mini-TCPA часто строже федерального минимума. Поэтому SMS GRANT без `evidence_id` — ошибка домена, не warning.

**FTC truth-in-advertising / claim substantiation.** Объективное утверждение должно иметь reasonable basis *до* публикации. Endorsement Guides, 16 CFR Part 255 (ред. 2023): отзывы = те же клеймы, что если бы их сказал рекламодатель; atypical results нельзя выдавать за typical; material connection раскрывается.

**AI disclosure.** Уже часть продукта 1 (SB 243, NY Article 47, EU AI Act Art. 50). Demand наследует: публичный текст не притворяется человеком.

Практический вывод: `claim_guard` + `consent_gate` — это УТП «детерминированный маркетинг», аналог `decision_router` для привлечения.

## 6. Карта рынка: где окно

| Класс | Примеры | Почему это не мы |
| --- | --- | --- |
| AI receptionist / intake | Rosie, AgentZap, Smith.ai | Это продукт 1, inbound обработка |
| AI SDR / cold outbound | 11x, AiSDR, Instantly, Apollo, Clay | Холодный охват, другая регуляторика, ломает границу «обратился сам» |
| AI copy | Jasper, Copy.ai | Нет воронки, нет handoff в процесс, нет запрета на выдуманные клеймы |
| Inbound suite | HubSpot Marketing Hub, Breeze | Платформа с CRM; мы — узкий движок Attract→Inquiry→Process |
| Retention email/SMS | Klaviyo | После покупки; у нас до обращения |

Ценовой якорь соседней категории (из уже существующего анализа продукта 1): AI SDR $180–499/мес. Это не цена Demand, а доказательство, что рынок платит mid-three-figures за замену маркетингово-продажной функции. Отстройка должна быть функцией, не ценой: **«приводим входящее обращение в детерминированный цикл сделки»**, а не «пишем больше писем».

HubSpot Breeze — та же структурная угроза, что и для продукта 1: дистрибуция внутри установленной CRM. Защита — связка двух продуктов и архитектурный запрет на импровизированные клеймы/отправки, который suite обычно держит политикой, не state machine.

## 7. Что сознательно не берём из моды 2026

- Автономные AI-агенты, которые сами выбирают сегмент и крутят рекламный бюджет. У нас AI не имеет права менять target state.
- «Influence systems вместо воронки» как отказ от стадий. Стадии оставляем для аудита; skip-ahead оставляем для реальности.
- Гейтинг whitepaper в обмен на email как главный TOFU. В AI-search это прячет бренд. Opt-in — для Loyalty, не для права прочитать explainer.
- Формулировку «холодный лид» в клиентских текстах. Для продукта 1 она врёт. Для продукта 2 она обещает холодный охват, которого продукт не делает.

## 8. Источники

STP и позиция

- [STP marketing: model, examples & step-by-step guide (2026) — Dashly](https://www.dashly.io/blog/stp-marketing/)
- [Segmentation, Targeting and Positioning (STP) Guide (2026) — SocioLabs](https://sociolabs.in/segmentation-targeting-and-positioning/)
- [A Quickstart Guide to Positioning — April Dunford](https://www.aprildunford.com/post/a-quickstart-guide-to-positioning)
- [Value Proposition Canvas — Strategyzer / Osterwalder](https://www.strategyzer.com/library/achieve-product-market-fit-with-our-brand-new-value-proposition-designer-canvas)
- Christensen, *Competing Against Luck* (HarperBusiness, 2016) — jobs-to-be-done
- Godin, *Permission Marketing* (Simon & Schuster, 1999) — согласие как актив

Воронка, контент, lifecycle

- [HubSpot lifecycle stages — Pedowitz Group](https://www.pedowitzgroup.com/blog/hubspot-lifecycle-stages-blog)
- [Nurture leads through TOFU/MOFU/BOFU — Squad4](https://www.squad4.io/blog/nurture-leads-b2b-sales-funnel-tofu-mofu)
- [Content Marketing Funnel Strategy: 2026 Framework — SEOAuthori](https://www.seoauthori.com/en/blog/content-marketing-funnel-2026)
- [4S behaviors / non-linear journeys — Passionfruit on Think with Google / BCG 2025](https://www.getpassionfruit.com/blog/how-to-build-a-content-strategy-that-works-across-all-four-buyer-behaviors)
- [B2B buyer journey in AI search — CONTADU](https://contadu.com/b2b-buyer-journey-ai-search/)
- [Buyer-journey SEO 2026 — BusySeed](https://busyseed.com/building-an-seo-strategy-for-every-stage-of-the-buyer-journey-in-2026)

Loyalty sequences

- [Welcome email sequence (5 emails / 10 days) — Fayedtion](https://fayedtion.com/welcome-email-sequence/)
- [Welcome Email Sequence Guide — EmailCloud](https://emailcloud.com/guides/welcome-email-sequence/)
- [Permission Marketing Explained — MMS](https://mmsvegas.com/library/permission-marketing-explained/)

Комплаенс

- [CAN-SPAM Act: A Compliance Guide for Business — FTC](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
- [TCPA text messages 2026 — ActiveProspect](https://activeprospect.com/blog/tcpa-text-messages/)
- [SMS lead gen: TCPA vs CAN-SPAM — LeadCompliant](https://leadcompliant.com/articles/sms-compliance/best-practices-for-sms-lead-gen-compliance-tcpa-can-spam)
- [Advertising and Marketing — FTC](https://www.ftc.gov/business-guidance/advertising-marketing)
- [16 CFR Part 255 Endorsement Guides](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-255)

Конкурентная карта

- [AI Lead Generation 2026 — Tested.media](https://tested.media/ai-lead-generation/)
- [Best Demand Generation Tools 2026 — AI-Led Growth](https://ailedgrowth.com/learn/best-demand-generation-tools-2026)
- [Jasper vs Copy.ai vs HubSpot AI 2026 — FastStrat](https://faststrat.ai/jasper-vs-copyai-vs-hubspot-ai-2026/)
- [AI Agents for Marketing 2026 — Mastra](https://mastra.ai/articles/ai-agents-for-marketing)
- Внутренние документы продукта 1: `docs/marketing/01-market-analysis-saas.md`, `docs/marketing/02-process-cost-risks-usp.md`
