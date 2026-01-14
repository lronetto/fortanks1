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
import shutil
import tempfile
import openpyxl
from openpyxl import load_workbook

from pylovepdf.tools.officepdf import OfficeToPdf



databook_concretagem_bp = Blueprint('databook_concretagem', __name__, url_prefix='/relatorios/databook/concretagem')

@databook_concretagem_bp.route('/')
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
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    
    # Se houver contrato selecionado, filtrar tanques
    if contrato_id:
        tanques = Tanques.query.filter_by(contrato_id=contrato_id).order_by(Tanques.nome).all()
    
    return render_template('relatorios/databook/concretagem/index.html', 
                         contratos=contratos, 
                         tanques=tanques,
                         contrato_id=contrato_id,
                         tanque_id=tanque_id,
                         data_inicio=data_inicio,
                         data_fim=data_fim)

@databook_concretagem_bp.route('/api/dados')
@login_required
def api_dados():
    """
    API para retornar dados do relatório em JSON (para DataTable)
    """
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_id = request.args.get('tanque_id', type=int)
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    
    # Converter datas se fornecidas
    data_inicio = None
    data_fim = None
    if data_inicio_str:
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        except ValueError:
            data_inicio = None
    
    if data_fim_str:
        try:
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        except ValueError:
            data_fim = None
    
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
    
    # Aplicar filtros de data (filtrar por data de moldagem)
    if data_inicio:
        # Converter para datetime para comparação correta
        data_inicio_dt = datetime.combine(data_inicio, datetime.min.time())
        query = query.filter(ConcretoUsinagensRompimentos.data_moldagem >= data_inicio_dt)
    
    if data_fim:
        # Converter para datetime e incluir o dia inteiro (até 23:59:59)
        from datetime import time as dt_time
        data_fim_dt = datetime.combine(data_fim, dt_time(23, 59, 59))
        query = query.filter(ConcretoUsinagensRompimentos.data_moldagem <= data_fim_dt)
    
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

@databook_concretagem_bp.route('/api/tanques')
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

def calcular_data_rompimento_28_dias(data_moldagem_dt):
    """Calcula data de rompimento 28 dias após a moldagem. Se cair em domingo, adiciona 1 dia."""
    data_rompimento = data_moldagem_dt + timedelta(days=28)
    # Verificar se é domingo (weekday() retorna 6 para domingo)
    if data_rompimento.weekday() == 6:  # Domingo
        data_rompimento += timedelta(days=1)  # Adiciona 1 dia (vira segunda-feira)
    return data_rompimento
def calcular_idade_cp(data_moldagem_dt, data_rompimento_dt):
    """Calcula idade do CP baseado na data de moldagem e data de rompimento."""
    if not data_moldagem_dt or not data_rompimento_dt:
        return 0
    diff_hours = (data_rompimento_dt - data_moldagem_dt).total_seconds() / 3600
    return int(diff_hours / 24) if diff_hours >= 24 else int(diff_hours)

def mapear_tipo_rompimento(tipo_rompimento, campos_base):
    """
    Mapeia o tipo de rompimento para os campos correspondentes.
    campos_base: lista de 4 campos (ex: [35, 36, 37, 38])
    Retorna um dicionário com os campos e valores ('X' ou '')
    """
    mapeamento = {
        '1': 0,
        '2': 1,
        '3': 2,
        '4': 3,
        '5': 3  # Assumindo que colunar também mapeia para o último campo
    }
    
    resultado = {}
    indice = mapeamento.get(tipo_rompimento.lower() if tipo_rompimento else '', 0)
    
    for i, campo in enumerate(campos_base):
        resultado[campo] = 'X' if i == indice else ''
    
    return resultado

