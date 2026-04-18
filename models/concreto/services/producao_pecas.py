"""Lógica de produção por peças (estoque, data_producao, usinagens do dia)."""

from datetime import datetime

from flask import json
import logging

from sqlalchemy.sql import func

from models.database import db
from models.produto_composto import ProdutoComposto
from models.estoque import Estoque, EstoqueMovimentacoes

from models.concreto.utils.qualidade import (
    peca_obj_ja_produzida,
    qualidade_peca_remover_data_producao_de_dados_adicionais,
)


def registrar_entrada_estoque_produto_composto_producao_peca(
    produto_composto,
    quantidade,
    nomes_pecas_grupo,
    data_movimento,
    usuario_id,
    log=True,
):
    """
    Registra entrada no Estoque do produto composto vinculado à peça do tanque (ProdComp_id).
    Se não existir item de estoque do tipo produto_composto para o produto, cria um (mesmo padrão
    do cadastro de produto composto: quantidade 0, localização Estoque Matriz).
    Usa origem_tipo 'producao_peca' e observação com nomes das peças para o mesmo critério de
    reversão em _remover_movimentacoes_producao_peca_escopo_concretagens (desfazer produção).
    """
    if not produto_composto or quantidade is None:
        return False
    try:
        qtd = int(quantidade)
    except (TypeError, ValueError):
        return False
    if qtd <= 0:
        return False
    estoque_pc = Estoque.query.filter_by(
        ProdComp_id=produto_composto.id,
        tipo_item='produto_composto',
    ).first()
    if not estoque_pc:
        estoque_pc = Estoque(
            produto_composto=produto_composto,
            quantidade=0,
            tipo_item='produto_composto',
            localizacao='Estoque Matriz',
        )
        if usuario_id:
            estoque_pc.usuario_id = usuario_id
        db.session.add(estoque_pc)
        db.session.flush()
        if log:
            logging.info(
                'Produção de peças: criado item de estoque para produto composto ID %s (%s).',
                produto_composto.id,
                produto_composto.nome or '',
            )
    nomes_txt = ', '.join(nomes_pecas_grupo) if nomes_pecas_grupo else ''
    motivo = (
        f'Produção peças — {produto_composto.nome or ""} — Peças: {nomes_txt} — Qtd: {qtd}'
    )
    try:
        mov_ent = EstoqueMovimentacoes()
        mov_ent.adicionar(
            quantidade=qtd,
            estoque_id=estoque_pc.id,
            origem_id=produto_composto.id,
            origem_tipo='producao_peca',
            usuario_id=usuario_id,
            motivo=motivo,
        )
        mov_ent.data_movimento = data_movimento
        mov_ent.save(log=log)
        return True
    except Exception as e:
        logging.error(
            'Erro ao registrar entrada de estoque do produto composto %s: %s',
            produto_composto.id,
            str(e),
        )
        return False


