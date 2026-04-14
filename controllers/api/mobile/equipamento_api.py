"""
API REST mobile para equipamentos.
"""
import base64
import binascii

from flask import request, jsonify, g, make_response, abort
from sqlalchemy import or_

from models.database import db
from models.equipamento import Equipamento, Manutencao, EquipamentoEmprestimo
from models.material import Materiais
from models.upload import Upload
from utils.decorators import jwt_required
from utils.equipamento_dados_adicionais import parse_extras, dump_extras


def _url_foto_material(material_id):
    """Retorna a URL da foto do material vinculado, ou None."""
    if not material_id:
        return None
    mat = Materiais.query.get(material_id)
    if not mat:
        return None
    img_id = mat.imagem_upload_id
    if not img_id:
        return None
    return f'/api/mobile/uploads/{img_id}/imagem'


def _serializar_manutencao(m: Manutencao) -> dict:
    return {
        'id': m.id,
        'equipamento_id': m.equipamento_id,
        'tipo': m.tipo,
        'descricao': m.descricao,
        'data_inicio': m.data_inicio.isoformat() if m.data_inicio else None,
        'data_fim': m.data_fim.isoformat() if m.data_fim else None,
        'custo': float(m.custo) if m.custo is not None else None,
        'responsavel': m.responsavel,
        'status': m.status,
        'observacoes': m.observacoes,
        'nota_fiscal_id': m.nota_fiscal_id,
        'data_cadastro': m.data_cadastro.isoformat() if m.data_cadastro else None,
    }


def _serializar_equipamento(eq: Equipamento) -> dict:
    ex = parse_extras(eq.dados_adicionais)
    material_id = ex.get('material_id')
    return {
        'id': eq.id,
        'nome': eq.nome,
        'tipo': eq.tipo,
        'propriedade': eq.propriedade,
        'modelo': eq.modelo,
        'numero_serie': eq.numero_serie,
        'nota_fiscal': eq.nota_fiscal,
        'data_aquisicao': eq.data_aquisicao.isoformat() if eq.data_aquisicao else None,
        'status': eq.status,
        'observacoes': eq.observacoes,
        'patrimonio': ex.get('patrimonio') or '',
        'checklist_modelo_id': ex.get('checklist_modelo_id'),
        'material_id': material_id,
        'foto_url': _url_foto_material(material_id),
        'fotos_ids': ex.get('fotos', []),
    }