def _gerar_excel_temp(numero_serie):
    """
    Função auxiliar que gera o Excel e retorna o caminho do arquivo temporário
    Retorna o caminho do arquivo temporário ou None em caso de erro
    """
    try:
        # Buscar todos os rompimentos da série
        rompimentos = db.session.query(ConcretoUsinagensRompimentos)\
            .filter(ConcretoUsinagensRompimentos.numero_serie == numero_serie).\
            order_by(ConcretoUsinagensRompimentos.data_rompimento.asc()).all()
        
        if not rompimentos:
            return None
        
        # Caminho do arquivo template
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'base/RELATORIO CONCRETAGEM.xlsx'
        )
        
        if not os.path.exists(template_path):
            return None
        
        # Criar uma cópia temporária do arquivo para preservar imagens
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        temp_file.close()
        shutil.copy2(template_path, temp_file.name)
        
        # Carregar o arquivo Excel base
        # Usar read_only=False para permitir edição
        wb = load_workbook(temp_file.name, data_only=False, keep_vba=False, read_only=False)
       
        # Processar apenas células com texto, preservando imagens e outros objetos
        for sheet in wb.worksheets:
            for index, row in enumerate(sheet.iter_rows()):
                if index == 60:
                    continue
                for index_cell, cell in enumerate(row):
                    if index_cell == 30:
                        continue
                    # Processar apenas células que contêm texto (string) e não estão vazias
                    if cell.value is not None and isinstance(cell.value, str) and len(cell.value.strip()) > 0:
                        # Criar uma cópia do valor original para evitar problemas
                        original_value = str(cell.value)
                        new_value = original_value
                        
                        # Substituir {1}, {2}, etc pelos dados correspondentes
                        new_value = new_value.replace('{1}', str(numero_serie))
                        #Cliente
                        new_value = new_value.replace('{2}', "Cliente 1")
                        #Obra
                        new_value = new_value.replace('{3}', "Obra 1")
                        #Tipo do concreto
                        new_value = new_value.replace('{4}', "40 MPa")
                        #Traço
                        new_value = new_value.replace('{5}', "FTK 40")
                        #Brita
                        new_value = new_value.replace('{6}', "0")
                        #Restrição
                        new_value = new_value.replace('{7}', "fck>=15,0 MPa P/ DESPROTENÇÂO")
                        #Cimento 1
                        new_value = new_value.replace('{8}', "CPIII 40 RS")
                        #Cimento 2
                        new_value = new_value.replace('{9}', "CP V")
                        #Aditivo
                        new_value = new_value.replace('{10}', "SUPER PLASTIFICANTE")
                        #Concreteira
                        new_value = new_value.replace('{11}', "Fortanks")
                        # Data de moldagem
                        if rompimentos[0].data_moldagem:
                            new_value = new_value.replace('{12}', str(rompimentos[0].data_moldagem.strftime('%d/%m/%Y')))
                        #Número do caminhao
                        new_value = new_value.replace('{13}', "01")
                        #Nota fiscal
                        new_value = new_value.replace('{14}', "1234567890")
                        #Horário de saída da usina 
                        if rompimentos[0].data_moldagem:
                            new_value = new_value.replace('{15}', str((rompimentos[0].data_moldagem - timedelta(minutes=15)).strftime('%H:%M')))
                        #Horário de chegada no destino
                        if rompimentos[0].data_moldagem:
                            new_value = new_value.replace('{16}', str((rompimentos[0].data_moldagem - timedelta(minutes=10)).strftime('%H:%M')))
                        #Consistencia SLUMP
                        new_value = new_value.replace('{17}', "")
                        #consistencia Slump
                        new_value = new_value.replace('{18}', "")
                        #consistencia FLOW
                        new_value = new_value.replace('{19}', "X")
                        #consistencia FLOW
                        new_value = new_value.replace('{20}', "600/610")
                        # hora de moldagem
                        if rompimentos[0].data_moldagem:
                            new_value = new_value.replace('{21}', str(rompimentos[0].data_moldagem.strftime('%H:%M')))
                        #volume
                        new_value = new_value.replace('{22}', "5,00 m³")
                        #pecas
                        new_value = new_value.replace('{23}', "1")

                        if (len(rompimentos) >= 4 and 
                            rompimentos[len(rompimentos)-1].data_moldagem and 
                            rompimentos[len(rompimentos)-1].data_rompimento and
                            calcular_idade_cp(rompimentos[len(rompimentos)-1].data_moldagem, rompimentos[len(rompimentos)-1].data_rompimento) >= 25):
                            #data de rompimento 1
                            if rompimentos[0].data_rompimento:
                                new_value = new_value.replace('{30}', str(rompimentos[0].data_rompimento.strftime('%d/%m/%Y')))
                            #idade de rompimento 1
                            if rompimentos[0].data_moldagem and rompimentos[0].data_rompimento:
                                idade = calcular_idade_cp(rompimentos[0].data_moldagem, rompimentos[0].data_rompimento)
                                if idade is not None:
                                    new_value = new_value.replace('{31}', str(idade))
                            #hora de rompimento 1
                            if rompimentos[0].data_rompimento:
                                new_value = new_value.replace('{32}', str(rompimentos[0].data_rompimento.strftime('%H:%M')))
                            #resultado de rompimento 1
                            if rompimentos[0].resultado:
                                resultado_1 = float(rompimentos[0].resultado) * float(rompimentos[0].fator_conversao or 1.2)
                                new_value = new_value.replace('{34}', str(round(resultado_1, 2)))
                            #tipo de rompimento 1
                            tipo_romp_1 = mapear_tipo_rompimento(rompimentos[0].tipo_rompimento, [35, 36, 37, 38,39])
                            for campo, valor in tipo_romp_1.items():
                                new_value = new_value.replace('{'+str(campo)+'}', valor)
                            #resultado de rompimento 2
                            if rompimentos[1].resultado:
                                resultado_2 = float(rompimentos[1].resultado) * float(rompimentos[1].fator_conversao or 1.2)
                                new_value = new_value.replace('{41}', str(round(resultado_2, 2)))
                            #tipo de rompimento 2
                            tipo_romp_2 = mapear_tipo_rompimento(rompimentos[1].tipo_rompimento, [42, 43, 44, 45,46])
                            for campo, valor in tipo_romp_2.items():
                                new_value = new_value.replace('{'+str(campo)+'}', valor)
                            #data de rompimento 3 e 4
                            if rompimentos[2].data_rompimento:
                                new_value = new_value.replace('{47}', str(rompimentos[2].data_rompimento.strftime('%d/%m/%Y')))
                            #hora de rompimento 3 e 4
                            if rompimentos[2].data_rompimento:
                                new_value = new_value.replace('{48}', str(rompimentos[2].data_rompimento.strftime('%H:%M')))
                            #resultado de rompimento 3
                            if rompimentos[2].resultado:
                                resultado_3 = float(rompimentos[2].resultado) * float(rompimentos[2].fator_conversao or 1.2)
                                new_value = new_value.replace('{49}', str(round(resultado_3, 2)))
                            #tipo de rompimento 3
                            tipo_romp_3 = mapear_tipo_rompimento(rompimentos[2].tipo_rompimento, [50, 51, 52, 53, 54])
                            for campo, valor in tipo_romp_3.items():
                                new_value = new_value.replace('{'+str(campo)+'}', valor)
                            #resultado de rompimento 4
                            if rompimentos[3].resultado:
                                resultado_4 = float(rompimentos[3].resultado) * float(rompimentos[3].fator_conversao or 1.2)
                                new_value = new_value.replace('{55}', str(round(resultado_4, 2)))
                            #tipo de rompimento 4
                            tipo_romp_4 = mapear_tipo_rompimento(rompimentos[3].tipo_rompimento, [56, 57, 58, 59, 60])
                            for campo, valor in tipo_romp_4.items():
                                new_value = new_value.replace('{'+str(campo)+'}', valor)

                            #resistencia final 1
                            if rompimentos[0].resultado and rompimentos[1].resultado:
                                resultado_0 = (rompimentos[0].resultado or 0) * (rompimentos[0].fator_conversao or 1.2)
                                resultado_1 = (rompimentos[1].resultado or 0) * (rompimentos[1].fator_conversao or 1.2)
                                resistencia_final_1 = max(resultado_0, resultado_1)
                                new_value = new_value.replace('{61}', str(round(resistencia_final_1, 2)))
                            #resistencia final 2
                            if rompimentos[2].resultado and rompimentos[3].resultado:
                                resultado_2 = (rompimentos[2].resultado or 0) * (rompimentos[2].fator_conversao or 1.2)
                                resultado_3 = (rompimentos[3].resultado or 0) * (rompimentos[3].fator_conversao or 1.2)
                                resistencia_final_2 = max(resultado_2, resultado_3)
                                new_value = new_value.replace('{63}', str(round(resistencia_final_2, 2)))
                        
                        # Atribuir o valor final à célula apenas uma vez
                        if new_value != original_value:
                            cell.value = new_value
        
        # Salvar o arquivo temporário (preserva imagens melhor que BytesIO)
        # Garantir que o arquivo seja salvo corretamente
        try:
            # Salvar o arquivo
            wb.save(temp_file.name)
        except Exception as save_error:
            # Se houver erro ao salvar, retornar None
            raise Exception(f'Erro ao salvar arquivo Excel: {str(save_error)}')
        finally:
            # Sempre fechar o workbook
            try:
                wb.close()
            except:
                pass
        
        # Verificar se o arquivo foi salvo corretamente
        if not os.path.exists(temp_file.name):
            return None
        
        file_size = os.path.getsize(temp_file.name)
        if file_size == 0:
            return None
        
        return temp_file.name
    except Exception as e:
        # Em caso de erro, tentar limpar o arquivo temporário
        try:
            if 'temp_file' in locals() and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
        except:
            pass
        return None

