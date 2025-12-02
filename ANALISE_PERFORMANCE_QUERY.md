# Análise de Performance - api_get_dados_notas_fiscais()

## 🔴 Gargalos Críticos (Alto Impacto)

### 1. **OUTER JOINs com Múltiplas Tabelas** (Linhas 335-336)
```python
query = query.outerjoin(DadoAnalitico, join_conditions_pagamento)
query = query.outerjoin(Upload, join_conditions_upload)
```
**Problema**: 
- Se uma nota tem múltiplos `DadoAnalitico` ou múltiplos `Upload`, cria múltiplas linhas
- Multiplica o número de linhas antes do GROUP BY
- Exemplo: 1 nota com 3 uploads = 3 linhas temporárias

**Impacto**: ⚠️⚠️⚠️ MUITO ALTO - Pode multiplicar linhas por 10x ou mais

**Solução**: Usar subqueries ou EXISTS ao invés de OUTER JOINs

---

### 2. **Múltiplas Funções Agregadas** (Linhas 311-316)
```python
pagamento_column = func.max(case((DadoAnalitico.id != None, 1), else_=0))
upload_column = func.max(case((Upload.id != None, 1), else_=0))
upload_arquivei_column = func.max(case((Upload.tipo == 1, 1), else_=0))
upload_protocolo_column = func.max(case((Upload.tipo == 2, 1), else_=0))
upload_reembolso_column = func.max(case((Upload.tipo == 3, 1), else_=0))
vencimento_column = func.json_extract(NotaFiscal.dados_adicionais, '$.fatura.vencimento')
```
**Problema**:
- Cada `func.max()` precisa processar todas as linhas do grupo
- `func.json_extract()` executa em TODAS as linhas antes do GROUP BY
- 6 funções agregadas = 6 passadas sobre os dados

**Impacto**: ⚠️⚠️⚠️ MUITO ALTO - Processamento pesado em cada linha

**Solução**: Mover para subqueries ou calcular apenas quando necessário

---

### 3. **GROUP BY em Query com Joins** (Linha 463)
```python
query = query.group_by(NotaFiscal.id)
```
**Problema**:
- GROUP BY precisa ordenar/agrupar todas as linhas duplicadas dos joins
- Quanto mais linhas duplicadas, mais custoso
- Executado DEPOIS de todos os filtros, mas ANTES da paginação

**Impacto**: ⚠️⚠️ ALTO - Necessário mas custoso com muitos dados

**Solução**: Reduzir duplicatas antes do GROUP BY (otimizar joins)

---

### 4. **Filtros com LIKE/ILIKE com Wildcard no Início** (Linhas 342-345, 352)
```python
NotaFiscal.numero_nf.ilike(busca_like)  # busca_like = '%termo%'
NotaFiscalItem.descricao.ilike(f'%{item_nome}%')
```
**Problema**:
- Wildcard no início (`%termo`) impede uso de índices
- Força scan completo da tabela
- ILIKE (case-insensitive) é mais lento que LIKE

**Impacto**: ⚠️⚠️ ALTO - Scan completo quando há busca

**Solução**: 
- Usar índices full-text se disponível
- Limitar busca a campos indexados
- Considerar busca apenas no início do campo

---

### 5. **Filtros em JSON com ILIKE** (Linhas 415, 419, 423)
```python
db.cast(NotaFiscal.dados_adicionais, db.Text).ilike(f'%"municipio_inicio": "{origem}"%')
```
**Problema**:
- Cast + ILIKE em campo JSON grande
- Não pode usar índices
- Processa todo o conteúdo JSON de cada linha

**Impacto**: ⚠️⚠️ ALTO - Muito custoso para CTEs

**Solução**: Usar `json_extract()` ao invés de ILIKE

---

### 6. **Múltiplas Subqueries EXISTS** (Linhas 430-450)
```python
db.session.query(Upload.id).filter(...).exists()
```
**Problema**:
- Cada EXISTS executa uma subquery separada
- Pode ser otimizado com joins ou índices

**Impacto**: ⚠️ MÉDIO - Depende do volume de dados

**Solução**: Usar os joins já existentes ao invés de subqueries

---

### 7. **Filtro de Status de Importação com ANY** (Linha 358)
```python
query = query.filter(~NotaFiscal.itens.any(NotaFiscalItem.importado_estoque == True))
```
**Problema**:
- ANY precisa verificar todos os itens de cada nota
- Não pode usar índices eficientemente

**Impacto**: ⚠️ MÉDIO - Pode ser lento com muitas notas

---

## 🟡 Problemas Moderados

### 8. **Filtro de Vencimento com .date()** (Linhas 460, 462)
```python
query = query.filter(vencimento_column.date() < datetime.now().date())
```
**Problema**:
- `.date()` em coluna calculada pode não usar índices
- Comparação de string JSON como data

**Impacto**: ⚠️ MÉDIO - Depende do banco de dados

**Solução**: Comparar strings diretamente ('YYYY-MM-DD')

---

### 9. **Join Condicional com LIKE** (Linha 329)
```python
DadoAnalitico.documento.like('%' + NotaFiscal.numero_nf + '%')
```
**Problema**:
- LIKE com wildcards impede uso de índices
- Executado para cada linha do join

**Impacto**: ⚠️ MÉDIO - Pode ser otimizado

---

## 📊 Ordem de Prioridade para Otimização

1. **CRÍTICO**: Otimizar OUTER JOINs (usar subqueries ou EXISTS)
2. **CRÍTICO**: Reduzir funções agregadas (calcular apenas quando necessário)
3. **ALTO**: Otimizar filtros LIKE/ILIKE (usar índices ou full-text search)
4. **ALTO**: Otimizar filtros JSON (usar json_extract ao invés de ILIKE)
5. **MÉDIO**: Otimizar subqueries EXISTS (usar joins existentes)
6. **MÉDIO**: Otimizar filtro de vencimento (comparar strings diretamente)

## 💡 Recomendações de Otimização

### Estratégia 1: Separar Query Base dos Dados Adicionais
- Query principal: apenas NotaFiscal com filtros básicos
- Dados adicionais: buscar em subqueries separadas ou calcular no Python

### Estratégia 2: Usar Índices
- Criar índices em: numero_nf, nome_emitente, chave_acesso, data_emissao
- Índice composto: (status_processamento, data_emissao)
- Índice JSON: se o banco suportar (PostgreSQL)

### Estratégia 3: Cache de Resultados
- Cachear resultados de queries frequentes
- Invalidar cache quando dados mudarem

### Estratégia 4: Paginação Antes de Processar
- Aplicar paginação o mais cedo possível
- Processar apenas os dados da página atual

