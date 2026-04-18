import logging
import time
from datetime import datetime

from flask import render_template, request
from flask_login import login_required
from sqlalchemy import func

from models.database import db
from models.nota_fiscal import CNPJS_FILIAIS, CNPJS_MATRIZ, NotaFiscal, NotaFiscalItem
from models.plano_conta import PlanoConta
from models.unidade import Unidades

from .. import nota_fiscal_bp
from ..services.query_notas import api_get_dados_notas_fiscais

logger = logging.getLogger(__name__)


@nota_fiscal_bp.route("/")
@login_required
def index():
    planos_conta = PlanoConta.query.filter_by(ativo=True).order_by(PlanoConta.indice).all()
    unidades = Unidades.query.filter_by(ativo=True).order_by(Unidades.nome).all()
    return render_template(
        "notas_fiscais/nota_fiscal/index.html",
        planos_conta=planos_conta,
        unidades=unidades,
    )




