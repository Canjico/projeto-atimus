import os
import json
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone

import requests
from fastapi import FastAPI, Depends, HTTPException, Body, Request, status, Cookie, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_, text
from sqlalchemy.exc import OperationalError, IntegrityError
from pydantic import BaseModel, Field
from openai import AzureOpenAI
from PyPDF2 import PdfReader

from .database import engine, get_db
from .models import Base, Edital, User, Cliente
from .auth import verificar_senha, hash_senha, criar_token, get_current_user, gerar_reset_token, hash_token
from .email_service import enviar_email_verificacao, enviar_email_recuperacao

# =========================
# App Initialization
# =========================
app = FastAPI(title="API de Editais + Chatbot")

# =========================
# Logging
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# =========================
# Configurações de Ambiente (URLs)
# =========================
# IMPORTANTE: No Azure App Service (Production), configure estas variáveis:
# FRONTEND_LOGIN_URL = https://login.atimus.agr.br
# FRONTEND_APP_URL = https://editais.atimus.agr.br

FRONTEND_LOGIN_URL = os.getenv("FRONTEND_LOGIN_URL", "http://127.0.0.1:5500/index.html")
FRONTEND_APP_URL = os.getenv("FRONTEND_APP_URL", "http://127.0.0.1:5500/editais.html")

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://login.atimus.agr.br",   # frontend de login
        "https://editais.atimus.agr.br", # frontend de editais
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
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
    # Aumentado para 64 chars (Modern Standards)
    senha: str = Field(..., min_length=6, max_length=64)
    celular: str
    cnpj: str
    contato_ok: bool
    politica_ok: bool

class EsqueciSenhaRequest(BaseModel):
    email: str

class RedefinirSenhaRequest(BaseModel):
    token: str
    # Aumentado para 64 chars (Modern Standards)
    nova_senha: str = Field(..., min_length=6, max_length=64)

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

def mask_email(email: str) -> str:
    """
    Ofusca o e-mail para logs (LGPD/Privacy).
    Ex: admin@atimus.agr.br -> ad***@atimus.agr.br
    """
    if not email or "@" not in email:
        return "***"
    try:
        user, domain = email.split("@")
        if len(user) <= 2:
            return f"{user}***@{domain}"
        return f"{user[:2]}***@{domain}"
    except Exception:
        return "***@***"

