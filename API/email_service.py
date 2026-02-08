import os
import logging
from azure.communication.email import EmailClient

logger = logging.getLogger("api.email")

# =========================
# Configurações ACS
# =========================

# ATENÇÃO: NUNCA commitar chaves reais aqui. 
# A Connection String deve vir das Variáveis de Ambiente (App Service Configuration ou .env local).
AZURE_ACS_CONNECTION_STRING = os.getenv("AZURE_ACS_CONNECTION_STRING")

# O remetente deve ser o endereço provisionado no Azure ou domínio verificado
# Ex: DoNotReply@<guid>.azurecomm.net ou noreply@atimus.agr.br
SENDER_EMAIL = os.getenv("AZURE_ACS_SENDER_ADDRESS")

# URL base da API para compor o link de verificação
# Em produção: https://api.atimus.agr.br (ou URL do App Service)
# Local: http://127.0.0.1:8000
BASE_API_URL = os.getenv("BASE_API_URL", "http://127.0.0.1:8000")

def enviar_email_verificacao(destinatario: str, token: str) -> bool:
    """
    Envia o e-mail de verificação usando Azure Communication Services.
    Retorna True se enviado, False se as chaves não estiverem configuradas ou houver erro.
    """
    # Validação de segurança: Se não houver config, não tenta enviar e não quebra o app.
    if not AZURE_ACS_CONNECTION_STRING or not SENDER_EMAIL:
        logger.warning("AZURE_ACS_CONNECTION_STRING ou SENDER_EMAIL não configurados. E-mail real ignorado.")
        return False

    try:
        client = EmailClient.from_connection_string(AZURE_ACS_CONNECTION_STRING)
        
        # Garante que a URL não termine com barra para evitar // no link
        base_url = BASE_API_URL.rstrip('/')
        link_verificacao = f"{base_url}/cliente/verificar-email?token={token}"
        
        logger.info(f"Iniciando envio de e-mail para {destinatario} via ACS...")

        message = {
            "senderAddress": SENDER_EMAIL,
            "recipients":  {
                "to": [{"address": destinatario}]
            },
            "content": {
                "subject": "Verificação de Email - Atimus",
                "plainText": f"Bem-vindo à Atimus! Clique no link para verificar seu e-mail: {link_verificacao}",
                "html": f"""
                <html>
                    <body style="font-family: Arial, sans-serif; color: #333;">
                        <div style="background-color: #f8fafc; padding: 20px; border-radius: 8px;">
                            <h1 style="color: #1e293b;">Bem-vindo à Atimus</h1>
                            <p>Obrigado por se cadastrar. Para ativar sua conta e acessar os editais, clique no botão abaixo:</p>
                            <p style="margin: 30px 0;">
                                <a href="{link_verificacao}" style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                                    Verificar Meu E-mail
                                </a>
                            </p>
                            <p style="font-size: 12px; color: #64748b;">
                                Ou cole este link no seu navegador: <br>
                                {link_verificacao}
                            </p>
                        </div>
                    </body>
                </html>
                """
            }
        }

        poller = client.begin_send(message)
        result = poller.result()
        
        # Tenta obter o ID da mensagem de forma segura
        msg_id = getattr(result, 'message_id', None)
        if not msg_id and isinstance(result, dict):
            msg_id = result.get('messageId')
        
        logger.info(f"E-mail enviado com sucesso! MessageId: {msg_id or 'desconhecido'}")
        return True

    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao enviar e-mail via ACS: {e}")
        # Não lançamos exceção para não quebrar o fluxo de cadastro no front,
        # mas logamos o erro crítico para monitoramento.
        return False
