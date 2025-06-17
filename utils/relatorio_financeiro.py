from datetime import datetime
import pandas as pd
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.tanque import Tanque
from models.dados_analiticos import DadoAnalitico
from datetime import timedelta
from sqlalchemy import or_
from models.plano_conta import PlanoConta
import time
from models.database import db
from models.centro_custo import CentroCusto
from models.contrato import Contrato
from models.nota_fiscal import CFOPS_VENDA,CFOPS_COMPRA
from models.arquivei import Arquivei
import time
from dateutil.relativedelta import relativedelta

def dados_relatorio_financeiro(data_inicio=datetime.now()-relativedelta(years=1), data_fim=datetime.now(),centro_custo_ids=None):
    """
    Gera um relatório financeiro com dados de notas fiscais e centros de custo.
    
    Args:
        data_inicio (datetime, optional): Data inicial para filtrar os dados
        data_fim (datetime, optional): Data final para filtrar os dados
    
    Returns:
        pd.DataFrame: DataFrame com os dados do relatório
    """
    # Buscar todas as notas fiscais no período
    query = NotaFiscal.query.join(NotaFiscalItem)
    
    if data_inicio:
        query = query.filter(NotaFiscal.data_emissao >= data_inicio)
    if data_fim:
        query = query.filter(NotaFiscal.data_emissao <= data_fim)
    tinicial=time.time()
    notas_fiscais = query.filter(NotaFiscal.cnpj_emitente.like('%27126997000187%'),\
                                 NotaFiscalItem.cfop.in_(CFOPS_VENDA)).\
        order_by(NotaFiscal.data_emissao.desc(),NotaFiscal.numero_nf.desc()).all()
    tfinal=time.time()
    print(f"Tempo de execução query: {tfinal-tinicial} segundos")
    #print(notas_fiscais)
    # Lista para armazenar os dados do relatório
    dados_relatorio = []
    tinicial=time.time()
    for nf in notas_fiscais:
        tq = db.session.query(Tanque,Contrato,CentroCusto,NotaFiscalItem,NotaFiscal).\
            join(Contrato,Contrato.id==Tanque.contrato_id).\
        join(CentroCusto,CentroCusto.id==Contrato.centro_custo_id).\
        join(NotaFiscalItem,NotaFiscalItem.codigo==Tanque.item_nf).\
        join(NotaFiscal,NotaFiscal.id==NotaFiscalItem.nf_id)
        if centro_custo_ids:
            tq = tq.filter(CentroCusto.id.in_(centro_custo_ids))
        tq = tq.filter(NotaFiscal.id==nf.id,NotaFiscal.status_processamento=='importado').first()

        tanque = None   
        contrato = None
        centro_custo = None
        nota_fiscal_item = None
        nota_fiscal = None
        if tq:
            tanque = tq[0]
            contrato = tq[1]
            centro_custo = tq[2]
            nota_fiscal_item = tq[3]
            nota_fiscal = tq[4]
            
            # Calcular data prevista
        data_prevista = None
        if tanque and contrato:
            data_prevista = nf.data_emissao + timedelta(days=contrato.prazo_pagamento_mat)
        dados_analiticos = db.session.query(DadoAnalitico).\
            join(PlanoConta,PlanoConta.id==DadoAnalitico.plano_conta_id).\
            filter(DadoAnalitico.documento.like("%"+nf.numero_nf.lstrip('0')+"%"),PlanoConta.codigo==118
            ).first()
        
        dados_relatorio.append({
            'Data': nf.data_emissao.strftime('%d/%m/%Y'),  # Mantém como datetime para ordenação
            'Centro de Custo': dados_analiticos.centro_custo.codigo if dados_analiticos else centro_custo.codigo if centro_custo else 'Não definido',
            'Nota Fiscal': nf.numero_nf,
            'Valor': float(nf.valor_total),
            'Data Prevista': data_prevista.strftime('%d/%m/%Y') if tanque and contrato else 'Não definido',  # Mantém como datetime para ordenação
            'Pago': dados_analiticos.data_pagamento.strftime('%d/%m/%Y') if dados_analiticos else 'Não',
            'Status': nf.status_processamento
        })
    tfinal=time.time()
    print(f"Tempo de execução dados_relatorio: {tfinal-tinicial} segundos")
    return dados_relatorio
def gerar_relatorio_financeiro(data_inicio=None, data_fim=None, output_path=None):
    dados_relatorio = dados_relatorio_financeiro(data_inicio, data_fim)
    if len(dados_relatorio) > 0:
        # Adicionar dados ao relatório
        #print(dados_relatorio)
    
        # Criar DataFrame
        df = pd.DataFrame(dados_relatorio)
        
        # Ordenar por data de emissão
        df = df.sort_values('Data', ascending=False)
        
        # Formatar datas para exibição
        df['Data'] = pd.to_datetime(df['Data']).dt.strftime('%d/%m/%Y')
        
        # Função auxiliar para formatar datas com tratamento de NaT
        def formatar_data(x):
            if pd.isna(x) or x == 'Não':
                return 'Não definido'
            try:
                return pd.to_datetime(x).strftime('%d/%m/%Y')
            except:
                return 'Não definido'
        
        # Aplicar formatação nas colunas de data
        df['Data Prevista'] = df['Data Prevista'].apply(formatar_data)
        df['Pago'] = df['Pago'].apply(formatar_data)
        
        # Salvar arquivo se output_path for fornecido
        if output_path:
            # Configurar o writer do Excel
            writer = pd.ExcelWriter(output_path, engine='openpyxl')
            
            # Escrever o DataFrame
            df.to_excel(writer, index=False, sheet_name='Relatório Financeiro')
            
            # Ajustar largura das colunas
            worksheet = writer.sheets['Relatório Financeiro']
            for idx, col in enumerate(df.columns):
                max_length = max(
                    df[col].astype(str).apply(len).max(),
                    len(col)
                )
                worksheet.column_dimensions[chr(65 + idx)].width = max_length + 2
            
            writer.close()
    
        return df 
    else:
        return None
    