# Mapeamento da pasta `utils` (revisado)

Este documento lista funções utilitárias e aponta duplicidades/sobreposições reais para manutenção.

## `utils/utils.py`
- `formatarMoeda(valor)`: formata para BRL (`R$` com vírgula decimal).
- `normalizar_data_str(s)`: remove espaços extras em data textual.
- `normalizar_para_data(valor, default=None)`: normaliza `date`/`datetime`/`YYYY-mm-dd` para `date`.
- `get_value_datetime(row, col_index)`: converte célula Excel/pandas/string para `datetime`.
- `is_date_string(valor_str)`: valida se um valor parece data.
- `format_float(value)`: formata float com 2 casas.
- `valor_para_str(valor, default=None)`: converte valor em string segura.
- `get_value_str(row, col_index, default=None)`: leitura de célula como string segura.
- `calcular_data_rompimento_28_dias(data_moldagem_dt)`: +28 dias com ajuste de domingo.
- `serialize_value(value)`: serializa `date`/`datetime`.
- `serialize_nested(data)`: serializa estruturas aninhadas.
- `separar_pdf_por_paginas(payload, filename)`: divide PDF em arquivos por página.
- `json_dumps_safe(obj)`: `json.dumps` com suporte a `datetime`/`Decimal`.
- `validar_chave_acesso(chave)`: valida formato de chave fiscal.
- `extrair_chave_do_pdf(payload)`: tenta extrair chave de barcode/QR.

## `utils/decorators.py`
- `role_required(roles)`: exige autenticação/perfil.
- `jwt_required(f)`: valida JWT e popula `g.usuario_atual`.

## `utils/security.py`
- `is_safe_redirect_url(target)`: bloqueia open redirect.
- `is_allowed_file(filename)`: valida extensão permitida.
- `sanitize_filename(filename)`: sanitiza nome de arquivo.
- `validate_password_strength(senha)`: valida complexidade mínima.

## `utils/password.py`
- Reexporta funções de senha de `models.usuario`: `hash_password`, `check_password`, `is_argon2_hash`.

## `utils/email_utils.py`
- `enviar_email(...)`: envio via Flask-Mail.
- `enviar_email_gmail(...)`: envio SMTP Gmail direto.

## `utils/material_imagem_upload.py`
- `guess_image_mime_from_bytes(head)`: detecta MIME por assinatura.
- `parse_dados_json(text)`: parse JSON de `dados_adicionais`.
- `dump_dados_json(data)`: serializa dict para JSON.
- `get_imagem_upload_id(text)`: obtém `imagem_upload_id`.
- `set_imagem_upload_id(text, upload_id)`: define/remove `imagem_upload_id`.
- `salvar_imagem_material(material_id, file_storage)`: persiste upload de imagem.
- `remover_upload_material_se_existir(upload_id, material_id)`: remove upload válido.

## `utils/equipamento_dados_adicionais.py`
- `_extras_vazios()`: shape padrão de extras.
- `_normaliza_id_opcional(val)`: helper único para `int|None`.
- `_normaliza_checklist_modelo_id(val)`: wrapper semântico.
- `_normaliza_nota_fiscal_id(val)`: wrapper semântico.
- `_normaliza_material_id(val)`: wrapper semântico.
- `parse_extras(text)`: parse/normalização de extras.
- `dump_extras(data)`: serialização saneada.
- `set_patrimonio_e_fotos(old_text, patrimonio, foto_ids)`: atualiza JSON de extras.
- `process_foto_uploads(...)`: processa fotos e retorna IDs.

## `utils/ca_scraper.py`
- `_headers_consultaca_navegador(...)`: headers de navegador.
- `baixar_pagina_consultaca(url)`: download HTML com fallback.
- `consultar_ca(numero_ca)`: consulta e extrai dados do CA.
- `json_serial(obj)`: serialização auxiliar.
- `limpar_texto(texto)`: limpeza de texto.
- `validar_ca(numero_ca)`: valida situação do CA.

## `utils/gerar_pdf.py`
- `parse_nf_xml(xml_path)`, `gerar_html_danfe(dados)`, `gerar_pdf_danfe(xml_path)`.

## `utils/feriados_brasil_api.py`
- `parse_codigo_ibge_municipio(val)`, `_parse_data_br(s)`,
  `buscar_feriados_nacionais(ano)`, `buscar_feriados_estaduais(ano, uf)`,
  `_carregar_lista_municipal_ano(ano)`, `buscar_feriados_municipais(ano, codigo_ibge)`,
  `consolidar_feriados_para_importacao(...)`.

## `utils/cronograma_calculo_pecas.py`
- Funções de cálculo de carga e distribuição por semanas para cronograma.

## `utils/cronograma_distribuicao_uteis.py`
- Funções equivalentes ao cálculo por semanas, incluindo calendário útil/feriados.

## `utils/cronograma_matriz_semanal.py`, `utils/cronograma_matriz_excel.py`, `utils/cronograma_curva_s_placas_mes.py`, `utils/cronograma_resolver_calendario.py`, `utils/cronograma_indice.py`
- Funções de apoio ao motor de cronograma (índices, matriz previsto/real, curva S, exportação, resolução de calendário).

## `utils/concretagem_previsto_cronograma.py`
- `pecas_previsto_por_mes_alinhado(...)`.

## `models/plr/utils/` (`calculo.py`, `importacao_planilha.py`)
- Cálculo de PLR e importação de planilhas (`.xls/.xlsx`); constantes da planilha em `models/plr/constants.py`.

## `utils/relatorio_financeiro.py`
- `dados_relatorio_financeiro(...)` e `gerar_relatorio_financeiro(...)`.

## `utils/__init__.py`
- Exporta `role_required`.

---

## Duplicidades e sobreposições (estado atual)

### 1) Duplicidade de caminho (não é duplicidade de arquivo)
- Entradas com `/` e `\` no Windows representam o mesmo arquivo.
- Não há evidência de arquivos físicos duplicados na pasta `utils`.

### 2) Funções com nomes idênticos entre arquivos
- Verificação atual: **nenhuma função top-level com mesmo nome em arquivos diferentes de `utils/*.py`**.

### 3) Repetição de lógica (parcialmente corrigida)
- `equipamento_dados_adicionais.py` tinha 3 funções de normalização de ID com o mesmo corpo.
- **Correção aplicada**: extração para `_normaliza_id_opcional(...)` e wrappers semânticos.

### 4) Sobreposição funcional válida
- `enviar_email` vs `enviar_email_gmail`: mesma finalidade, mecanismos distintos (Flask-Mail vs SMTP direto).
- Cronograma (`cronograma_calculo_pecas.py` vs `cronograma_distribuicao_uteis.py`): estruturas parecidas com regras de calendário diferentes.
- Upload de imagem (`material_imagem_upload.py` vs `equipamento_dados_adicionais.py`): fluxos semelhantes com contratos de dados diferentes (material x equipamento).

### 5) Pendências recomendadas (próxima rodada)
- Avaliar criação de um utilitário comum para parse/dump de JSON textual para reduzir divergência entre módulos de upload/extras.
- Avaliar helper compartilhado para upload de imagem (validação MIME + naming + persistência) parametrizado por `pai/tipo`.

---

## Resumo
- O mapeamento foi atualizado com `normalizar_para_data`.
- A duplicação mais clara e local foi corrigida.
- Restam sobreposições aceitáveis de domínio e duas oportunidades de extração utilitária transversal.