def processar_producao_por_pecas(pecas_list, usuario_id=1, log=True, _usinagem=True):
    """Processa a produção para uma lista específica de peças (ex.: peças de uma concretagem).
    Consome estoque, marca data_producao e processa usinagens do dia. Retorna True se ok, False se lista vazia."""
    from datetime import date as date_type

    print(f"[_processar_producao_por_pecas] Pecas: {pecas_list}")
    if not pecas_list:
        return False
    pecas_list = [p for p in pecas_list if not peca_obj_ja_produzida(p)]
    if not pecas_list:
        return False
    dia = pecas_list[0].data_concretagem
    if not dia:
        return False
    if isinstance(dia, datetime):
        dia_date = dia.date()
    elif isinstance(dia, date_type):
        dia_date = dia
    else:
        try:
            dia_date = datetime.strptime(str(dia), '%Y-%m-%d').date() if isinstance(dia, str) else dia
        except (ValueError, TypeError):
            logging.warning(f"Erro ao converter data: {dia}")
            return False
    grupos = {}
    for peca in pecas_list:
        chave = (peca.tanque_id, peca.tipo)
        if chave not in grupos:
            grupos[chave] = []
        grupos[chave].append(peca)
    if _usinagem:
        from models.concreto.entities.usinagens import ConcretoUsinagens

        usinagens = ConcretoUsinagens.query.filter(
            ConcretoUsinagens.data_usinagem.like(f'%{dia_date}%'),
            func.json_extract(ConcretoUsinagens.dados_adicionais, '$.data_producao').is_(None),
        ).all()
        for usinagem in usinagens:
            try:
                usinagem.produzir(usuario_id=usuario_id, total=True)
            except Exception as e:
                logging.error(f"Erro ao processar usinagem {usinagem.id}: {str(e)}")
    materiais_necessarios = {}
    todas_pecas_processadas = []
    from models.tanque import TanquesProdutoComposto

    for (tanque_id, tipo_peca), pecas_grupo in grupos.items():
        vinculacao = TanquesProdutoComposto.query.filter_by(
            tanque_id=tanque_id,
            tipo_peca=tipo_peca
        ).first()
        if not vinculacao:
            nomes_pecas_grupo = [p.nome or f"Peça {p.id}" for p in pecas_grupo]
            if log:
                print(f"Peças {', '.join(nomes_pecas_grupo)} sem vinculação de produto composto (Tanque: {tanque_id}, Tipo: {tipo_peca})")
            continue
        produto_composto = ProdutoComposto.query.get(vinculacao.produto_composto_id)
        if not produto_composto:
            continue
        quantidade_grupo = len(pecas_grupo)
        nomes_pecas_grupo = [p.nome or f"Peça {p.id}" for p in pecas_grupo]
        todas_pecas_processadas.extend(nomes_pecas_grupo)
        if log:
            print(f"Processando grupo: Tanque {tanque_id}, Tipo {tipo_peca}, {quantidade_grupo} peça(s) dia: {dia_date}")
        produtos_processados = set()
        try:
            produto_composto.produzir(
                quantidade=quantidade_grupo,
                data_movimento=dia_date,
                usuario_id=usuario_id,
                log=True,
                produtos_processados=produtos_processados,
                materiais_necessarios=materiais_necessarios,
                traco=_usinagem
            )
        except Exception as e:
            logging.error(f"Erro ao processar produto composto {produto_composto.id}: {str(e)}")
            continue
        data_producao = datetime.now().isoformat() if isinstance(dia_date, date_type) else (datetime.now().strftime('%Y-%m-%d') if isinstance(dia_date, datetime) else str(datetime.now()))
        for peca in pecas_grupo:
            try:
                qualidade_dict = {}
                if peca.qualidade:
                    try:
                        qualidade_dict = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else peca.qualidade
                    except (json.JSONDecodeError, TypeError):
                        qualidade_dict = {}
                if 'data_producao' not in qualidade_dict:
                    qualidade_dict['data_producao'] = None
                qualidade_dict['data_producao'] = data_producao
                qualidade_peca_remover_data_producao_de_dados_adicionais(qualidade_dict)
                peca.qualidade = json.dumps(qualidade_dict, ensure_ascii=False)
                db.session.add(peca)
            except Exception as e:
                logging.warning(f"Erro ao salvar data_producao na peça {peca.id}: {str(e)}")
                continue
        registrar_entrada_estoque_produto_composto_producao_peca(
            produto_composto,
            quantidade_grupo,
            nomes_pecas_grupo,
            dia_date,
            usuario_id,
            log=log,
        )
    if materiais_necessarios:
        for info in materiais_necessarios.values():
            try:
                estoque = info['estoque']
                quantidade_total = info['quantidade']
                produto_id = info['produto_id']
                if log:
                    print(f"  -> Componente material: {estoque.material.nome} - Quantidade total agrupada: {quantidade_total}")
                mov = EstoqueMovimentacoes()
                mov.remover(
                    quantidade=quantidade_total,
                    estoque_id=estoque.id,
                    origem_id=produto_id,
                    origem_tipo='producao_peca',
                    usuario_id=usuario_id,
                    motivo=f'Produção das peças: {", ".join(todas_pecas_processadas)} - Quantidade total: {quantidade_total} - len: {len(todas_pecas_processadas)}',
                    log=log
                )
                mov.data_movimento = dia_date
                mov.save()
            except Exception as e:
                logging.error(f"Erro ao criar movimentação de estoque: {str(e)}")
                continue
    try:
        db.session.commit()
    except Exception as e:
        logging.error(f"Erro ao fazer commit: {str(e)}")
        db.session.rollback()
        return False
    return True