@databook_concretagem_bp.route('/exportar-excel/<int:numero_serie>')
@login_required
def exportar_excel(numero_serie):
    """
    Exporta dados de uma série específica para Excel usando template base
    """
    try:
        excel_path = _gerar_excel_temp(numero_serie)
        
        if not excel_path:
            return jsonify({'error': 'Nenhum rompimento encontrado para a série ' + str(numero_serie)}), 404
        
        try:
            # Ler o arquivo salvo para o buffer
            output = io.BytesIO()
            with open(excel_path, 'rb') as f:
                output.write(f.read())
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
        finally:
            # Limpar arquivo temporário
            if os.path.exists(excel_path):
                try:
                    os.unlink(excel_path)
                except:
                    pass
        
    except Exception as e:
        return jsonify({'error': f'Erro ao exportar Excel: {str(e)}'}), 500

@databook_concretagem_bp.route('/exportar-pdf/<int:numero_serie>')
@login_required
def exportar_pdf(numero_serie):
    """
    Exporta dados de uma série específica para PDF convertendo do Excel gerado usando iLovePDF API
    """
    excel_path = None
    pdf_temp_path = None
    
    try:
        excel_path = _gerar_excel_temp(numero_serie)
        
        if not excel_path or not os.path.exists(excel_path):
            return jsonify({'error': 'Nenhum rompimento encontrado para a série ' + str(numero_serie)}), 404
        
       
        # Obter credenciais da API do ambiente
        ilovepdf_public_key = os.getenv('ILOVEPDF_PUBLIC_KEY')
        ilovepdf_secret_key = os.getenv('ILOVEPDF_SECRET_KEY')
        
        if not ilovepdf_public_key or not ilovepdf_secret_key:
            return jsonify({
                'error': 'Credenciais iLovePDF não configuradas. Configure as variáveis ILOVEPDF_PUBLIC_KEY e ILOVEPDF_SECRET_KEY.'
            }), 500
        
        # Inicializar cliente iLovePDF
        officepdf = OfficeToPdf(ilovepdf_public_key, verify_ssl=True, proxies=None)
        # Criar diretório temporário para salvar o PDF
        pdf_temp_dir = tempfile.mkdtemp()
        
        # Criar arquivo PDF temporário
        pdf_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', dir=pdf_temp_dir)
        pdf_temp_file.close()
        pdf_temp_path = pdf_temp_file.name
        
        # Adicionar arquivo Excel
        officepdf.add_file(excel_path)
        
        # Definir diretório de saída (deve ser um diretório, não um arquivo)
        officepdf.set_output_folder(pdf_temp_dir)
        
        # Executar conversão
        officepdf.execute()
        
        # Baixar PDF gerado
        officepdf.download()
        
        # Limpar tarefa na API
        officepdf.delete_current_task()
        
        # Encontrar o arquivo PDF gerado (pode ter nome diferente)
        pdf_files = [f for f in os.listdir(pdf_temp_dir) if f.endswith('.pdf')]
        if not pdf_files:
            
            return jsonify({'error': 'PDF não foi gerado pela API iLovePDF'}), 500
        print(f'pdf_files: {pdf_files}')

        # Se encontrou arquivo, usar o primeiro
        generated_pdf_path = os.path.join(pdf_temp_dir, pdf_files[0])
        if not os.path.exists(generated_pdf_path):
            return jsonify({'error': 'Arquivo PDF gerado não encontrado'}), 500
        
       
        print(f'pdf_temp_dir: {pdf_temp_dir}')
        # Ler o PDF gerado para buffer de memória
        output = io.BytesIO()
        with open(pdf_temp_dir+'/'+pdf_files[1], 'rb') as f:
            output.write(f.read())
        output.seek(0)
        
        # Nome do arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'relatorio_concretagem_serie_{numero_serie}_{timestamp}.pdf'
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        # Garantir que a mensagem de erro seja sempre uma string
        try:
            error_msg = str(e) if e is not None else 'Erro desconhecido'
        except:
            error_msg = 'Erro desconhecido ao processar exceção'
        return jsonify({'error': f'Erro ao exportar PDF: {error_msg}'}), 500
    finally:
        # Limpar arquivos temporários
        if excel_path and os.path.exists(excel_path):
            try:
                os.unlink(excel_path)
            except:
                pass
        if pdf_temp_path and os.path.exists(pdf_temp_path):
            try:
                pass#os.unlink(pdf_temp_path)
            except:
                pass
        # Limpar diretório temporário se existir
        if 'pdf_temp_dir' in locals() and pdf_temp_dir and os.path.exists(pdf_temp_dir):
            try:
                shutil.rmtree(pdf_temp_dir)
                pass
            except:
                pass

