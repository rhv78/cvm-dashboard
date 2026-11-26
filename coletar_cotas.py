"""
Coletor de Cotas CVM 2026 - PythonAnywhere
Baixa os informes diarios da CVM e salva o CSV consolidado.
Tambem baixa o CDI diario real (serie 12 do SGS/Banco Central) e salva num
CSV separado, pra gerar_dashboard.py usar a taxa publicada de verdade em vez
de so a taxa anual fixa aproximada em CDI_PERIODOS.
"""

import requests
import zipfile
import io
import os
import csv
import time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

CNPJS_FUNDOS = [
    "63662461000140",
    "63110432000175",
    "63105699000174",
    "07152165000128",
    "01608399000150",   # CSHG Top Acoes (fundo aberto)
]

# Gera meses de 2026 até o mês atual
hoje = datetime.today()
MESES = [f"2026{m:02d}" for m in range(1, hoje.month + 1)] if hoje.year == 2026 else [f"2026{m:02d}" for m in range(1, 13)]

PASTA_SAIDA = os.path.join(os.getcwd(), "output")
BASE_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/"

# ── CDI diario (Banco Central / SGS) ──────────────────────────────────────────
# Serie 12 = "Taxa de juros - CDI", em % ao dia. Base publica e gratuita:
# https://www3.bcb.gov.br/sgspub/localizarseries/localizarSeries.do
CDI_SERIE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
CDI_DT_INICIO = "01/01/2026"   # dd/mm/aaaa, formato exigido pela API do BCB
CDI_TENTATIVAS = 3
CDI_BACKOFF = 5   # segundos: 5s, 10s, 15s

def baixar_cdi_bcb():
    """Baixa a serie diaria do CDI do SGS/BCB. Retorna lista de dicts
    {"DT_COMPTC": "AAAA-MM-DD", "TAXA_PCT": "0.055131"} ou [] se falhar
    (nesse caso gerar_dashboard.py cai de volta pra taxa anual fixa)."""
    dt_fim = hoje.strftime("%d/%m/%Y")
    params = {"formato": "json", "dataInicial": CDI_DT_INICIO, "dataFinal": dt_fim}
    for tentativa in range(1, CDI_TENTATIVAS + 1):
        try:
            print(f"  Baixando CDI diario do BCB (serie 12), tentativa {tentativa}...")
            r = requests.get(CDI_SERIE_URL, params=params, timeout=30)
            r.raise_for_status()
            dados = r.json()
            if not dados:
                print("  AVISO: BCB retornou lista vazia.")
                return []
            saida = []
            for item in dados:
                dia, mes, ano = item["data"].split("/")
                saida.append({"DT_COMPTC": f"{ano}-{mes}-{dia}", "TAXA_PCT": item["valor"]})
            print(f"  OK — {len(saida)} dias de CDI baixados do BCB")
            return saida
        except Exception as e:
            print(f"  ERRO ao baixar CDI (tentativa {tentativa}/{CDI_TENTATIVAS}): {e}")
            if tentativa < CDI_TENTATIVAS:
                time.sleep(CDI_BACKOFF * tentativa)
    print("  AVISO: nao foi possivel baixar o CDI do BCB. gerar_dashboard.py vai usar a taxa anual fixa (CDI_PERIODOS) como fallback.")
    return []

# ── FIIs / ativos de bolsa (B3) — fontes oficiais da B3 ───────────────────────
# FII nao aparece no informe diario da CVM.
#  - Fechamento: arquivo COTAHIST diario da B3 (um ZIP por pregao), mercado a
#    vista (TPMERC 010). So baixa os pregoes que ainda nao estao no cache.
#  - Rendimentos: pagina do fundo no site da B3 (fundsProxy), por data-com.
# Tudo vai para docs/b3_cotacoes.csv, que o workflow ja commita: se a B3 falhar
# num dia, o dashboard segue com o cache. Na 1a execucao baixa o ano inteiro
# (~230 arquivos, alguns minutos); depois, so os dias novos.
TICKERS_B3 = {"HFOF11": "18307582000119"}   # ticker -> CNPJ
B3_CACHE = os.path.join(os.getcwd(), "docs", "b3_cotacoes.csv")
B3_DT_INICIO = "2025-12-29"
B3_HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{d}.ZIP"
B3_FUNDS_URL = "https://sistemaswebb3-listados.b3.com.br/fundsProxy/fundsCall/GetListedSupplementFunds/{p}"

def _cotahist_dia(dt, tickers):
    """dt 'aaaa-mm-dd' -> {ticker: fechamento}; None se o arquivo nao existe (sem pregao/ainda nao publicado)."""
    nome = dt[8:10] + dt[5:7] + dt[0:4]
    r = requests.get(COTAHIST_URL.format(d=nome), headers=B3_HDR, timeout=60)
    if r.status_code == 404 or (r.status_code == 200 and not r.content.startswith(b"PK")):
        return None
    r.raise_for_status()
    out = {}
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            for raw in f:
                lin = raw.decode("latin-1")
                if not lin.startswith("01"):
                    continue
                tk = lin[12:24].strip()
                if tk in tickers and lin[24:27] == "010":       # mercado a vista
                    preult = int(lin[108:121]) / 100.0
                    fatcot = int(lin[210:217] or 1) or 1
                    out[tk] = preult / fatcot
    return out

