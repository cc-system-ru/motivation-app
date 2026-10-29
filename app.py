import io
import json
from datetime import date
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_file, session, url_for)

import motivation_engine as calc
import exports
from motivation_engine import num
from config import (DEPARTMENTS, ROLE_NAMES, ROLE_PASSWORDS, ROLE_DEPTS,
                    SECRET_KEY)
from db import (current_period, ensure_period, get_db, get_period, get_settings,
                init_db, log, save_settings)

app = Flask(__name__)
app.secret_key = SECRET_KEY

POSITIONS = calc.DEFAULTS.keys()


# ---------- форматирование ----------
def fmt_num(value, decimals=0):
    if value is None or value == "":
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = f"{v:,.{decimals}f}".replace(",", " ")
    if decimals:
        s = s.replace(".", ",")
    return s


app.jinja_env.filters["num"] = fmt_num


@app.template_filter("pct")
def fmt_pct(value):
    try:
        return f"{float(value) * 100:.1f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


# ---------- авторизация ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("role"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


@app.before_request
def load_ctx():
    g.role = session.get("role")
    g.role_name = ROLE_NAMES.get(g.role, "")
    g.depts = ROLE_DEPTS.get(g.role, [])
    g.is_admin = g.role == "admin"


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pwd = (request.form.get("password") or "").strip()
        role = ROLE_PASSWORDS.get(pwd)
        if role:
            session.clear()
            session["role"] = role
            with get_db() as db:
                log(db, role, "вход")
            return redirect(url_for("index"))
        flash("Неверный пароль", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def allowed_depts():
    return g.depts


def check_employee(db, emp_id):
    emp = db.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
    if not emp:
        abort(404)
    if emp["dept"] not in g.depts:
        abort(403)
    return emp


# ---------- главная ----------
@app.route("/")
@login_required
def index():
    with get_db() as db:
        period = current_period(db)
        q = ",".join("?" * len(g.depts))
        emps = db.execute(
            f"SELECT * FROM employees WHERE active=1 AND dept IN ({q}) ORDER BY dept, position, fio",
            g.depts,
        ).fetchall()
        saved = {
            r["employee_id"]: r
            for r in db.execute(
                "SELECT * FROM payroll WHERE period_id=?", (period["id"],)
            ).fetchall()
        }
    return render_template("index.html", employees=emps, period=period, saved=saved)


# ---------- сотрудники ----------
@app.route("/employees", methods=["GET", "POST"])
@login_required
def employees():
    with get_db() as db:
        if request.method == "POST":
            if not g.is_admin:
                abort(403)
            fio = request.form["fio"].strip()
            pos = request.form["position"]
            level = int(request.form.get("level") or 1)
            dept = calc_dept(pos)
            db.execute(
                "INSERT INTO employees (fio, position, level, dept, salary, active, created_at)"
                " VALUES (?,?,?,?,?,1, datetime('now'))",
                (fio, pos, level, dept, calc.DEFAULTS[pos].get("salary", 0)),
            )
            log(db, g.role, "добавил сотрудника", fio)
            return redirect(url_for("employees"))
        q = ",".join("?" * len(g.depts))
        rows = db.execute(
            f"SELECT * FROM employees WHERE active=1 AND dept IN ({q}) ORDER BY dept, fio",
            g.depts,
        ).fetchall()
    return render_template("employees.html", employees=rows,
                           positions=calc.FIELDS.keys(), deps=DEPARTMENTS)


def calc_dept(pos):
    from config import POSITIONS
    return POSITIONS[pos][1]


@app.post("/employees/<int:emp_id>/delete")
@login_required
def employee_delete(emp_id):
    if not g.is_admin:
        abort(403)
    with get_db() as db:
        db.execute("UPDATE employees SET active=0 WHERE id=?", (emp_id,))
        log(db, g.role, "удалил сотрудника", str(emp_id))
    return redirect(url_for("employees"))


# ---------- мотивация ----------
@app.route("/settings/<position>", methods=["GET", "POST"])
@login_required
def settings(position):
    if position not in calc.DEFAULTS:
        abort(404)
    with get_db() as db:
        if request.method == "POST":
            data = json.loads(request.form["payload"])
            save_settings(db, position, data)
            log(db, g.role, "изменил мотивацию", position)
            flash("Настройки сохранены", "ok")
            return redirect(url_for("settings", position=position))
        data = get_settings(db, position, calc.DEFAULTS[position])
    return render_template("settings.html", position=position, data=data,
                           common=calc.COMMON, defaults=calc.DEFAULTS[position])


# ---------- расчёт ----------
@app.route("/payroll/<int:emp_id>", methods=["GET", "POST"])
@login_required
def payroll(emp_id):
    with get_db() as db:
        emp = check_employee(db, emp_id)
        period = current_period(db)
        if period["closed"] and not g.is_admin:
            abort(403)

        row = db.execute(
            "SELECT * FROM payroll WHERE employee_id=? AND period_id=?",
            (emp_id, period["id"]),
        ).fetchone()
        inputs = json.loads(row["inputs"]) if row else {}

        if request.method == "POST":
            if period["closed"] and not g.is_admin:
                abort(403)
            raw = request.form.to_dict()
            if raw.get("action") == "pay":
                paid = num(raw.get("paid"))
                exists = db.execute(
                    "SELECT id FROM payroll WHERE employee_id=? AND period_id=?",
                    (emp_id, period["id"]),
                ).fetchone()
                if exists:
                    db.execute(
                        "UPDATE payroll SET paid=?, updated_at=datetime('now')"
                        " WHERE employee_id=? AND period_id=?",
                        (paid, emp_id, period["id"]),
                    )
                else:
                    result = calc.calc(emp["position"], emp["level"], {},
                                       load_settings(db, emp["position"]))
                    db.execute(
                        "INSERT INTO payroll (employee_id, period_id, inputs, calc, total, paid,"
                        " saved, updated_at) VALUES (?,?,?,?,?,?,0,datetime('now'))",
                        (emp_id, period["id"], "{}",
                         json.dumps(result, ensure_ascii=False), result["total"], paid),
                    )
                log(db, g.role, "начислил ЗП", f"{emp['fio']}: выплачено {paid}")
                flash("ЗП начислена", "ok")
                return redirect(url_for("payroll", emp_id=emp_id))

            inputs = {k: v for k, v in raw.items() if k not in ("action",)}
            result = calc.calc(emp["position"], emp["level"], inputs,
                               load_settings(db, emp["position"]))
            db.execute(
                "INSERT INTO payroll (employee_id, period_id, inputs, calc, total, paid, saved, updated_at)"
                " VALUES (?,?,?,?,?,COALESCE((SELECT paid FROM payroll WHERE employee_id=? AND period_id=?),0),1,datetime('now'))"
                " ON CONFLICT(employee_id, period_id) DO UPDATE SET"
                " inputs=excluded.inputs, calc=excluded.calc, total=excluded.total, saved=1,"
                " updated_at=excluded.updated_at",
                (emp_id, period["id"], json.dumps(inputs, ensure_ascii=False),
                 json.dumps(result, ensure_ascii=False), result["total"], emp_id, period["id"]),
            )
            log(db, g.role, "рассчитал", emp["fio"])
            flash("Расчёт сохранён в базу", "ok")
            row = db.execute(
                "SELECT * FROM payroll WHERE employee_id=? AND period_id=?",
                (emp_id, period["id"]),
            ).fetchone()

        result = None
        saved = None
        if row:
            inputs = json.loads(row["inputs"])
            saved = json.loads(row["calc"])
            if saved.get("components"):
                result = saved
            else:
                result = calc.calc(emp["position"], emp["level"], inputs,
                                   load_settings(db, emp["position"]))
        preview = calc.calc(emp["position"], emp["level"], inputs,
                            load_settings(db, emp["position"]))
        settings_data = load_settings(db, emp["position"])

    return render_template(
        "payroll.html", emp=emp, period=period, fields=calc.FIELDS[emp["position"]],
        inputs=inputs, result=preview, saved=row, settings=settings_data,
    )


def load_settings(db, position):
    return get_settings(db, position, calc.DEFAULTS[position])


# ---------- расчётные листки ----------
@app.route("/payslips")
@login_required
def payslips():
    with get_db() as db:
        period = current_period(db)
        q = ",".join("?" * len(g.depts))
        rows = db.execute(
            f"""SELECT e.*, p.total, p.paid, p.saved, p.inputs
                FROM employees e
                LEFT JOIN payroll p ON p.employee_id=e.id AND p.period_id=?
                WHERE e.active=1 AND e.dept IN ({q})
                ORDER BY e.dept, e.fio""",
            [period["id"], *g.depts],
        ).fetchall()
    return render_template("payslips.html", rows=rows, period=period)


@app.route("/payslips/pdf")
@login_required
def payslips_pdf():
    emps = collect_payslips()
    if not emps:
        flash("Нет сохранённых расчётов за период", "error")
        return redirect(url_for("payslips"))
    buf = io.BytesIO()
    exports.build_pdf(buf, emps, period_label())
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"raschetnye_listki_{period_label()}.pdf")


