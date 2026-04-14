from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import logging

# Configurar logger
logger = logging.getLogger(__name__)

# Criar instância do SQLAlchemy
db = SQLAlchemy()
migrate = None

def init_app(app):
    """
    Inicializa a extensão SQLAlchemy com a aplicação Flask
    """
    global migrate
    db.init_app(app)
    migrate = Migrate(app, db)
    logger.info("SQLAlchemy e Migrate inicializados com a aplicação Flask.")

def init_db():
    """
    Inicializa o banco de dados, criando as tabelas conforme os modelos
    e configurando dados iniciais se necessário.
    """
    logger.info("Inicializando banco de dados...")
    
    # Criar todas as tabelas se não existirem
    #logger.info("Criando tabelas se não existirem...")
    #db.create_all()
    #logger.info("Tabelas criadas/verificadas com sucesso!")
    
    # Verificar e criar usuário admin se não existir
    #criar_usuario_admin()
    
    logger.info("Inicialização do banco de dados concluída com sucesso!")

def criar_usuario_admin():
    """
    Cria um usuário administrador padrão se não existir
    """
    try:
        # Precisa importar aqui para evitar importação circular
        from models.usuario import Usuario
        
        # Verifica se o usuário admin já existe
        admin = Usuario.query.filter_by(email='admin@exemplo.com').first()
        if admin is None:
            logger.info("Criando usuário administrador padrão...")
            
            # Criar o usuário admin
            admin = Usuario(
                nome='Administrador',
                email='admin@exemplo.com',
                senha=Usuario.hash_password('admin123'),
                cargo='admin',
                departamento='Administrativo',
            )
            
            # Adicionar e confirmar no banco de dados
            db.session.add(admin)
            db.session.commit()
            logger.info("Usuário administrador criado com sucesso!")
        else:
            logger.info("Usuário administrador já existe. Verificação concluída.")
    except Exception as e:
        logger.error(f"Erro ao criar usuário administrador: {str(e)}", exc_info=True)
        # Faz rollback se houver erro
        db.session.rollback()
    finally:
        # Sempre fechar a sessão para evitar memory leak
        db.session.close() 