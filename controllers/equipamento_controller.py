import base64
from datetime import datetime
from typing import Optional
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    make_response,
    abort,
)
from flask_login import login_required, current_user
from sqlalchemy import or_
from models.database import db
from models.equipamento import (
    EQ_STATUS,
    Equipamento,
    EquipamentoEmprestimo,
    Manutencao,
    ChecklistModelo,
    ChecklistItem,
    ChecklistEquipamento,
    ChecklistResposta,
)
from models.colaborador import Colaborador
from models.material import Materiais
from models.upload import Upload
from utils.equipamento_dados_adicionais import (
    parse_extras,
    dump_extras,
    set_patrimonio_e_fotos,
    process_foto_uploads,
    PAI_EQUIPAMENTO,
    TIPO_FOTO_EQUIPAMENTO,
)

equipamento_bp = Blueprint('equipamento', __name__, url_prefix='/equipamentos')


def _status_equipamento_validado(valor):
    if not valor or valor not in EQ_STATUS:
        raise ValueError('Status do equipamento inválido.')
    return valor


@equipamento_bp.route('/upload/<int:upload_id>/foto')
@login_required
def equipamento_foto(upload_id):
    """Imagem inline de Upload vinculado a equipamento (foto patrimônio)."""
    u = Upload.query.get_or_404(upload_id)
    if u.pai != PAI_EQUIPAMENTO or u.tipo != TIPO_FOTO_EQUIPAMENTO or not u.blob:
        abort(404)
    data = base64.b64decode(u.blob)
    resp = make_response(data)
    resp.headers['Content-Type'] = u.mimetype or 'image/jpeg'
    resp.headers['Content-Disposition'] = f'inline; filename="{u.filename}"'
    return resp


@equipamento_bp.route('/')
@login_required
def index():
    checklist_modelos = ChecklistModelo.query.order_by(ChecklistModelo.nome).all()
    return render_template(
        'equipamentos/index.html',
        checklist_modelos=checklist_modelos,
    )


@equipamento_bp.route('/datatables', methods=['POST'])
@login_required
def equipamentos_datatables():
    """JSON server-side para DataTables da listagem de equipamentos."""
    draw = int(request.form.get('draw', 1))
    start = int(request.form.get('start', 0))
    length = int(request.form.get('length', 25))
    search_value = (request.form.get('search[value]') or '').strip()

    query = Equipamento.query
    records_total = Equipamento.query.count()

    if search_value:
        term = f'%{search_value}%'
        clauses = [
            Equipamento.nome.ilike(term),
            Equipamento.modelo.ilike(term),
            Equipamento.status.ilike(term),
            Equipamento.dados_adicionais.ilike(term),
        ]
        if search_value.isdigit():
            clauses.append(Equipamento.id == int(search_value))
        query = query.filter(or_(*clauses))

    records_filtered = query.count()

    order_col_index = request.form.get('order[0][column]', '0')
    order_dir = request.form.get('order[0][dir]', 'asc')
    # Coluna 2 = patrimônio (JSON) — sem ordenação SQL confiável; usa nome como desempate visual
    col_map = {
        '0': Equipamento.nome,
        '1': Equipamento.modelo,
        '2': Equipamento.nome,
        '3': Equipamento.status,
    }
    order_col = col_map.get(str(order_col_index), Equipamento.nome)
    if order_dir == 'desc':
        query = query.order_by(order_col.desc())
    else:
        query = query.order_by(order_col.asc())

    page_items = query.offset(start).limit(length).all()

    data = []
    for eq in page_items:
        ex = parse_extras(eq.dados_adicionais)
        data.append({
            'id': eq.id,
            'nome': eq.nome or '',
            'modelo': eq.modelo or '',
            'patrimonio': ex.get('patrimonio') or '',
            'status': eq.status or '',
        })

    return jsonify({
        'draw': draw,
        'recordsTotal': records_total,
        'recordsFiltered': records_filtered,
        'data': data,
    })


_CATEGORIAS_MATERIAL_EQUIPAMENTO = ('Equipamento', 'Ferramenta')


