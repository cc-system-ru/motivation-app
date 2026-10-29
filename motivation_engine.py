"""Расчёт мотивации. Все пороги и ставки берутся из настроек (редактируются в UI)."""

DEFAULTS = {
    "kd": {
        "salary": 100000,
        "base_premium": 50000,
        "plan_scale": [[0, 0.70, 0], [0.70, 0.90, 0.8], [0.90, 1.00, 1.0],
                       [1.00, 1.10, 1.2], [1.10, 99, 1.4]],
    },
    "mop": {
        "salary_l1": 35000,
        "salary_l2": 45000,
        "rate_l1": 0.007,
        "rate_l2": 0.010,
        "plan_scale": [[0, 0.70, 0], [0.70, 0.90, 0.8], [0.90, 1.00, 1.0],
                       [1.00, 1.10, 1.2], [1.10, 99, 1.4]],
        "k4_scale": [[0.3, 99, 1.15], [0.0, 0.3, 1.10],
                     [-0.3, 0.0, 1.0], [-0.6, -0.3, 0.9], [-99, -0.6, 0.8]],
    },
    "od": {
        "salary": 90000,
        "disc_base": 10000,
        "premium_base": 40000,
        "premium_step": 4000,
        "contract_threshold": 400,
        "contract_step": 100,
    },
    "and": {
        "salary": 45000,
        "disc_base": 15000,
        "premium_base": 35000,
        "disc_limit": 15000,
    },
    "and_sr": {
        "salary": 50000,
        "disc_base": 15000,
        "premium_base": 35000,
        "disc_limit": 15000,
        "duty_bonus": 15000,
    },
    "rep": {
        "salary": 50000,
        "disc_base": 20000,
        "visit_rate": 2500,
        "fuel_per_100": 10,
        "fuel_price": 65,
        "amort_rate": 2.5,
        "wash": 2000,
        "brand_rear": 2500,
        "brand_side": 5000,
    },
    "sb": {
        "salary": 20000,
        "premium_base": 30000,
        "seizure_rate": 8000,
        "k1_scale": [[0.90, 2, 1.2], [0.70, 0.90, 1.0], [0.50, 0.70, 0.6], [0, 0.50, 0]],
        "k2_scale": [[0, 5, 1.2], [5, 8, 1.0], [8, 12, 0.7], [12, 999, 0.5]],
        "collect_scale": [[0, 100000, 0.05], [100000, 200000, 0.10], [200000, 10**9, 0.15]],
    },
    "adm": {
        "salary": 45000,
        "premium_base": 15000,
        "smm_bonus": 10000,
        "k1_scale": [[0, 0, 1.0], [1, 1, 0.8], [2, 2, 0.5], [3, 99, 0]],
        "k2_scale": [[0, 0, 1.0], [1, 2, 0.8], [3, 99, 0]],
    },
}

# единые шкалы для андеррайтеров и ОД
COMMON = {
    "k1_yellow": [[0, 0.15, 0.6], [0.15, 0.20, 0.8], [0.20, 0.25, 1.2], [0.25, 1, 1.0]],
    "k2_red": [[0, 0.04, 1.1], [0.04, 0.07, 1.0], [0.07, 0.10, 0.8], [0.10, 1, 0.5]],
    "k3_volume": [[0, 150, 1.0], [150, 10**9, 1.15]],
    "k4_sb": [[0, 0.03, 1.0], [0.03, 0.045, 0.9], [0.045, 0.06, 0.8], [0.06, 1, 0.5]],
    "stop_lost": [[0, 0.5, 1.0], [1, 1.5, 0.3], [2, 99, 0.0]],
    "k3_quality": [[0, 0.5, 1.2], [1, 1.5, 0.9], [2, 99, 0.7]],
    "k5_chief": [[0, 0.06, 1.0], [0.06, 0.09, 0.8], [0.09, 1, 0.5]],
}


def lookup(scale, value):
    """scale: список [от, до, значение]."""
    if value is None:
        return 0
    for lo, hi, val in scale:
        if lo <= value < hi:
            return val
    return scale[-1][2]


def scale_plan(value):
    return lookup(DEFAULTS["mop"]["plan_scale"], value)


def num(v, default=0.0):
    if v is None or v == "":
        return default
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(",", ".").replace(" ", "").replace("\u00a0", ""))


def f0(x):
    try:
        return f"{float(x):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(x)


def pct(v, default=0.0):
    """Процент из поля ввода -> доля. «22», «22,5», «0.225» -> 0.22."""
    x = num(v, default * 100)
    return x / 100.0


