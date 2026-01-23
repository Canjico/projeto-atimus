import os
import json
import logging
import requests
import io
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Body, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import OperationalError
from database import engine, get_db
from models import Base, Edital, User
from auth import verificar_senha, criar_token, get_current_user
from pydantic import BaseModel
from openai import AzureOpenAI
from PyPDF2 import PdfReader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# Config Azure OpenAI via ENV
# =========================
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

if not AZURE_API_KEY or not AZURE_ENDPOINT or not DEPLOYMENT_NAME:
    raise RuntimeError("Variáveis Azure OpenAI não configuradas no App Service")

client = AzureOpenAI(
    api_key=AZURE_API_KEY,
    api_version=API_VERSION,
    azure_endpoint=AZURE_ENDPOINT
)

app = FastAPI(title="API de Editais + Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    Base.metadata.create_all(bind=engine)
    logger.info("Banco de Dados conectado com sucesso.")
except OperationalError as e:
    logger.error(f"Erro de Conexão: {e}")
    logger.error("Verifique firewall do Azure SQL Server.")

class LoginAdmin(BaseModel):
    email: str
    senha: str

class ChatMessage(BaseModel):
    message: str

@app.get("/editais")
def listar_editais(db: Session = Depends(get_db)):
    resultados = db.query(Edital).all()
    
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://seusite.com/index.html?id=")

    lista_formatada = []
    for r in resultados:
        try:
            data_dict = json.loads(r.json_data) if r.json_data and isinstance(r.json_data, str) else (r.json_data or {})
        except Exception:
            data_dict = {}

        try:
            arquivos_list = json.loads(r.arquivos_json) if r.arquivos_json and isinstance(r.arquivos_json, str) else (r.arquivos_json or [])
        except Exception:
            arquivos_list = []
            
        if not arquivos_list and r.pdf_url:
            arquivos_list.append({"nome": "Edital Completo (PDF)", "url": r.pdf_url})

        share_link = f"{FRONTEND_URL}{r.id}"

        item = {
            "id": r.id,
            "json_data": data_dict,
            "arquivos_json": arquivos_list,
            "titulo": r.titulo,
            "data_final_submissao": str(r.data_final_submissao) if r.data_final_submissao else None,
            "share_link": share_link
        }
        lista_formatada.append(item)
    return JSONResponse(content=lista_formatada)

@app.post("/chat")
async def chat_search(msg: ChatMessage, db: Session = Depends(get_db)):
    try:
        user_text = msg.message.strip()
        text_lower = user_text.lower()

        greetings = ["oi", "ola", "olá", "bom dia", "boa tarde", "boa noite", "opa", "eai", "tudo bem", "help", "ajuda"]
        
        if text_lower in greetings or (len(text_lower) < 3 and text_lower not in ["ia", "ai"]):
            return {
                "reply": "Olá! 👋 Sou seu assistente de editais. Me diga um tema ou palavra-chave e eu encontro as melhores oportunidades!"
            }

        termos = user_text.split()
        termos_busca = [t for t in termos if len(t) > 2]
        
        if not termos_busca:
            return {"reply": "Tente palavras mais específicas como: Inovação, Saúde, Tecnologia, Educação."}

        query = db.query(Edital)
        filtros = []
        for t in termos_busca:
            filtros.append(Edital.titulo.ilike(f"%{t}%"))
            filtros.append(Edital.json_data.ilike(f"%{t}%"))
        
        query = query.filter(or_(*filtros))
        resultados = query.limit(5).all()

        if not resultados:
            return {
                "reply": (
                    "Ainda não encontrei editais com esses termos.\n"
                    "Tente palavras mais gerais como: Inovação, Tecnologia, Saúde, Educação."
                )
            }

        opcoes = [{"id": r.id, "titulo": r.titulo} for r in resultados]
        return {
            "reply": "Encontrei estes editais! Selecione um para eu ler o documento e responder suas dúvidas:",
            "options": opcoes
        }

    except Exception as e:
        logger.error(f"Erro no chat search: {e}")
        return {"reply": "Erro técnico. Tente novamente mais tarde.", "details": str(e)}

@app.post("/chat/edital/{edital_id}")
async def chat_edital(edital_id: int, msg: ChatMessage, db: Session = Depends(get_db)):
    try:
        edital = db.query(Edital).filter(Edital.id == edital_id).first()
        if not edital:
            return {"reply": "Edital não encontrado."}

        try:
            arquivos = json.loads(edital.arquivos_json) if edital.arquivos_json else []
        except:
            arquivos = []
        
        if not arquivos and edital.pdf_url:
            arquivos.append({"url": edital.pdf_url})

        pdf_urls = [a.get("url") for a in arquivos if a.get("url") and ".pdf" in a.get("url", "").lower()]

        if not pdf_urls:
            return {"reply": "Este edital não possui PDF anexado."}

        texto_contexto = ""
        max_pages = 1000
        
        for url in pdf_urls:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    f = io.BytesIO(response.content)
                    reader = PdfReader(f)
                    paginas_ler = min(len(reader.pages), max_pages)
                    for i in range(paginas_ler):
                        texto_contexto += reader.pages[i].extract_text() + "\n"
            except Exception as e:
                logger.error(f"Erro ao ler PDF {url}: {e}")
                continue

        if not texto_contexto.strip():
            return {"reply": "Não consegui extrair texto do edital."}

        texto_contexto = texto_contexto[:200000]

        system_prompt = (
            "Você é um assistente especializado em editais. "
            "Responda apenas com base no texto do edital abaixo. "
            "Se não estiver no texto, diga que não encontrou."
        )

        user_prompt = f"Pergunta: {msg.message}\n\n--- TEXTO DO EDITAL ---\n{texto_contexto}"

        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=50000
        )
        
        reply = response.choices[0].message.content
        return {"reply": reply}

    except Exception as e:
        logger.error(f"Erro na análise do edital: {e}")
        return {"reply": "Erro ao analisar o documento.", "details": str(e)}

