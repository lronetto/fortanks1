# Mapeamento da pasta `utils`

Este documento lista as funções existentes em `utils` e aponta duplicidades (código repetido, sobreposição funcional ou arquivos redundantes).

## `utils/utils.py`
- `formatarMoeda(valor)`: formata número para moeda BRL (`R$` com vírgula decimal).
- `normalizar_data_str(s)`: normaliza espaços em strings de data.
- `get_value_datetime(row, col_index)`: converte célula (Excel/pandas/string) para `datetime`.
- `is_date_string(valor_str)`: verifica se valor parece data válida.
- `format_float(value)`: formata float com duas casas e separador de milhar.
- `valor_para_str(valor, default=None)`: converte valor em string tratando `NaN`, `None` e `float` inteiro.
- `get_value_str(row, col_index, default=None)`: lê célula e retorna string segura.
- `calcular_data_rompimento_28_dias(data_moldagem_dt)`: soma 28 dias e ajusta domingo para segunda.
- `serialize_value(value)`: serializa tipos de data para string ISO simples.
- `serialize_nested(data)`: serializa recursivamente `dict/list`.
- `separar_pdf_por_paginas(payload, filename)`: divide PDF em arquivos por página.
- `json_dumps_safe(obj)`: `json.dumps` com serialização de `datetime` e `Decimal`.
- `validar_chave_acesso(chave)`: valida formato básico de chave fiscal.
- `extrair_chave_do_pdf(payload)`: tenta extrair chave fiscal de barcode/QR em PDF.

## `utils/decorators.py`
- `role_required(roles)`: exige autenticação e perfil/cargo permitido na rota.
- `jwt_required(f)`: valida JWT Bearer de API mobile e popula `g.usuario_atual`.

## `utils/security.py`
- `is_safe_redirect_url(target)`: bloqueia open redirect, validando host/scheme.
- `is_allowed_file(filename)`: valida extensão permitida via `ALLOWED_EXTENSIONS`.
- `sanitize_filename(filename)`: sanitiza nome de arquivo com `secure_filename`.
- `validate_password_strength(senha)`: valida complexidade mínima de senha.

## `utils/password.py`
- Não define funções novas; apenas re-exporta:
  - `hash_password`
  - `check_password`
  - `is_argon2_hash`

## `utils/email_utils.py`
- `enviar_email(destinatario, assunto, corpo_html, corpo_texto='', anexos=None)`: envia e-mail via Flask-Mail.
- `enviar_email_gmail(destinatario, assunto, corpo_html, corpo_texto='', anexos=None, remetente_nome=None)`: envia e-mail via SMTP Gmail direto.

## `utils/material_imagem_upload.py`
- `guess_image_mime_from_bytes(head)`: infere MIME de imagem por assinatura binária.
- `parse_dados_json(text)`: converte JSON textual em `dict`.
- `dump_dados_json(data)`: serializa `dict` para JSON.
- `get_imagem_upload_id(text)`: obtém `imagem_upload_id` do JSON.
- `set_imagem_upload_id(text, upload_id)`: define/remove `imagem_upload_id` no JSON.
- `salvar_imagem_material(material_id, file_storage)`: valida e salva imagem em `Upload`.
- `remover_upload_material_se_existir(upload_id, material_id)`: remove upload válido de material.

## `utils/equipamento_dados_adicionais.py`
- `_extras_vazios()`: estrutura padrão dos extras de equipamento.
- `_normaliza_checklist_modelo_id(val)`: normaliza ID de checklist para `int|None`.
- `_normaliza_nota_fiscal_id(val)`: normaliza ID de nota fiscal para `int|None`.
- `_normaliza_material_id(val)`: normaliza ID de material para `int|None`.
- `parse_extras(text)`: parse/normalização de `dados_adicionais` de equipamento.
- `dump_extras(data)`: serialização saneada dos extras.
- `set_patrimonio_e_fotos(old_text, patrimonio, foto_ids)`: atualiza patrimônio/fotos no JSON.
- `process_foto_uploads(equipamento_id, files_storage, field_name='fotos')`: salva uploads de fotos e retorna IDs.

## `utils/ca_scraper.py`
- `_headers_consultaca_navegador(referer=None, same_origin=False)`: monta headers HTTP simulando navegador.
- `baixar_pagina_consultaca(url)`: baixa HTML do consultaca.com com fallback de proteção 403.
- `consultar_ca(numero_ca)`: consulta CA e extrai dados estruturados da página.
- `json_serial(obj)`: serializa `date/datetime` para JSON.
- `limpar_texto(texto)`: remove HTML/ruído textual.
- `validar_ca(numero_ca)`: verifica se CA consultado está em situação válida.

## `utils/gerar_pdf.py`
- `parse_nf_xml(xml_path)`: extrai dados principais de NF-e XML.
- `gerar_html_danfe(dados)`: gera HTML DANFE a partir dos dados extraídos.
- `gerar_pdf_danfe(xml_path)`: converte HTML DANFE em PDF.

