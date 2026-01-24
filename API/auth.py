# API/auth.py

import os
from datetime import datetime, timedelta
from typing import Dict

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext

# =========================
# Configurações JWT
# =========================

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

# Não derruba a aplicação no import
JWT_SECRET = os.getenv("JWT_SECRET", "")

# =========================
# Segurança
# =========================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

bearer_scheme = HTTPBearer(auto_error=True)

# =========================
# Utilitários
# =========================

def _get_jwt_secret() -> str:
    """
    Retorna o segredo JWT.
    Lança erro apenas no uso, não no import.
    """
    if not JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET não configurado no ambiente"
        )
    return JWT_SECRET

# =========================
# Hash de senha
# =========================

def hash_senha(senha: str) -> str:
    """
    Gera hash bcrypt da senha.
    Limita em 72 chars (limite do bcrypt).
    """
    return pwd_context.hash(senha[:72])

def verificar_senha(senha: str, senha_hash: str) -> bool:
    """
    Verifica se a senha confere com o hash.
    """
    return pwd_context.verify(senha[:72], senha_hash)

# =========================
# JWT
# =========================

def criar_token(dados: Dict) -> str:
    """
    Cria token JWT com expiração.
    """
    secret = _get_jwt_secret()

    payload = dados.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload.update({"exp": expire})

    return jwt.encode(payload, secret, algorithm=ALGORITHM)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> Dict:
    """
    Dependency do FastAPI para recuperar usuário a partir do JWT.
    """
    secret = _get_jwt_secret()
    token = credentials.credentials

    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado"
        )
