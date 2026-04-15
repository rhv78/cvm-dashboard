"""
Coletor de Cotas CVM 2026 - PythonAnywhere
Baixa os informes diarios da CVM e salva o CSV consolidado.
"""

import requests
import zipfile
import io
import os
import csv
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

CNPJS_FUNDOS = [
    "63662461000140",
    "63110432000175",
    "63105699000174",
    "07152165000128",
]

# Gera meses de 2026 até o mês atual
hoje = datetime.today()
MESES = [f"2026{m:02d}" for m in range(1, hoje.month + 1)] if hoje.year == 2026 else [f"2026{m:02d}" for m in range(1, 13)]

PASTA_SAIDA = os.path.join(os.getcwd(), "output")
BASE_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/"

def normcnpj(s):
    return "".join(c for c in (s or "") if c.isdigit())

def baixar_mes(mes):
    url = BASE_URL + f"inf_diario_fi_{mes}.zip"
    print(f"  Baixando {mes}...")
    r = requests.get(url, timeout=180)
    if r.status_code == 404:
        print(f"  {mes} ainda nao disponivel.")
        return None
    r.raise_for_status()
    print(f"  OK — {len(r.content)//1024} KB")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csvname = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(csvname) as f:
            content = f.read().decode("latin-1")
    return content

def processar(csv_text, cnpjs):
    linhas = csv_text.replace("\r","").split("\n")
    if not linhas: return []
    hdrs = linhas[0].split(";")
    # Detecta coluna CNPJ
    col_cnpj = next((h for h in hdrs if "CNPJ_FUNDO" in h), hdrs[0])
    idx_cnpj = hdrs.index(col_cnpj)
    resultado = []
    for linha in linhas[1:]:
        if not linha.strip(): continue
        cols = linha.split(";")
        if len(cols) <= idx_cnpj: continue
        cnpj = normcnpj(cols[idx_cnpj])
        if cnpj not in cnpjs: continue
        obj = dict(zip(hdrs, cols))
        obj["CNPJ_FUNDO"] = cnpj
        resultado.append(obj)
    return resultado

def main():
    print("\n=== Coletor CVM 2026 (PythonAnywhere) ===\n")
    os.makedirs(PASTA_SAIDA, exist_ok=True)

    cnpjs = set(CNPJS_FUNDOS)
    todos = []

    for mes in MESES:
        try:
            texto = baixar_mes(mes)
            if texto is None:
                break
            rows = processar(texto, cnpjs)
            todos.extend(rows)
            print(f"  {len(rows)} registros dos fundos")
        except Exception as e:
            print(f"  ERRO em {mes}: {e}")
            break

    if not todos:
        print("Nenhum dado encontrado.")
        return False

    # Salva CSV consolidado
    saida = os.path.join(PASTA_SAIDA, "cotas_fundos_2026_consolidado.csv")
    campos = list(todos[0].keys())
    with open(saida, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(todos)

    print(f"\nCSV salvo: {saida} ({len(todos)} registros)\n")
    return True

if __name__ == "__main__":
    main()
