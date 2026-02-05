import os
import json
import io
import logging
import uuid
from datetime import datetime, timedelta

import requests
from fastapi import FastAPI, Depends, HTTPException, Body, Request, status, Cookie, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import OperationalError, IntegrityError
from pydantic import BaseModel, Field
from openai import AzureOpenAI
from PyPDF2 import PdfReader

from .database import engine, get_db
from .models import Base, Edital, User, Cliente
from .auth import verificar_senha, hash_senha, criar_token, get_current_user

# =========================
# Configuração de Ambiente
# =========================
ENV = os.getenv("ENV", "DEV") # 'PROD' ou 'DEV'
IS_PROD = ENV == "PROD"

# =========================
# App Initialization
# =========================
app = FastAPI(title="API de Editais + Chatbot")

@app.get("/ping")
def ping():
    return {"status": "ok", "time": datetime.utcnow().isoformat(), "env": ENV}

# =========================
# Logging
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# =========================
# Utils de URL
# =========================
def get_frontend_url():
    """
    Retorna a URL base do Frontend.
    Em PROD, deve ser a URL do Azure Static Web App ou similar.
    """
    return os.getenv("FRONTEND_URL", "http://127.0.0.1:8000/static/index.html")

def get_api_url():
    """
    Retorna a URL base da API.
    Necessário para gerar links de verificação de e-mail corretos.
    """
    return os.getenv("API_URL", "http://127.0.0.1:8000")

# =========================
# CORS
# =========================
# Lista base de origens permitidas
origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://editais.atimus.agr.br",
]

# Adiciona URL do Frontend configurada no ambiente (se houver)
frontend_env = os.getenv("FRONTEND_URL")
if frontend_env:
    # Remove path se houver (ex: http://site.com/index.html -> http://site.com)
    base_origin = "/".join(frontend_env.split("/")[:3])
    origins.append(base_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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

client: AzureOpenAI | None = None
if AZURE_API_KEY and AZURE_ENDPOINT and DEPLOYMENT_NAME:
    client = AzureOpenAI(
        api_key=AZURE_API_KEY,
        api_version=API_VERSION,
        azure_endpoint=AZURE_ENDPOINT
    )
    logger.info("Azure OpenAI configurado com sucesso.")
else:
    logger.warning("Azure OpenAI NÃO configurado.")

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

class LoginCliente(BaseModel):
    email: str
    senha: str

class ChatMessage(BaseModel):
    message: str

class CadastroCliente(BaseModel):
    nome: str
    email: str
    senha: str = Field(..., min_length=6, max_length=12)
    celular: str
    cnpj: str
    contato_ok: bool
    politica_ok: bool

# =========================
# Utils Auxiliares
# =========================
def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).split("T")[0], "%Y-%m-%d").date()
    except ValueError:
        return None

def simular_envio_email(email: str, token: str):
    api_base = get_api_url()
    link = f"{api_base}/cliente/verificar-email?token={token}"
    logger.info("====================================================")
    logger.info(f"[SIMULAÇÃO DE EMAIL] Para: {email}")
    logger.info(f"[AÇÃO] Clique no link para verificar: {link}")
    logger.info("====================================================")

# =========================
# Middleware de Log
# =========================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url}")
    response = await call_next(request)
    return response

# =========================
# Routes Public
# =========================
@app.get("/")
def root():
    return {"msg": "API Atimus Online. Acesse /index.html se estiver servindo estático ou configure o frontend.", "env": ENV}

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
            "share_link": f"{frontend_url}?id={r.id}"
        })

    return JSONResponse(content=lista)

