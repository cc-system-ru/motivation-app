import sqlite3
from datetime import datetime
import pandas as pd
import streamlit as st

# Настройка страницы
st.set_page_config(
    page_title="Система мотивации", page_icon="💼", layout="wide"
)

DB_NAME = "motivation.db"


# Инициализация базы данных
def init_db():
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()

  # Таблица сотрудников
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fio TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT DEFAULT 'Активен'
        )
    """)

  # Таблица настроек мотивации (версионность по периодам)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS motivation_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            start_period TEXT NOT NULL, -- формат ГГГГ-ММ
            param_name TEXT NOT NULL,
            param_value REAL NOT NULL
        )
    """)

  # Таблица закрытых периодов
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS closed_periods (
            period TEXT PRIMARY KEY
        )
    """)

  # Таблица сохраненных расчетов (история)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS calculations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT NOT NULL,
            employee_id INTEGER,
            fio TEXT,
            role TEXT,
            base_salary REAL,
            discipline_penalty REAL,
            bonus REAL,
            additional_pay REAL,
            total_payout REAL,
            details TEXT,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        )
    """)
  conn.commit()
  conn.close()


init_db()

# Пароль руководителя
ADMIN_PASSWORD = "admin"  # Можете изменить на свой

# Авторизация
if "authenticated" not in st.session_state:
  st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
  st.markdown("## 🔐 Вход в систему мотивации")
  password = st.text_input("Введите пароль руководителя:", type="password")
  if st.button("Войти"):
    if password == ADMIN_PASSWORD:
      st.session_state["authenticated"] = True
      st.rerun()
    else:
      st.error("Неверный пароль")
  st.stop()

# Главное меню
st.sidebar.title("📌 Навигация")
menu = st.sidebar.selectbox(
    "Выберите раздел",
    [
        "👥 Сотрудники",
        "⚙️ Настройки мотивации",
        "🧮 Расчет зарплаты",
        "📊 Итоги и закрытие периода",
    ],
)

if st.sidebar.button("Выйти из системы"):
  st.session_state["authenticated"] = False
  st.rerun()

# ----------------------------------------------------
# 1. СОТРУДНИКИ
# ----------------------------------------------------
if menu == "👥 Сотрудники":
  st.header("👥 Управление сотрудниками")

  conn = sqlite3.connect(DB_NAME)
  df_emp = pd.read_sql("SELECT * FROM employees", conn)
  conn.close()

  with st.form("add_employee_form"):
    st.subheader("Добавить нового сотрудника")
    new_fio = st.text_input("ФИО сотрудника")
    new_role = st.selectbox(
        "Роль",
        [
            "Операционный директор",
            "Андеррайтер",
            "Старший андеррайтер",
            "Региональный представитель",
            "Менеджер по продажам (МОП)",
            "Коммерческий директор",
        ],
    )
    submit_emp = st.form_submit_button("Добавить")

    if submit_emp and new_fio:
      conn = sqlite3.connect(DB_NAME)
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO employees (fio, role, status) VALUES (?, ?, 'Активен')",
          (new_fio, new_role),
      )
      conn.commit()
      conn.close()
      st.success(f"Сотрудник {new_fio} успешно добавлен!")
      st.rerun()

  st.subheader("Список сотрудников")
  if not df_emp.empty:
    # Редактирование статуса
    for index, row in df_emp.iterrows():
      col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
      col1.text(row["fio"])
      col2.text(row["role"])

      new_status = col3.selectbox(
          "Статус",
          ["Активен", "Уволен"],
          index=0 if row["status"] == "Активен" else 1,
          key=f"status_{row['id']}",
      )
      if new_status != row["status"]:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE employees SET status = ? WHERE id = ?",
            (new_status, row["id"]),
        )
        conn.commit()
        conn.close()
        st.success("Статус обновлен!")
        st.rerun()

      if col4.button("Удалить", key=f"del_{row['id']}"):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM employees WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        st.rerun()
  else:
    st.info("Список сотрудников пуст.")

