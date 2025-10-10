import os
import csv
import sys
from decimal import Decimal, ROUND_HALF_UP
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string


def main() -> None:
    # Garante saída UTF-8 no console do Windows, quando possível
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    base_dir = os.path.dirname(__file__)
    xlsx_path = os.path.join(base_dir, 'orc.xlsx')

    if not os.path.exists(xlsx_path):
        print(f"Arquivo não encontrado: {xlsx_path}")
        return

    try:
        wb = load_workbook(filename=xlsx_path, data_only=True, read_only=True)
    except Exception as exc:
        print(f"Falha ao abrir o arquivo Excel: {exc}")
        return

    sheet_name = 'INSUMOS'
    if sheet_name not in wb.sheetnames:
        print(f"Aba '{sheet_name}' não encontrada. Abas disponíveis: {', '.join(wb.sheetnames)}")
        return

    ws = wb[sheet_name]

    column_letters = ['D', 'K', 'O', 'Q', 'R']
    column_indices = [column_index_from_string(letter) for letter in column_letters]

    # Cabeçalho (linha 1)
    header = []
    for letter, idx in zip(column_letters, column_indices):
        value = ws.cell(row=1, column=idx).value
        header.append(str(value) if value is not None else letter)

    def format_two_decimals(value):
        if value is None or value == "":
            return ""
        if isinstance(value, (int, float, Decimal)):
            try:
                dec = Decimal(str(value))
                return str(dec.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            except Exception:
                return f"{value:.2f}" if isinstance(value, (int, float)) else str(value)
        return value

    # Linhas com dados a partir da linha 2
    rows = []
    max_row = ws.max_row or 1
    print(f"colunas: {column_letters}")
    print(f"indices: {column_indices}")
    for row_idx in range(2, max_row + 1):
        current = []
        has_any_value = False
        if ws.cell(row=row_idx, column=4).value in (None, ""):
            continue
        for idx in column_indices:
            value = ws.cell(row=row_idx, column=idx).value
            if value not in (None, ""):
                has_any_value = True
            formatted = format_two_decimals(value)
            current.append(formatted)
        if has_any_value:
            rows.append(current)

    # Exporta CSV
    out_csv = os.path.join(base_dir, 'insumos_D_K_P_Q_R.csv')
    try:
        # utf-8-sig adiciona BOM para melhor compatibilidade com Excel no Windows
        with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)
            writer.writerows(rows)
    except Exception as exc:
        print(f"Falha ao salvar CSV: {exc}")

    # Imprime uma prévia como tabela Markdown (primeiras 20 linhas)
    preview = rows[:20]
    print("| " + " | ".join(header) + " |")
    print("| " + " | ".join(["---"] * len(header)) + " |")
    for r in preview:
        print("| " + " | ".join(str(c) if c is not None else "" for c in r) + " |")

    print(f"\nArquivo CSV salvo em: {out_csv}")
    print(f"Total de linhas: {len(rows)} (mostrando as primeiras {len(preview)})")


if __name__ == '__main__':
    main()

