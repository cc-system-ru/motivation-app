import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "motivation.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-9f3a")

# Пароли ролей (как в ТЗ)
ROLE_PASSWORDS = {
    "KD20": "kd",       # Коммерческий департамент
    "OD20": "od",       # Операционный департамент
    "admin": "admin",   # Администратор
}

ROLE_NAMES = {
    "kd": "Коммерческий департамент",
    "od": "Операционный департамент",
    "admin": "Администратор",
}

# Какие департаменты видит роль. admin — все.
ROLE_DEPTS = {
    "kd": ["commercial"],
    "od": ["operations"],
    "admin": ["commercial", "operations", "admin_dept", "security"],
}

DEPARTMENTS = [
    ("commercial", "Коммерческий департамент"),
    ("operations", "Операционный департамент"),
    ("admin_dept", "Административный отдел"),
    ("security", "Служба безопасности"),
]

# Должности: код -> (название, департамент)
POSITIONS = {
    "kd":      ("Коммерческий директор", "commercial"),
    "mop":     ("МОП", "commercial"),
    "od":      ("Операционный директор", "operations"),
    "and":     ("Андеррайтер", "operations"),
    "and_sr":  ("Старший андеррайтер", "operations"),
    "rep":     ("Региональный представитель", "operations"),
    "sb":      ("Служба безопасности", "security"),
    "adm":     ("Администратор офиса", "admin_dept"),
}