def calc(position, level, inputs, settings=None):
    """Возвращает dict: components, coefficients, total, notes."""
    s = dict(DEFAULTS[position])
    if settings:
        s.update(settings)
    inp = inputs or {}
    out = {"coefficients": {}, "components": [], "total": 0.0, "notes": []}

    def add(name, value, note=""):
        out["components"].append({"name": name, "value": round(value, 2), "note": note})

    if position == "kd":
        salary = num(inp.get("salary"), s["salary"])
        fact, plan = num(inp.get("volume_fact")), num(inp.get("plan"))
        compl = fact / plan if plan else 0
        k = lookup(s["plan_scale"], compl)
        premium = s["base_premium"] * k
        disc = num(inp.get("discipline"))
        spec = num(inp.get("spec_bonus"))
        out["coefficients"] = {"K план": k, "Выполнение плана": round(compl, 4)}
        add("Оклад", salary)
        add("Переменная часть", premium, f"база {f0(s['base_premium'])} × K {k}")
        add("Дисциплинарная часть", -disc, "удержание")
        add("Спецпремии", spec)
        out["total"] = salary + premium - disc + spec

    elif position == "mop":
        lvl = int(level or 1)
        salary = num(inp.get("salary"), s["salary_l2"] if lvl == 2 else s["salary_l1"])
        fact, plan = num(inp.get("volume_fact")), num(inp.get("plan"))
        compl = fact / plan if plan else 0
        k_plan = lookup(s["plan_scale"], compl)
        rate = s["rate_l2"] if lvl == 2 else s["rate_l1"]
        diff = pct(inp.get("rate_fact")) * 100 - pct(inp.get("rate_plan")) * 100
        k4 = lookup(s["k4_scale"], diff)
        variable = fact * rate * k_plan * k4
        disc = num(inp.get("discipline"))
        spec = num(inp.get("spec_bonus"))
        out["coefficients"] = {"K план": k_plan, "K4 ставка": k4,
                               "Выполнение": round(compl, 4), "Откл. ставки": round(diff, 3)}
        add("Оклад", salary)
        add("Переменная часть", variable,
            f"{fact:,.0f} × {rate*100:.2f}% × K {k_plan} × K4 {k4}")
        add("Дисциплинарная часть", -disc, "удержание")
        add("Спецпремии", spec)
        out["total"] = salary + variable - disc + spec

    elif position in ("and", "and_sr"):
        sr = position == "and_sr"
        salary = num(inp.get("salary"), s["salary"])
        disc_base = s["disc_base"]
        fines = [num(inp.get(f"fine{i}")) for i in range(1, 6)]
        fine_rates = [3000, 3000, 1000, 2000, 2000]
        disc_cut = min(s["disc_limit"], sum(n * r for n, r in zip(fines, fine_rates)))
        k1 = lookup(COMMON["k1_yellow"], pct(inp.get("yellow")))
        k2 = lookup(COMMON["k2_red"], pct(inp.get("red")))
        k3 = lookup(COMMON["k3_volume"], num(inp.get("contracts")))
        k4 = lookup(COMMON["k4_sb"], pct(inp.get("to_sb")))
        stop = lookup(COMMON["stop_lost"], num(inp.get("lost")))
        prod = k1 * k2 * k3 * k4 * stop
        premium = s["premium_base"] * prod
        coeffs = {"K1 жёлтая": k1, "K2 красная": k2, "K₃ объём": k3,
                  "K4 СБ": k4, "Стоп-фактор": stop, "Произведение": round(prod, 4)}
        add("Оклад база", salary)
        add("Дисциплинарная часть", disc_base - disc_cut, f"база {f0(disc_base)} − вычеты {f0(disc_cut)}")
        add("Переменная часть", premium, f"база {f0(s['premium_base'])} × {prod:.2f}")
        if sr:
            k5 = lookup(COMMON["k5_chief"], pct(inp.get("dept_red")))
            dept_lost = num(inp.get("dept_lost"))
            if dept_lost >= 1:
                k5 = 0
            duty = s["duty_bonus"] * k5
            coeffs["K5 дежурство"] = k5
            add("Премия старшего (дежурство)", duty, f"{f0(s['duty_bonus'])} × K5 {k5}")
            out["total"] = salary + (disc_base - disc_cut) + premium + duty
        else:
            out["total"] = salary + (disc_base - disc_cut) + premium
        out["coefficients"] = coeffs

    elif position == "od":
        salary = num(inp.get("salary"), s["salary"])
        disc_base = s["disc_base"]
        fines = [num(inp.get(f"fine{i}")) for i in range(1, 5)]
        fine_rates = [2000, 3000, 2000, 3000]
        disc_cut = min(disc_base, sum(n * r for n, r in zip(fines, fine_rates)))
        contracts = num(inp.get("contracts"))
        over = max(0, (contracts - s["contract_threshold"]) // s["contract_step"])
        prem_base = s["premium_base"] + s["premium_step"] * over
        k1 = lookup(COMMON["k1_yellow"], pct(inp.get("yellow")))
        k2 = lookup(COMMON["k2_red"], pct(inp.get("red")))
        k3 = lookup(COMMON["k3_quality"], num(inp.get("violations")))
        k4 = lookup(COMMON["stop_lost"], num(inp.get("lost")))
        prod = k1 * k2 * k3 * k4
        premium = prem_base * prod
        out["coefficients"] = {"K1 жёлтая": k1, "K2 красная": k2, "K3 качество": k3,
                               "K4 потери": k4, "Произведение": round(prod, 4)}
        add("Оклад база", salary)
        add("Дисциплинарная часть", disc_base - disc_cut)
        add("Базовая премия", prem_base, f"{f0(s['premium_base'])} + {over} × {f0(s['premium_step'])}")
        add("Переменная часть", premium, f"база {prem_base} × {prod:.4f}")
        out["total"] = salary + (disc_base - disc_cut) + premium

    elif position == "rep":
        salary = num(inp.get("salary"), s["salary"])
        disc_base = s["disc_base"]
        fines = [num(inp.get(f"fine{i}")) for i in range(1, 10)]
        fine_rates = [10000, 10000, 5000, 5000, 8000, 15000, 5000, 10000, 15000]
        disc_cut = min(disc_base, sum(n * r for n, r in zip(fines, fine_rates)))
        visits = num(inp.get("visits"))
        km = num(inp.get("km"))
        visit_pay = visits * s["visit_rate"]
        fuel = km * s["fuel_per_100"] / 100 * s["fuel_price"]
        amort = km * s["amort_rate"]
        wash = s["wash"] if num(inp.get("video")) >= 1 else 0
        brand = 0
        if num(inp.get("video")) >= 1:
            if num(inp.get("brand_rear")) >= 1:
                brand += s["brand_rear"]
            if num(inp.get("brand_side")) >= 1:
                brand += s["brand_side"]
        out["coefficients"] = {"Выездов": visits, "Пробег": km, "Вычеты": disc_cut}
        add("Оклад база", salary)
        add("Дисциплинарная часть", disc_base - disc_cut, f"база {f0(disc_base)} − вычеты {f0(disc_cut)}")
        add("Оплата выездов", visit_pay, f"{f0(visits)} × {f0(s['visit_rate'])}")
        add("ГСМ", fuel, f"{f0(km)} км × {s['fuel_per_100']}/100 × {f0(s['fuel_price'])}")
        add("Амортизация", amort, f"{f0(km)} км × {s['amort_rate']}")
        add("Мойка", wash)
        add("Брендирование", brand)
        out["total"] = salary + (disc_base - disc_cut) + visit_pay + fuel + amort + wash + brand

    elif position == "sb":
        salary = num(inp.get("salary"), s["salary"])
        closed, total_tasks = num(inp.get("closed")), num(inp.get("total_tasks"))
        share = closed / total_tasks if total_tasks else 0
        k1 = lookup(s["k1_scale"], share)
        avg_days = num(inp.get("avg_days"), 0)
        k2 = lookup(s["k2_scale"], avg_days)
        premium = s["premium_base"] * k1 * k2
        seizures = num(inp.get("seizures"))
        seizure_pay = seizures * s["seizure_rate"]
        collected = num(inp.get("collected"))
        rate = lookup(s["collect_scale"], collected)
        collect_pay = collected * rate
        out["coefficients"] = {"K1 закрытие": k1, "K2 скорость": k2,
                               "Доля закрытых": round(share, 4), "Ср. срок": avg_days,
                               "Ставка взыскания": rate}
        add("Оклад", salary)
        add("Базовая премия", premium, f"{f0(s['premium_base'])} × K1 {k1} × K2 {k2}")
        add("Изъятия", seizure_pay, f"{f0(seizures)} × {f0(s['seizure_rate'])}")
        add("Взыскание", collect_pay, f"{f0(collected)} × {rate*100:.0f}%")
        out["total"] = salary + premium + seizure_pay + collect_pay

    elif position == "adm":
        salary = num(inp.get("salary"), s["salary"])
        k1 = lookup(s["k1_scale"], num(inp.get("errors")))
        k2 = lookup(s["k2_scale"], num(inp.get("delays")))
        premium = s["premium_base"] * k1 * k2
        smm = s["smm_bonus"] if num(inp.get("smm")) >= 1 else 0
        out["coefficients"] = {"K1 казначейство": k1, "K2 дисциплина": k2}
        add("Оклад", salary)
        add("Базовая премия", premium, f"{f0(s['premium_base'])} × K1 {k1} × K2 {k2}")
        add("Бонус SMM", smm)
        out["total"] = salary + premium + smm

    out["total"] = round(out["total"], 0)
    return out


FIELDS = {
    "kd": [("volume_fact", "Объём факт, ₽", "money"), ("plan", "План, ₽", "money"),
           ("discipline", "Дисциплинарные удержания, ₽", "money"),
           ("spec_bonus", "Спецпремии, ₽", "money")],
    "mop": [("volume_fact", "Объём факт, ₽", "money"), ("plan", "План, ₽", "money"),
            ("rate_fact", "Средняя ставка факт, %", "pct"),
            ("rate_plan", "Средняя ставка план, %", "pct"),
            ("discipline", "Дисциплинарные удержания, ₽", "money"),
            ("spec_bonus", "Спецпремии, ₽", "money")],
    "and": [("contracts", "Активных договоров", "num"), ("yellow", "Доля жёлтой зоны", "pct"),
            ("red", "Доля красной зоны", "pct"), ("to_sb", "Доля передач в СБ", "pct"),
            ("lost", "Потерянных авто", "num"),
            ("fine1", "Нарушение: проверка заявки > 2 ч", "num"),
            ("fine2", "Нарушение: согласование авто > 2 ч", "num"),
            ("fine3", "Нарушение: неполная карточка CRM", "num"),
            ("fine4", "Нарушение: пропуск контрольной точки", "num"),
            ("fine5", "Нарушение: проблемный лист", "num")],
    "and_sr": [("contracts", "Активных договоров", "num"), ("yellow", "Доля жёлтой зоны", "pct"),
               ("red", "Доля красной зоны", "pct"), ("to_sb", "Доля передач в СБ", "pct"),
               ("lost", "Потерянных авто", "num"),
               ("dept_red", "Красная зона департамента", "pct"),
               ("dept_lost", "Потеряно авто в департаменте", "num"),
               ("fine1", "Нарушение: проверка заявки > 2 ч", "num"),
               ("fine2", "Нарушение: согласование авто > 2 ч", "num"),
               ("fine3", "Нарушение: неполная карточка CRM", "num"),
               ("fine4", "Нарушение: пропуск контрольной точки", "num"),
               ("fine5", "Нарушение: проблемный лист", "num")],
    "od": [("contracts", "Активных договоров", "num"), ("yellow", "Доля жёлтой зоны", "pct"),
           ("red", "Доля красной зоны", "pct"), ("violations", "Нарушений SLA", "num"),
           ("lost", "Потерянных авто", "num"),
           ("fine1", "Нарушение: опоздание > 15 мин", "num"),
           ("fine2", "Нарушение: поручение не исполнено", "num"),
           ("fine3", "Нарушение: отчёт не сдан", "num"),
           ("fine4", "Нарушение: жалоба смежного отдела", "num")],
    "rep": [("visits", "Выездов на сделки", "num"), ("km", "Пробег, км", "num"),
            ("video", "Видеоотчёт сдан (1/0)", "num"),
            ("brand_rear", "Брендирование: заднее стекло (1/0)", "num"),
            ("brand_side", "Брендирование: бока (1/0)", "num"),
            ("fine1", "Отказ от выезда", "num"),
            ("fine2", "Опоздание на сделку > 1 ч", "num"),
            ("fine3", "Просрочка фото/видеоотчёта", "num"),
            ("fine4", "Просрочка отправки оригиналов", "num"),
            ("fine5", "Отсутствие документа (частичное)", "num"),
            ("fine6", "Полное отсутствие документов", "num"),
            ("fine7", "Жалоба клиента", "num"),
            ("fine8", "Обнаружение маяка клиентом", "num"),
            ("fine9", "Не установлен маяк", "num")],
    "sb": [("closed", "Закрыто задач", "num"), ("total_tasks", "Задач в работе", "num"),
           ("avg_days", "Средний срок закрытия, дней", "num"),
           ("seizures", "Изъято авто", "num"),
           ("collected", "Взыскано, ₽", "money")],
    "adm": [("errors", "Ошибок казначейских", "num"), ("delays", "Просрочек", "num"),
            ("smm", "План SMM выполнен (1/0)", "num")],
}
