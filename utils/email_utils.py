from flask import current_app
from flask_mail import Message
import re
# Você precisará inicializar a extensão Mail no seu app principal (app.py ou similar)
# from flask_mail import Mail
# mail = Mail(app)

def enviar_email(destinatario, assunto, corpo_html, corpo_texto='', anexos=None):
    """
    Envia um e-mail usando a configuração do Flask-Mail.

    Args:
        destinatario (str or list): O endereço de e-mail do destinatário ou uma lista de endereços.
        assunto (str): O assunto do e-mail.
        corpo_html (str): O corpo do e-mail em formato HTML.
        corpo_texto (str, optional): O corpo do e-mail em texto puro (fallback). Defaults to ''.
        anexos (list, optional): Lista de tuplas para anexos. 
                                 Cada tupla deve ser (nome_arquivo, content_type, dados_binarios).
                                 Ex: [('solicitacao.pdf', 'application/pdf', pdf_bytes)]. 
                                 Defaults to None.

    Returns:
        bool: True se o e-mail foi enviado com sucesso (ou enfileirado), False caso contrário.
    """
    mail = current_app.extensions.get('mail')
    if not mail:
        current_app.logger.error("Flask-Mail não inicializado ou configurado.")
        return False
        
    # Garante que temos um corpo de texto, mesmo que básico
    if not corpo_texto:
        corpo_texto = re.sub('<[^<]+?>', '', corpo_html) # Remove tags HTML

    # Garante que destinatario seja uma lista
    if isinstance(destinatario, str):
        recipients = [destinatario]
    elif isinstance(destinatario, list):
        recipients = destinatario
    else:
        current_app.logger.error(f"Tipo inválido para destinatario: {type(destinatario)}")
        return False
        
    msg = Message(
        assunto,
        sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'default@sender.com'), # Usar o remetente padrão configurado
        recipients=recipients
    )
    msg.body = corpo_texto
    msg.html = corpo_html
    
    # Adicionar anexos
    if anexos:
        if not isinstance(anexos, list):
            anexos = [anexos] # Trata caso passe apenas uma tupla
            
        for anexo in anexos:
            try:
                nome_arquivo, content_type, dados = anexo
                msg.attach(nome_arquivo, content_type, dados)
            except Exception as e:
                current_app.logger.error(f"Erro ao anexar arquivo '{nome_arquivo if 'nome_arquivo' in locals() else 'desconhecido'}': {e}")
                # Decide se quer falhar o envio ou apenas logar e continuar
                return False # Falha o envio se não conseguir anexar

    try:
        mail.send(msg)
        current_app.logger.info(f"E-mail enviado para {recipients} com assunto '{assunto}'")
        return True
    except Exception as e:
        current_app.logger.error(f"Falha ao enviar e-mail para {recipients}: {e}")
        return False

# Exemplo de como inicializar no app.py:
# from flask import Flask
# from flask_mail import Mail

# app = Flask(__name__)
# Configurações do Flask-Mail (EXEMPLO - use suas configurações reais!)
# app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
# app.config['MAIL_PORT'] = 587
# app.config['MAIL_USE_TLS'] = True
# app.config['MAIL_USERNAME'] = 'seu_email@gmail.com'  # Ou pegue de variáveis de ambiente
# app.config['MAIL_PASSWORD'] = 'sua_senha_de_app' # Ou pegue de variáveis de ambiente
# app.config['MAIL_DEFAULT_SENDER'] = ('Nome Remetente', 'seu_email@gmail.com')

# mail = Mail(app) 