## `utils/feriados_brasil_api.py`
- `parse_codigo_ibge_municipio(val)`: valida/normaliza código IBGE municipal.
- `_parse_data_br(s)`: converte data `dd/mm/yyyy` para `date`.
- `buscar_feriados_nacionais(ano)`: busca feriados nacionais na Brasil API.
- `buscar_feriados_estaduais(ano, uf)`: busca feriados estaduais por UF.
- `_carregar_lista_municipal_ano(ano)`: baixa/cacheia dataset municipal do ano.
- `buscar_feriados_municipais(ano, codigo_ibge)`: busca feriados municipais por IBGE.
- `consolidar_feriados_para_importacao(...)`: consolida listas de feriados para importação.

## `utils/cronograma_calculo_pecas.py`
- `_parse_float_br(s)`: parse de número com vírgula/ponto.
- `indices_tanque_para_mapa(dados_adicionais_raw)`: extrai mapa de índices numéricos do tanque.
- `_normalizar_tipo(tipo)`: normaliza tipo de peça.
- `_primeira_chave_existente(chaves, candidatos)`: retorna primeira chave existente.
- `chave_tempo_para_tipo(tipo, chaves_indices)`: resolve índice `TEMPO_*`/`TEMPOS_*` por tipo.
- `_indice_ritmo_cronograma(k)`: identifica chaves de ritmo de cronograma.
- `_merge_indices_tanque_simulacao(chaves, tid, indices_por_tanque)`: sobrepõe índices simulados.
- `calcular_projeto_pecas(contrato_id, indices_por_tanque=None)`: calcula carga por tanque/tipo e avisos.
- `total_dias_por_tanque_contrato(contrato_id, indices_por_tanque=None)`: soma dias por tanque.
- `total_placas_por_tanque_contrato(contrato_id)`: conta placas por tanque.
- `segunda_feira_semana(d)`: retorna segunda da semana de `d`.
- `distribuir_dias_por_semana(total_dias, inicio)`: distribui carga em semanas corridas.
- `primeiro_dia_apos_trabalho(total_unidades, inicio)`: calcula início de sucessor após carga.
- `semanas_no_intervalo(data_inicio, data_fim)`: lista semanas de um intervalo.
- `dados_simulacao_indices_tanques_contrato(contrato_id)`: monta grade de simulação de índices.

## `utils/cronograma_curva_s_placas_mes.py`
- `placas_previsto_e_real_por_mes(semanas, linhas)`: agrega previsto/real por mês a partir das semanas.

## `utils/cronograma_distribuicao_uteis.py`
- `is_dia_util(d, cal, feriados)`: define se dia é útil no calendário.
- `distribuir_dias_uteis_por_semana(total_dias, inicio, cal, feriados)`: distribui carga em dias úteis por semana.
- `primeiro_dia_apos_trabalho_uteis(total_unidades, inicio, cal, feriados)`: calcula próximo dia após carga útil.
- `distribuir_carga_por_semana(total_dias, inicio, calendario, feriados)`: delega para corrido/útil.
- `primeiro_dia_apos_carga(total_unidades, inicio, calendario, feriados)`: próximo dia após carga corrido/útil.
- `dias_corridos_na_carga(total_dias, inicio, calendario, feriados)`: conta dias corridos cobertos pela carga.

## `utils/cronograma_indice.py`
- `normalizar_indice(s)`: valida índice hierárquico (`1`, `1.2`, `1.2.3`).
- `indice_para_sort_key(s)`: gera chave lexicográfica de ordenação para índice.
- `mensagem_indice_invalido()`: mensagem padrão de validação.

## `utils/cronograma_matriz_excel.py`
- `_hex_gradiente_tempo(indice_semana, n_semanas)`: cor de gradiente temporal.
- `_hex_heatmap_dias(val, vmax)`: cor de heatmap por intensidade de dias.
- `_fmt_heatmap_cached(workbook, cache, hex_color, ...)`: cache de formatos Excel.
- `build_matriz_semanal_xlsx_bytes(...)`: exporta matriz e heatmap em XLSX.

## `utils/cronograma_matriz_semanal.py`
- `_to_date(val)`: converte valores em `date`.
- `minima_segunda_feira_anchor_cronograma(contrato_id)`: encontra âncora inicial do cronograma.
- `_peso_share_por_item(itens)`: calcula share de peso por tanque/item.
- `_parent_indice_str(indice)`: retorna índice pai imediato.
- `_tem_descendente_indice(indice, todos)`: verifica existência de descendentes.
- `_filhos_diretos_indice(parent_indice, itens)`: busca filhos diretos na hierarquia.
- `_placas_efetivas_por_item(itens, share, placas_tank)`: calcula placas efetivas por item.
- `_dias_efetivos_por_item(itens, share, dias_tank)`: calcula dias efetivos por item.
- `_ordenar_itens_topologico(itens)`: ordena itens respeitando predecessores.
- `_real_placas_por_tanque_semana(contrato_id, week_keys)`: agrega real por tanque/semana.
- `runs_intervalos_dias_semana_horizontais(dias_por_semana, week_keys)`: agrupa semanas consecutivas de carga.
- `montar_matriz_previsto_real(...)`: monta semanas/linhas com previsto, real, acumulados e barras.
- `agregar_curva_s_projeto(semanas, linhas)`: agrega curva S global.
- `totais_semana_previsto_real_curva_s(semanas, linhas)`: totais semanais previsto/real.
- `max_data_concretagem_contrato(contrato_id)`: última concretagem no contrato.
- `data_fim_horizonte_matriz(contrato_id, data_inicio, data_fim_formulario)`: define horizonte de cálculo.
- `trim_trailing_semanas_sem_previsto_nem_real(semanas, linhas, barras_dias=None)`: remove cauda sem dados.