def _rendimentos_b3(ticker, cnpj):
    """[(data_com 'aaaa-mm-dd', valor por cota)] dos rendimentos em dinheiro."""
    import base64, json
    par = {"cnpj": cnpj, "identifierFund": ticker[:4], "typeFund": 7}
    url = B3_FUNDS_URL.format(p=base64.b64encode(json.dumps(par, separators=(",", ":")).encode()).decode())
    r = requests.get(url, headers=B3_HDR, timeout=30)
    r.raise_for_status()
    js = r.json()
    if js.get("stockDividends"):
        print(f"  ATENCAO {ticker}: B3 lista eventos em cotas (desdobramento/grupamento/bonificacao): "
              f"{js['stockDividends']} — confira a quantidade de cotas")
    out = []
    for ev in js.get("cashDividends") or []:
        d = ev.get("lastDatePrior") or ""
        if len(d) == 10:
            out.append((f"{d[6:10]}-{d[3:5]}-{d[0:2]}", float(ev["rate"].replace(".", "").replace(",", "."))))
    return out

def atualizar_b3():
    from datetime import date, timedelta
    cache = {}   # (ticker, data) -> {"fech": float|None, "div": float}
    if os.path.exists(B3_CACHE):
        with open(B3_CACHE, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=";"):
                cache[(row["TICKER"], row["DATA"])] = {
                    "fech": float(row["FECHAMENTO"]) if row["FECHAMENTO"] else None,
                    "div": float(row["DIVIDENDO"] or 0)}
    tickers = set(TICKERS_B3)
    sem_pregao = {d for (t, d), v in cache.items() if t == "_SEM_PREGAO"}
    # dias ja processados (arquivo baixado). Se incluir um ticker novo em
    # TICKERS_B3, apague docs/b3_cotacoes.csv para rebaixar o historico.
    feitos = {d for (t, d), v in cache.items() if t == "_BAIXADO"}

    # 1) Fechamentos (COTAHIST diario) — dias uteis que faltam
    hoje = date.today()
    d = date.fromisoformat(B3_DT_INICIO); novos = falhas = 0
    while d <= hoje:
        ds = d.isoformat()
        if d.weekday() < 5 and ds not in feitos and ds not in sem_pregao:
            try:
                res = _cotahist_dia(ds, tickers)
                if res is None:
                    if (hoje - d).days > 5:          # antigo e sem arquivo = feriado
                        cache[("_SEM_PREGAO", ds)] = {"fech": None, "div": 0.0}
                else:
                    cache[("_BAIXADO", ds)] = {"fech": None, "div": 0.0}
                    for tk, v in res.items():
                        cache[(tk, ds)] = {"fech": v, "div": cache.get((tk, ds), {}).get("div", 0.0)}
                    novos += 1
            except Exception as e:
                falhas += 1
                print(f"  ERRO COTAHIST {ds}: {e}")
                if falhas >= 5:
                    print("  AVISO: muitas falhas na B3 — paro por hoje e mantenho o cache")
                    break
        d += timedelta(days=1)
    print(f"  COTAHIST: {novos} pregao(oes) novo(s) baixado(s)")

    # 2) Rendimentos (por data-com) — a lista da B3 substitui a do cache
    for tk, cnpj in TICKERS_B3.items():
        try:
            evs = _rendimentos_b3(tk, cnpj)
            for k in [k for k in cache if k[0] == tk]:
                cache[k]["div"] = 0.0
            for dc, v in evs:
                if dc >= B3_DT_INICIO:
                    c = cache.setdefault((tk, dc), {"fech": None, "div": 0.0})
                    c["div"] += v
            print(f"  {tk}: {sum(1 for dc, _ in evs if dc >= B3_DT_INICIO)} rendimento(s) desde {B3_DT_INICIO}")
        except Exception as e:
            print(f"  AVISO: rendimentos de {tk} nao baixados ({e}) — mantendo o cache")

    os.makedirs(os.path.dirname(B3_CACHE), exist_ok=True)
    with open(B3_CACHE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["TICKER", "DATA", "FECHAMENTO", "DIVIDENDO"])
        for (t, ds), v in sorted(cache.items()):
            w.writerow([t, ds, "" if v["fech"] is None else f"{v['fech']:.4f}", f"{v['div']:.8f}"])
    print(f"  Cache B3 salvo: {B3_CACHE} ({len(cache)} linhas)\n")

def salvar_cdi(linhas):
    if not linhas:
        return
    saida = os.path.join(PASTA_SAIDA, "cdi_bcb_2026.csv")
    with open(saida, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["DT_COMPTC", "TAXA_PCT"], delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    print(f"  CDI salvo: {saida} ({len(linhas)} registros)\n")

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

    # CDI real do BCB — nao derruba o coletor se falhar, so fica sem cache
    # e o gerador do dashboard usa a taxa anual fixa como fallback.
    print("Baixando CDI diario (Banco Central)...")
    cdi_linhas = baixar_cdi_bcb()
    salvar_cdi(cdi_linhas)

    # Cotacoes da B3 (FIIs) — tambem nunca derruba o coletor
    print("Baixando cotacoes e rendimentos da B3 (FIIs)...")
    try:
        atualizar_b3()
    except Exception as e:
        print(f"  AVISO: falha nas cotacoes B3 ({e}) — dashboard usa o cache existente")

    return True

if __name__ == "__main__":
    main()