def simular_envio_email(email: str, token: str, tipo: str = "verificacao"):
    # Fallback para caso o ACS não esteja configurado
    if tipo == "verificacao":
        base_api_url = os.getenv("BASE_API_URL", "http://127.0.0.1:8000")
        link = f"{base_api_url}/cliente/verificar-email?token={token}"
    else:
        # Recuperação
        if "?" in FRONTEND_LOGIN_URL:
            link = f"{FRONTEND_LOGIN_URL}&reset_token={token}"
        else:
            link = f"{FRONTEND_LOGIN_URL}?reset_token={token}"
    
    logger.info("====================================================")
    logger.info(f"[SIMULAÇÃO DE EMAIL - {tipo.upper()}] Para: {mask_email(email)}")
    logger.info(f"[AÇÃO] Clique no link: {link}")
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
# Routes Public / System
# =========================
@app.get("/ping")
def ping():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Verifica saúde dos componentes críticos: Banco de Dados e OpenAI.
    Útil para monitoramento em produção.
    """
    status_report = {"status": "ok", "components": {}}
    
    # Check Database
    try:
        # SQLAlchemy 2.0 requer text()
        db.execute(text("SELECT 1"))
        status_report["components"]["database"] = "healthy"
    except Exception as e:
        logger.error(f"Health Check Falhou (DB): {e}")
        status_report["status"] = "degraded"
        status_report["components"]["database"] = str(e)

    # Check Azure OpenAI
    if client:
        status_report["components"]["openai"] = "configured"
    else:
        status_report["components"]["openai"] = "not_configured"

    if status_report["status"] != "ok":
        return JSONResponse(status_code=503, content=status_report)
        
    return status_report

@app.get("/")
def root():
    return {"msg": "API Atimus Online. Acesse /index.html se estiver servindo estático ou configure o frontend."}

@app.get("/editais")
def listar_editais(db: Session = Depends(get_db)):
    resultados = db.query(Edital).all()
    # Share link aponta para a aplicação principal
    frontend_url = FRONTEND_APP_URL

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
    
    # Verifica existência e verificação de e-mail
    if not cliente or not cliente.email_verificado:
        return {"logado": False}
    
    now = datetime.now(timezone.utc)

    # Verifica expiração
    if cliente.token_expiration and now > cliente.token_expiration:
        return {"logado": False, "msg": "Sessão expirada"}
    
    # Renovação de Sessão (Rolling Session)
    # Se faltar menos de 5 dias para expirar, renova por mais 30 dias
    if cliente.token_expiration and (cliente.token_expiration - now).days < 5:
        cliente.token_expiration = now + timedelta(days=30)
        db.commit()
        logger.info(f"Sessão renovada para cliente {cliente.id} ({mask_email(cliente.email)})")
    
    # Retorna redirecionamento para o App Principal
    return {"logado": True, "nome": cliente.nome, "id": cliente.id, "redirect": FRONTEND_APP_URL}

@app.post("/cliente/cadastro")
def cadastro_cliente(dados: CadastroCliente, db: Session = Depends(get_db)):
    existente = db.query(Cliente).filter(or_(Cliente.email == dados.email, Cliente.cnpj == dados.cnpj)).first()
    if existente:
        return JSONResponse(status_code=400, content={"detail": "E-mail ou CNPJ já cadastrados. Tente fazer login."}) 

    verificacao_token = str(uuid.uuid4())
    
    # UX: Token expira em 72h (3 dias) para dar tempo ao usuário, conforme ajuste de produção
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
        email_token_expiration=datetime.now(timezone.utc) + timedelta(hours=72)
    )
    db.add(novo_cliente)
    db.commit()

    # Tenta enviar e-mail real via ACS
    enviado = enviar_email_verificacao(dados.email, verificacao_token)
    
    # Se não foi enviado (por falta de config), simula no log para dev local
    if not enviado:
        simular_envio_email(dados.email, verificacao_token, "verificacao")

    logger.info(f"Novo cadastro iniciado: {mask_email(dados.email)}")
    return {"sucesso": True, "msg": "Cadastro realizado! Verifique seu e-mail para ativar a conta."}

@app.post("/cliente/login")
def login_cliente(dados: LoginCliente, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.email == dados.email).first()
    if not cliente or not verificar_senha(dados.senha, cliente.senha_hash):
        logger.warning(f"Tentativa de login falha para: {mask_email(dados.email)}")
        return JSONResponse(status_code=401, content={"detail": "E-mail ou senha incorretos."}) 
    
    if not cliente.email_verificado:
        return JSONResponse(status_code=403, content={"detail": "Seu e-mail ainda não foi verificado. Verifique sua caixa de entrada."}) 

    sessao_token = str(uuid.uuid4())
    cliente.token = sessao_token
    # Define expiração para 30 dias (Segurança Corporativa)
    cliente.token_expiration = datetime.now(timezone.utc) + timedelta(days=30)
    
    # SECURITY: Se o usuário logou com senha, invalida qualquer pedido de recuperação pendente
    # Isso fecha o vetor onde um atacante poderia usar um token de reset antigo se tivesse acesso ao email
    if cliente.reset_token_hash:
        cliente.reset_token_hash = None
        cliente.reset_token_expiration = None

    db.commit()

    logger.info(f"Login sucesso: Cliente {cliente.id} ({mask_email(cliente.email)})")
    
    # Redireciona para o App Principal após login
    response = JSONResponse(content={"redirect": FRONTEND_APP_URL, "sucesso": True})
    
    # Ajuste para Cross-Site (Frontend no Storage/CDN e Backend no App Service)
    response.set_cookie(
        key="cliente_token",
        value=sessao_token,
        httponly=True,
        secure=True,     # obrigigatoriamente True em produção
        samesite="none"  # permite que seja usado entre subdomínios
    )

    return response

@app.get("/cliente/verificar-email")
def verificar_email(token: str, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.email_token == token).first()
    
    if not cliente:
        return JSONResponse(status_code=400, content={"detail": "Token inválido ou não encontrado."}) 
    
    # Segurança: Se já verificado, redireciona para Login sem processar novamente
    if cliente.email_verificado:
        return RedirectResponse(url=f"{FRONTEND_LOGIN_URL}?verificado=true")

    if cliente.email_token_expiration and datetime.now(timezone.utc) > cliente.email_token_expiration:
        return JSONResponse(status_code=400, content={"detail": "Este link de verificação expirou."}) 
    
    cliente.email_verificado = True
    cliente.email_token = None
    cliente.email_token_expiration = None
    db.commit()

    logger.info(f"E-mail verificado com sucesso: {mask_email(cliente.email)}")
    
    # Após verificar, manda para a tela de Login
    return RedirectResponse(url=f"{FRONTEND_LOGIN_URL}?verificado=true")

# =========================
# Recuperação de Senha (HARDENED)
# =========================
@app.post("/cliente/esqueci-senha")
def esqueci_senha(req: EsqueciSenhaRequest, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.email == req.email).first()
    
    msg_padrao = "Se este e-mail estiver cadastrado, você receberá um link de recuperação."

    if cliente:
        # Anti-flood e Timing Protection:
        # Se já existe um token válido recente, não envia outro.
        now = datetime.utcnow()  # Use UTC sem timezone
        if cliente.reset_token_expiration and now < cliente.reset_token_expiration:
             # Token ainda válido. Logamos e ignoramos para evitar spam/flood.
             # Retornamos sucesso para não indicar diferença.
             logger.warning(f"Solicitação de recuperação ignorada (token ativo): {mask_email(req.email)}")
             return {"msg": msg_padrao}

        # CLEANUP: Limpa token antigo explicitamente para evitar estado ambíguo
        cliente.reset_token_hash = None
        cliente.reset_token_expiration = None

        # Gera novo token raw (para enviar) e hash (para salvar)
        raw_token = gerar_reset_token()
        hashed_token = hash_token(raw_token)

        cliente.reset_token_hash = hashed_token
        # Token expira em 30 min (Segurança) → convertido para naive datetime
        cliente.reset_token_expiration = (now + timedelta(minutes=30)).replace(tzinfo=None)
        db.commit()

        # Envia o token RAW por e-mail (link único)
        enviado = enviar_email_recuperacao(cliente.email, raw_token)
        if not enviado:
             simular_envio_email(cliente.email, raw_token, "recuperacao")

    return {"msg": msg_padrao}


@app.post("/cliente/redefinir-senha")
def redefinir_senha(req: RedefinirSenhaRequest, db: Session = Depends(get_db)):
    # 1. Validação Redundante de Tamanho de Senha (Backend Enforcement)
    if len(req.nova_senha) < 6 or len(req.nova_senha) > 64:
        raise HTTPException(status_code=400, detail="A senha deve ter entre 6 e 64 caracteres.")

    # 2. Busca o usuário pelo HASH do token recebido
    # MELHORIA: Validação de expiração DIRETAMENTE NO SQL
    # Evita race conditions e garante que o banco só retorne se for válido
    hashed_input = hash_token(req.token)
    
    cliente = db.query(Cliente).filter(
        Cliente.reset_token_hash == hashed_input,
        Cliente.reset_token_expiration > datetime.now(timezone.utc)
    ).first()
    
    if not cliente:
        # Se não achou, pode ser token inválido ou expirado (já filtrado no SQL)
        return JSONResponse(status_code=400, content={"detail": "Link inválido ou expirado. Solicite um novo."}) 
    
    # 3. Atualiza a senha
    cliente.senha_hash = hash_senha(req.nova_senha)
    
    # 4. Invalida Sessões Ativas (Segurança Crítica)
    # Força logout em todos os dispositivos ao trocar a senha
    cliente.token = None
    cliente.token_expiration = None

    # 5. Limpa o token de recuperação (Single Use)
    cliente.reset_token_hash = None
    cliente.reset_token_expiration = None
    db.commit()

    logger.info(f"Senha redefinida com sucesso para o cliente {cliente.id}. Sessões invalidadas.")
    return {"msg": "Senha redefinida com sucesso. Faça login agora."}


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
    
    # TODO: Para escalar, implementar chunking e embeddings (Vector Search).
    # Atualmente truncamos para evitar estouro de tokens/memória.
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
    # Retorna link para a aplicação principal
    frontend_url = FRONTEND_APP_URL
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
