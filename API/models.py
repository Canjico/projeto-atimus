# API/models.py

from sqlalchemy import Column, Integer, String, Date, Text, DateTime, Boolean
from sqlalchemy.dialects.mssql import NVARCHAR
from datetime import datetime

from .database import Base

# =========================
# Models
# =========================

class Edital(Base):
    __tablename__ = "editais"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, index=True)
    
    # JSON armazenado como texto (decisão consciente)
    json_data = Column(Text)
    
    # Lista de arquivos serializada em JSON
    arquivos_json = Column(Text)
    
    data_final_submissao = Column(Date)
    pdf_url = Column(String)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(NVARCHAR(255), nullable=False, unique=True, index=True)
    senha_hash = Column(NVARCHAR(255), nullable=False)
    role = Column(NVARCHAR(50), nullable=False)


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True)
    nome = Column(NVARCHAR(255), nullable=False)
    email = Column(NVARCHAR(255), nullable=False, unique=True, index=True)
    celular = Column(NVARCHAR(50))
    cnpj = Column(NVARCHAR(20), nullable=False, unique=True)
    
    # Autenticação e Segurança
    senha_hash = Column(NVARCHAR(255), nullable=False)
    email_verificado = Column(Boolean, default=False)
    
    # Verificação de E-mail
    email_token = Column(NVARCHAR(255), unique=True, index=True)
    email_token_expiration = Column(DateTime, nullable=True)

    # Consentimento e Sessão
    contato_ok = Column(Boolean, default=False)
    politica_ok = Column(Boolean, default=False)
    
    token = Column(NVARCHAR(255), unique=True, index=True)  # Token de sessão (cookie)
    criado_em = Column(DateTime, default=datetime.utcnow)
