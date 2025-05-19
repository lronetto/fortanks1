"""
Módulo de migrações do banco de dados.
Este arquivo define as migrações disponíveis no sistema.
"""

# Importar todas as migrações
from . import create_clientes_table
from . import adicionar_clientes_contrato
from . import add_unidade_to_materiais
from . import remove_preco_unitario_from_materiais
from . import unify_material_date_fields 