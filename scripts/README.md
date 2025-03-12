# Centralização de Funções do Sistema

Este diretório contém scripts que foram criados para auxiliar na centralização de funções comuns do sistema, tornando a manutenção mais simples e reduzindo a duplicação de código.

## Funções Centralizadas

As funções foram centralizadas nos seguintes arquivos:

### 1. utils/db.py
- `get_db_connection()`: Estabelece conexão com o banco de dados
- `db_cursor()`: Context manager para gerenciar cursores de banco de dados
- `execute_query()`: Executa queries SQL e retorna resultados
- `execute_many()`: Executa múltiplas queries em batch
- `get_single_result()`: Obtém um único resultado de uma query
- `insert_data()`: Insere dados em uma tabela
- `update_data()`: Atualiza dados em uma tabela

### 2. utils/auth.py
- `verificar_permissao()`: Verifica se um usuário tem permissão para uma ação
- `login_obrigatorio()`: Decorator para exigir login nas rotas
- `admin_obrigatorio()`: Decorator para exigir cargo de admin nas rotas
- `verificar_login_api()`: Função para verificar login em APIs
- `get_user_id()`: Retorna o ID do usuário logado

### 3. utils/file_handlers.py
- `salvar_arquivo_upload()`: Salva um arquivo enviado pelo usuário
- `processar_arquivo_excel()`: Processa um arquivo Excel e retorna um DataFrame

## Benefícios da Centralização

A centralização dessas funções traz os seguintes benefícios:

1. **Redução de Duplicação**: O mesmo código não precisa ser repetido em vários arquivos
2. **Manutenção Simplificada**: Correções e melhorias podem ser feitas em um único lugar
3. **Consistência de Comportamento**: Todas as partes do sistema usam as mesmas funções
4. **Melhor Gerenciamento de Erros**: Tratamento de erros centralizado e consistente
5. **Facilidade de Testes**: É mais fácil testar funções centralizadas
6. **Menor Acoplamento**: Os módulos ficam menos dependentes de detalhes de implementação

## Como Usar

Para usar as funções centralizadas, basta importá-las no início de cada arquivo:

```python
# Importações para banco de dados
from utils.db import get_db_connection, execute_query, get_single_result, insert_data, update_data

# Importações para autenticação
from utils.auth import login_obrigatorio, admin_obrigatorio, verificar_permissao, get_user_id

# Importações para manipulação de arquivos
from utils.file_handlers import salvar_arquivo_upload, processar_arquivo_excel
```

## Exemplo de Uso

```python
@app.route('/listar')
@login_obrigatorio
def listar():
    # Verificar se o usuário tem permissão
    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para visualizar este recurso.', 'warning')
        return redirect(url_for('dashboard'))
    
    # Buscar dados no banco
    itens = execute_query("SELECT * FROM tabela WHERE ativo = 1")
    
    return render_template('lista.html', itens=itens)
``` 