## `utils/cronograma_resolver_calendario.py`
- `_segmentos(indice)`: conta segmentos do índice.
- `indice_caso_prefixo(indice_item, prefixo)`: verifica se índice está sob prefixo.
- `resolver_calendario_para_indice(contrato_id, indice, cache_vinculos=None)`: resolve calendário mais específico.
- `mapa_feriados_por_calendario(calendario_ids)`: mapa de feriados por calendário.

## `utils/concretagem_previsto_cronograma.py`
- `pecas_previsto_por_mes_alinhado(...)`: gera previsto mensal alinhado ao relatório de concretagem.

## `utils/plr_calculo.py`
- `tempo_de_casa_meses(data_admissao, data_fechamento)`: calcula meses de casa.
- `assiduidade_pct_por_faltas(faltas)`: converte faltas em percentual de assiduidade.
- `nota_media_com_assiduidade(avaliacao, assiduidade_pct=None)`: calcula nota média (com regra de assiduidade).
- `multiplicador_tempo_casa(tempo_mes)`: retorna multiplicador para PLR por tempo de casa.
- `salario_base_plr(colaborador, mes_ref, ano_ref, data_fechamento, db_session)`: calcula salário base PLR.

## `utils/plr_import_planilha.py`
- `_normalizar_cpf(val)`: higieniza CPF em 11 dígitos.
- `_parse_sheet_name(nome)`: extrai mês/ano do nome da aba.
- `_cell_value(book, sheet, row, col)`: leitura segura de célula `.xls`.
- `_cell_value_xlsx(sheet, row, col)`: leitura segura de célula `.xlsx`.
- `_valor_nota(val)`: converte célula para nota numérica.
- `ler_avaliacoes_planilha_xls(caminho)`: lê avaliações PLR de planilha `.xls`.
- `_ler_avaliacoes_planilha_xlsx_impl(caminho)`: lê avaliações PLR de planilha `.xlsx`.
- `ler_avaliacoes_planilha(caminho)`: dispatcher de leitura `.xls/.xlsx`.

## `utils/relatorio_financeiro.py`
- `dados_relatorio_financeiro(data_inicio=..., data_fim=..., centro_custo_ids=None, cancelada=False)`: consulta e monta dados financeiros.
- `gerar_relatorio_financeiro(data_inicio=None, data_fim=None, output_path=None)`: transforma dados em DataFrame e opcionalmente exporta Excel.

## `utils/__init__.py`
- Não há funções; apenas exporta `role_required`.

---

## Duplicidades e sobreposições encontradas

### 1) Duplicidade de caminho/arquivo (observação de workspace)
- `utils/decorators.py` e `utils\decorators.py` referem ao mesmo arquivo no Windows (variação de separador).
- `utils/password.py` e `utils\password.py` idem.
- Não parece ser duplicidade física real de conteúdo, apenas representação de caminho.

### 2) Repetição de lógica (candidata a refatoração)
- `material_imagem_upload.py` e `equipamento_dados_adicionais.py` repetem padrões de:
  - parse/dump de JSON textual;
  - validação de MIME/upload;
  - fluxo de salvar `Upload` e recuperar registro por `filename`.
- Em `equipamento_dados_adicionais.py`, `_normaliza_checklist_modelo_id`, `_normaliza_nota_fiscal_id` e `_normaliza_material_id` têm lógica praticamente idêntica (mudando só nome semântico).

### 3) Código redundante/inacessível
- `plr_calculo.py` em `tempo_de_casa_meses`: havia bloco duplicado após `return max(0, meses)` (dead code), removido.

### 4) Sobreposição funcional (não necessariamente erro)
- `enviar_email` e `enviar_email_gmail` possuem responsabilidades semelhantes (envio de e-mail), mas por mecanismos diferentes (Flask-Mail vs SMTP direto).
- Funções de distribuição temporal em `cronograma_calculo_pecas.py` e `cronograma_distribuicao_uteis.py` são parecidas, porém a segunda adiciona calendário útil/feriados (diferença válida).

### 5) Pequenas duplicações de import
- `relatorio_financeiro.py` importava `time` duas vezes (ajustado).

---

## Observação final
- A pasta está funcionalmente bem segmentada por domínio.
- As duplicidades mais relevantes para manutenção são a repetição de utilitários de **parse/upload JSON** e funções de normalização muito parecidas em alguns módulos.