def register(bp):
    """Registra rotas mobile de equipamentos no blueprint fornecido."""

    @bp.route('/mobile/equipamentos/busca', methods=['GET'])
    @jwt_required
    def mobile_equipamento_busca():
        """
        Busca equipamento por tag (id ou patrimônio).
        Query param: ?tag=valor
        """
        tag = (request.args.get('tag') or '').strip()
        if not tag:
            return jsonify({'error': 'Parâmetro "tag" é obrigatório.'}), 400

        # 1) Busca direta por ID
        if tag.isdigit():
            eq = Equipamento.query.get(int(tag))
            if eq:
                return jsonify({'equipamento': _serializar_equipamento(eq)})

        # 2) Busca por patrimônio dentro de dados_adicionais (JSON)
        like_pattern = f'%"patrimonio"%:%"{tag}"%'
        equipamentos = (
            Equipamento.query
            .filter(Equipamento.dados_adicionais.ilike(like_pattern))
            .all()
        )

        # Filtragem exata do patrimônio (o LIKE pode trazer falsos positivos)
        resultados = []
        for eq in equipamentos:
            ex = parse_extras(eq.dados_adicionais)
            patrimonio = (ex.get('patrimonio') or '').strip()
            if patrimonio.lower() == tag.lower():
                resultados.append(eq)

        if len(resultados) == 1:
            return jsonify({'equipamento': _serializar_equipamento(resultados[0])})

        if len(resultados) > 1:
            return jsonify({
                'equipamentos': [_serializar_equipamento(eq) for eq in resultados],
                'total': len(resultados),
            })

        return jsonify({'error': 'Equipamento não encontrado.'}), 404

    @bp.route('/mobile/equipamentos/busca-nome', methods=['GET'])
    @jwt_required
    def mobile_equipamento_busca_nome():
        print('request.args: ',request.args)
        """
        Busca equipamentos por nome (parcial, case-insensitive).
        Query params: ?nome=valor  &limite=20 (opcional, padrão 20)
        """
        nome = (request.args.get('nome') or '').strip()
        if not nome:
            return jsonify({'error': 'Parâmetro "nome" é obrigatório.'}), 400

        limite = min(int(request.args.get('limite', 20)), 100)
        equipamentos = (
            Equipamento.query
            .filter(Equipamento.nome.ilike(f'%{nome}%'))
            .order_by(Equipamento.nome)
            .limit(limite)
            .all()
        )

        output = {
            'equipamentos': [_serializar_equipamento(eq) for eq in equipamentos],
            'total': len(equipamentos),
        }
        print('output: ',output)
        return jsonify(output)

    @bp.route('/mobile/equipamentos/<int:id>/tag', methods=['PUT'])
    @jwt_required
    def mobile_equipamento_set_tag(id):
        """Grava ou atualiza o número da tag (patrimônio) no equipamento."""
        eq = Equipamento.query.get(id)
        if not eq:
            return jsonify({'error': 'Equipamento não encontrado.'}), 404

        dados = request.get_json(silent=True)
        if not dados:
            return jsonify({'error': 'Corpo JSON obrigatório.'}), 400

        tag = (dados.get('tag') or '').strip()
        if not tag:
            return jsonify({'error': 'Campo "tag" é obrigatório.'}), 400

        extras = parse_extras(eq.dados_adicionais)
        extras['patrimonio'] = tag
        eq.dados_adicionais = dump_extras(extras)
        db.session.commit()

        return jsonify({
            'message': 'Tag atualizada com sucesso.',
            'equipamento': _serializar_equipamento(eq),
        })

    @bp.route('/mobile/equipamentos/<int:id>/manutencoes', methods=['GET'])
    @jwt_required
    def mobile_listar_manutencoes(id):
        print('request.args: ',request)
        """Lista manutenções de um equipamento."""
        eq = Equipamento.query.get(id)
        if not eq:
            return jsonify({'error': 'Equipamento não encontrado.'}), 404

        manutencoes = (
            Manutencao.query
            .filter_by(equipamento_id=id)
            .order_by(Manutencao.data_inicio.desc())
            .all()
        )
        output = {
            'manutencoes': [_serializar_manutencao(m) for m in manutencoes],
            'total': len(manutencoes),
        }
        print('output: ',output)
        return jsonify(output)

    @bp.route('/mobile/equipamentos/<int:id>/manutencoes', methods=['POST'])
    @jwt_required
    def mobile_criar_manutencao(id):
        """Cria uma nova manutenção para o equipamento."""
        from datetime import datetime

        eq = Equipamento.query.get(id)
        if not eq:
            return jsonify({'error': 'Equipamento não encontrado.'}), 404

        dados = request.get_json(silent=True)
        if not dados:
            return jsonify({'error': 'Corpo JSON obrigatório.'}), 400

        descricao = (dados.get('descricao') or '').strip()
        if not descricao:
            return jsonify({'error': 'Campo "descricao" é obrigatório.'}), 400

        data_inicio_str = (dados.get('data_inicio') or '').strip()
        if not data_inicio_str:
            return jsonify({'error': 'Campo "data_inicio" é obrigatório.'}), 400

        try:
            data_inicio = datetime.fromisoformat(data_inicio_str)
        except ValueError:
            return jsonify({'error': 'Campo "data_inicio" com formato inválido. Use ISO 8601 (ex: 2026-04-13T10:00:00).'}), 400

        tipo = (dados.get('tipo') or 'Corretiva').strip()
        if tipo not in ('Preventiva', 'Corretiva'):
            return jsonify({'error': 'Campo "tipo" deve ser "Preventiva" ou "Corretiva".'}), 400

        status_m = (dados.get('status') or 'Pendente').strip()
        if status_m not in ('Pendente', 'Em Andamento', 'Concluída'):
            return jsonify({'error': 'Campo "status" deve ser "Pendente", "Em Andamento" ou "Concluída".'}), 400

        usuario = g.usuario_atual
        responsavel = (dados.get('responsavel') or '').strip() or usuario.nome

        manutencao = Manutencao(
            equipamento_id=id,
            tipo=tipo,
            descricao=descricao,
            data_inicio=data_inicio,
            responsavel=responsavel,
            status=status_m,
            observacoes=(dados.get('observacoes') or '').strip(),
        )

        data_fim_str = (dados.get('data_fim') or '').strip()
        if data_fim_str:
            try:
                manutencao.data_fim = datetime.fromisoformat(data_fim_str)
            except ValueError:
                pass

        custo = dados.get('custo')
        if custo is not None:
            try:
                manutencao.custo = float(custo)
            except (ValueError, TypeError):
                pass

        nf_id = dados.get('nota_fiscal_id')
        if nf_id:
            try:
                manutencao.nota_fiscal_id = int(nf_id)
            except (ValueError, TypeError):
                pass

        try:
            db.session.add(manutencao)
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({'error': 'Erro ao registrar manutenção.'}), 500

        return jsonify({
            'message': 'Manutenção registrada com sucesso.',
            'manutencao': _serializar_manutencao(manutencao),
        }), 201

    @bp.route('/mobile/uploads/<int:upload_id>/imagem', methods=['GET'])
    @jwt_required
    def mobile_upload_imagem(upload_id):
        print('request.args: ',request.args)
        """Serve a imagem de um Upload (foto equipamento ou imagem material)."""
        u = Upload.query.get_or_404(upload_id)
        try:
            data = u.get_blob()
        except (binascii.Error, ValueError, TypeError):
            abort(404)
        if not data:
            abort(404)
        resp = make_response(data)
        resp.headers['Content-Type'] = u.mimetype or 'image/jpeg'
        resp.headers['Content-Disposition'] = f'inline; filename="{u.filename}"'
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
