$(function() {
  $(document).on('click', '.visualizar-concretagem', function(e) {
    e.preventDefault();
    const id = $(this).data('id');
    $('#visualizar-concretagem-id').text(`#${id}`);
    $('#visualizar-concretagem-loading').show();
    $('#visualizar-concretagem-conteudo').hide();
    $('#modalVisualizarConcretagem').modal('show');

    $.get(`/concretagens/api/${id}/visualizar`, function(data) {
      let html = '';
      html += '<div class="row">';
      html += '<div class="col-12 col-lg-6 mb-4">';
      html += '<div class="card shadow h-100">';
      html += '<div class="card-header py-3 d-flex justify-content-between align-items-center">';
      html += '<h6 class="m-0 font-weight-bold text-primary">Informações Gerais</h6>';
      html += '</div>';
      html += '<div class="card-body">';
      html += '<div class="table-responsive">';
      html += '<table class="table table-sm table-borderless mb-0">';
      html += '<tbody>';
      html += '<tr><th style="width: 35%">Tanques:</th><td>';
      if (data.tanques.length > 0) {
        html += data.tanques.map(t => `${t.nome} (${t.sistema})`).join(', ');
      } else {
        html += '<span class="text-muted fst-italic">Nenhum</span>';
      }
      html += '</td></tr>';
      html += `<tr><th>Pista:</th><td>${data.pista}</td></tr>`;
      html += `<tr><th>Data Concretagem:</th><td>${data.data_concretagem}</td></tr>`;
      html += `<tr><th>Observações:</th><td>${data.observacoes ? data.observacoes : '<span class=\"text-muted fst-italic\">Nenhuma observação</span>'}</td></tr>`;
      html += `<tr><th>Data Cadastro:</th><td>${data.data_cadastro}</td></tr>`;
      html += `<tr><th>Última Atualização:</th><td>${data.ultima_atualizacao}</td></tr>`;
      html += '</tbody></table></div></div></div></div>';
      // Peças
      html += '<div class="col-12 col-lg-6 mb-4">';
      html += '<div class="card shadow h-100">';
      html += '<div class="card-header py-3 d-flex justify-content-between align-items-center">';
      html += `<h6 class="m-0 font-weight-bold text-primary">Peças Concretadas</h6><span class="badge bg-primary text-white rounded-pill">${data.pecas.length}</span>`;
      html += '</div>';
      html += '<div class="card-body p-0 p-sm-3">';
      if (data.pecas.length > 0) {
        html += '<div class="table-responsive">';
        html += '<table class="table table-sm table-hover" id="tabelaPecasVisualizar">';
        html += '<thead><tr><th>Tipo</th><th>Nome</th><th class="d-none d-md-table-cell">Nº Seq.</th><th>Forma</th><th>Usinagem</th></tr></thead>';
        html += '<tbody>';
        data.pecas.forEach(function(p) {
          html += '<tr>';
          html += `<td>${p.tipo}</td>`;
          html += `<td>${p.nome}</td>`;
          html += `<td class="d-none d-md-table-cell">${p.numero_sequencial || '-'}</td>`;
          html += `<td>${p.forma || '-'}</td>`;
          if (p.usinagem) {
            html += `<td><span title="${p.usinagem.data_usinagem} - ${p.usinagem.traco_nome}"><span class="d-none d-md-inline">${p.usinagem.data_usinagem} - ${p.usinagem.traco_nome}</span><span class="d-md-none">${p.usinagem.data_usinagem}</span></span></td>`;
          } else {
            html += '<td>-</td>';
          }
          html += '</tr>';
        });
        html += '</tbody></table></div>';
      } else {
        html += '<div class="alert alert-warning m-3"><i class="fas fa-exclamation-triangle"></i> Nenhuma peça registrada nesta concretagem.</div>';
      }
      html += '</div></div></div></div>';
      html += '</div>';
      $('#visualizar-concretagem-conteudo').html(html);
      $('#visualizar-concretagem-loading').hide();
      $('#visualizar-concretagem-conteudo').show();
      // Inicializar DataTable
      $('#tabelaPecasVisualizar').DataTable({
        responsive: true,
        dom: '<"row"<"col-sm-12 col-md-6"f><"col-sm-12 col-md-6">>rt<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        pageLength: 5,
        lengthChange: false,
        language: {
          url: '//cdn.datatables.net/plug-ins/1.13.4/i18n/pt-BR.json',
          search: "Buscar:",
          zeroRecords: "Nenhuma peça encontrada",
          info: "Mostrando _START_ a _END_ de _TOTAL_ peças",
          infoEmpty: "Mostrando 0 peças",
          infoFiltered: "(filtrado de _MAX_ peças no total)"
        },
        ordering: true,
        order: [[1, 'asc']],
        columnDefs: [
          { responsivePriority: 1, targets: [0, 1, 3, 4] },
          { responsivePriority: 2, targets: [2] }
        ]
      });
    }).fail(function() {
      $('#visualizar-concretagem-loading').html('<span class="text-danger">Erro ao carregar dados da concretagem.</span>');
    });
  });
}); 