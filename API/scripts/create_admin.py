# =========================
# ARQUIVO: create_admin.py
# =========================

from API.auth import hash_senha
from API.models import User
from API.database import SessionLocal

EMAIL = "admin@atimus.com"
SENHA = "Atimus@Admin2025!"

db = SessionLocal()

admin = db.query(User).filter(User.email == EMAIL).first()

if admin:
    print("⚠️ Admin já existe")
else:
    novo_admin = User(
        email=EMAIL,
        senha_hash=hash_senha(SENHA),
        role="admin"
    )
    db.add(novo_admin)
    db.commit()
    print("✅ Admin criado com sucesso")

db.close()
