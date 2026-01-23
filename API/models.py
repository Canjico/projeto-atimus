from sqlalchemy import Column, Integer, String, Date, Text
from sqlalchemy.dialects.mssql import NVARCHAR
from database import Base

class Edital(Base):
    __tablename__ = "editais"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, index=True)
    json_data = Column(Text, index=True)
    arquivos_json = Column(Text)
    data_final_submissao = Column(Date)
    pdf_url = Column(String)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(NVARCHAR(255), nullable=False, unique=True)
    senha_hash = Column(NVARCHAR(255), nullable=False)
    role = Column(NVARCHAR(50), nullable=False)