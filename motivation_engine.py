"""
Движок расчёта мотивации.
Чистая логика без UI: правила (пороги, коэффициенты, оклады) описываются словарями,
которые хранятся в БД и редактируются в интерфейсе.
"""

from copy import deepcopy

ROLES = [
    "Операционный директор",
    "Андеррайтер",
    "Старший андеррайтер",
    "Региональный представитель",
    "Менеджер по продажам (МОП)",
    "Коммерческий директор",
]


def _rows(*triples):
    """(от, до, значение, комментарий) -> список строк шкалы. до=None -> без верхней границы."""
    out = []
    for t in triples:
        a, b, v = t[0], t[1], t[2]
        note = t[3] if len(t) > 3 else ""
        out.append({"from": a, "to": b, "value": v, "comment": note})
    return out


def _p(key, label, value, unit=""):
    return {"key": key, "label": label, "value": value, "unit": unit}


def _pen(key, label, amount):
    return {"key": key, "label": label, "amount": amount}


def _inp(key, label, unit, default=0.0):
    return {"key": key, "label": label, "unit": unit, "default": default}


DEFAULT_RULES = {
    # ------------------------------------------------------------------ ОД
    "Операционный директор": {
        "formula": "premium",
        "params": [
            _p("base_salary", "Базовая часть оклада", 90000, "₽"),
            _p("disc_salary", "Дисциплинарная часть оклада", 10000, "₽"),
            _p("base_premium", "Базовая премия", 40000, "₽"),
            _p("premium_indexation", "Индексация премии по портфелю (1 — вкл, 0 — выкл)", 1, ""),
            _p("sla_request_limit", "SLA: проверка заявки, не более", 2, "ч"),
            _p("sla_auto_limit", "SLA: согласование авто, не более", 2, "ч"),
            _p("sla_overdue_limit", "SLA: просроченных мероприятий, не более", 5, "%"),
        ],
        "penalties": [
            _pen("late", "Опоздание без уважительной причины (более 15 мин)", 2000),
            _pen("task", "Неисполнение письменного поручения собственника в срок", 3000),
            _pen("report", "Непредоставление отчёта в срок", 2000),
            _pen("complaint", "Подтверждённая жалоба смежного отдела", 3000),
        ],
        "inputs": [
            _inp("contracts", "Активных договоров в департаменте", "шт", 450),
            _inp("yellow_pct", "Доля жёлтой зоны", "%", 22),
            _inp("red_pct", "Доля красной зоны", "%", 5),
            _inp("avg_request_h", "Ср. время проверки заявки", "ч", 2),
            _inp("avg_auto_h", "Ср. время согласования автомобиля", "ч", 2),
            _inp("overdue_events_pct", "Просроченных мероприятий", "%", 3),
            _inp("lost_cars", "Потерянных авто", "шт", 0),
        ],
        "coeffs": [
            {"key": "k1", "label": "К₁ — жёлтая зона", "input": "yellow_pct",
             "rows": _rows((None, 15, 0.6), (15, 20, 0.8), (20, 25, 1.2), (25, None, 1.0))},
            {"key": "k2", "label": "К₂ — красная зона", "input": "red_pct",
             "rows": _rows((None, 4, 1.1), (4, 7, 1.0), (7, 10, 0.8), (10, None, 0.5))},
            {"key": "k3", "label": "К₃ — качество работы (SLA)", "input": "__sla_violations",
             "rows": _rows((0, 1, 1.2), (1, 2, 0.9), (2, None, 0.7))},
            {"key": "k4", "label": "К₄ — потерянные авто", "input": "lost_cars",
             "rows": _rows((0, 1, 1.0), (1, 2, 0.3), (2, None, 0.0))},
        ],
        "zero_if": [],
        "percent_scale": [],
    },
    # -------------------------------------------------------- Андеррайтер
    "Андеррайтер": {
        "formula": "premium",
        "params": [
            _p("base_salary", "Базовая часть оклада", 45000, "₽"),
            _p("disc_salary", "Дисциплинарная часть оклада", 15000, "₽"),
            _p("base_premium", "Базовая премия", 35000, "₽"),
        ],
        "penalties": [
            _pen("req_time", "Проверка заявки клиента > 2 часов", 3000),
            _pen("auto_time", "Согласование автомобиля > 2 часов", 3000),
            _pen("crm", "Неполное заполнение карточки в CRM", 1000),
            _pen("ppk", "Пропуск контрольной точки постзапускного контроля (ПТС, ключи, ОСАГО)", 2000),
            _pen("problem", "Договор в проблемном листе без мероприятий / просрочены мероприятия", 2000),
        ],
        "inputs": [
            _inp("yellow_pct", "Доля жёлтой зоны", "%", 22),
            _inp("red_pct", "Доля красной зоны", "%", 5),
            _inp("contracts", "Активных договоров в портфеле", "шт", 150),
            _inp("sb_share_pct", "Доля договоров, переданных в СБ", "%", 2),
            _inp("lost_cars", "Потерянных авто", "шт", 0),
        ],
        "coeffs": [
            {"key": "k1", "label": "К₁ — жёлтая зона", "input": "yellow_pct",
             "rows": _rows((None, 15, 0.6), (15, 20, 0.8), (20, 25, 1.2), (25, None, 1.0))},
            {"key": "k2", "label": "К₂ — красная зона", "input": "red_pct",
             "rows": _rows((None, 4, 1.1), (4, 7, 1.0), (7, 10, 0.8), (10, None, 0.5))},
            {"key": "k3", "label": "К₃ — объём портфеля", "input": "contracts",
             "rows": _rows((None, 150, 1.0), (150, 170, 1.15), (170, None, 1.15))},
            {"key": "k4", "label": "К₄ — передача в СБ", "input": "sb_share_pct",
             "rows": _rows((None, 3, 1.0), (3, 4.5, 0.9), (4.5, 6, 0.8), (6, None, 0.5))},
        ],
        "zero_if": [{"input": "lost_cars", "threshold": 1,
                     "label": "Есть потерянное авто"}],
        "percent_scale": [],
    },
    # ----------------------------------------------- Старший андеррайтер
    "Старший андеррайтер": {
        "formula": "premium_duty",
        "params": [
            _p("base_salary", "Базовая часть оклада", 50000, "₽"),
            _p("disc_salary", "Дисциплинарная часть оклада", 15000, "₽"),
            _p("base_premium", "Базовая премия (личный портфель)", 35000, "₽"),
            _p("duty_allowance", "Надбавка за дежурство", 15000, "₽"),
        ],
        "penalties": [
            _pen("req_time", "Проверка заявки клиента > 2 часов", 3000),
            _pen("auto_time", "Согласование автомобиля > 2 часов", 3000),
            _pen("crm", "Неполное заполнение карточки в CRM", 1000),
            _pen("ppk", "Пропуск контрольной точки постзапускного контроля (ПТС, ключи, ОСАГО)", 2000),
            _pen("problem", "Договор в проблемном листе без мероприятий / просрочены мероприятия", 2000),
        ],
        "inputs": [
            _inp("yellow_pct", "Доля жёлтой зоны (личный портфель)", "%", 22),
            _inp("red_pct", "Доля красной зоны (личный портфель)", "%", 5),
            _inp("contracts", "Активных договоров в портфеле", "шт", 160),
            _inp("sb_share_pct", "Доля договоров, переданных в СБ", "%", 2),
            _inp("lost_cars", "Потерянных авто (лично)", "шт", 0),
            _inp("dept_red_pct", "Красная зона по отделу", "%", 5),
            _inp("dept_lost_cars", "Потерянных авто по отделу", "шт", 0),
        ],
        "coeffs": [
            {"key": "k1", "label": "К₁ — жёлтая зона", "input": "yellow_pct",
             "rows": _rows((None, 15, 0.6), (15, 20, 0.8), (20, 25, 1.2), (25, None, 1.0))},
            {"key": "k2", "label": "К₂ — красная зона", "input": "red_pct",
             "rows": _rows((None, 4, 1.1), (4, 7, 1.0), (7, 10, 0.8), (10, None, 0.5))},
            {"key": "k3", "label": "К₃ — объём портфеля", "input": "contracts",
             "rows": _rows((None, 150, 1.0), (150, 170, 1.15), (170, None, 1.15))},
            {"key": "k4", "label": "К₄ — передача в СБ", "input": "sb_share_pct",
             "rows": _rows((None, 3, 1.0), (3, 4.5, 0.9), (4.5, 6, 0.8), (6, None, 0.5))},
            {"key": "k5", "label": "К₅ — командный (отдел)", "input": "dept_red_pct",
             "rows": _rows((None, 7, 1.0), (7, 9, 0.8), (9, None, 0.5))},
        ],
        "zero_if": [{"input": "lost_cars", "threshold": 1,
                     "label": "Есть потерянное авто"}],
        "percent_scale": [],
        "duty_zero_if": [{"input": "dept_lost_cars", "threshold": 1,
                          "label": "Есть потерянное авто по отделу"}],
    },
    # ------------------------------------------ Региональный представитель
    "Региональный представитель": {
        "formula": "trip",
        "params": [
            _p("base_salary", "Базовая часть оклада", 50000, "₽"),
            _p("disc_salary", "Дисциплинарная часть оклада", 20000, "₽"),
            _p("trip_rate", "Оплата за выезд", 2500, "₽"),
            _p("fuel_per_100", "Расход топлива на 100 км", 10, "л"),
            _p("fuel_price", "Цена топлива (АИ-95)", 65, "₽/л"),
            _p("amort_rate", "Амортизация за км", 2.5, "₽/км"),
            _p("wash", "Мойка (за месяц при видеоотчёте)", 2000, "₽"),
            _p("brand_back", "Брендирование — заднее стекло", 2500, "₽"),
            _p("brand_side", "Брендирование — бока", 5000, "₽"),
        ],
        "penalties": [
            _pen("refuse", "Отказ от выезда без уважительной причины", 10000),
            _pen("late", "Опоздание на сделку более чем на 1 час", 10000),
            _pen("report_late", "Несвоевременная загрузка фото/видео отчёта (>24 ч)", 5000),
            _pen("docs_late", "Несвоевременная отправка оригиналов документов", 5000),
            _pen("docs_missing", "Отсутствие документа в пакете сделки (частичное)", 8000),
            _pen("docs_none", "Полное отсутствие документов в пакете сделки", 15000),
            _pen("client_complaint", "Жалоба клиента на представителя", 5000),
            _pen("beacon_found", "Обнаружение маяка клиентом", 10000),
            _pen("beacon_missing", "Не установлен маяк на авто при выезде на сделку", 15000),
        ],
        "inputs": [
            _inp("trips", "Количество выездов", "шт", 10),
            _inp("km", "Пробег за месяц", "км", 1500),
            _inp("fuel_price", "Цена топлива за месяц", "₽/л", 65),
            _inp("wash", "Мойка (1 — да, 0 — нет)", "0/1", 1),
            _inp("brand_back", "Брендирование: заднее стекло (0/1)", "0/1", 1),
            _inp("brand_side", "Брендирование: бока (0/1)", "0/1", 0),
        ],
        "coeffs": [],
        "zero_if": [],
        "percent_scale": [],
    },
    # ---------------------------------------------------- МОП
    "Менеджер по продажам (МОП)": {
        "formula": "percent",
        "params": [
            _p("base_salary", "Оклад (фиксированная часть)", 35000, "₽"),
            _p("disc_salary", "Дисциплинарный бонус", 15000, "₽"),
        ],
        "penalties": [
            _pen("crm", "Нарушение CRM-дисциплины / SLA", 3000),
            _pen("sb30", "Договор ушёл в СБ в первые 30 дней", 15000),
        ],
        "inputs": [
            _inp("volume", "Объём финансирования (факт)", "₽", 7000000),
            _inp("plan", "Личный план на месяц", "₽", 7000000),
            _inp("conv_incoming_pct", "Конверсия входящих лидов", "%", 5),
            _inp("conv_target_pct", "Конверсия целевых лидов", "%", 25),
            _inp("team_plan_pct", "Выполнение плана отдела", "%", 100),
            _inp("avg_rate_pct", "Средняя ставка по договорам", "%", 0.153),
            _inp("reviews_share_pct", "Доля отзывов с Авито", "%", 65),
        ],
        "coeffs": [
            {"key": "k1", "label": "К₁ — конверсия (взвеш.)",
             "parts": [
                 {"input": "conv_incoming_pct", "weight": 0.4,
                  "rows": _rows((None, 15, 0.7), (15, 20, 0.9), (20, 25, 1.0), (25, 30, 1.1), (30, None, 1.2))},
                 {"input": "conv_target_pct", "weight": 0.6,
                  "rows": _rows((None, 15, 0.7), (15, 20, 0.9), (20, 25, 1.0), (25, 30, 1.1), (30, None, 1.2))},
             ]},
            {"key": "k2", "label": "К₂ — командный (план отдела)", "input": "team_plan_pct",
             "rows": _rows((None, 70, 0.8), (70, 90, 0.9), (90, 100, 1.0), (100, None, 1.1))},
            {"key": "k3", "label": "К₃ — средняя ставка", "input": "avg_rate_pct",
             "rows": _rows((None, 0.148, 0.7), (0.148, 0.152, 0.85), (0.152, 0.156, 1.0), (0.156, None, 1.15))},
            {"key": "k4", "label": "К₄ — отзывы (Авито и др.)", "input": "reviews_share_pct",
             "rows": _rows((None, 60, 0.9), (60, None, 1.0))},
        ],
        "zero_if": [],
        "percent_scale": _rows(
            (None, 70, 0.0, "порог не пройден"),
            (70, 90, 0.45, "пониженная ставка"),
            (90, 100, 0.55, "базовая ставка"),
            (100, 110, 0.65, "целевая ставка"),
            (110, None, 0.70, "повышенная ставка"),
        ),
    },
    # ------------------------------------------- Коммерческий директор
    "Коммерческий директор": {
        "formula": "percent",
        "params": [
            _p("base_salary", "Оклад (фиксированная часть)", 100000, "₽"),
            _p("disc_salary", "Дисциплинарная часть (если есть)", 0, "₽"),
        ],
        "penalties": [],
        "inputs": [
            _inp("volume", "Объём финансирования департамента", "₽", 30000000),
            _inp("plan", "План департамента", "₽", 30000000),
            _inp("conv_pct", "Конверсия департамента (лид → договор)", "%", 17),
            _inp("avg_rate_pct", "Средняя ставка по договорам", "%", 0.150),
            _inp("cac", "CAC (факт), ₽ на договор", "₽", 20000),
            _inp("plan_cac", "Плановый CAC, ₽ на договор", "₽", 20000),
            _inp("neg_reviews", "Негативных отзывов (по существу)", "шт", 0),
            _inp("spetz", "Спецпремии за месяц", "₽", 0),
        ],
        "coeffs": [
            {"key": "k1", "label": "К₁ — конверсия департамента", "input": "conv_pct",
             "rows": _rows((None, 10, 0.7), (10, 15, 0.85), (15, 20, 1.0), (20, 25, 1.1), (25, None, 1.2))},
            {"key": "k2", "label": "К₂ — средняя ставка", "input": "avg_rate_pct",
             "rows": _rows((None, 0.146, 0.8), (0.146, 0.148, 0.9), (0.148, 0.1501, 1.0), (0.1501, None, 1.2))},
            {"key": "k3", "label": "К₃ — CAC (отклонение от плана, %)", "input": "__cac_dev",
             "rows": _rows((None, -20, 1.2), (-20, -10, 1.1), (-10, 10, 1.0), (10, 20, 0.85), (20, None, 0.7))},
            {"key": "k4", "label": "К₄ — отзывы клиентов", "input": "neg_reviews",
             "rows": _rows((0, 1, 1.0), (1, 2, 0.7), (2, 3, 0.5), (3, None, 0.0))},
        ],
        "zero_if": [],
        "percent_scale": _rows(
            (None, 70, 0.0, "порог не пройден"),
            (70, 90, 0.40, "пониженная ставка"),
            (90, 100, 0.55, "базовая ставка"),
            (100, 110, 0.65, "целевая ставка"),
            (110, None, 0.75, "повышенная ставка"),
        ),
    },
}

