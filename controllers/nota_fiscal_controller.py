"""
Shim de compatibilidade.

Histórico:
- Este arquivo já foi um controller monolítico (milhares de linhas).
- Para melhorar manutenção, as rotas de Nota Fiscal foram divididas no pacote
  `controllers/nota_fiscal/` em módulos menores.

Importante:
- `app.py` importa `nota_fiscal_bp` daqui.
- Outros controladores podem importar funções utilitárias daqui (ex.: `api_get_dados_notas_fiscais`).
"""

from controllers.nota_fiscal import api_get_dados_notas_fiscais, nota_fiscal_bp  # noqa: F401