@app.route("/payslips/xlsx")
@login_required
def payslips_xlsx():
    emps = collect_payslips()
    if not emps:
        flash("Нет сохранённых расчётов за период", "error")
        return redirect(url_for("payslips"))
    buf = io.BytesIO()
    exports.build_xlsx(buf, emps, period_label())
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f"raschetnye_listki_{period_label()}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def collect_payslips():
    out = []
    with get_db() as db:
        period = current_period(db)
        q = ",".join("?" * len(g.depts))
        rows = db.execute(
            f"""SELECT e.fio, e.position, e.level, e.dept, p.calc, p.total, p.paid
                FROM employees e JOIN payroll p ON p.employee_id=e.id AND p.period_id=?
                WHERE e.active=1 AND e.dept IN ({q}) AND p.saved=1""",
            [period["id"], *g.depts],
        ).fetchall()
        from config import POSITIONS
        for r in rows:
            out.append({
                "fio": r["fio"],
                "position": POSITIONS[r["position"]][0],
                "dept": r["dept"],
                "calc": json.loads(r["calc"]),
                "total": r["total"],
                "paid": r["paid"],
            })
    return out


def period_label():
    with get_db() as db:
        p = current_period(db)
    months = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль",
              "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    return f"{months[p['month']]} {p['year']}"


