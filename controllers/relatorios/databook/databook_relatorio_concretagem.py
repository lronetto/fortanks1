from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required
from models.concreto import ConcretoUsinagensRompimentos, ConcretoUsinagens, ConcretoConcretagens, ConcretoConcretagensTanques
from models.contrato import Contrato
from models.tanque import Tanques
from models.database import db
from sqlalchemy import or_, and_
from datetime import datetime, timedelta
import os
import io
import openpyxl
from openpyxl import load_workbook

databook_bp = Blueprint('relatorios_databook', __name__, url_prefix='/relatorios/databook')

@databook_bp.route('/')
@login_required
def index():
    """
    Página principal do relatório de inspeção (DataBook)
    """
    # Buscar contratos ativos para o filtro
    contratos = Contrato.query.filter_by(ativo=True).order_by(Contrato.nome).all()
    
    # Buscar tanques para o filtro (inicialmente todos)
    tanques = Tanques.query.order_by(Tanques.nome).all()
    
    # Obter filtros da requisição
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_id = request.args.get('tanque_id', type=int)
    
    # Se houver contrato selecionado, filtrar tanques
    if contrato_id:
        tanques = Tanques.query.filter_by(contrato_id=contrato_id).order_by(Tanques.nome).all()
    
    return render_template('relatorios/databook/index.html', 
                         contratos=contratos, 
                         tanques=tanques,
                         contrato_id=contrato_id,
                         tanque_id=tanque_id)

@databook_bp.route('/api/dados')
@login_required
def api_dados():
    """
    API para retornar dados do relatório em JSON (para DataTable)
    """
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_id = request.args.get('tanque_id', type=int)
    
    # Construir query base - usar outerjoin para não perder rompimentos sem usinagem
    query = db.session.query(ConcretoUsinagensRompimentos)\
        .outerjoin(ConcretoUsinagens, ConcretoUsinagensRompimentos.usinagem_id == ConcretoUsinagens.id)\
        .outerjoin(ConcretoConcretagens, ConcretoUsinagens.concretagem_id == ConcretoConcretagens.id)\
        .outerjoin(ConcretoConcretagensTanques, ConcretoConcretagens.id == ConcretoConcretagensTanques.concretagem_id)\
        .outerjoin(Tanques, ConcretoConcretagensTanques.tanque_id == Tanques.id)
    
    # Aplicar filtros
    if tanque_id:
        query = query.filter(Tanques.id == tanque_id)
    
    if contrato_id:
        query = query.filter(Tanques.contrato_id == contrato_id)
    
    # Executar query e ordenar por série e depois por data de rompimento
    rompimentos = query.order_by(
        ConcretoUsinagensRompimentos.numero_serie.asc(),
        ConcretoUsinagensRompimentos.data_rompimento.desc()
    ).all()
    
    # Agrupar dados por número de série e manter apenas uma linha por série
    series_unicas = {}
    for rompimento in rompimentos:
        numero_serie = rompimento.numero_serie
        
        # Se já processamos esta série, pular
        if numero_serie in series_unicas:
            continue
        
        # Obter data de moldagem do rompimento (primeiro rompimento da série)
        data_moldagem = rompimento.data_moldagem
        
        # Obter informações do tanque (pode haver múltiplos tanques associados)
        tanques_info = []
        if rompimento.usinagem and rompimento.usinagem.concretagem:
            for tanque_assoc in rompimento.usinagem.concretagem.tanques_associados:
                if tanque_assoc.tanque:
                    tanques_info.append({
                        'id': tanque_assoc.tanque.id,
                        'nome': tanque_assoc.tanque.nome,
                        'contrato_nome': tanque_assoc.tanque.contrato.nome if tanque_assoc.tanque.contrato else None
                    })
        
        # Contar total de rompimentos desta série
        total_rompimentos_serie = sum(1 for r in rompimentos if r.numero_serie == numero_serie)
        
        # Criar estrutura de dados da série (apenas uma linha por série)
        series_unicas[numero_serie] = {
            'id': rompimento.id,
            'numero_serie': numero_serie,
            'data_moldagem': data_moldagem.strftime('%d/%m/%Y %H:%M') if data_moldagem else 'N/A',
            'data_moldagem_raw': data_moldagem.isoformat() if data_moldagem else None,
            'tanque_nome': ', '.join([t['nome'] for t in tanques_info]) if tanques_info else 'N/A',
            'projeto_nome': tanques_info[0]['contrato_nome'] if tanques_info and tanques_info[0].get('contrato_nome') else 'N/A',
            'data_rompimento': rompimento.data_rompimento.strftime('%d/%m/%Y %H:%M') if rompimento.data_rompimento else 'N/A',
            'resultado': float(rompimento.resultado) if rompimento.resultado else None,
            'idade_cp': rompimento.idade_cp if rompimento.idade_cp else None,
            'total_rompimentos': total_rompimentos_serie
        }
    
    # Preparar dados finais (apenas séries únicas)
    dados = []
    for numero_serie in sorted(series_unicas.keys()):
        dados.append(series_unicas[numero_serie])
    
    return jsonify({
        'data': dados,
        'recordsTotal': len(dados),
        'recordsFiltered': len(dados)
    })

