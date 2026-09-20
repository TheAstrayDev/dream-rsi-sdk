<p align="center">
  <img src="assets/banner.svg" alt="Dream-RSI SDK Alpha — независимый SDK: Explore. Record. Replay. Improve." width="100%">
</p>

<p align="center">
  <a href="https://github.com/TheAstrayDev/dream-rsi-sdk/actions/workflows/ci.yml"><img src="https://github.com/TheAstrayDev/dream-rsi-sdk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/status-alpha-eebc73?style=flat-square" alt="Alpha">
  <img src="https://img.shields.io/badge/Python-3.11%2B-75e0be?style=flat-square" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/runtime_dependencies-0-75e0be?style=flat-square" alt="Без обязательных runtime-зависимостей">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-c3d0d4?style=flat-square" alt="Apache 2.0"></a>
</p>

<p align="center"><strong>Ваш агент. Ваша оценка. Стратегия поиска, которая учится на истории попыток.</strong></p>
<p align="center">
  <a href="#quickstart">Быстрый старт</a> ·
  <a href="#architecture">Как устроено</a> ·
  <a href="#comparison">Сравнение с исследованием</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="docs/integration.md">Интеграция</a>
</p>

> [!IMPORTANT]
> **Это независимый, неофициальный проект. Не продукт Google.**
>
> Я — [TheAstrayDev](https://github.com/TheAstrayDev), независимый разработчик. Я не сотрудник
> Google или Google DeepMind. Этот репозиторий — моя личная исследовательская инициатива,
> **не коммерческая разработка компании Google**, не официальный SDK и не проект,
> поддерживаемый или одобренный авторами исследования.
>
> Я попытался собрать Dream-RSI SDK по доступной открытой информации: статье, сайту
> и материалам авторов. Планирую развивать его дальше, проверять идеи на практике
> и постепенно сокращать разрыв между этой реализацией и описанным методом.

## Зачем нужен этот проект

**Dream-RSI SDK** — небольшой Python-слой для управления поиском решений поверх существующего
ИИ-агента. Вы подключаете генерацию кандидатов и оценку результата; библиотека организует
попытки, сохраняет дерево поиска и сравнивает стратегии на записанной истории.

Цель — сделать такое управление поиском простым для встраивания в разные архитектуры:
от обычной функции до агента с памятью, инструментами и отдельной рабочей средой.
Ядро не зависит от провайдера модели и не требует API-ключей само по себе.

**Alpha означает рабочую основу, а не полное воспроизведение исследования.** Сейчас реализованы
дерево, строгий replay, адаптеры и цикл выбора политик. Главный упрощённый участок —
оптимизатор: он перебирает параметры встроенных стратегий, а не пишет новый код при помощи LLM.

| Основа | Состояние |
| :--- | :--- |
| Язык и зависимости | Python 3.11+ · 0 обязательных сторонних зависимостей |
| Подключение | Sync/async функции · адаптер состояния · полный протокол агента |
| Проверка качества | 33 теста · Ruff · Pyright · сборка и установка wheel |
| Версия | `0.1.0a1` · API ещё может изменяться |
| Дистрибуция | Из исходников или GitHub; публикация на PyPI пока не выполнена |

<a id="architecture"></a>
## Как устроен цикл

Идея Dream-RSI — использовать прошлый поиск как среду для проверки новых стратегий.
Реальные запуски создают историю; replay читает записанные переходы; выбранная политика
управляет следующим запуском. Модель агента и оценщик при этом остаются прежними.
См. [официальное объяснение метода](https://dream-rsi.com/#method).

<p align="center">
  <img src="assets/architecture.svg" alt="Три стадии: online-поиск с агентом и оценщиком → записанные replay-миры → сравнение и выбор политики → следующий online-запуск. Разработчик кода политик на LLM, независимая валидация, долговременные кампании и песочница запланированы." width="100%">
</p>

*Собственная схема SDK, сопоставленная с Figure 1 и разделом 3
[статьи Dream-RSI](https://arxiv.org/html/2609.14858v1#S3).
Это не официальная иллюстрация Google. Зелёным обозначены работающие компоненты,
пунктиром — запланированные.*

1. **Online explore.** Политика выбирает узлы; агент создаёт кандидатов, оценщик возвращает
   результат. Попытки выполняются с ограничениями и записываются в `DiscoveryTree`.
2. **Replay worlds.** Завершённое дерево фиксируется и становится `ReplayWorld`.
   Повторная оценка политики не вызывает агента и оценщик.
3. **Dream & select.** Текущая политика и кандидаты проходят один набор миров.
   `PromotionGate` решает, принимать ли новую политику. Следующий запуск расширяет историю.

Replay видит только записанные результаты. Он не умеет предсказывать, что случилось бы
в неизученной ветви. Рост replay-оценки на той же истории не гарантирует роста качества
следующего реального запуска.

<a id="quickstart"></a>
## Установка

Нужны **Python 3.11+** и Git. Рекомендуется отдельное окружение.

```bash
git clone https://github.com/TheAstrayDev/dream-rsi-sdk.git
cd dream-rsi-sdk
python -m venv .venv
```

Активируйте окружение:

```bash
# Linux / macOS
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Затем установите SDK:

```bash
python -m pip install -e .
python examples/01_toy_optimization.py
```

Либо установите прямо из репозитория без рабочего checkout:

```bash
python -m pip install "git+https://github.com/TheAstrayDev/dream-rsi-sdk.git@main"
```

Последняя команда берёт текущую ветку `main`. Для воспроизводимой установки замените
`main` на конкретный commit SHA. Имя Python-пакета и импорта — **`dreamrsi`**.

## Первый запуск: две функции

```python
from dreamrsi import Budget, DreamRSI

def agent(task):
    # Здесь может быть вызов вашей модели или существующего агента.
    return task.upper()

def evaluate(answer):
    return float(len(answer))

rsi = DreamRSI(agent=agent, evaluator=evaluate, budget=Budget(model_calls=4))
result = rsi.run_sync("hello")

print(result.best)                 # HELLO
print(result.best_score)           # 5.0
print(result.costs.model_calls)    # 4
```

Это пример подключения, а не демонстрация роста качества: детерминированная функция
возвращает один ответ. В простом режиме каждая попытка получает **исходную задачу**.
Для уточнения предыдущего результата используйте адаптер состояния.

## Улучшение кандидата по шагам

```python
from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter
from dreamrsi.policies import DepthFirstPolicy

def refine(state, context):
    return {"x": state["x"] * 0.5}

rsi = DreamRSI(
    adapter=FunctionalAgentAdapter(refine),
    evaluator=lambda candidate: -(candidate["x"] ** 2),
    policy=DepthFirstPolicy(),
    budget=Budget(model_calls=6),
)

result = rsi.run_sync({"x": 8.0})
print(result.best)        # {'x': 0.125}
print(result.best_score)  # -0.015625
```

Результат `refine` становится состоянием следующей попытки в этой ветви.
**Большая оценка всегда лучше**; для минимизации здесь используется `-x²`.

## Цикл поиска и replay

```python
import asyncio

from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter

async def main():
    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(lambda state: {"x": state["x"] * 0.5}),
        evaluator=lambda candidate: -(candidate["x"] ** 2),
        budget=Budget(model_calls=20, max_parallelism=4, max_depth=8),
    )
    result = await rsi.improve({"x": 8.0}, rounds=3)
    print("Best:", result.best)
    print("Worlds:", len(result.worlds))
    print("Promotions:", result.metrics["policy_promotions"])

asyncio.run(main())
```

Каждый вызов `run` внутри `improve` имеет свой бюджет: пример разрешает до **60 вызовов**
`propose` за три запуска. Отсутствие принятой новой политики — допустимый результат.
В уже работающем event loop вызывайте `await rsi.run(...)` / `await rsi.improve(...)`
непосредственно, без `asyncio.run` или `run_sync`.

## Встраивание в свою архитектуру

| Уровень | Интерфейс | Подходит для |
| :--- | :--- | :--- |
| Минимальный | `agent(task)` + `evaluator(candidate)` | Независимых попыток и существующего API модели |
| Состояние | `FunctionalAgentAdapter(step)` | Уточнения ответа, кода, параметров или плана |
| Полный контроль | `AgentAdapter` | Собственной памяти, исполнения инструментов и снимков среды |

Полный адаптер не требует наследования. Достаточно реализовать пять методов:

```text
initial_state(task)
    └─ propose(state, context)
          └─ execute(proposal, state, context)
                └─ observe(execution, state)
                      ├─ evaluator(observation, context)
                      └─ next_state(observation, state)
```

Методы поддерживают sync/async. Клиент модели храните **в адаптере**, а состояние —
как копируемый снимок данных. Независимые ветви не должны изменять общую рабочую среду.
Для внешних файлов или процессов изоляцию обеспечивает ваш адаптер.

[Полное руководство: состояние, context, бюджеты и экспорт →](docs/integration.md)

### Основные точки расширения

| Компонент | Назначение | Готовая реализация |
| :--- | :--- | :--- |
| Agent | Создание и исполнение кандидатов | Два функциональных адаптера; ваш объект по протоколу |
| Evaluator | Оценка результата | Callable, Numeric, Composite |
| ExplorationPolicy | Какие ветви продолжать | Balanced, Greedy, BreadthFirst, DepthFirst, Random, EpsilonGreedy, FixedParallel |
| PolicyOptimizer | Кандидаты стратегий | DeterministicPolicyOptimizer, ParameterSearchOptimizer |
| PromotionGate | Условия принятия политики | ReplayOnlyGate, HoldoutGate, CompositeGate |
| Store | Запуски, узлы, события и версии | InMemoryStore |

<a id="comparison"></a>
## Исследование Dream-RSI и этот SDK

Сравнение опирается на [раздел 3](https://arxiv.org/html/2609.14858v1#S3),
[приложение B.2](https://arxiv.org/html/2609.14858v1#A2.SS2) и
[сайт авторов](https://dream-rsi.com/). Это сопоставление **описанного метода с локальным кодом**,
а не аудит совместимости с официальной реализацией. На 20 сентября 2026 года
[официальный репозиторий](https://github.com/zhengkid/Dream-RSI) сообщает о подготовке кода к выпуску.

**✓ Есть** — работает и проверяется. **◐ Частично** — есть явное упрощение. **○ План** — не реализовано.

| В оригинальном методе | Здесь | Реализация / отличие |
| :--- | :---: | :--- |
| Фиксированные discovery-agent и evaluator | ✓ | Независимые адаптеры; SDK не обновляет веса модели |
| Дерево попыток с состояниями и результатами | ✓ | DiscoveryTree, снимки Python-данных; внешняя среда — ответственность адаптера |
| Выбор root / leaf и группировка попыток | ✓ | Единый контракт решений, проверка допустимости, параллельный запуск |
| Replay записанных переходов | ✓ | StrictReplay; скрытые результаты не раскрываются заранее |
| Растущий пул исторических миров | ◐ | Накапливается в памяти экземпляра; нет восстановления после перезапуска |
| Политика использует раскрытые наблюдения | ◐ | Пока доступны сводки frontier; нет полного контекста наблюдений и диагностики |
| Оценка качества, работы и параллелизма | ✓ | Формула раздела 3, настраиваемые β₁ и β₂; не все метрики приложения B.2 |
| Последовательное редактирование кода политики LLM-агентом | ○ | Сейчас только перебор параметров; генерация программ запланирована |
| Сравнение с текущей политикой и повторный online-запуск | ✓ | Improve-цикл и evidence gate на одном пуле миров |
| Эксперименты: алгоритмы, математика, GPU-ядра | ○ | Численный пример и тесты SDK; результаты статьи не воспроизведены |

Отдельно от сравнительной таблицы: `HoldoutGate` и `SandboxExecutor` — точки развития
этой библиотеки. Наличие gate или протокола не означает готовую независимую валидацию
или действующую песочницу.

## Ограничения Alpha

- **Нет обещания универсального ускорения.** Возможность подключить архитектуру не доказывает
  эффективность метода для неё. Нужны управляемое состояние, качественная оценка и измерения.
- **Нет обучения весов и генератора кода политик.** Текущий оптимизатор меняет параметры;
  он не воспроизводит весь процесс разработки стратегий из статьи.
- **Бюджет применяется к одному run.** Счётчики отражают вызовы адаптера/оценщика,
  а не скрытые обращения к API внутри них. Денежный бюджет пока отклоняется явно.
- **Хранилище в памяти.** JSON-экспорт сохраняет совместимые данные; произвольные клиентские
  объекты и полный перезапуск кампаний не поддерживаются.
- **Отмена зависит от интеграции.** SDK отменяет async-ожидание, но не может принудительно
  остановить уже работающий синхронный поток или внешний сервис.
- **Независимая проверка не автоматизирована.** Обучающие replay-оценки не выдаются за holdout.
  Данные для HoldoutGate должен подготовить вызывающий код.

<a id="roadmap"></a>
## Roadmap

Порядок отражает приоритеты, а не обещанные даты релизов. Критерий прогресса — рабочий код
и воспроизводимая проверка, а не количество объявленных интеграций.

| Этап | Результат | Критерий готовности |
| :--- | :--- | :--- |
| **01 · Foundation** ✓ | Адаптеры, дерево, replay, политики, бюджеты, тесты | Рабочие примеры и проверки контрактов |
| **02 · Observable policies** ○ | Полные раскрытые наблюдения, диагностика и исторический контекст | Тесты отсутствия доступа к будущим данным |
| **03 · Reliable campaigns** ○ | Долговременное хранение, возобновление, общие лимиты | Кампания продолжается после перезапуска без потери истории |
| **04 · Evidence before promotion** ○ | Отдельные validation-миры и отчёты | Train и validation разделены; решения воспроизводимы |
| **05 · Dreaming with code** ○ | LLM-разработчик политик и изолированное исполнение | Несколько ревизий с replay-feedback; недопустимый код не запускается в основном процессе |
| **06 · Real integrations** ○ | Примеры с реальными агентами и учёт провайдерских затрат | Публичные сравнения при одинаковых бюджетах и документированных условиях |
| **07 · Stable SDK** ○ | Стабилизация API, версионирование данных, публикация пакета | Проверки совместимости и понятный путь миграции |

Подробный технический план и история исправлений — в [ARCHITECTURE.md](ARCHITECTURE.md).

## Разработка и проверка

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests
python -m pyright
```

Сборка дистрибутива:

```bash
python -m pip install build
python -m build
```

Локально проверены **33 теста**, Ruff, Pyright, сборка и установка wheel на Python 3.14.6.
CI настроен на Python 3.11–3.14 в Linux и Python 3.14 в Windows; актуальное состояние
показывает [вкладка Actions](https://github.com/TheAstrayDev/dream-rsi-sdk/actions).
Тесты не используют платные API и не требуют ключей моделей.

```text
src/dreamrsi/
├── adapters.py     # подключение существующего агента
├── runtime.py      # online-поиск и improve-цикл
├── discovery/      # дерево попыток и снимки
├── replay/         # воспроизведение записанной истории
├── policies/       # семь встроенных стратегий
├── optimization/   # кандидаты стратегий и версии
├── promotion/      # решения по доказательствам
├── evaluation/     # функции оценки и композиция
├── storage/        # in-memory хранилище
├── events/         # события и callbacks
├── models/         # общие структуры данных
└── protocols/      # контракты расширения
```

## Участие

Приветствуются воспроизводимые bug reports, небольшие исправления, предложения по API
и реальные примеры интеграции. Начните с [CONTRIBUTING.md](CONTRIBUTING.md).
Измеренные результаты полезнее общих заявлений об «улучшении интеллекта».

## Источники и авторство

Исследовательская идея принадлежит **Tong Zheng и соавторам** — исследователям Google,
Google DeepMind, University of Maryland и University of Virginia.
Оригинальные материалы:

- [Dream-RSI: Recursive Self-Improvement through Evolving Worlds — arXiv:2609.14858](https://arxiv.org/abs/2609.14858)
- [Официальная страница проекта](https://dream-rsi.com/)
- [Официальный репозиторий zhengkid/Dream-RSI](https://github.com/zhengkid/Dream-RSI)

Автор независимого SDK — **[TheAstrayDev](https://github.com/TheAstrayDev)**.
Пожалуйста, различайте ссылку на исследование и ссылку на эту реализацию.
Логотип и схема в этом репозитории созданы для SDK и не являются символикой Google.

Код распространяется по [Apache License 2.0](LICENSE). Уведомление о независимом
происхождении — [NOTICE](NOTICE). Личный характер инициативы не меняет условия лицензии.

---

<p align="center"><img src="assets/logo.svg" width="48" alt="Логотип независимого Dream-RSI SDK"><br><sub>Built independently. Grounded in recorded experience. Still evolving.</sub></p>