INPUT_HELP = {
    "yellow_pct": "Доля портфеля в жёлтой зоне (ОПЗ 4–25 дней)",
    "red_pct": "Доля портфеля в красной зоне (по триггерам)",
    "sb_share_pct": "Доля договоров, переданных в СБ",
    "contracts": "Количество активных договоров",
    "lost_cars": "Авто, не возвращённые в управляемую зону за 1 месяц",
    "avg_rate_pct": "Средневзвешенная ставка (например 0,153%)",
    "cac": "Маркетинговые расходы / количество договоров",
}


def default_rules(role):
    return deepcopy(DEFAULT_RULES[role])


def param_value(rules, key, default=0.0):
    for p in rules.get("params", []):
        if p["key"] == key:
            return p["value"]
    return default


def lookup(rows, x):
    """Находит значение по шкале. from включительно, to — не включая."""
    if not rows:
        return 1.0
    x = float(x or 0)
    for r in rows:
        lo, hi = r.get("from"), r.get("to")
        if (lo is None or x >= lo) and (hi is None or x < hi):
            return float(r["value"])
    return float(rows[-1]["value"])


def _sla_violations(rules, inp):
    n = 0
    if float(inp.get("avg_request_h") or 0) > param_value(rules, "sla_request_limit", 2):
        n += 1
    if float(inp.get("avg_auto_h") or 0) > param_value(rules, "sla_auto_limit", 2):
        n += 1
    if float(inp.get("overdue_events_pct") or 0) > param_value(rules, "sla_overdue_limit", 5):
        n += 1
    return n