# ---------- период ----------
@app.route("/period", methods=["GET", "POST"])
@login_required
def period():
    with get_db() as db:
        if request.method == "POST":
            action = request.form.get("action")
            year = int(request.form["year"])
            month = int(request.form["month"])
            p = ensure_period(db, year, month)
            if action == "close":
                if not g.is_admin:
                    abort(403)
                db.execute("UPDATE periods SET closed=1, closed_at=datetime('now') WHERE id=?",
                           (p["id"],))
                log(db, g.role, "закрыл период", f"{month}.{year}")
                flash(f"Период {month}.{year} закрыт", "ok")
            elif action == "open":
                if not g.is_admin:
                    abort(403)
                db.execute("UPDATE periods SET closed=0, closed_at=NULL WHERE id=?",
                           (p["id"],))
                log(db, g.role, "открыл период", f"{month}.{year}")
                flash("Период открыт", "ok")
            return redirect(url_for("period"))
        rows = db.execute("SELECT * FROM periods ORDER BY year DESC, month DESC").fetchall()
    return render_template("period.html", periods=rows)


# ---------- аналитика ----------
@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


@app.route("/api/analytics")
@login_required
def api_analytics():
    with get_db() as db:
        q = ",".join("?" * len(g.depts))
        rows = db.execute(
            f"""SELECT e.dept, e.position, e.fio, p.total, pe.year, pe.month
                FROM payroll p
                JOIN employees e ON e.id=p.employee_id
                JOIN periods pe ON pe.id=p.period_id
                WHERE p.saved=1 AND pe.closed=1 AND e.dept IN ({q})""",
            g.depts,
        ).fetchall()
    from config import DEPARTMENTS, POSITIONS
    dept_names = dict(DEPARTMENTS)
    months, depts, positions = [], {}, {}
    total = 0.0
    for r in rows:
        total += r["total"] or 0
        label = f"{r['year']}-{r['month']:02d}"
        if label not in months:
            months.append(label)
        dn = dept_names.get(r["dept"], r["dept"])
        depts.setdefault(dn, {})
        depts[dn][label] = depts[dn].get(label, 0) + (r["total"] or 0)
        pn = POSITIONS.get(r["position"], (r["position"], ""))[0]
        positions.setdefault(pn, {"sum": 0, "count": 0})
        positions[pn]["sum"] += r["total"] or 0
        positions[pn]["count"] += 1
    months.sort()
    return {
        "total": total,
        "months": months,
        "depts": [{"name": k, "data": [round(v.get(m, 0)) for m in months]}
                  for k, v in depts.items()],
        "positions": [{"name": k, "avg": round(v["sum"] / v["count"]) if v["count"] else 0,
                       "count": v["count"]} for k, v in positions.items()],
    }


@app.context_processor
def inject_globals():
    from config import POSITIONS
    return {
        "dept_names": dict(DEPARTMENTS),
        "role_names": ROLE_NAMES,
        "positions_names": {k: v[0] for k, v in POSITIONS.items()},
    }


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