# ----------------------------------------------------
# 2. НАСТРОЙКИ МОТИВАЦИИ
# ----------------------------------------------------
elif menu == "⚙️ Настройки мотивации":
  st.header("⚙️ Настройки коэффициентов и окладов по периодам")
  st.markdown(
      "Здесь вы можете задавать базовые оклады, премии и коэффициенты, которые"
      " действуют с определенного месяца и года."
  )

  conn = sqlite3.connect(DB_NAME)
  settings_df = pd.read_sql("SELECT * FROM motivation_settings", conn)
  conn.close()

  with st.form("settings_form"):
    col1, col2, col3, col4 = st.columns(4)
    s_role = col1.selectbox(
        "Роль",
        [
            "Операционный директор",
            "Андеррайтер",
            "Старший андеррайтер",
            "Региональный представитель",
            "Менеджер по продажам (МОП)",
            "Коммерческий директор",
        ],
    )
    s_period = col2.text_input("Период начала действия (ГГГГ-ММ)", "2026-01")
    s_param = col3.text_input(
        "Название параметра (например, Базовый оклад)"
    )
    s_val = col4.number_input("Значение", value=0.0, step=100.0)

    submit_setting = st.form_submit_button("Сохранить настройку")
    if submit_setting and s_param:
      conn = sqlite3.connect(DB_NAME)
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO motivation_settings (role, start_period, param_name,"
          " param_value) VALUES (?, ?, ?, ?)",
          (s_role, s_period, s_param, s_val),
      )
      conn.commit()
      conn.close()
      st.success("Настройка сохранена!")
      st.rerun()

  st.subheader("Текущие настройки в базе")
  if not settings_df.empty:
    st.dataframe(settings_df, use_container_width=True)
  else:
    st.info("Настроек пока нет.")