def _cac_dev(inp):
    cac = float(inp.get("cac") or 0)
    plan = float(inp.get("plan_cac") or 0)
    if plan <= 0:
        return 0.0
    return (cac / plan - 1) * 100


def _coeff_raw(rules, c, inp):
    if "parts" in c:
        return None
    key = c.get("input")
    if key == "__sla_violations":
        return _sla_violations(rules, inp)
    if key == "__cac_dev":
        return _cac_dev(inp)
    return float(inp.get(key) or 0)


def compute(role, rules, inp):
    """Возвращает подробный расчёт для одного сотрудника за месяц."""
    base = param_value(rules, "base_salary")
    disc = param_value(rules, "disc_salary")

    # --- штрафы / дисциплинарные удержания
    pen_total = 0.0
    pen_lines = []
    for p in rules.get("penalties", []):
        cnt = float(inp.get(f"pen_{p['key']}") or 0)
        if cnt:
            amount = cnt * float(p["amount"])
            pen_total += amount
            pen_lines.append((f"{p['label']} × {int(cnt)}", -amount))

    disc_after = max(0.0, disc - pen_total)
    capped = min(pen_total, disc)

    # --- коэффициенты
    coeffs = {}
    for c in rules.get("coeffs", []):
        if "parts" in c:
            val = 0.0
            x = None
            for part in c["parts"]:
                px = float(inp.get(part["input"]) or 0)
                val += lookup(part["rows"], px) * float(part.get("weight", 1))
        else:
            x = _coeff_raw(rules, c, inp)
            val = lookup(c["rows"], x)
        coeffs[c["key"]] = {"label": c["label"], "value": round(val, 4), "input": x}

    prod = 1.0
    for c in coeffs.values():
        prod *= c["value"]

    # --- стоп-факторы
    zeroed = None
    for z in rules.get("zero_if", []):
        if float(inp.get(z["input"]) or 0) >= float(z.get("threshold", 1)):
            zeroed = z.get("label", "стоп-фактор")
            prod = 0.0

    formula = rules.get("formula", "premium")
    variable = 0.0
    var_label = "Переменная часть"
    base_var = 0.0
    plan_pct = None
    pct_rate = None
    extras = 0.0
    lines = []

    if formula in ("premium", "premium_duty"):
        base_var = param_value(rules, "base_premium")
        if role == "Операционный директор" and param_value(rules, "premium_indexation", 0):
            contracts = float(inp.get("contracts") or 0)
            extra_steps = int(max(0, contracts - 400) // 100)
            base_var += 4000 * extra_steps
        variable = base_var * prod
        var_label = "Переменная часть (личный портфель)"
        lines.append(("Базовая премия", base_var))
        for c in coeffs.values():
            lines.append((c["label"], c["value"]))
        if formula == "premium_duty":
            duty = param_value(rules, "duty_allowance")
            duty_prod = 1.0
            if "k5" in coeffs:
                duty_prod = coeffs["k5"]["value"]
            for z in rules.get("duty_zero_if", []):
                if float(inp.get(z["input"]) or 0) >= float(z.get("threshold", 1)):
                    duty_prod = 0.0
            extras = duty * duty_prod
            lines.append(("Надбавка за дежурство (база)", duty))
            lines.append(("Надбавка за дежурство к выплате", extras))

    elif formula == "percent":
        volume = float(inp.get("volume") or 0)
        plan = float(inp.get("plan") or 0)
        plan_pct = (volume / plan * 100) if plan > 0 else 0.0
        pct_rate = lookup(rules.get("percent_scale", []), plan_pct)
        base_var = volume * pct_rate / 100.0
        variable = base_var * prod
        var_label = "Переменная часть (процент от объёма)"
        lines.append(("Выполнение плана", round(plan_pct, 1)))
        lines.append(("Ставка, % от объёма", pct_rate))
        lines.append(("База переменной части", base_var))
        for c in coeffs.values():
            lines.append((c["label"], c["value"]))
        if role == "Коммерческий директор":
            extras = float(inp.get("spetz") or 0)
            lines.append(("Спецпремии", extras))

    elif formula == "trip":
        trips = float(inp.get("trips") or 0)
        km = float(inp.get("km") or 0)
        fuel_price = float(inp.get("fuel_price") or param_value(rules, "fuel_price") or 0)
        fuel = km / 100.0 * param_value(rules, "fuel_per_100") * fuel_price
        amort = km * param_value(rules, "amort_rate")
        wash = param_value(rules, "wash") * (1 if float(inp.get("wash") or 0) >= 1 else 0)
        brand_back = param_value(rules, "brand_back") * (1 if float(inp.get("brand_back") or 0) >= 1 else 0)
        brand_side = param_value(rules, "brand_side") * (1 if float(inp.get("brand_side") or 0) >= 1 else 0)
        trips_pay = trips * param_value(rules, "trip_rate")
        variable = trips_pay
        extras = fuel + amort + wash + brand_back + brand_side
        var_label = "Бонус за выезды"
        lines.append((f"Выезды × {param_value(rules, 'trip_rate'):,.0f} ₽", trips_pay))
        lines.append(("ГСМ", fuel))
        lines.append(("Амортизация", amort))
        lines.append(("Мойка", wash))
        lines.append(("Брендирование: заднее стекло", brand_back))
        lines.append(("Брендирование: бока", brand_side))

    total = base + disc_after + variable + extras

    return {
        "base": round(base, 2),
        "disc_full": round(disc, 2),
        "penalties": round(pen_total, 2),
        "penalties_capped": round(capped, 2),
        "disc_after": round(disc_after, 2),
        "coefficients": coeffs,
        "base_variable": round(base_var, 2),
        "variable": round(variable, 2),
        "extras": round(extras, 2),
        "total": round(total, 2),
        "plan_pct": round(plan_pct, 2) if plan_pct is not None else None,
        "pct_rate": pct_rate,
        "zeroed": zeroed,
        "lines": lines,
        "penalty_lines": pen_lines,
        "var_label": var_label,
    }