@equipamento_bp.route('/busca-materiais-equipamento', methods=['GET'])
@login_required
def busca_materiais_equipamento():
    """Autocomplete: materiais ativos com categoria Equipamento ou Ferramenta."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'results': []})
    term = f'%{q}%'
    query = (
        Materiais.query.filter(
            Materiais.categoria.in_(_CATEGORIAS_MATERIAL_EQUIPAMENTO),
            Materiais.nome.ilike(term),
            or_(Materiais.ativo.is_(True), Materiais.ativo.is_(None)),
        )
        .order_by(Materiais.nome.asc())
        .limit(30)
    )
    rows = query.all()
    return jsonify({
        'results': [
            {
                'id': m.id,
                'nome': m.nome or '',
                'categoria': m.categoria or '',
                'codigo': (m.codigo or '').strip(),
            }
            for m in rows
        ],
    })


@equipamento_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            patrimonio = (request.form.get('patrimonio') or '').strip()
            st_eq = _status_equipamento_validado(request.form.get('status'))
            extras_novo = parse_extras(None)
            extras_novo['patrimonio'] = patrimonio
            extras_novo['fotos'] = []
            cm_novo = (request.form.get('checklist_modelo_id') or '').strip()
            extras_novo['checklist_modelo_id'] = (
                int(cm_novo) if cm_novo.isdigit() else None
            )
            equipamento = Equipamento(
                nome=request.form['nome'],
                tipo=request.form['tipo'],
                propriedade=request.form['propriedade'],
                modelo=request.form['modelo'],
                numero_serie=request.form['numero_serie'],
                nota_fiscal=request.form.get('nota_fiscal', ''),
                data_aquisicao=datetime.strptime(
                    request.form['data_aquisicao'], '%Y-%m-%d').date(),
                status=st_eq,
                observacoes=request.form.get('observacoes') or '',
                dados_adicionais=dump_extras(extras_novo),
            )
            db.session.add(equipamento)
            db.session.commit()
            novas_fotos = process_foto_uploads(equipamento.id, request.files)
            if novas_fotos:
                equipamento.dados_adicionais = set_patrimonio_e_fotos(
                    equipamento.dados_adicionais, patrimonio, novas_fotos
                )
                db.session.commit()
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Equipamento cadastrado com sucesso!',
                })
            flash('Equipamento cadastrado com sucesso!', 'success')
            return redirect(url_for('equipamento.index'))
        except Exception as e:
            db.session.rollback()
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': f'Erro ao cadastrar equipamento: {str(e)}',
                })
            flash(f'Erro ao cadastrar equipamento: {str(e)}', 'danger')
    return redirect(url_for('equipamento.index'))


@equipamento_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    equipamento = Equipamento.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        try:
            patrimonio = (request.form.get('patrimonio') or '').strip()
            extras = parse_extras(equipamento.dados_adicionais)
            ids_atuais = list(extras['fotos'])
            remover = {
                int(x) for x in request.form.getlist('remover_foto')
                if str(x).isdigit()
            }
            for rid in remover:
                if rid not in ids_atuais:
                    continue
                up = Upload.query.get(rid)
                if (
                    up
                    and up.pai == PAI_EQUIPAMENTO
                    and up.pai_id == equipamento.id
                    and up.tipo == TIPO_FOTO_EQUIPAMENTO
                ):
                    up.delete()
            ids_atuais = [i for i in ids_atuais if i not in remover]
            novas = process_foto_uploads(equipamento.id, request.files)
            extras['patrimonio'] = patrimonio
            extras['fotos'] = ids_atuais + novas
            cm_ed = (request.form.get('checklist_modelo_id') or '').strip()
            extras['checklist_modelo_id'] = (
                int(cm_ed) if cm_ed.isdigit() else None
            )
            equipamento.dados_adicionais = dump_extras(extras)

            equipamento.nome = request.form['nome']
            equipamento.tipo = request.form['tipo']
            equipamento.propriedade = request.form['propriedade']
            equipamento.modelo = request.form['modelo']
            equipamento.numero_serie = request.form.get('numero_serie') or ''
            equipamento.nota_fiscal = request.form.get('nota_fiscal') or ''
            da = request.form.get('data_aquisicao')
            if da:
                equipamento.data_aquisicao = datetime.strptime(
                    da, '%Y-%m-%d').date()
            else:
                equipamento.data_aquisicao = None
            equipamento.status = _status_equipamento_validado(
                request.form.get('status')
            )
            equipamento.observacoes = request.form.get('observacoes') or ''
            db.session.commit()
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Equipamento atualizado com sucesso!',
                })
            flash('Equipamento atualizado com sucesso!', 'success')
            return redirect(url_for('equipamento.index'))
        except Exception as e:
            db.session.rollback()
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': f'Erro ao atualizar equipamento: {str(e)}',
                })
            flash('Erro ao atualizar equipamento!', 'danger')

    if is_ajax:
        ex = parse_extras(equipamento.dados_adicionais)
        fotos_json = []
        for fid in ex['fotos']:
            u = Upload.query.get(fid)
            if (
                u
                and u.pai == PAI_EQUIPAMENTO
                and u.pai_id == equipamento.id
                and u.tipo == TIPO_FOTO_EQUIPAMENTO
            ):
                fotos_json.append({
                    'id': u.id,
                    'filename': u.filename,
                    'preview_url': url_for(
                        'equipamento.equipamento_foto', upload_id=u.id
                    ),
                })
        return jsonify({
            'id': equipamento.id,
            'nome': equipamento.nome,
            'tipo': equipamento.tipo,
            'propriedade': equipamento.propriedade,
            'modelo': equipamento.modelo or '',
            'numero_serie': equipamento.numero_serie or '',
            'nota_fiscal': equipamento.nota_fiscal or '',
            'data_aquisicao': equipamento.data_aquisicao.strftime('%Y-%m-%d')
            if equipamento.data_aquisicao else '',
            'status': equipamento.status,
            'observacoes': equipamento.observacoes or '',
            'patrimonio': ex.get('patrimonio', ''),
            'checklist_modelo_id': ex.get('checklist_modelo_id'),
            'fotos': fotos_json,
        })

    extras_tpl = parse_extras(equipamento.dados_adicionais)
    fotos_tpl = []
    for fid in extras_tpl['fotos']:
        u = Upload.query.get(fid)
        if (
            u
            and u.pai == PAI_EQUIPAMENTO
            and u.pai_id == equipamento.id
        ):
            fotos_tpl.append(u)

    checklist_modelos = ChecklistModelo.query.order_by(ChecklistModelo.nome).all()
    return render_template(
        'equipamentos/editar.html',
        equipamento=equipamento,
        extras_editar=extras_tpl,
        fotos_equipamento=fotos_tpl,
        checklist_modelos=checklist_modelos,
    )


@equipamento_bp.route('/<int:id>/visualizar')
@login_required
def visualizar(id):
    equipamento = Equipamento.query.get_or_404(id)
    ex = parse_extras(equipamento.dados_adicionais)
    fotos_v = []
    for fid in ex['fotos']:
        u = Upload.query.get(fid)
        if (
            u
            and u.pai == PAI_EQUIPAMENTO
            and u.pai_id == equipamento.id
            and u.tipo == TIPO_FOTO_EQUIPAMENTO
        ):
            fotos_v.append(u)
    return render_template(
        'equipamentos/visualizar.html',
        equipamento=equipamento,
        extras_visualizar=ex,
        fotos_visualizar=fotos_v,
    )


def _requer_ajax_modal():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@equipamento_bp.route('/<int:id>/modal/visualizar')
@login_required
def modal_visualizar_equipamento(id):
    equipamento = Equipamento.query.get_or_404(id)
    if not _requer_ajax_modal():
        return redirect(url_for('equipamento.visualizar', id=id))
    ex = parse_extras(equipamento.dados_adicionais)
    fotos_modal = []
    for fid in ex['fotos']:
        u = Upload.query.get(fid)
        if (
            u
            and u.pai == PAI_EQUIPAMENTO
            and u.pai_id == equipamento.id
            and u.tipo == TIPO_FOTO_EQUIPAMENTO
        ):
            fotos_modal.append(u)
    return render_template(
        'equipamentos/modais/partials/visualizar_equipamento.html',
        equipamento=equipamento,
        extras_modal=ex,
        fotos_modal=fotos_modal,
    )


@equipamento_bp.route('/<int:id>/modal/manutencoes')
@login_required
def modal_manutencoes_equipamento(id):
    equipamento = Equipamento.query.get_or_404(id)
    if not _requer_ajax_modal():
        return redirect(url_for('equipamento.manutencoes', id=id))
    return render_template(
        'equipamentos/modais/partials/manutencoes_equipamento.html',
        equipamento=equipamento,
        pode_excluir_manutencao=current_user.is_admin,
    )


@equipamento_bp.route('/<int:id>/modal/checklist-novo')
@login_required
def modal_checklist_novo_equipamento(id):
    equipamento = Equipamento.query.get_or_404(id)
    if not _requer_ajax_modal():
        flash(
            'Use o botão Novo checklist nesta tela para abrir o formulário.',
            'info',
        )
        return redirect(url_for('equipamento.visualizar', id=id))
    ex_chk = parse_extras(equipamento.dados_adicionais)
    modelo_padrao_id = ex_chk.get('checklist_modelo_id')
    modelos = ChecklistModelo.query.order_by(ChecklistModelo.nome).all()
    return render_template(
        'equipamentos/modais/partials/form_novo_checklist_equipamento.html',
        equipamento=equipamento,
        modelos=modelos,
        modelo_padrao_id=modelo_padrao_id,
        now1=datetime.now(),
    )


@equipamento_bp.route('/<int:id>/modal/manutencao-nova')
@login_required
def modal_form_nova_manutencao(id):
    equipamento = Equipamento.query.get_or_404(id)
    if not _requer_ajax_modal():
        return redirect(url_for('equipamento.nova_manutencao', id=id))
    return render_template(
        'equipamentos/modais/partials/form_nova_manutencao_equipamento.html',
        equipamento=equipamento,
        now1=datetime.now(),
    )


# Rotas para Manutenção


def _manutencao_do_equipamento(equipamento_id: int, manutencao_id: int) -> Manutencao:
    man = Manutencao.query.get_or_404(manutencao_id)
    if man.equipamento_id != equipamento_id:
        abort(404)
    return man


@equipamento_bp.route('/<int:id>/manutencoes')
@login_required
def manutencoes(id):
    equipamento = Equipamento.query.get_or_404(id)
    return render_template('equipamentos/manutencoes/index.html', equipamento=equipamento)


@equipamento_bp.route('/<int:id>/manutencoes/nova', methods=['GET', 'POST'])
@login_required
def nova_manutencao(id):
    from models.nota_fiscal import NotaFiscal

    equipamento = Equipamento.query.get_or_404(id)
    notas = (
        NotaFiscal.query.order_by(NotaFiscal.data_emissao.desc())
        .limit(300)
        .all()
    )

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            if request.form.get('manutencao_modal_rapida') == '1':
                obs = (request.form.get('observacoes') or '').strip()
                descricao = obs if obs else 'Registro de manutenção.'
                nome_resp = (
                    getattr(current_user, 'nome', None) or str(current_user.get_id())
                )
                manutencao = Manutencao(
                    equipamento_id=id,
                    tipo='Corretiva',
                    descricao=descricao,
                    data_inicio=datetime.strptime(
                        request.form['data_inicio'], '%Y-%m-%dT%H:%M'),
                    responsavel=nome_resp,
                    status='Pendente',
                    observacoes=obs,
                )
            else:
                manutencao = Manutencao(
                    equipamento_id=id,
                    tipo=request.form['tipo'],
                    descricao=request.form['descricao'],
                    data_inicio=datetime.strptime(
                        request.form['data_inicio'], '%Y-%m-%dT%H:%M'),
                    responsavel=request.form['responsavel'],
                    status=request.form['status'],
                    observacoes=request.form.get('observacoes') or '',
                )
                if request.form.get('data_fim'):
                    manutencao.data_fim = datetime.strptime(
                        request.form['data_fim'], '%Y-%m-%dT%H:%M')
                if request.form.get('custo'):
                    manutencao.custo = float(request.form['custo'])
                nf_raw = (request.form.get('nota_fiscal_id') or '').strip()
                if nf_raw:
                    manutencao.nota_fiscal_id = int(nf_raw)

            db.session.add(manutencao)
            db.session.commit()
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Manutenção registrada com sucesso!',
                })
            flash('Manutenção registrada com sucesso!', 'success')
            return redirect(url_for('equipamento.manutencoes', id=id))
        except Exception:
            db.session.rollback()
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': 'Erro ao registrar manutenção. Verifique os dados.',
                })
            flash('Erro ao registrar manutenção!', 'danger')

    return render_template(
        'equipamentos/manutencoes/nova.html',
        equipamento=equipamento,
        notas=notas,
        now1=datetime.now(),
    )


@equipamento_bp.route('/<int:id>/manutencoes/<int:manutencao_id>/modal/editar')
@login_required
def modal_editar_manutencao(id, manutencao_id):
    from models.nota_fiscal import NotaFiscal

    equipamento = Equipamento.query.get_or_404(id)
    manutencao = _manutencao_do_equipamento(id, manutencao_id)
    if not _requer_ajax_modal():
        return redirect(url_for('equipamento.manutencoes', id=id))
    notas = (
        NotaFiscal.query.order_by(NotaFiscal.data_emissao.desc())
        .limit(300)
        .all()
    )
    return render_template(
        'equipamentos/modais/partials/form_editar_manutencao_equipamento.html',
        equipamento=equipamento,
        manutencao=manutencao,
        notas=notas,
    )


def _status_manutencao_validado(valor: Optional[str]) -> str:
    permitidos = {'Pendente', 'Em Andamento', 'Concluída'}
    if not valor or valor not in permitidos:
        raise ValueError('Status da manutenção inválido.')
    return valor


@equipamento_bp.route('/<int:id>/manutencoes/<int:manutencao_id>/modal/finalizar')
@login_required
def modal_finalizar_manutencao(id, manutencao_id):
    from models.nota_fiscal import NotaFiscal

    equipamento = Equipamento.query.get_or_404(id)
    manutencao = _manutencao_do_equipamento(id, manutencao_id)
    if not _requer_ajax_modal():
        return redirect(url_for('equipamento.manutencoes', id=id))
    notas = (
        NotaFiscal.query.order_by(NotaFiscal.data_emissao.desc())
        .limit(300)
        .all()
    )
    return render_template(
        'equipamentos/modais/partials/form_finalizar_manutencao_equipamento.html',
        equipamento=equipamento,
        manutencao=manutencao,
        notas=notas,
    )


@equipamento_bp.route('/<int:id>/manutencoes/<int:manutencao_id>/finalizar', methods=['POST'])
@login_required
def finalizar_manutencao(id, manutencao_id):
    manutencao = _manutencao_do_equipamento(id, manutencao_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        manutencao.status = _status_manutencao_validado(
            request.form.get('status')
        )
        if request.form.get('data_fim'):
            try:
                manutencao.data_fim = datetime.strptime(
                    request.form['data_fim'], '%Y-%m-%dT%H:%M')
            except ValueError:
                raise ValueError('Data de conclusão inválida.')
        else:
            manutencao.data_fim = None
        custo_raw = (request.form.get('custo') or '').strip()
        try:
            manutencao.custo = float(custo_raw) if custo_raw else None
        except ValueError:
            raise ValueError('Valor de custo inválido.')
        nf_raw = (request.form.get('nota_fiscal_id') or '').strip()
        try:
            manutencao.nota_fiscal_id = int(nf_raw) if nf_raw else None
        except ValueError:
            raise ValueError('Nota fiscal inválida.')
        manutencao.observacoes = request.form.get('observacoes') or ''
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Finalização salva com sucesso!',
            })
        flash('Finalização salva com sucesso!', 'success')
        return redirect(url_for('equipamento.manutencoes', id=id))
    except ValueError as err:
        db.session.rollback()
        msg = str(err) or 'Dados inválidos.'
        if is_ajax:
            return jsonify({'success': False, 'message': msg})
        flash(msg, 'danger')
        return redirect(url_for('equipamento.manutencoes', id=id))
    except Exception:
        db.session.rollback()
        if is_ajax:
            return jsonify({
                'success': False,
                'message': 'Erro ao salvar finalização. Verifique os dados.',
            })
        flash('Erro ao salvar finalização!', 'danger')
        return redirect(url_for('equipamento.manutencoes', id=id))


@equipamento_bp.route('/<int:id>/manutencoes/<int:manutencao_id>/editar', methods=['POST'])
@login_required
def editar_manutencao(id, manutencao_id):
    manutencao = _manutencao_do_equipamento(id, manutencao_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        manutencao.tipo = request.form['tipo']
        manutencao.descricao = request.form['descricao']
        manutencao.data_inicio = datetime.strptime(
            request.form['data_inicio'], '%Y-%m-%dT%H:%M')
        manutencao.responsavel = request.form['responsavel']
        manutencao.status = request.form['status']
        manutencao.observacoes = request.form.get('observacoes') or ''
        if request.form.get('data_fim'):
            manutencao.data_fim = datetime.strptime(
                request.form['data_fim'], '%Y-%m-%dT%H:%M')
        else:
            manutencao.data_fim = None
        custo_raw = (request.form.get('custo') or '').strip()
        manutencao.custo = float(custo_raw) if custo_raw else None
        nf_raw = (request.form.get('nota_fiscal_id') or '').strip()
        manutencao.nota_fiscal_id = int(nf_raw) if nf_raw else None
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Manutenção atualizada com sucesso!',
            })
        flash('Manutenção atualizada com sucesso!', 'success')
        return redirect(url_for('equipamento.manutencoes', id=id))
    except Exception:
        db.session.rollback()
        if is_ajax:
            return jsonify({
                'success': False,
                'message': 'Erro ao atualizar manutenção. Verifique os dados.',
            })
        flash('Erro ao atualizar manutenção!', 'danger')
        return redirect(url_for('equipamento.manutencoes', id=id))


@equipamento_bp.route('/<int:id>/manutencoes/<int:manutencao_id>/excluir', methods=['POST'])
@login_required
def excluir_manutencao(id, manutencao_id):
    if not current_user.is_admin:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Apenas administradores podem excluir manutenções.',
            }), 403
        flash('Apenas administradores podem excluir manutenções.', 'danger')
        return redirect(url_for('equipamento.manutencoes', id=id))
    manutencao = _manutencao_do_equipamento(id, manutencao_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        db.session.delete(manutencao)
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Manutenção excluída com sucesso.',
            })
        flash('Manutenção excluída com sucesso.', 'success')
        return redirect(url_for('equipamento.manutencoes', id=id))
    except Exception:
        db.session.rollback()
        if is_ajax:
            return jsonify({
                'success': False,
                'message': 'Erro ao excluir manutenção.',
            })
        flash('Erro ao excluir manutenção!', 'danger')
        return redirect(url_for('equipamento.manutencoes', id=id))


def _emprestimo_aberto_equipamento(equipamento_id: int):
    return EquipamentoEmprestimo.query.filter(
        EquipamentoEmprestimo.equipamento_id == equipamento_id,
        EquipamentoEmprestimo.data_recebimento.is_(None),
    ).first()


@equipamento_bp.route('/emprestimos')
@login_required
def emprestimos():
    ativos = (
        EquipamentoEmprestimo.query.filter(
            EquipamentoEmprestimo.data_recebimento.is_(None)
        )
        .order_by(EquipamentoEmprestimo.data_entrega.desc())
        .all()
    )
    total_historico = EquipamentoEmprestimo.query.count()
    total_devolvido = EquipamentoEmprestimo.query.filter(
        EquipamentoEmprestimo.data_recebimento.isnot(None)
    ).count()
    em_posse = len(ativos)
    colab_distintos = len({e.colaborador_id for e in ativos})
    equip_status_emprestado = Equipamento.query.filter_by(status='Emprestado').count()
    qtd_disponiveis = Equipamento.query.filter_by(status='Ativo').count()
    recentes_devolvidos = (
        EquipamentoEmprestimo.query.filter(
            EquipamentoEmprestimo.data_recebimento.isnot(None)
        )
        .order_by(EquipamentoEmprestimo.data_recebimento.desc())
        .limit(12)
        .all()
    )
    equipamentos_disponiveis = (
        Equipamento.query.filter(Equipamento.status == 'Ativo')
        .order_by(Equipamento.nome)
        .all()
    )
    colaboradores = (
        Colaborador.query.filter(Colaborador.status == 'Ativo')
        .order_by(Colaborador.nome)
        .all()
    )
    return render_template(
        'equipamentos/emprestimos/index.html',
        ativos=ativos,
        recentes_devolvidos=recentes_devolvidos,
        total_historico=total_historico,
        total_devolvido=total_devolvido,
        em_posse=em_posse,
        colab_distintos=colab_distintos,
        equip_status_emprestado=equip_status_emprestado,
        qtd_disponiveis=qtd_disponiveis,
        equipamentos_disponiveis=equipamentos_disponiveis,
        colaboradores=colaboradores,
        now1=datetime.now(),
    )


@equipamento_bp.route('/emprestimos/entregar', methods=['POST'])
@login_required
def emprestimo_entregar():
    try:
        eq_id = int(request.form['equipamento_id'])
        colab_id = int(request.form['colaborador_id'])
        equip = Equipamento.query.get_or_404(eq_id)
        if equip.status != 'Ativo':
            flash('Só é possível emprestar equipamentos com status Ativo.', 'danger')
            return redirect(url_for('equipamento.emprestimos'))
        if _emprestimo_aberto_equipamento(eq_id):
            flash('Este equipamento já possui empréstimo em aberto.', 'danger')
            return redirect(url_for('equipamento.emprestimos'))
        de = (request.form.get('data_entrega') or '').strip()
        data_ent = (
            datetime.strptime(de, '%Y-%m-%dT%H:%M') if de else datetime.now()
        )
        obs = (request.form.get('observacoes') or '').strip()
        emp = EquipamentoEmprestimo(
            equipamento_id=eq_id,
            colaborador_id=colab_id,
            data_entrega=data_ent,
            observacoes=obs,
            usuario_registro_id=current_user.id,
        )
        equip.status = 'Emprestado'
        db.session.add(emp)
        db.session.commit()
        flash('Entrega registrada com sucesso.', 'success')
    except Exception:
        db.session.rollback()
        flash('Erro ao registrar entrega. Verifique os dados.', 'danger')
    return redirect(url_for('equipamento.emprestimos'))


@equipamento_bp.route('/emprestimos/receber', methods=['POST'])
@login_required
def emprestimo_receber():
    try:
        eid = int(request.form['emprestimo_id'])
        emp = EquipamentoEmprestimo.query.get_or_404(eid)
        if emp.data_recebimento is not None:
            flash('Este empréstimo já foi encerrado.', 'warning')
            return redirect(url_for('equipamento.emprestimos'))
        dr = (request.form.get('data_recebimento') or '').strip()
        emp.data_recebimento = (
            datetime.strptime(dr, '%Y-%m-%dT%H:%M') if dr else datetime.now()
        )
        extra = (request.form.get('observacoes') or '').strip()
        if extra:
            prefix = '\n' if (emp.observacoes or '').strip() else ''
            emp.observacoes = (emp.observacoes or '') + prefix + 'Devolução: ' + extra
        eq = emp.equipamento
        if eq and eq.status == 'Emprestado':
            eq.status = 'Ativo'
        db.session.commit()
        flash('Recebimento registrado com sucesso.', 'success')
    except Exception:
        db.session.rollback()
        flash('Erro ao registrar recebimento.', 'danger')
    return redirect(url_for('equipamento.emprestimos'))


# Rotas para Checklist


@equipamento_bp.route('/checklists')
@login_required
def checklists():
    modelos = ChecklistModelo.query.all()
    return render_template('equipamentos/checklists/index.html', modelos=modelos)


@equipamento_bp.route('/checklists/novo', methods=['GET', 'POST'])
@login_required
def novo_checklist():
    if request.method == 'POST':
        try:
            print("Dados do formulário:", request.form)
            print("Itens:", request.form.getlist('item_descricao[]'))
            print("Tipos:", request.form.getlist('item_tipo[]'))
            print("Obrigatórios:", request.form.getlist('item_obrigatorio[]'))
            
            modelo = ChecklistModelo(
                nome=request.form['nome'],
                descricao=request.form['descricao']
            )
            db.session.add(modelo)
            db.session.commit()

            # Adicionar itens do checklist
            itens = request.form.getlist('item_descricao[]')
            tipos = request.form.getlist('item_tipo[]')
            obrigatorios = request.form.getlist('item_obrigatorio[]')

            print(f"Total de itens: {len(itens)}")
            
            for i, descricao in enumerate(itens):
                if descricao.strip():
                    # Garantir que temos um valor para obrigatorio
                    obrigatorio = False
                    if i < len(obrigatorios):
                        obrigatorio = True if obrigatorios[i] == '1' else False
                    
                    print(f"Adicionando item {i+1}: {descricao}, tipo: {tipos[i]}, obrigatório: {obrigatorio}")
                    
                    item = ChecklistItem(
                        modelo_id=modelo.id,
                        descricao=descricao,
                        tipo=tipos[i],
                        obrigatorio=obrigatorio,
                        ordem=i+1
                    )
                    db.session.add(item)

            db.session.commit()
            flash('Modelo de checklist criado com sucesso!', 'success')
            return redirect(url_for('equipamento.checklists'))
        except Exception as e:
            print(f"Erro ao criar checklist: {str(e)}")
            flash('Erro ao criar modelo de checklist!', 'danger')
            db.session.rollback()
            return redirect(url_for('equipamento.checklists'))
    # Se for GET, redireciona para a listagem (já que agora usamos modal)
    return redirect(url_for('equipamento.checklists'))


@equipamento_bp.route('/<int:id>/checklist/novo', methods=['GET', 'POST'])
@login_required
def novo_checklist_equipamento(id):
    # Se o ID for 0 e vier do formulário, usamos o ID do formulário
    if id == 0 and request.method == 'POST' and 'equipamento_id' in request.form:
        id = int(request.form['equipamento_id'])
        
    equipamento = Equipamento.query.get_or_404(id)

    if request.method == 'GET':
        flash(
            'O novo checklist é feito pelo modal: use Novo checklist na listagem ou na ficha do equipamento.',
            'info',
        )
        return redirect(url_for('equipamento.visualizar', id=id))

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            checklist = ChecklistEquipamento(
                equipamento_id=id,
                modelo_id=request.form['modelo_id'],
                data_checklist=datetime.strptime(
                    request.form['data_checklist'], '%Y-%m-%dT%H:%M'),
                responsavel=current_user.nome,
                status='Em Andamento',
                observacoes=request.form.get('observacoes') or ''
            )
            db.session.add(checklist)
            db.session.commit()

            # Criar respostas vazias para cada item do modelo
            modelo = ChecklistModelo.query.get(request.form['modelo_id'])
            for item in modelo.itens:
                resposta = ChecklistResposta(
                    checklist_id=checklist.id,
                    item_id=item.id
                )
                db.session.add(resposta)

            db.session.commit()
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Checklist iniciado com sucesso!',
                    'preencher_equipamento_id': id,
                    'preencher_checklist_id': checklist.id,
                })
            flash('Checklist iniciado com sucesso!', 'success')
            return redirect(
                url_for('equipamento.visualizar', id=id)
                + f'?preencher_checklist={checklist.id}'
            )
        except Exception:
            db.session.rollback()
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': 'Erro ao iniciar checklist. Verifique os dados.',
                })
            flash('Erro ao iniciar checklist!', 'danger')

    return redirect(url_for('equipamento.visualizar', id=id))


@equipamento_bp.route('/<int:id>/checklist/<int:checklist_id>/preencher', methods=['GET', 'POST'])
@login_required
def preencher_checklist(id, checklist_id):
    checklist = ChecklistEquipamento.query.get_or_404(checklist_id)
    if checklist.equipamento_id != id:
        abort(404)

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            for resposta in checklist.respostas:
                resposta_valor = request.form.get(f'resposta_{resposta.id}')
                observacao = request.form.get(f'observacao_{resposta.id}')

                resposta.resposta = resposta_valor
                resposta.observacao = observacao
                resposta.data_resposta = datetime.utcnow()

            checklist.status = 'Concluído'
            db.session.commit()
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Checklist preenchido com sucesso!',
                })
            flash('Checklist preenchido com sucesso!', 'success')
            return redirect(url_for('equipamento.visualizar', id=id))
        except Exception:
            db.session.rollback()
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': 'Erro ao salvar respostas do checklist.',
                })
            flash('Erro ao salvar respostas do checklist!', 'danger')
            return redirect(
                url_for('equipamento.visualizar', id=id)
                + f'?preencher_checklist={checklist_id}'
            )

    if _requer_ajax_modal():
        return render_template(
            'equipamentos/modais/partials/form_preencher_checklist_equipamento.html',
            equipamento=checklist.equipamento,
            checklist=checklist,
        )
    return redirect(
        url_for('equipamento.visualizar', id=id)
        + f'?preencher_checklist={checklist_id}'
    )


@equipamento_bp.route('/checklists/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_checklist(id):
    modelo = ChecklistModelo.query.get_or_404(id)
    if request.method == 'POST':
        try:
            modelo.nome = request.form['nome']
            modelo.descricao = request.form['descricao']
            
            # Remover itens antigos
            for item in modelo.itens:
                db.session.delete(item)
            
            # Adicionar novos itens
            itens = request.form.getlist('item_descricao[]')
            tipos = request.form.getlist('item_tipo[]')
            obrigatorios = request.form.getlist('item_obrigatorio[]')
            
            for i, descricao in enumerate(itens):
                if descricao.strip():
                    # Garantir que temos um valor para obrigatorio
                    obrigatorio = False
                    if i < len(obrigatorios):
                        obrigatorio = True if obrigatorios[i] == '1' else False
                    
                    item = ChecklistItem(
                        modelo_id=modelo.id,
                        descricao=descricao,
                        tipo=tipos[i],
                        obrigatorio=obrigatorio,
                        ordem=i+1
                    )
                    db.session.add(item)
            
            db.session.commit()
            flash('Modelo de checklist atualizado com sucesso!', 'success')
            return redirect(url_for('equipamento.checklists'))
        except Exception as e:
            flash('Erro ao atualizar modelo de checklist!', 'danger')
            db.session.rollback()
    return render_template('equipamentos/checklists/editar.html', modelo=modelo)


@equipamento_bp.route('/checklists/pendentes', methods=['GET'])
@login_required
def checklists_pendentes():
    # Buscar todos os checklists com status "Em Andamento" ou "Pendente"
    checklists = ChecklistEquipamento.query.filter(
        ChecklistEquipamento.status.in_(['Pendente', 'Em Andamento'])
    ).order_by(ChecklistEquipamento.data_checklist.desc()).all()
    
    return render_template('equipamentos/checklists/pendentes.html', checklists=checklists)


@equipamento_bp.route('/checklists/realizar', methods=['GET'])
@login_required
def realizar_checklist():
    # Buscar todos os equipamentos ativos
    equipamentos = Equipamento.query.filter_by(status='Ativo').order_by(Equipamento.nome).all()
    modelos = ChecklistModelo.query.order_by(ChecklistModelo.nome).all()
    
    return render_template('equipamentos/checklists/realizar.html', 
                           equipamentos=equipamentos, 
                           modelos=modelos,
                           now1=datetime.now())


@equipamento_bp.route('/<int:id>/excluir', methods=['GET', 'POST'])
@login_required
def excluir(id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not current_user.is_gerente_ou_superior:
        if is_ajax:
            return jsonify({
                'success': False,
                'message': 'Você não tem permissão para excluir equipamentos!',
            })
        flash('Você não tem permissão para excluir equipamentos!', 'danger')
        return redirect(url_for('equipamento.index'))
    equipamento = Equipamento.query.get_or_404(id)

    if request.method == 'GET' and is_ajax:
        return jsonify({
            'success': True,
            'equipamento_nome': equipamento.nome,
            'equipamento_id': id,
        })

    if request.method == 'GET' and not is_ajax:
        flash('Use a listagem para excluir equipamentos.', 'info')
        return redirect(url_for('equipamento.index'))

    try:
        if equipamento.manutencoes or equipamento.checklists:
            msg = (
                'Não é possível excluir este equipamento pois existem '
                'registros associados a ele!'
            )
            if is_ajax:
                return jsonify({'success': False, 'message': msg})
            flash(msg, 'warning')
            return redirect(url_for('equipamento.index'))

        nome_equipamento = equipamento.nome
        db.session.delete(equipamento)
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'message': f'Equipamento "{nome_equipamento}" excluído com sucesso!',
            })
        flash(f'Equipamento "{nome_equipamento}" excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({
                'success': False,
                'message': f'Erro ao excluir equipamento: {str(e)}',
            })
        flash(f'Erro ao excluir equipamento: {str(e)}', 'danger')

    return redirect(url_for('equipamento.index'))