# ----------------------------------------------------
# 3. РАСЧЕТ ЗАРПЛАТЫ
# ----------------------------------------------------
elif menu == "🧮 Расчет зарплаты":
  st.header("🧮 Калькулятор расчета зарплаты за месяц")

  # Выбор периода
  col_p1, col_p2 = st.columns(2)
  calc_period = col_p1.text_input(
      "Расчетный период (ГГГГ-ММ)", datetime.now().strftime("%Y-%m")
  )

  # Проверка, закрыт ли период
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT 1 FROM closed_periods WHERE period = ?", (calc_period,)
  )
  is_closed = cursor.fetchone() is not None
  conn.close()

  if is_closed:
    st.warning(
        f"🔒 Период {calc_period} **ЗАКРЫТ**. Изменение расчетов заблокировано."
    )

  # Выбор сотрудника
  conn = sqlite3.connect(DB_NAME)
  employees_df = pd.read_sql(
      "SELECT * FROM employees WHERE status = 'Активен'", conn
  )
  conn.close()

  if employees_df.empty:
    st.warning("Сначала добавьте активных сотрудников в разделе «Сотрудники».")
  else:
    emp_dict = {
        f"{row['fio']} ({row['role']})": row
        for index, row in employees_df.iterrows()
    }
    selected_emp_str = st.selectbox(
        "Выберите сотрудника для расчета", list(emp_dict.keys())
    )
    emp = emp_dict[selected_emp_str]

    st.info(f"Роль сотрудника: **{emp['role']}**")

    # Формы расчета в зависимости от роли
    role = emp["role"]
    base_salary = 0.0
    discipline_penalty = 0.0
    bonus = 0.0
    additional_pay = 0.0
    details = ""

    with st.form("calc_form"):
      st.subheader("Ввод параметров за месяц")

      if role == "Операционный директор":
        base_salary = st.number_input("Базовый оклад + дисциплинарная", value=100000.0)
        penalties_sum = st.number_input(
            "Сумма штрафов по дисциплине", value=0.0, step=1000.0
        )
        base_prem = st.number_input("Базовая премия (по портфелю)", value=40000.0)
        k1 = st.slider("К1 (Желтая зона)", 0.5, 1.5, 1.2, 0.1)
        k2 = st.slider("К2 (Красная зона)", 0.5, 1.2, 1.1, 0.1)
        k3 = st.slider("К3 (Качество работы / SLA)", 0.5, 1.2, 1.2, 0.1)
        k4 = st.slider("К4 (Черная зона / потери)", 0.0, 1.0, 1.0, 0.1)

        discipline_penalty = penalties_sum
        bonus = base_prem * k1 * k2 * k3 * k4
        total_payout = (base_salary - discipline_penalty) + bonus
        details = (
            f"База: {base_salary}, Штрафы: {penalties_sum}, Баз. премия:"
            f" {base_prem}, К1:{k1}, К2:{k2}, К3:{k3}, К4:{k4}"
        )

      elif role in ["Андеррайтер", "Старший андеррайтер"]:
        def_base = 60000.0 if role == "Андеррайтер" else 65000.0
        base_salary = st.number_input("Оклад (база + дисциплина)", value=def_base)
        penalties_sum = st.number_input("Штрафы по дисциплине/SLA", value=0.0)
        base_prem = st.number_input("Базовая премия", value=35000.0)
        k1 = st.slider("К1 (Желтая зона)", 0.5, 1.5, 1.2, 0.1)
        k2 = st.slider("К2 (Красная зона)", 0.5, 1.2, 1.1, 0.1)
        k3 = st.slider("К3 (Объем портфеля)", 0.8, 1.3, 1.0, 0.05)
        k4 = st.slider("К4 (Передача в СБ)", 0.5, 1.0, 1.0, 0.1)

        duty_pay = 0.0
        if role == "Старший андеррайтер":
          duty_pay = st.number_input("Надбавка за дежурство * К5", value=15000.0)

        discipline_penalty = penalties_sum
        bonus = base_prem * k1 * k2 * k3 * k4
        additional_pay = duty_pay
        total_payout = (base_salary - discipline_penalty) + bonus + additional_pay
        details = (
            f"Оклад: {base_salary}, Штрафы: {penalties_sum}, Премия:"
            f" {base_prem}*К1..К4, Дежурство: {duty_pay}"
        )

      elif role == "Региональный представитель":
        base_salary = st.number_input("Оклад (база + дисциплина)", value=70000.0)
        penalties_sum = st.number_input("Штрафы по нарушениям", value=0.0)
        trips = st.number_input("Количество выездов", value=10, step=1)
        trip_rate = 2500.0
        compensations = st.number_input(
            "Компенсации (ГСМ, амортизация, мойка, брендирование)", value=10000.0
        )

        discipline_penalty = penalties_sum
        bonus = trips * trip_rate
        additional_pay = compensations
        total_payout = (base_salary - discipline_penalty) + bonus + additional_pay
        details = (
            f"Оклад: {base_salary}, Штрафы: {penalties_sum}, Выездов:"
            f" {trips}*2500, Компенсации: {compensations}"
        )

      elif role == "Менеджер по продажам (МОП)":
        base_salary = st.number_input("Оклад + дисциплинарный бонус", value=50000.0)
        penalties_sum = st.number_input("Дисциплинарные удержания", value=0.0)
        fin_volume = st.number_input(
            "Объем лизингового финансирования (факт)", value=5000000.0, step=100000.0
        )
        fin_percent = st.number_input(
            "Процент от объема финансирования (%)", value=0.7, step=0.05
        )
        k1 = st.slider("К1 (Конверсия)", 0.7, 1.2, 1.0, 0.05)
        k2 = st.slider("К2 (Командный коэффициент)", 0.8, 1.1, 1.0, 0.05)
        k3 = st.slider("К3 (Командный план %)", 0.8, 1.1, 1.0, 0.05)
        k4 = st.slider("К4 (Ставка договора)", 0.7, 1.15, 1.0, 0.05)
        k5 = st.slider("К5 (Отзывы Авито/другие)", 0.9, 1.0, 1.0, 0.05)

        discipline_penalty = penalties_sum
        base_bonus = fin_volume * (fin_percent / 100.0)
        bonus = base_bonus * k1 * k2 * k3 * k4 * k5
        total_payout = (base_salary - discipline_penalty) + bonus
        details = (
            f"Объем: {fin_volume}, %:{fin_percent}, К1..К5 учтены, Баз.бонус:"
            f" {base_bonus}"
        )

      elif role == "Коммерческий директор":
        base_salary = st.number_input("Оклад фиксированный", value=100000.0)
        dept_volume = st.number_input(
            "Объем финансирования департамента",
            value=30000000.0,
            step=500000.0,
        )
        dept_percent = st.number_input(
            "Процент от объема департамента (%)", value=0.5, step=0.05
        )
        k1 = st.slider("К1 (Конверсия департамента)", 0.7, 1.2, 1.0, 0.05)
        k2 = st.slider("К2 (Средняя ставка)", 0.8, 1.2, 1.0, 0.05)
        k3 = st.slider("К3 (CAC - стоимость привлечения)", 0.7, 1.2, 1.0, 0.05)
        k4 = st.slider("К4 (Качество / отзывы)", 0.0, 1.0, 1.0, 0.1)

        base_bonus = dept_volume * (dept_percent / 100.0)
        bonus = base_bonus * k1 * k2 * k3 * k4
        total_payout = base_salary + bonus
        details = (
            f"Деп.объем: {dept_volume}, %:{dept_percent}, К1..К4 учтены"
        )

      st.markdown(f"### 💰 Предварительный итог к выплате: **{total_payout:,.2f} ₽**")

      submit_calc = st.form_submit_button(
          "Сохранить расчет в базу", disabled=is_closed
      )

      if submit_calc:
        if is_closed:
          st.error("Период закрыт, сохранение невозможно!")
        else:
          conn = sqlite3.connect(DB_NAME)
          cursor = conn.cursor()
          cursor.execute(
              """
                        INSERT INTO calculations (period, employee_id, fio, role, base_salary, discipline_penalty, bonus, additional_pay, total_payout, details)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
              (
                  calc_period,
                  emp["id"],
                  emp["fio"],
                  emp["role"],
                  base_salary,
                  discipline_penalty,
                  bonus,
                  additional_pay,
                  total_payout,
                  details,
              ),
          )
          conn.commit()
          conn.close()
          st.success(
              f"Расчет для {emp['fio']} за {calc_period} успешно сохранен!"
          )

# ----------------------------------------------------
# 4. ИТОГИ И ЗАКРЫТИЕ ПЕРИОДА
# ----------------------------------------------------
elif menu == "📊 Итоги и закрытие периода":
  st.header("📊 Сводная таблица итогов и закрытие периода")

  report_period = st.text_input(
      "Выберите период для отчета (ГГГГ-ММ)", datetime.now().strftime("%Y-%m")
  )

  conn = sqlite3.connect(DB_NAME)
  df_calc = pd.read_sql(
      "SELECT * FROM calculations WHERE period = ?",
      conn,
      params=(report_period,),
  )

  cursor = conn.cursor()
  cursor.execute(
      "SELECT 1 FROM closed_periods WHERE period = ?", (report_period,)
  )
  is_closed = cursor.fetchone() is not None
  conn.close()

  if not df_calc.empty:
    st.subheader(f"Итоги расчетов за {report_period}")
    st.dataframe(df_calc, use_container_width=True)

    # Экспорт в Excel
    from io import BytesIO

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
      df_calc.to_excel(writer, index=False, sheet_name="Расчеты")
    processed_data = output.getvalue()

    st.download_button(
        label="📥 Скачать сводный отчет в Excel",
        data=processed_data,
        file_name=f"motivation_{report_period}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
  else:
    st.info(f"За период {report_period} пока нет сохраненных расчетов.")

  st.divider()

  # Блок закрытия периода
  st.subheader("🔒 Закрытие периода")
  if is_closed:
    st.success(
        f"Период **{report_period}** официально закрыт. Изменения заблокированы."
    )
  else:
    st.warning(
        f"Внимание! После нажатия кнопки «Закрыть период {report_period}»"
        " любые изменения и новые расчеты за этот месяц будут заблокированы навсегда."
    )
    if st.button(f"🔒 Закрыть период {report_period}"):
      conn = sqlite3.connect(DB_NAME)
      cursor = conn.cursor()
      cursor.execute(
          "INSERT OR IGNORE INTO closed_periods (period) VALUES (?)",
          (report_period,),
      )
      conn.commit()
      conn.close()
      st.success(f"Период {report_period} успешно закрыт!")
      st.rerun()