# =========================
# Fluxo Cliente: Auth & Cadastro
# =========================
@app.get("/cliente/me")
def cliente_me(cliente_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not cliente_token:
        return {"logado": False}
    cliente = db.query(Cliente).filter(Cliente.token == cliente_token).first()
    if not cliente or not cliente.email_verificado:
        return {"logado": False}
    
    # Redireciona para o Front configurado
    redirect_url = get_frontend_url()
    return {"logado": True, "nome": cliente.nome, "redirect": redirect_url}

@app.post("/cliente/cadastro")
def cadastro_cliente(dados: CadastroCliente, db: Session = Depends(get_db)):
    existente = db.query(Cliente).filter(or_(Cliente.email == dados.email, Cliente.cnpj == dados.cnpj)).first()
    if existente:
        return JSONResponse(status_code=400, content={"detail": "E-mail ou CNPJ já cadastrados. Tente fazer login."})

    verificacao_token = str(uuid.uuid4())
    novo_cliente = Cliente(
        nome=dados.nome,
        email=dados.email,
        senha_hash=hash_senha(dados.senha),
        celular=dados.celular,
        cnpj=dados.cnpj,
        contato_ok=dados.contato_ok,
        politica_ok=dados.politica_ok,
        email_verificado=False,
        email_token=verificacao_token,
        email_token_expiration=datetime.utcnow() + timedelta(hours=24)
    )
    db.add(novo_cliente)
    db.commit()

    simular_envio_email(dados.email, verificacao_token)
    return {"sucesso": True, "msg": "Cadastro realizado! Verifique seu e-mail para ativar a conta."}

@app.post("/cliente/login")
def login_cliente(dados: LoginCliente, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.email == dados.email).first()
    if not cliente or not verificar_senha(dados.senha, cliente.senha_hash):
        return JSONResponse(status_code=401, content={"detail": "E-mail ou senha incorretos."}) 
    if not cliente.email_verificado:
        return JSONResponse(status_code=403, content={"detail": "Seu e-mail ainda não foi verificado. Verifique sua caixa de entrada."}) 

    sessao_token = str(uuid.uuid4())
    cliente.token = sessao_token
    db.commit()
    
    # URL de redirecionamento dinâmica
    frontend_url = get_frontend_url()
    
    response = JSONResponse(content={"redirect": frontend_url, "sucesso": True})
    
    # Ajuste de Cookies para Azure/Prod (HTTPS) vs Local (HTTP)
    # Em PROD (Azure), SameSite="None" e Secure=True são obrigatórios para cross-site cookies.
    samesite_mode = "None" if IS_PROD else "lax"
    secure_mode = True if IS_PROD else False
    
    response.set_cookie(
        key="cliente_token", 
        value=sessao_token, 
        httponly=True, 
        max_age=60*60*24*30, 
        samesite=samesite_mode, 
        secure=secure_mode
    )
    return response

@app.get("/cliente/verificar-email")
def verificar_email(token: str, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.email_token == token).first()
    if not cliente:
        return JSONResponse(status_code=400, content={"detail": "Token inválido ou não encontrado."}) 
    if cliente.email_token_expiration and datetime.utcnow() > cliente.email_token_expiration:
        return JSONResponse(status_code=400, content={"detail": "Este link de verificação expirou."}) 
    
    cliente.email_verificado = True
    cliente.email_token = None
    cliente.email_token_expiration = None
    db.commit()
    
    # Redireciona para o Front real com parâmetro de sucesso
    frontend_url = get_frontend_url()
    # Garante que frontend_url não aponte para arquivo específico se não quisermos, 
    # mas aqui assumimos que aponta para a página principal ou index.html
    sep = "&" if "?" in frontend_url else "?"
    return RedirectResponse(url=f"{frontend_url}{sep}verificado=true")

# =========================
# Chat Geral (Busca SQL)
# =========================
@app.post("/chat")
async def chat_search(msg: ChatMessage, db: Session = Depends(get_db)):
    if not msg.message or not msg.message.strip():
        return {"reply": "Me diga algo para eu procurar (ex: Inovação, Saúde, Finep)."}
    user_text = msg.message.strip()
    termos = [t for t in user_text.split() if len(t) > 2]
    if not termos:
        return {"reply": "Use palavras mais específicas como Inovação, Tecnologia, Saúde."}
    filtros = [or_(Edital.titulo.ilike(f"%{t}%"), Edital.json_data.ilike(f"%{t}%")) for t in termos]
    resultados = db.query(Edital).filter(or_(*filtros)).limit(5).all()
    if not resultados:
        return {"reply": "Não encontrei editais com esses termos. Tente algo mais geral."}
    return {"reply": "Encontrei estes editais:", "options": [{"id": r.id, "titulo": r.titulo} for r in resultados]}

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
    return {"msg": "Edital criado com sucesso", "id": novo.id, "share_link": f"{frontend_url}?id={novo.id}"}

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
