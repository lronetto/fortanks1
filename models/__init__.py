"""
Módulo de inicialização dos modelos
Este arquivo importa e configura todos os modelos do sistema, assegurando
a correta ordem de carregamento e evitando problemas de referência circular.
"""
import sys
import logging
from sqlalchemy.orm import configure_mappers as sa_configure_mappers
from sqlalchemy import exc

logger = logging.getLogger(__name__)

# Primeiro importamos o banco de dados
from .database import db

# Importar os modelos na ordem correta
# Nota: as importações devem ser feitas aqui para evitar importações circulares
from .unidade import Unidade
from .usuario import Usuario
from .centro_custo import CentroCusto
from .plano_conta import PlanoConta
from .contrato import Contrato
from .cliente import Cliente
from .endereco import Endereco
from .tanque import Tanque
from .peca import Peca
from .concretagem import Concretagem, ConcretagemPeca, ConcretagemTanque
from .equipamento import Equipamento, Manutencao, ChecklistModelo, ChecklistItem, ChecklistEquipamento, ChecklistResposta
from .colaborador import Colaborador
from .solicitacao import Solicitacao
from .cargo import Cargo
from .departamento import Departamento

# Importamos material e solicitacao explicitamente
from .material import Material
from .grupo_material import GrupoMaterial
from .estoque import Estoque, MovimentacaoEstoque
from .nota_fiscal import NotaFiscal, NotaFiscalItem

# Importamos os novos modelos de usinagem de concreto
from .usinagem_concreto import TracoConcreto, ItemTracoConcreto, UsinagemConcreto, UsinagemEquipamento, UsinagemMaterial, RompimentoCorpoProva

# Importamos o modelo de conversão de unidades
from .conversao_unidade import ConversaoUnidade

# Importamos os novos modelos de produto composto
from .produto_composto import ProdutoComposto, ProdutoCompostoItem
from .dados_analiticos import DadoAnalitico
from .reembolso import Reembolso, ReembolsoDocumento, ReembolsoAnexo

def configure_mappers():
    """
    Configura explicitamente todos os mappers SQLAlchemy
    chamando a função interna do SQLAlchemy
    """
    try:
        logger.info("Configurando mappers SQLAlchemy...")
        # Força a configuração de todos os mappers
        sa_configure_mappers()
        logger.info("Configuração de mappers SQLAlchemy bem-sucedida!")
        return True
    except Exception as e:
        logger.error(f"Erro ao configurar mappers SQLAlchemy: {str(e)}", exc_info=True)
        raise

# Executar a configuração na importação inicial
try:
    configure_mappers()
except Exception as e:
    logger.error(f"Falha na inicialização de mappers: {str(e)}", exc_info=True)
    # Em produção, talvez seja melhor não reraise a exceção
    # para permitir que a aplicação continue (com risco de erros futuros)
    # Em desenvolvimento, reraise para identificar problemas rapidamente
    if 'pytest' not in sys.modules:
        raise

# Exportar modelos relevantes
__all__ = [
    'db', 'Usuario', 'CentroCusto', 'PlanoConta', 'Contrato',
    'Material', 'ItemSolicitacao', 'Solicitacao','Cargo','Departamento','Colaborador','DadosBancarios',
    'NotaFiscal', 'NotaFiscalItem', 'Cliente', 'Endereco', 'Tanque', 'Peca',
    'Concretagem', 'ConcretagemPeca', 'ConcretagemTanque', 'Equipamento', 'Manutencao', 
    'ChecklistModelo', 'ChecklistItem', 'ChecklistEquipamento', 'ChecklistResposta',
    'TracoConcreto', 'ItemTracoConcreto', 'UsinagemConcreto', 'UsinagemEquipamento',
    'UsinagemMaterial', 'ConversaoUnidade', 'Unidade', 'RompimentoCorpoProva',
    'Colaborador', 'ProdutoComposto', 'ProdutoCompostoItem', 'Estoque', 'MovimentacaoEstoque',
    'DadoAnalitico', 'configure_mappers', 'Reembolso', 'ReembolsoDocumento', 'ReembolsoAnexo',
] 