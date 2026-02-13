# API/models.py

from sqlalchemy import Column, Integer, String, Date, Text, DateTime, Boolean
from sqlalchemy.dialects.mssql import NVARCHAR
from datetime import datetime

from .database import Base

# =========================
# Models (Production Ready)
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
    # index=True explicitamente para buscas rápidas no login
    email = Column(NVARCHAR(255), nullable=False, unique=True, index=True)
    celular = Column(NVARCHAR(50))
    
    # index=True adicionado para otimizar validação de unicidade no cadastro
    cnpj = Column(NVARCHAR(20), nullable=False, unique=True, index=True)
    
    # Autenticação e Segurança
    senha_hash = Column(NVARCHAR(255), nullable=False)
    email_verificado = Column(Boolean, default=False)
    
    # Verificação de E-mail
    # Unique=True + Index=True: garante performance na busca pelo token de verificação
    email_token = Column(NVARCHAR(255), unique=True, index=True)
    
    # Removido timezone=True para compatibilidade com DATETIME do SQL Server
    email_token_expiration = Column(DateTime, nullable=True)

    # Recuperação de Senha (HARDENING)
    # Armazenamos apenas o HASH do token. Se o banco vazar, o token raw continua seguro.
    reset_token_hash = Column(NVARCHAR(255), nullable=True, index=True)
    reset_token_expiration = Column(DateTime, nullable=True)

    # Consentimento e Sessão
    contato_ok = Column(Boolean, default=False)
    politica_ok = Column(Boolean, default=False)
    
    # Token de sessão (cookie)
    token = Column(NVARCHAR(255), unique=True, index=True)
    token_expiration = Column(DateTime, nullable=True)
    
    # Sempre UTC para consistência (Naive datetime)
    criado_em = Column(DateTime, default=datetime.utcnow)