@databook_bp.route('/api/tanques')
@login_required
def api_tanques():
    """
    API para retornar tanques filtrados por projeto
    """
    contrato_id = request.args.get('contrato_id', type=int)
    
    if contrato_id:
        tanques = Tanques.query.filter_by(contrato_id=contrato_id).order_by(Tanques.nome).all()
    else:
        tanques = Tanques.query.order_by(Tanques.nome).all()
    
    tanques_json = [{
        'id': tanque.id,
        'nome': tanque.nome
    } for tanque in tanques]
    
    return jsonify({'tanques': tanques_json})

@databook_bp.route('/exportar-excel/<int:numero_serie>')
@login_required
def exportar_excel(numero_serie):
    """
    Exporta dados de uma série específica para Excel usando template base
    """
    try:
        # Buscar todos os rompimentos da série
        rompimentos = db.session.query(ConcretoUsinagensRompimentos)\
            .filter(ConcretoUsinagensRompimentos.numero_serie == numero_serie).order_by(ConcretoUsinagensRompimentos.data_rompimento.desc()).all()
        
        if not rompimentos:
            return jsonify({'error': 'Nenhum rompimento encontrado para a série ' + str(numero_serie)}), 404
        
        # Caminho do arquivo template
        # O arquivo está em controllers/relatorios/RELATORIO CONCRETAGEM.xlsx
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'base/RELATORIO CONCRETAGEM.xlsx'
        )
        
        if not os.path.exists(template_path):
            return jsonify({'error': 'Arquivo template não encontrado: ' + template_path}), 404
        
        # Carregar o arquivo Excel base
        wb = load_workbook(template_path)
           
        # TODO: Aqui será feito o mapeamento manual dos campos {1} a {63}
        # Por enquanto, apenas carregamos o arquivo e preparamos os dados
        # Exemplo de como fazer o preenchimento (será implementado manualmente):
        for sheet in wb.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value and isinstance(cell.value, str):
                        # Substituir {1}, {2}, etc pelos dados correspondentes
                        cell.value = cell.value.replace('{1}', str(numero_serie))
                        #Cliente
                        cell.value = cell.value.replace('{2}', "Cliente 1")
                        #Obra
                        cell.value = cell.value.replace('{3}', "Obra 1")
                        #Tipo do concreto
                        cell.value = cell.value.replace('{4}', "40 MPa")
                        #Traço
                        cell.value = cell.value.replace('{5}', "FTK 40")
                        #Brita
                        cell.value = cell.value.replace('{6}', "0")
                        #Restrição
                        cell.value = cell.value.replace('{7}', "fck>=15,0 MPa P/ DESPROTENÇÂO")
                        #Cimento 1
                        cell.value = cell.value.replace('{8}', "CPIII 40 RS")
                        #Cimento 2
                        cell.value = cell.value.replace('{9}', "CP V")
                        #Aditivo
                        cell.value = cell.value.replace('{10}', "SUPER PLASTIFICANTE")
                        #Concreteira
                        cell.value = cell.value.replace('{11}', "Fortanks")
                        # Data de moldagem
                        cell.value = cell.value.replace('{12}', str(rompimentos[0].data_moldagem.strftime('%d/%m/%Y')))
                        #Número do caminhao
                        cell.value = cell.value.replace('{13}', "01")
                        #Nota fiscal
                        cell.value = cell.value.replace('{14}', "1234567890")
                        #Horário de saída da usina 
                        cell.value = cell.value.replace('{15}', str((rompimentos[0].data_moldagem - timedelta(minutes=15)).strftime('%H:%M')))
                        #Horário de chegada no destino
                        cell.value = cell.value.replace('{16}', str((rompimentos[0].data_moldagem - timedelta(minutes=10)).strftime('%H:%M')))
                        #Consistencia SLUMP
                        cell.value = cell.value.replace('{17}', "")
                        #consistencia Slump
                        cell.value = cell.value.replace('{18}', "")
                        #consistencia FLOW
                        cell.value = cell.value.replace('{19}', "X")
                        #consistencia FLOW
                        cell.value = cell.value.replace('{20}', "600/610")
                       # hora de moldagem
                        cell.value = cell.value.replace('{21}', str(rompimentos[0].data_moldagem.strftime('%H:%M')))
                        #volume
                        cell.value = cell.value.replace('{22}', "5,00 m³")
                        #pecas
                        cell.value = cell.value.replace('{23}', "1")


                        pass
        
        # Salvar em buffer de memória
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        # Nome do arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'relatorio_concretagem_serie_{numero_serie}_{timestamp}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'error': f'Erro ao exportar Excel: {str(e)}'}), 500

