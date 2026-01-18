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
from .usuario import Usuario
from .centro_custo import CentroCusto
from .plano_conta import PlanoConta
from .contrato import Contrato
from .cliente import Cliente
from .endereco import Endereco
from .tanque import Tanques, TanquesGrupos, TanquesProdutoComposto, TanquesPecas
from .equipamento import Equipamento, Manutencao, ChecklistModelo, ChecklistItem, ChecklistEquipamento, ChecklistResposta
from .colaborador import Colaborador
from .solicitacao import Solicitacoes, SolicitacoesItens
from .cargo import Cargo
from .departamento import Departamento

# Importamos material e solicitacao explicitamente
from .material import Materiais, MateriaisGrupos
from .estoque import Estoque, EstoqueMovimentacoes, EstoqueInventarios, EstoqueInventariosItens
from .nota_fiscal import NotaFiscal, NotaFiscalItem

# Importamos os novos modelos de usinagem de concreto
from .concreto import ConcretoTracos, ConcretoTracosItens, ConcretoUsinagens, ConcretoUsinagensMateriais, ConcretoUsinagensRompimentos
from .concreto import ConcretoConcretagens, ConcretoConcretagensTanques

# Importamos o modelo de conversão de unidades
from .unidade import UnidadesConversao, Unidades

# Importamos os novos modelos de produto composto
from .produto_composto import ProdutoComposto, ProdutoCompostoItem
from .dados_analiticos import DadoAnalitico
from .reembolso import Reembolsos, ReembolsosDocumentos
from .epi import Epi, EpiEntregas
from .certificado import Certificado
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
    'Materiais', 'MateriaisGrupos', 
    'Solicitacoes', 'SolicitacoesItens', 
    'Cargo','Departamento','Colaborador','DadosBancarios', 
    'Estoque', 'EstoqueMovimentacoes', 'EstoqueInventarios', 'EstoqueInventariosItens',
    'NotaFiscal', 'NotaFiscalItem', 
    'Cliente', 'Endereco', 
    'Tanques', 'TanquesGrupos', 'TanquesPecas',
    'Equipamento', 'Manutencao', 
    'ChecklistModelo', 'ChecklistItem', 'ChecklistEquipamento', 'ChecklistResposta',
    'ConcretoTracos', 'ConcretoTracosItens', 'ConcretoUsinagens', 'ConcretoUsinagensMateriais', 'ConcretoUsinagensRompimentos',
    'ConcretoConcretagens', 'ConcretoConcretagensTanques',
    'Unidades', 'UnidadesConversao',
    'ProdutoComposto', 'ProdutoCompostoItem', 'TanquesProdutoComposto',
    'DadoAnalitico', 'configure_mappers', 
    'Reembolsos', 'ReembolsosDocumentos',
    'Epi', 'EpiEntregas',
    'Certificado',
] 