@app.post("/admin/login")
def login_admin(login: LoginAdmin = Body(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login.email).first()
    if not user or not verificar_senha(login.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    token = criar_token({"sub": user.email, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/admin/protected")
def admin_area(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")
    return {"msg": f"Bem-vindo, {user['sub']}!"}

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url}")
    response = await call_next(request)
    return response

@app.post("/admin/editais")
def criar_edital(dados: dict = Body(...), db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    attachments = dados.get("attachments", [])
    dados_conteudo = dados.copy()
    if "attachments" in dados_conteudo: 
        del dados_conteudo["attachments"]

    titulo = dados.get("titulo", "Sem Título")
    data_submissao = parse_date(dados.get("data_final_submissao"))
    
    pdf_url = ""
    if attachments and len(attachments) > 0:
        pdf_url = attachments[0].get("url", "")

    novo_edital = Edital(
        titulo=titulo,
        data_final_submissao=data_submissao,
        pdf_url=pdf_url,
        json_data=json.dumps(dados_conteudo),
        arquivos_json=json.dumps(attachments)
    )

    db.add(novo_edital)
    db.commit()
    db.refresh(novo_edital)

    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://seusite.com/index.html?id=")
    share_link = f"{FRONTEND_URL}{novo_edital.id}"

    return {"msg": "Edital criado com sucesso", "id": novo_edital.id, "share_link": share_link}

@app.put("/admin/editais/{edital_id}")
def atualizar_edital(edital_id: int, dados: dict = Body(...), db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")

    attachments = dados.get("attachments", [])
    dados_conteudo = dados.copy()
    if "attachments" in dados_conteudo: 
        del dados_conteudo["attachments"]

    edital.titulo = dados.get("titulo", edital.titulo)
    edital.data_final_submissao = parse_date(dados.get("data_final_submissao"))
    
    if attachments:
        edital.pdf_url = attachments[0].get("url", "")
    
    edital.json_data = json.dumps(dados_conteudo)
    edital.arquivos_json = json.dumps(attachments)

    db.commit()
    return {"msg": "Edital atualizado com sucesso"}

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).split('T')[0], "%Y-%m-%d").date()
    except ValueError:
        return None