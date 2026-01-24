import os
import json
import io
import logging
from datetime import datetime

import requests
from fastapi import FastAPI, Depends, HTTPException, Body, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import OperationalError
from pydantic import BaseModel
from openai import AzureOpenAI
from PyPDF2 import PdfReader

from .database import engine, get_db
from .models import Base, Edital, User
from .auth import verificar_senha, criar_token, get_current_user

app = FastAPI()

@app.get("/ping")
def ping():
    return {"status": "ok", "message": "API no ar!"}

# =========================
# Logging
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# =========================
# App
# =========================
app = FastAPI(title="API de Editais + Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Azure OpenAI Config
# =========================
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

# Cliente AzureOpenAI com validação
client: AzureOpenAI | None = None
if AZURE_API_KEY and AZURE_ENDPOINT and DEPLOYMENT_NAME:
    client = AzureOpenAI(
        api_key=AZURE_API_KEY,
        api_version=API_VERSION,
        azure_endpoint=AZURE_ENDPOINT
    )
    logger.info("Azure OpenAI configurado com sucesso.")
else:
    logger.warning(
        "Azure OpenAI NÃO configurado. "
        "Defina AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT e AZURE_OPENAI_DEPLOYMENT."
    )

# =========================
# Startup
# =========================
@app.on_event("startup")
def startup():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Banco de dados pronto.")
    except OperationalError as e:
        logger.error(f"Erro ao conectar no banco: {e}")

# =========================
# Models (Pydantic)
# =========================
class LoginAdmin(BaseModel):
    email: str
    senha: str

class ChatMessage(BaseModel):
    message: str

# =========================
# Utils
# =========================
def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).split("T")[0], "%Y-%m-%d").date()
    except ValueError:
        return None

def get_frontend_url():
    return os.getenv("FRONTEND_URL", "https://seusite.com/index.html?id=")

# =========================
# Middleware de Log
# =========================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url}")
    response = await call_next(request)
    return response

# =========================
# Routes
# =========================
@app.get("/editais")
def listar_editais(db: Session = Depends(get_db)):
    resultados = db.query(Edital).all()
    frontend_url = get_frontend_url()

    lista = []
    for r in resultados:
        try:
            json_data = json.loads(r.json_data) if r.json_data else {}
        except Exception:
            json_data = {}

        try:
            arquivos = json.loads(r.arquivos_json) if r.arquivos_json else []
        except Exception:
            arquivos = []

        if not arquivos and r.pdf_url:
            arquivos.append({
                "nome": "Edital Completo (PDF)",
                "url": r.pdf_url
            })

        lista.append({
            "id": r.id,
            "titulo": r.titulo,
            "json_data": json_data,
            "arquivos_json": arquivos,
            "data_final_submissao": str(r.data_final_submissao) if r.data_final_submissao else None,
            "share_link": f"{frontend_url}{r.id}"
        })

    return JSONResponse(content=lista)

# =========================
# Chat Geral (Busca SQL)
# =========================
@app.post("/chat")
async def chat_search(msg: ChatMessage, db: Session = Depends(get_db)):
    if not msg.message or not msg.message.strip():
        return {"reply": "Me diga algo para eu procurar (ex: Inovação, Saúde, Finep)."}

    user_text = msg.message.strip()
    text_lower = user_text.lower()

    greetings = ["oi", "ola", "olá", "bom dia", "boa tarde", "boa noite", "opa", "eai", "tudo bem", "help", "ajuda"]
    if text_lower in greetings or len(text_lower) < 3:
        return {
            "reply": (
                "Olá! 👋 Sou seu assistente de editais. "
                "Digite um tema ou palavra-chave."
            )
        }

    termos = [t for t in user_text.split() if len(t) > 2]
    if not termos:
        return {
            "reply": (
                "Use palavras mais específicas como "
                "Inovação, Tecnologia, Saúde."
            )
        }

    filtros = []
    for t in termos:
        filtros.append(Edital.titulo.ilike(f"%{t}%"))
        filtros.append(Edital.json_data.ilike(f"%{t}%"))

    resultados = db.query(Edital).filter(or_(*filtros)).limit(5).all()
    if not resultados:
        return {
            "reply": (
                "Não encontrei editais com esses termos. "
                "Tente algo mais geral."
            )
        }

    return {
        "reply": "Encontrei estes editais:",
        "options": [{"id": r.id, "titulo": r.titulo} for r in resultados]
    }

# =========================
# Chat por Edital (RAG PDF)
# =========================
@app.post("/chat/edital/{edital_id}")
async def chat_edital(edital_id: int, msg: ChatMessage, db: Session = Depends(get_db)):
    if not client:
        return {"reply": "Chat indisponível no momento. (Azure OpenAI não configurado)."}

    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        return {"reply": "Edital não encontrado."}

    try:
        arquivos = json.loads(edital.arquivos_json) if edital.arquivos_json else []
    except Exception:
        arquivos = []

    if not arquivos and edital.pdf_url:
        arquivos.append({"url": edital.pdf_url})

    pdf_urls = [a.get("url") for a in arquivos if a.get("url", "").lower().endswith(".pdf")]
    if not pdf_urls:
        return {"reply": "Este edital não possui PDF."}

    texto = ""
    for url in pdf_urls:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                reader = PdfReader(io.BytesIO(r.content))
                for page in reader.pages:
                    texto += page.extract_text() or ""
        except Exception as e:
            logger.error(f"Erro ao ler PDF {url}: {e}")

    if not texto.strip():
        return {"reply": "Não consegui extrair texto do edital."}

    texto = texto[:200_000]

    response = client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=[
            {"role": "system", "content": "Você é um assistente especializado em editais. Responda apenas com base no texto fornecido."},
            {"role": "user", "content": f"Pergunta: {msg.message}\n\n{texto}"}
        ],
        max_completion_tokens=2048
    )

    return {"reply": response.choices[0].message.content}

# =========================
# Admin
# =========================
@app.post("/admin/login")
def login_admin(login: LoginAdmin = Body(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login.email).first()
    if not user or not verificar_senha(login.senha, user.senha_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    token = criar_token({"sub": user.email, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/admin/protected")
def admin_area(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito")
    return {"msg": f"Bem-vindo, {user['sub']}!"}

# =========================
# CRUD Editais (Admin)
# =========================
@app.post("/admin/editais")
def criar_edital(dados: dict = Body(...), db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    attachments = dados.get("attachments", [])
    conteudo = dados.copy()
    conteudo.pop("attachments", None)

    novo = Edital(
        titulo=dados.get("titulo", "Sem Título"),
        data_final_submissao=parse_date(dados.get("data_final_submissao")),
        pdf_url=attachments[0].get("url") if attachments else "",
        json_data=json.dumps(conteudo),
        arquivos_json=json.dumps(attachments)
    )

    db.add(novo)
    db.commit()
    db.refresh(novo)

    frontend_url = get_frontend_url()
    return {"msg": "Edital criado com sucesso", "id": novo.id, "share_link": f"{frontend_url}{novo.id}"}

@app.put("/admin/editais/{edital_id}")
def atualizar_edital(edital_id: int, dados: dict = Body(...), db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")

    attachments = dados.get("attachments", [])
    conteudo = dados.copy()
    conteudo.pop("attachments", None)

    edital.titulo = dados.get("titulo", edital.titulo)
    edital.data_final_submissao = parse_date(dados.get("data_final_submissao"))
    if attachments:
        edital.pdf_url = attachments[0].get("url")
    edital.json_data = json.dumps(conteudo)
    edital.arquivos_json = json.dumps(attachments)

    db.commit()
    return {"msg": "Edital atualizado com sucesso"}
