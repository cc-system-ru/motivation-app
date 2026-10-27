import json
import sqlite3
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from motivation_engine import (
    DEFAULT_RULES,
    ROLES,
    compute,
    default_rules,
    lookup,
    param_value,
)

st.set_page_config(page_title="Система мотивации", page_icon="💼", layout="wide")

DB_PATH = "motivation.db"
ADMIN_PASSWORD = "admin"

SEED_EMPLOYEES = [
    ("Мамий Инвер", "Андеррайтер"),
    ("Серёгин Евгений", "Андеррайтер"),
    ("Щербань Дмитрий", "Андеррайтер"),
    ("Кирсанов Данил", "Старший андеррайтер"),
    ("Вадим", "Менеджер по продажам (МОП)"),
    ("Данил", "Менеджер по продажам (МОП)"),
    ("Александр", "Менеджер по продажам (МОП)"),
    ("Антон", "Менеджер по продажам (МОП)"),
    ("Руслан", "Коммерческий директор"),
    ("Владимир", "Операционный директор"),
]


# ---------------------------------------------------------------- БАЗА
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fio TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT DEFAULT 'Активен',
                hired TEXT,
                note TEXT
            );
            CREATE TABLE IF NOT EXISTS rule_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                start_period TEXT NOT NULL,
                rules TEXT NOT NULL,
                UNIQUE(role, start_period)
            );
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL,
                employee_id INTEGER NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT,
                UNIQUE(period, employee_id)
            );
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL,
                employee_id INTEGER NOT NULL,
                fio TEXT,
                role TEXT,
                result TEXT NOT NULL,
                snapshot_at TEXT,
                UNIQUE(period, employee_id)
            );
            CREATE TABLE IF NOT EXISTS closed_periods (
                period TEXT PRIMARY KEY,
                closed_at TEXT
            );
            """
        )
        if conn.execute("SELECT COUNT(*) c FROM employees").fetchone()["c"] == 0:
            conn.executemany(
                "INSERT INTO employees (fio, role, status) VALUES (?,?, 'Активен')",
                SEED_EMPLOYEES,
            )
        for role in ROLES:
            if not conn.execute(
                "SELECT 1 FROM rule_versions WHERE role=?", (role,)
            ).fetchone():
                conn.execute(
                    "INSERT INTO rule_versions (role, start_period, rules) VALUES (?,?,?)",
                    (role, "2026-01", json.dumps(default_rules(role), ensure_ascii=False)),
                )


init_db()


def load_rules(role, period):
    """Правила роли, действующие в указанном периоде."""
    with db() as conn:
        row = conn.execute(
            "SELECT rules FROM rule_versions WHERE role=? AND start_period<=? "
            "ORDER BY start_period DESC LIMIT 1",
            (role, period),
        ).fetchone()
        if row:
            return json.loads(row["rules"])
    return default_rules(role)


def rule_versions(role):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM rule_versions WHERE role=? ORDER BY start_period",
            (role,),
        ).fetchall()


def save_rules(role, period, rules):
    with db() as conn:
        conn.execute(
            "INSERT INTO rule_versions (role, start_period, rules) VALUES (?,?,?) "
            "ON CONFLICT(role, start_period) DO UPDATE SET rules=excluded.rules",
            (role, period, json.dumps(rules, ensure_ascii=False)),
        )


def employees(active_only=False):
    q = "SELECT * FROM employees"
    if active_only:
        q += " WHERE status='Активен'"
    with db() as conn:
        return [dict(r) for r in conn.execute(q + " ORDER BY role, fio")]


def is_closed(period):
    with db() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM closed_periods WHERE period=?", (period,)
            ).fetchone()
            is not None
        )


def load_entries(period):
    with db() as conn:
        rows = conn.execute(
            "SELECT employee_id, payload FROM entries WHERE period=?", (period,)
        ).fetchall()
    return {r["employee_id"]: json.loads(r["payload"]) for r in rows}


def save_entries(period, data):
    with db() as conn:
        for emp_id, payload in data.items():
            conn.execute(
                "INSERT INTO entries (period, employee_id, payload, updated_at) "
                "VALUES (?,?,?,?) ON CONFLICT(period, employee_id) "
                "DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (
                    period,
                    emp_id,
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )


def load_calc(period):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM calculations WHERE period=?", (period,)
        ).fetchall()
    return {r["employee_id"]: json.loads(r["result"]) for r in rows}


def save_calc(period, results):
    with db() as conn:
        for emp_id, res in results.items():
            conn.execute(
                "INSERT INTO calculations (period, employee_id, fio, role, result, snapshot_at) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(period, employee_id) DO UPDATE SET "
                "result=excluded.result, snapshot_at=excluded.snapshot_at",
                (
                    period,
                    emp_id,
                    res.get("fio"),
                    res.get("role"),
                    json.dumps(res, ensure_ascii=False),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )


def period_label(p):
    months = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    ]
    try:
        y, m = p.split("-")
        return f"{months[int(m) - 1]} {y}"
    except Exception:
        return p


def period_select(key):
    now = datetime.now()
    years = ["2025", "2026", "2027", "2028"]
    c1, c2 = st.columns(2)
    y = c1.selectbox("Год", years, index=years.index(str(now.year)) if str(now.year) in years else 1, key=f"y_{key}")
    m = c2.selectbox(
        "Месяц",
        list(range(1, 13)),
        index=now.month - 1,
        format_func=lambda x: ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
                               "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][x - 1],
        key=f"m_{key}",
    )
    return f"{y}-{m:02d}"


# ---------------------------------------------------------------- ВХОД
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("💼 Система мотивации")
    st.caption("Доступ только для руководителя")
    with st.form("login"):
        pw = st.text_input("Пароль", type="password")
        ok = st.form_submit_button("Войти", type="primary")
    if ok:
        if pw == ADMIN_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Неверный пароль")
    st.stop()


st.sidebar.title("💼 Мотивация")
menu = st.sidebar.radio(
    "Раздел",
    ["📝 Ввод данных", "📊 Лист расчёта", "⚙️ Настройки мотивации", "👥 Сотрудники", "🗄 Архив"],
)
if st.sidebar.button("Выйти"):
    st.session_state.auth = False
    st.rerun()

# ================================================================ ВВОД
if menu == "📝 Ввод данных":
    st.header("📝 Ввод данных за месяц")
    st.caption(
        "Заполните фактические показатели. Жёлтые столбцы — сотрудники, строки — показатели. "
        "Коэффициенты и суммы посчитаются на листе расчёта."
    )
    period = period_select("entry")
    st.info(f"Период: **{period_label(period)}**")

    if is_closed(period):
        st.error("🔒 Период закрыт. Изменение данных заблокировано.")
        st.stop()

    emps = employees(active_only=True)
    if not emps:
        st.warning("Нет активных сотрудников. Добавьте их в разделе «Сотрудники».")
        st.stop()

    stored = load_entries(period)

    for role in ROLES:
        role_emps = [e for e in emps if e["role"] == role]
        if not role_emps:
            continue
        rules = load_rules(role, period)
        with st.expander(f"{role} — {len(role_emps)} чел.", expanded=(role == "Андеррайтер")):
            rows, labels = [], []
            for inp in rules["inputs"]:
                labels.append(f"{inp['label']}, {inp['unit']}")
                rows.append([
                    float(stored.get(e["id"], {}).get(inp["key"], inp["default"]))
                    for e in role_emps
                ])
            for pen in rules.get("penalties", []):
                labels.append(f"⚠️ {pen['label']}, шт")
                rows.append([
                    float(stored.get(e["id"], {}).get(f"pen_{pen['key']}", 0))
                    for e in role_emps
                ])

            df = pd.DataFrame(rows, index=labels, columns=[e["fio"] for e in role_emps])
            edited = st.data_editor(
                df,
                use_container_width=True,
                key=f"editor_{period}_{role}",
                num_rows="fixed",
            )

            if st.button(f"💾 Сохранить данные: {role}", key=f"save_{role}"):
                payload = {}
                for i, e in enumerate(role_emps):
                    d = {}
                    idx = 0
                    for inp in rules["inputs"]:
                        d[inp["key"]] = float(edited.iloc[idx, i] or 0)
                        idx += 1
                    for pen in rules.get("penalties", []):
                        d[f"pen_{pen['key']}"] = float(edited.iloc[idx, i] or 0)
                        idx += 1
                    payload[e["id"]] = d
                save_entries(period, payload)
                st.success(f"Данные сохранены за {period_label(period)}")
                st.rerun()

# ============================================================ РАСЧЁТ
elif menu == "📊 Лист расчёта":
    st.header("📊 Лист расчёта зарплаты")
    period = period_select("calc")
    closed = is_closed(period)
    st.info(f"Период: **{period_label(period)}**" + ("  ·  🔒 закрыт" if closed else ""))

    emps = employees(active_only=True)
    entries = load_entries(period)

    if closed:
        results = load_calc(period)
        if not results:
            st.warning("За этот период нет сохранённых расчётов.")
            st.stop()
    else:
        results = {}
        for e in emps:
            payload = entries.get(e["id"])
            if not payload:
                continue
            rules = load_rules(e["role"], period)
            res = compute(e["role"], rules, payload)
            res["fio"] = e["fio"]
            res["role"] = e["role"]
            results[e["id"]] = res

    if not results:
        st.warning("Нет введённых данных за этот период. Заполните «Ввод данных».")
        st.stop()

    # --- сводная таблица
    table = []
    for emp_id, r in results.items():
        row = {
            "Сотрудник": r.get("fio"),
            "Роль": r.get("role"),
            "Оклад (база)": r["base"],
            "Дисциплинарная часть": r["disc_full"],
            "Удержания": -r["penalties"],
            "Дисциплинарная к выплате": r["disc_after"],
        }
        if r.get("plan_pct") is not None:
            row["Выполнение плана, %"] = r["plan_pct"]
            row["Ставка, % от объёма"] = r["pct_rate"]
        row["База переменной части"] = r["base_variable"]
        for k, c in r["coefficients"].items():
            row[c["label"]] = c["value"]
        row[r.get("var_label") or "Переменная часть"] = r["variable"]
        row["Компенсации / доплаты"] = r["extras"]
        row["ИТОГО К ВЫПЛАТЕ"] = r["total"]
        table.append(row)

    df_out = pd.DataFrame(table)
    st.dataframe(
        df_out,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Оклад (база)": st.column_config.NumberColumn(format="%.0f ₽"),
            "Дисциплинарная часть": st.column_config.NumberColumn(format="%.0f ₽"),
            "Удержания": st.column_config.NumberColumn(format="%.0f ₽"),
            "Дисциплинарная к выплате": st.column_config.NumberColumn(format="%.0f ₽"),
            "База переменной части": st.column_config.NumberColumn(format="%.0f ₽"),
            "ИТОГО К ВЫПЛАТЕ": st.column_config.NumberColumn(format="%.0f ₽"),
        },
    )

    total_sum = sum(r["total"] for r in results.values())
    st.metric("Фонд оплаты труда за период", f"{total_sum:,.0f} ₽".replace(",", " "))

    # --- детализация
    with st.expander("🔍 Детализация по сотруднику"):
        who = st.selectbox("Сотрудник", [r.get("fio") for r in results.values()])
        emp_id = [k for k, r in results.items() if r.get("fio") == who][0]
        r = results[emp_id]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Начисления и коэффициенты**")
            for label, val in r["lines"]:
                st.write(f"{label}: **{val:,.2f}**".replace(",", " "))
        with c2:
            st.markdown("**Удержания**")
            if r["penalty_lines"]:
                for label, val in r["penalty_lines"]:
                    st.write(f"{label}: **{val:,.0f} ₽**".replace(",", " "))
                st.write(f"Удержано (не более дисциплинарной части): **{r['penalties_capped']:,.0f} ₽**".replace(",", " "))
            else:
                st.write("Нет")
            if r["zeroed"]:
                st.error(f"Стоп-фактор: {r['zeroed']} — переменная часть обнулена")

    # --- экспорт
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name=period)
    st.download_button(
        "📥 Скачать в Excel",
        buf.getvalue(),
        f"zarplata_{period}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    colA, colB = st.columns(2)
    if not closed:
        if colA.button("💾 Сохранить расчёт в базу", type="primary"):
            save_calc(period, results)
            st.success("Расчёт сохранён.")
        if colB.button("🔒 Закрыть период"):
            save_calc(period, results)
            with db() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO closed_periods (period, closed_at) VALUES (?,?)",
                    (period, datetime.now().isoformat(timespec="seconds")),
                )
            st.success(f"Период {period_label(period)} закрыт. Изменения заблокированы.")
            st.rerun()
        st.caption(
            "Закрытие фиксирует текущие правила и цифры: даже если позже изменить "
            "коэффициенты, расчёт за этот месяц останется прежним."
        )
    else:
        st.success("Период закрыт. Данные заморожены.")

# =========================================================== НАСТРОЙКИ
elif menu == "⚙️ Настройки мотивации":
    st.header("⚙️ Настройки системы мотивации")
    st.caption(
        "Каждый параметр, коэффициент, порог и процент настраивается. "
        "Изменения сохраняются как новая версия с датой начала действия — "
        "прошлые месяцы пересчитываться не будут."
    )

    role = st.selectbox("Роль", ROLES)
    versions = rule_versions(role)
    start_period = period_select("settings")

    existing = [v for v in versions if v["start_period"] == start_period]
    if existing:
        rules = json.loads(existing[0]["rules"])
        st.success(f"Редактируется версия от {period_label(start_period)}")
    else:
        base = load_rules(role, start_period)
        rules = json.loads(json.dumps(base, ensure_ascii=False))
        st.warning(
            f"Версии от {period_label(start_period)} нет — будет создана новая "
            "на основе предыдущей."
        )

    if is_closed(start_period):
        st.error("🔒 Период закрыт, менять настройки нельзя.")
        st.stop()

    tabs = st.tabs(["💰 Оклады и параметры", "📉 Штрафы и удержания", "📐 Коэффициенты", "📈 Проценты от объёма"])

    with tabs[0]:
        for p in rules.get("params", []):
            p["value"] = st.number_input(
                f"{p['label']}" + (f", {p['unit']}" if p.get("unit") else ""),
                value=float(p["value"]),
                step=100.0 if p.get("unit") == "₽" else 0.01,
                key=f"par_{role}_{start_period}_{p['key']}",
            )

    with tabs[1]:
        for pen in rules.get("penalties", []):
            pen["amount"] = st.number_input(
                f"{pen['label']}, ₽ за случай",
                value=float(pen["amount"]),
                step=500.0,
                key=f"pen_{role}_{start_period}_{pen['key']}",
            )

    with tabs[2]:
        if not rules.get("coeffs"):
            st.info("У этой роли нет коэффициентов.")
        for c in rules.get("coeffs", []):
            st.markdown(f"**{c['label']}**")
            if "parts" in c:
                for part in c["parts"]:
                    st.caption(f"Вес {int(part['weight']*100)}% · показатель: {part['input']}")
                    st.data_editor(
                        pd.DataFrame(part["rows"]),
                        use_container_width=True,
                        hide_index=True,
                        num_rows="fixed",
                        key=f"c_{role}_{start_period}_{c['key']}_{part['input']}",
                        column_config={
                            "from": st.column_config.NumberColumn("от (вкл.)"),
                            "to": st.column_config.NumberColumn("до (не вкл.)"),
                            "value": st.column_config.NumberColumn("коэффициент"),
                            "comment": st.column_config.TextColumn("пояснение"),
                        },
                        disabled=["from", "to", "value", "comment"],
                    )
            else:
                st.caption(f"Показатель: {c['input']}")
                st.data_editor(
                    pd.DataFrame(c["rows"]),
                    use_container_width=True,
                    hide_index=True,
                    num_rows="fixed",
                    key=f"c_{role}_{start_period}_{c['key']}",
                )
            st.divider()

    with tabs[3]:
        if not rules.get("percent_scale"):
            st.info("У этой роли нет процента от объёма.")
        else:
            st.data_editor(
                pd.DataFrame(rules["percent_scale"]),
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key=f"ps_{role}_{start_period}",
            )
            st.caption("«от» — включительно, «до» — не включается. Пустое «до» = без верхней границы.")

    if st.button("💾 Сохранить настройки", type="primary"):
        save_rules(role, start_period, rules)
        st.success(f"Настройки для роли «{role}» сохранены с {period_label(start_period)}")
        st.rerun()

# =========================================================== СОТРУДНИКИ
elif menu == "👥 Сотрудники":
    st.header("👥 Сотрудники")

    with st.form("add"):
        c1, c2, c3 = st.columns([3, 3, 1])
        fio = c1.text_input("ФИО")
        role_new = c2.selectbox("Роль", ROLES)
        if c3.form_submit_button("Добавить") and fio.strip():
            with db() as conn:
                conn.execute(
                    "INSERT INTO employees (fio, role, status) VALUES (?,?, 'Активен')",
                    (fio.strip(), role_new),
                )
            st.rerun()

    st.subheader("Список сотрудников")
    emps = employees()
    for e in emps:
        with st.expander(f"{e['fio']} — {e['role']} ({e['status']})"):
            c1, c2, c3 = st.columns([3, 3, 2])
            new_fio = c1.text_input("ФИО", value=e["fio"], key=f"fio_{e['id']}")
            new_role = c2.selectbox(
                "Роль", ROLES,
                index=ROLES.index(e["role"]) if e["role"] in ROLES else 0,
                key=f"role_{e['id']}",
            )
            new_status = c3.selectbox(
                "Статус", ["Активен", "Уволен"],
                index=0 if e["status"] == "Активен" else 1,
                key=f"st_{e['id']}",
            )
            b1, b2 = st.columns([1, 1])
            if b1.button("💾 Сохранить", key=f"sv_{e['id']}"):
                with db() as conn:
                    conn.execute(
                        "UPDATE employees SET fio=?, role=?, status=? WHERE id=?",
                        (new_fio, new_role, new_status, e["id"]),
                    )
                st.success("Сохранено")
                st.rerun()
            if b2.button("🗑 Удалить", key=f"del_{e['id']}"):
                with db() as conn:
                    conn.execute("DELETE FROM employees WHERE id=?", (e["id"],))
                st.rerun()

# ============================================================== АРХИВ
elif menu == "🗄 Архив":
    st.header("🗄 Архив расчётов")
    with db() as conn:
        periods = [
            r["period"]
            for r in conn.execute(
                "SELECT DISTINCT period FROM calculations ORDER BY period DESC"
            )
        ]
        closed = {
            r["period"] for r in conn.execute("SELECT period FROM closed_periods")
        }

    if not periods:
        st.info("Сохранённых расчётов пока нет.")
    for p in periods:
        mark = "🔒" if p in closed else "📄"
        results = load_calc(p)
        fund = sum(r["total"] for r in results.values())
        with st.expander(f"{mark} {period_label(p)} — {len(results)} чел. — {fund:,.0f} ₽".replace(",", " ")):
            rows = [
                {
                    "Сотрудник": r.get("fio"),
                    "Роль": r.get("role"),
                    "Оклад (база)": r["base"],
                    "Дисциплинарная к выплате": r["disc_after"],
                    "Удержания": -r["penalties"],
                    "Переменная часть": r["variable"],
                    "Доплаты": r["extras"],
                    "ИТОГО К ВЫПЛАТЕ": r["total"],
                }
                for r in results.values()
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                pd.DataFrame(rows).to_excel(writer, index=False, sheet_name=p)
            st.download_button(
                "📥 Excel", buf.getvalue(), f"zarplata_{p}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_{p}",
            )

    st.divider()
    st.subheader("Резервная копия")
    st.caption(
        "На бесплатном хостинге файл базы может очищаться при перезапуске сервиса. "
        "Скачивайте копию после каждого закрытия месяца."
    )
    with open(DB_PATH, "rb") as f:
        st.download_button("💾 Скачать базу данных", f.read(), "motivation_backup.db")
