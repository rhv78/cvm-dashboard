"""
Gerador de Dashboard CVM 2026
Le o CSV consolidado gerado pelo cotas_cvm_app.py e gera um HTML
com graficos interativos de rentabilidade real dos fundos.

Uso: python gerar_dashboard_cvm.py
O dashboard HTML sera aberto automaticamente no browser.
"""

import pandas as pd
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACAO
# ──────────────────────────────────────────────────────────────────────────────

_BASE = os.getcwd()
CSV_PATH = os.path.join(_BASE, "output", "cotas_fundos_2026_consolidado.csv")

# Regras de cotas por fundo e periodo
# "ate": None = vale ate o fim dos dados
COTAS_REGRAS = {
    "63662461000140": [
        {"cotas": 10207.491, "ate": "2026-03-17"},
        {"cotas": 12182.748, "ate": None},
    ],
    "63110432000175": [
        {"cotas": 11162.360, "ate": None},
    ],
    "63105699000174": [
        {"cotas": 10849.349, "ate": None},
    ],
    "07152165000128": [
        {"cotas": 1793.758, "ate": "2026-03-17"},
        {"cotas": 0.0,      "ate": None},
    ],
}

# ── ESCALA E FLUXOS ───────────────────────────────────────────────────────────
# Os valores da CVM sao em R$ cheios. O dashboard trabalha com valores
# divididos por ESCALA (mesma convencao das cotas em COTAS_REGRAS).
ESCALA = 1000.0

# True  -> patrimonio = VL_PATRIM_LIQ / ESCALA (dado real da CVM, absorve
#          resgates e aportes automaticamente). Exige ser 100% cotista.
# False -> patrimonio = VL_QUOTA * cotas fixas de COTAS_REGRAS (modo antigo).
USAR_PL_CVM = True

# Movimentacoes que NAO sao entrada/saida de dinheiro seu, e sim transferencia
# entre fundos da propria carteira (ex.: incorporacao). Continuam neutralizadas
# no calculo de rentabilidade, mas nao entram no total de "Resgates".
FLUXOS_INTERNOS = [
    {"cnpj": "07152165000128", "de": "2026-03-16", "ate": "2026-03-20"},  # EVEREST -> Lagunna
    {"cnpj": "63662461000140", "de": "2026-03-16", "ate": "2026-03-20"},  # Lagunna <- EVEREST
]

def eh_fluxo_interno(cnpj_raw, dt):
    for r in FLUXOS_INTERNOS:
        if r["cnpj"] == cnpj_raw and r["de"] <= dt <= r["ate"]:
            return True
    return False

CORES = {
    "63662461000140": "#1D9E75",
    "63110432000175": "#378ADD",
    "63105699000174": "#BA7517",
    "07152165000128": "#D85A30",
    "cdi":            "#7F77DD",
}

NOMES_FUNDOS = {
    "63662461000140": "Lagunna_78",
    "63110432000175": "Neblina_78",
    "63105699000174": "Neblina_Equity_78",
    "07152165000128": "EVEREST",
}

VALOR_RF_CDI = 27040.55  # R$ aplicados a 100% CDI

# Taxa diária CDI por período (fórmula: (1 + taxa_anual)^(1/252) - 1)
CDI_PERIODOS = [
    {"de": "2026-01-01", "ate": "2026-03-18", "anual": 14.90},
    {"de": "2026-03-19", "ate": "2099-12-31", "anual": 14.65},
]

def taxa_diaria_cdi(dt):
    for p in CDI_PERIODOS:
        if p["de"] <= dt <= p["ate"]:
            return (1 + p["anual"] / 100) ** (1 / 252) - 1
    return 0.0

# ──────────────────────────────────────────────────────────────────────────────
# AUXILIARES
# ──────────────────────────────────────────────────────────────────────────────

def norm(s):
    return "".join(c for c in (s or "") if c.isdigit())

def fmt_cnpj(s):
    s = s.zfill(14)
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"

def cotas_em(cnpj_raw, dt):
    for r in COTAS_REGRAS.get(cnpj_raw, []):
        if r["ate"] is None or dt <= r["ate"]:
            return r["cotas"]
    return 0.0

# ──────────────────────────────────────────────────────────────────────────────
# LEITURA
# ──────────────────────────────────────────────────────────────────────────────

print("\n=== Gerador de Dashboard CVM 2026 ===\n")

if not os.path.exists(CSV_PATH):
    print(f"ERRO: {CSV_PATH} nao encontrado.")
    print("Execute o cotas_cvm_app.py primeiro para gerar o CSV.")
    input("\nPressione Enter para fechar...")
    sys.exit(1)

print(f"Lendo: {CSV_PATH}")
df = pd.read_csv(CSV_PATH, sep=";", encoding="utf-8-sig", dtype=str)
print(f"  {len(df):,} registros | colunas: {list(df.columns)}\n")

# ── COTA BASE: último dia útil de dez/2025 ───────────────────────────────────
def baixar_cota_base(cnpjs_raw):
    url = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202512.zip"
    print("  Baixando cota base (dez/2025) da CVM...")
    try:
        import requests as req, zipfile, io, csv
        r = req.get(url, timeout=120)
        print(f"  HTTP {r.status_code} — {len(r.content)//1024} KB")
        if r.status_code != 200:
            print(f"  AVISO: nao foi possivel baixar dez/2025. Usando primeira cota de 2026.")
            return {}
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csvname = next(n for n in z.namelist() if n.endswith(".csv"))
            with z.open(csvname) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")
                all_rows = list(reader)
        if not all_rows:
            print("  AVISO: arquivo vazio"); return {}
        col_cnpj = "CNPJ_FUNDO_CLASSE" if "CNPJ_FUNDO_CLASSE" in all_rows[0] else "CNPJ_FUNDO"
        print(f"  Coluna CNPJ: {col_cnpj}")
        print(f"  Exemplos de CNPJ no arquivo: {[norm(r.get(col_cnpj,'')) for r in all_rows[:5]]}")
        print(f"  CNPJs buscados: {list(cnpjs_raw)}")
        rows = [r for r in all_rows if norm(r.get(col_cnpj,"")) in cnpjs_raw]
        print(f"  {len(rows)} registros dos fundos em dez/2025")
        ultima = {}
        for row in rows:
            c  = norm(row.get(col_cnpj,""))
            dt = row.get("DT_COMPTC","")
            if c not in ultima or dt > ultima[c]["dt"]:
                try: vl = float(row.get("VL_QUOTA","0").replace(",","."))
                except: vl = 0.0
                try: pl = float((row.get("VL_PATRIM_LIQ") or "0").replace(",","."))
                except: pl = 0.0
                ultima[c] = {"dt": dt, "cota": vl, "pl": pl}
        for c, v in ultima.items():
            print(f"    {fmt_cnpj(c)}: cota {v['cota']:.8f} | PL R$ {v['pl']:,.2f} em {v['dt']}")
        print()
        return ultima
    except Exception as e:
        print(f"  AVISO: {e}\n  Usando primeira cota de 2026 como base.\n")
        return {}

cota_base_dez25 = baixar_cota_base(set(COTAS_REGRAS.keys()))

col = next((c for c in ["CNPJ_FUNDO","CNPJ_FUNDO_CLASSE"] if c in df.columns), df.columns[0])
df["CNPJ_NORM"] = df[col].apply(norm)
df["VL_QUOTA_F"] = pd.to_numeric(df["VL_QUOTA"].str.replace(",","."), errors="coerce")
df["DT_COMPTC"]  = df["DT_COMPTC"].str.strip()

# ── Colunas de patrimonio e movimentacao (nomes variam entre layouts da CVM) ──
def achar_col(*fragmentos):
    cols = [c.strip() for c in df.columns]
    for frag in fragmentos:
        for c in cols:
            if c.upper() == frag:
                return c
    for frag in fragmentos:
        for c in cols:
            if frag in c.upper():
                return c
    return None

def serie_num(nome_log, *fragmentos):
    c = achar_col(*fragmentos)
    if c is None:
        print(f"  AVISO: coluna {nome_log} nao encontrada no CSV — assumindo zero.")
        return pd.Series(0.0, index=df.index)
    print(f"  Coluna {nome_log}: {c}")
    return pd.to_numeric(
        df[c].astype(str).str.strip().str.replace(",", ".", regex=False),
        errors="coerce"
    ).fillna(0.0)

df["PL_F"]    = serie_num("patrimonio", "VL_PATRIM_LIQ", "PATRIM_LIQ")
df["CAPTC_F"] = serie_num("captacao",   "CAPTC_DIA", "CAPTC")
df["RESG_F"]  = serie_num("resgate",    "RESG_DIA", "RESG")

# Diagnostico: mostra o que foi realmente lido nas colunas de movimentacao
_soma_r = float(df["RESG_F"].sum()); _soma_c = float(df["CAPTC_F"].sum())
print(f"  Colunas disponiveis no CSV: {list(df.columns[:12])}")
print(f"  Soma bruta RESG_DIA no CSV: R$ {_soma_r:,.2f}  |  CAPTC_DIA: R$ {_soma_c:,.2f}")
if _soma_r == 0 and _soma_c == 0:
    print("  ATENCAO: nenhuma movimentacao encontrada no CSV. Ou nao houve resgate/aporte")
    print("           no periodo, ou a coluna nao veio no arquivo da CVM.")
print()

df = df.dropna(subset=["VL_QUOTA_F","DT_COMPTC"]).sort_values("DT_COMPTC")

datas_todas = sorted(df["DT_COMPTC"].unique())

# Fator CDI diário por data
fator_cdi = {dt: taxa_diaria_cdi(dt) for dt in datas_todas}

cdi_idx = {}; acum = 1.0
for dt in datas_todas:
    acum *= (1+fator_cdi[dt]); cdi_idx[dt] = acum

# ──────────────────────────────────────────────────────────────────────────────
# PROCESSA FUNDOS
# ──────────────────────────────────────────────────────────────────────────────

fundos = []

for cnpj_raw in COTAS_REGRAS:
    df_f = df[df["CNPJ_NORM"]==cnpj_raw].drop_duplicates("DT_COMPTC").sort_values("DT_COMPTC")
    if df_f.empty:
        print(f"  SEM DADOS: {fmt_cnpj(cnpj_raw)}"); continue

    nome = NOMES_FUNDOS.get(cnpj_raw, fmt_cnpj(cnpj_raw))
    cota_map = dict(zip(df_f["DT_COMPTC"], df_f["VL_QUOTA_F"]))
    pl_map   = dict(zip(df_f["DT_COMPTC"], df_f["PL_F"]))
    capt_map = dict(zip(df_f["DT_COMPTC"], df_f["CAPTC_F"]))
    resg_map = dict(zip(df_f["DT_COMPTC"], df_f["RESG_F"]))
    dt_ini   = df_f["DT_COMPTC"].iloc[0]

    if cnpj_raw in cota_base_dez25 and cota_base_dez25[cnpj_raw]["cota"] > 0:
        cota_ini = cota_base_dez25[cnpj_raw]["cota"]
        print(f"  Base: cota de dez/2025 = {cota_ini:.8f}")
    else:
        cota_ini = cota_map[dt_ini]
        print(f"  Base: primeira cota de 2026 = {cota_ini:.8f}")

    def patrim_em(dt, cota):
        """Patrimonio na escala do dashboard (R$ / ESCALA)."""
        if USAR_PL_CVM:
            pl = pl_map.get(dt, 0.0)
            if pl and pl > 0:
                return pl / ESCALA
        return cota * cotas_em(cnpj_raw, dt)

    hist = []
    # acumulados: *_tot inclui transferencias internas; *_ext so dinheiro seu
    resg_tot = capt_tot = resg_ext_ac = capt_ext_ac = 0.0

    if cnpj_raw in cota_base_dez25:
        base = cota_base_dez25[cnpj_raw]
        if USAR_PL_CVM and base.get("pl", 0) > 0:
            pat0   = round(base["pl"] / ESCALA, 2)
            qt_dez = round(pat0 / cota_ini, 3) if cota_ini else 0.0
        else:
            qt_dez = cotas_em(cnpj_raw, "2025-12-31")
            pat0   = round(cota_ini * qt_dez, 2)
        hist.append({
            "dt": "2025-12-31",
            "cota": round(cota_ini, 8),
            "cotas_qt": qt_dez,
            "patrimonio": pat0,
            "rent_acum": 0.0,
            "var_diaria": 0.0,
            "capt": 0.0, "resg": 0.0, "capt_ext": 0.0, "resg_ext": 0.0,
            "resg_acum": 0.0, "capt_acum": 0.0,
        })

    for dt in datas_todas:
        if dt not in cota_map: continue
        if cotas_em(cnpj_raw, dt) == 0.0: continue   # fundo encerrado pela regra
        c   = cota_map[dt]
        pat = round(patrim_em(dt, c), 2)
        qt  = round(pat / c, 3) if c else 0.0

        capt = round(capt_map.get(dt, 0.0) / ESCALA, 2)
        resg = round(resg_map.get(dt, 0.0) / ESCALA, 2)
        interno  = eh_fluxo_interno(cnpj_raw, dt)
        capt_ext = 0.0 if interno else capt
        resg_ext = 0.0 if interno else resg

        capt_tot    += capt;     resg_tot    += resg
        capt_ext_ac += capt_ext; resg_ext_ac += resg_ext

        ra = round((c/cota_ini-1)*100, 6) if cota_ini else 0.0
        if hist and hist[-1]["cota"] and hist[-1]["cota"] != 0:
            vd = round((c/hist[-1]["cota"]-1)*100, 6)
        else:
            vd = 0.0
        hist.append({
            "dt": dt, "cota": round(c,8), "cotas_qt": qt, "patrimonio": pat,
            "rent_acum": ra, "var_diaria": vd,
            "capt": capt, "resg": resg, "capt_ext": capt_ext, "resg_ext": resg_ext,
            "resg_acum": round(resg_ext_ac, 2), "capt_acum": round(capt_ext_ac, 2),
        })

    if not hist: continue

    dt_fim      = hist[-1]["dt"]
    dt_ini_exib = "2025-12-31" if cnpj_raw in cota_base_dez25 else dt_ini
    cota_fim    = hist[-1]["cota"]
    rent_final  = round((cota_fim/cota_ini-1)*100, 6) if cota_ini else 0.0
    patrim_ini  = hist[0]["patrimonio"]
    patrim_fim  = hist[-1]["patrimonio"]
    # Resultado do fundo: neutraliza todo capital que entrou/saiu, inclusive
    # a incorporacao (do ponto de vista do fundo, ela e capital novo).
    ganho       = round(patrim_fim + resg_tot - capt_tot - patrim_ini, 2)

    fundos.append({
        "cnpj": fmt_cnpj(cnpj_raw), "cnpj_raw": cnpj_raw,
        "nome": nome, "nome_curto": NOMES_FUNDOS.get(cnpj_raw, cnpj_raw[:6]),
        "color": CORES.get(cnpj_raw,"#aaa"),
        "cota_ini": cota_ini, "cota_fim": cota_fim,
        "rent": rent_final, "patrim_ini": patrim_ini, "patrim_fim": patrim_fim,
        "ganho": ganho, "dt_ini": dt_ini_exib, "dt_fim": dt_fim,
        "n_dias": len(hist), "historico": hist,
        "resg_total": round(resg_ext_ac, 2), "capt_total": round(capt_ext_ac, 2),
        "resg_bruto": round(resg_tot, 2),   "capt_bruto": round(capt_tot, 2),
        "incorporado": "Incorporado ao Lagunna_78 em 18/03/2026" if cnpj_raw == "07152165000128" else "",
    })

    print(f"  OK  {fmt_cnpj(cnpj_raw)}  {nome[:40]}")
    print(f"      Rent: {rent_final:+.4f}%  |  Patrim: R$ {patrim_ini:,.2f} -> R$ {patrim_fim:,.2f}  |  Resultado: R$ {ganho:+,.2f}")
    if resg_ext_ac or capt_ext_ac:
        print(f"      Resgates: R$ {resg_ext_ac:,.2f}  |  Aportes: R$ {capt_ext_ac:,.2f}")
    if USAR_PL_CVM:
        qt_regra = cotas_em(cnpj_raw, dt_fim)
        qt_real  = hist[-1]["cotas_qt"]
        if qt_regra:
            dif = (qt_real/qt_regra - 1) * 100
            flag = "OK" if abs(dif) < 0.5 else "ATENCAO"
            print(f"      [{flag}] Cotas CVM {qt_real:,.3f} vs regra fixa {qt_regra:,.3f}  ({dif:+.3f}%)")
    print()

if not fundos:
    print("ERRO: nenhum fundo processado.")
    input("\nPressione Enter para fechar..."); sys.exit(1)

# ── INCORPORACOES: detecta a data real do salto patrimonial ───────────────────
# O fundo incorporado precisa sair da consolidacao exatamente no dia em que o
# fundo destino absorve o patrimonio dele. Se sair um dia depois, o dinheiro e
# contado duas vezes e o grafico do grupo dispara. "data": None = auto-detecta.
INCORPORACOES = [
    {"origem": "07152165000128", "destino": "63662461000140", "data": None},
]

ATIVO_ATE = {}   # cnpj -> ultima data em que o fundo entra na consolidacao

def _get(cnpj_raw):
    return next((f for f in fundos if f["cnpj_raw"] == cnpj_raw), None)

for inc in INCORPORACOES:
    fo, fd = _get(inc["origem"]), _get(inc["destino"])
    if not fo or not fd:
        continue
    data = inc.get("data")
    if not data:
        for i in range(1, len(fd["historico"])):
            a, b = fd["historico"][i-1], fd["historico"][i]
            if not a["cota"] or not a["patrimonio"]:
                continue
            esperado = a["patrimonio"] * (b["cota"] / a["cota"])
            salto    = b["patrimonio"] - esperado
            ev = next((x for x in reversed(fo["historico"]) if x["dt"] <= a["dt"]), None)
            if ev and ev["patrimonio"] > 0 and salto > 0.5 * ev["patrimonio"]:
                data = b["dt"]
                print(f"  Incorporacao detectada: {NOMES_FUNDOS.get(inc['origem'],'')} -> "
                      f"{NOMES_FUNDOS.get(inc['destino'],'')} em {data}")
                print(f"    Salto em {NOMES_FUNDOS.get(inc['destino'],'')}: R$ {salto:,.2f}  |  "
                      f"Patrimonio do incorporado em {ev['dt']}: R$ {ev['patrimonio']:,.2f}")
                break
    if not data:
        print(f"  Incorporacao nao detectada para {fmt_cnpj(inc['origem'])} — usando COTAS_REGRAS.\n")
        continue

    # Origem so vale ate o dia anterior ao salto
    antes = [h for h in fo["historico"] if h["dt"] < data]
    if not antes:
        continue
    ATIVO_ATE[inc["origem"]] = antes[-1]["dt"]
    fo["historico"]  = antes
    fo["dt_fim"]     = antes[-1]["dt"]
    fo["cota_fim"]   = antes[-1]["cota"]
    fo["patrim_fim"] = antes[-1]["patrimonio"]
    fo["n_dias"]     = len(antes)
    fo["rent"]       = round((fo["cota_fim"]/fo["cota_ini"]-1)*100, 6) if fo["cota_ini"] else 0.0
    fo["resg_total"] = round(sum(h.get("resg_ext",0.0) for h in antes), 2)
    fo["capt_total"] = round(sum(h.get("capt_ext",0.0) for h in antes), 2)
    fo["resg_bruto"] = round(sum(h.get("resg",0.0) for h in antes), 2)
    fo["capt_bruto"] = round(sum(h.get("capt",0.0) for h in antes), 2)
    fo["ganho"]      = round(fo["patrim_fim"] + fo["resg_bruto"] - fo["capt_bruto"] - fo["patrim_ini"], 2)
    print(f"    {NOMES_FUNDOS.get(inc['origem'],'')} encerrado na consolidacao em {antes[-1]['dt']}\n")

def ativo_em(cnpj_raw, dt):
    """O fundo entra na consolidacao nesta data?"""
    limite = ATIVO_ATE.get(cnpj_raw)
    if limite is not None and dt > limite:
        return False
    return cotas_em(cnpj_raw, dt) != 0.0

# ── RF CDI ────────────────────────────────────────────────────────────────────
dt_base = "2025-12-31"

rf_hist  = [{"dt": "2025-12-31", "patrimonio": round(VALOR_RF_CDI, 2), "rent_acum": 0.0, "var_diaria": 0.0}]
for dt in datas_todas:
    if dt < dt_base: continue
    rf_hist.append({
        "dt": dt,
        "patrimonio": round(VALOR_RF_CDI * cdi_idx[dt], 2),
        "rent_acum":  round((cdi_idx[dt]-1)*100, 6),
        "var_diaria": round(fator_cdi[dt]*100, 6),
    })

rf_ini  = VALOR_RF_CDI
rf_fim  = rf_hist[-1]["patrimonio"] if rf_hist else rf_ini
rf_rent = rf_hist[-1]["rent_acum"]  if rf_hist else 0.0
rf_ganho= round(rf_fim-rf_ini, 2)
print(f"  RF CDI  R$ {rf_ini:,.2f} -> R$ {rf_fim:,.2f}  |  Rent: {rf_rent:+.4f}%  |  Resultado: R$ {rf_ganho:+,.2f}\n")

# ── FLUXOS EXTERNOS POR DATA (aportes/resgates seus) ──────────────────────────
fluxo_dia = {}
resgates_lista = []
for f in fundos:
    for h in f["historico"]:
        d = fluxo_dia.setdefault(h["dt"], {"capt": 0.0, "resg": 0.0})
        d["capt"] += h.get("capt_ext", 0.0)
        d["resg"] += h.get("resg_ext", 0.0)
        if h.get("resg_ext", 0.0) > 0:
            resgates_lista.append({"dt": h["dt"], "fundo": f["nome_curto"],
                                   "color": f["color"], "valor": h["resg_ext"], "tipo": "resgate"})
        if h.get("capt_ext", 0.0) > 0:
            resgates_lista.append({"dt": h["dt"], "fundo": f["nome_curto"],
                                   "color": f["color"], "valor": h["capt_ext"], "tipo": "aporte"})
        # transferencias internas (incorporacao): aparecem na lista, mas nao somam
        r_int = round(h.get("resg", 0.0) - h.get("resg_ext", 0.0), 2)
        c_int = round(h.get("capt", 0.0) - h.get("capt_ext", 0.0), 2)
        if r_int > 0:
            resgates_lista.append({"dt": h["dt"], "fundo": f["nome_curto"], "color": f["color"],
                                   "valor": r_int, "tipo": "incorporacao", "interno": True, "sinal": -1})
        if c_int > 0:
            resgates_lista.append({"dt": h["dt"], "fundo": f["nome_curto"], "color": f["color"],
                                   "valor": c_int, "tipo": "incorporacao", "interno": True, "sinal": 1})
resgates_lista.sort(key=lambda x: (x["dt"], x["fundo"]))

resg_geral = round(sum(f["resg_total"] for f in fundos), 2)
capt_geral = round(sum(f["capt_total"] for f in fundos), 2)
if resgates_lista:
    print(f"  MOVIMENTACOES: {len(resgates_lista)} evento(s)  |  Resgates R$ {resg_geral:,.2f}  |  Aportes R$ {capt_geral:,.2f}")
    for m in resgates_lista:
        print(f"    {m['dt']}  {m['tipo']:8s} {m['fundo']:20s} R$ {m['valor']:>12,.2f}")
    print()
else:
    print("  MOVIMENTACOES: nenhum aporte ou resgate externo no periodo.\n")

# ── TOTAIS ────────────────────────────────────────────────────────────────────
tot_ini   = sum(f["patrim_ini"] for f in fundos) + rf_ini
tot_fim   = sum(f["patrim_fim"] for f in fundos) + rf_fim
tot_ganho = round(tot_fim-tot_ini, 2)
tot_rent  = round((tot_fim/tot_ini-1)*100, 6) if tot_ini else 0
ultima_dt = min(f["dt_fim"] for f in fundos if f["cnpj_raw"] != "07152165000128")

print(f"  TOTAL  R$ {tot_ini:,.2f} -> R$ {tot_fim:,.2f}  |  {tot_rent:+.4f}%  |  R$ {tot_ganho:+,.2f}\n")

# ── VERIFICAÇÃO DA INCORPORAÇÃO EVEREST → LAGUNNA ────────────────────────────
cnpj_lagunna  = "63662461000140"
cnpj_everest  = "07152165000128"
f_lagunna = next((f for f in fundos if f["cnpj_raw"] == cnpj_lagunna), None)
f_everest = next((f for f in fundos if f["cnpj_raw"] == cnpj_everest), None)

if f_lagunna and f_everest:
    print("  === Verificação Incorporação EVEREST → Lagunna_78 ===")
    dt_corte = ATIVO_ATE.get(cnpj_everest, "2026-03-17")
    h_ev_17 = next((h for h in reversed(f_everest["historico"]) if h["dt"] <= dt_corte), None)
    h_la_17 = next((h for h in reversed(f_lagunna["historico"]) if h["dt"] <= dt_corte), None)
    h_la_18 = next((h for h in f_lagunna["historico"] if h["dt"] > dt_corte), None)

    if h_ev_17 and h_la_17 and h_la_18:
        tot_antes = h_la_17["patrimonio"] + h_ev_17["patrimonio"]
        tot_depois = h_la_18["patrimonio"]
        diff = tot_depois - tot_antes
        print(f"  Lagunna em {h_la_17['dt']}:  R$ {h_la_17['patrimonio']:,.2f}")
        print(f"  EVEREST em {h_ev_17['dt']}:   R$ {h_ev_17['patrimonio']:,.2f}")
        print(f"  SOMA antes:                  R$ {tot_antes:,.2f}")
        print(f"  Lagunna em {h_la_18['dt']}:  R$ {h_la_18['patrimonio']:,.2f}")
        print(f"  Diferença:                   R$ {diff:+,.2f}")
        if abs(diff) < tot_antes * 0.01:
            print("  [OK] Incorporação consistente (diferença < 1%)")
        else:
            print("  [ATENCAO] Diferença relevante — verifique as cotas")
    print()

# ── CARTEIRA CONSOLIDADA ──────────────────────────────────────────────────────
cart_hist = []
pat_ini_cart = sum(f["patrim_ini"] for f in fundos) + VALOR_RF_CDI
cart_hist.append({"dt": "2025-12-31", "patrimonio": round(pat_ini_cart, 2),
                  "rent_acum": 0.0, "var_diaria": 0.0,
                  "capt": 0.0, "resg": 0.0, "resg_acum": 0.0, "capt_acum": 0.0})

idx_cart = 1.0
resg_ac_cart = capt_ac_cart = 0.0

for i, dt in enumerate(datas_todas):
    if dt < dt_base: continue
    pat_fundos = 0.0
    for f in fundos:
        if not ativo_em(f["cnpj_raw"], dt):
            continue
        h = next((x for x in f["historico"] if x["dt"] == dt), None)
        if h:
            pat_fundos += h["patrimonio"]
        else:
            # Forward-fill: usa ultimo patrimonio conhecido se a CVM ainda nao publicou
            anteriores = [x for x in f["historico"] if x["dt"] <= dt]
            if anteriores:
                pat_fundos += anteriores[-1]["patrimonio"]
    pat_rf  = round(VALOR_RF_CDI * cdi_idx[dt], 2)
    pat_tot = round(pat_fundos + pat_rf, 2)

    fx        = fluxo_dia.get(dt, {"capt": 0.0, "resg": 0.0})
    capt_d    = round(fx["capt"], 2)
    resg_d    = round(fx["resg"], 2)
    fluxo_liq = capt_d - resg_d            # + entrou dinheiro, - saiu dinheiro
    resg_ac_cart += resg_d
    capt_ac_cart += capt_d

    # Retorno do dia neutralizando o fluxo: um resgate reduz o patrimonio
    # sem ser prejuizo, entao ele sai da base de comparacao.
    pat_ant  = cart_hist[-1]["patrimonio"]
    base_dia = pat_ant + fluxo_liq
    r        = (pat_tot / base_dia - 1) if base_dia else 0.0
    idx_cart *= (1 + r)

    cart_hist.append({
        "dt": dt, "patrimonio": pat_tot,
        "rent_acum": round((idx_cart - 1) * 100, 6),
        "var_diaria": round(r * 100, 6),
        "capt": capt_d, "resg": resg_d,
        "resg_acum": round(resg_ac_cart, 2), "capt_acum": round(capt_ac_cart, 2),
    })

cart_rent = cart_hist[-1]["rent_acum"] if cart_hist else 0.0

cart_na_ultima = next((h for h in reversed(cart_hist) if h["dt"] <= ultima_dt), cart_hist[-1] if cart_hist else None)
tot_fim_exib   = cart_na_ultima["patrimonio"] if cart_na_ultima else tot_fim
resg_exib      = cart_na_ultima["resg_acum"] if cart_na_ultima else 0.0
capt_exib      = cart_na_ultima["capt_acum"] if cart_na_ultima else 0.0
# Resultado em R$: o que voce resgatou ja e ganho realizado, e o que voce
# aportou nao e lucro. Ambos entram na conta.
tot_ganho_exib = round(tot_fim_exib + resg_exib - capt_exib - tot_ini, 2)
tot_rent_exib  = cart_na_ultima["rent_acum"] if cart_na_ultima else 0.0
cart_rent_exib = tot_rent_exib
print(f"  CARTEIRA  R$ {tot_ini:,.2f} -> R$ {tot_fim_exib:,.2f}  |  Rent: {cart_rent_exib:+.4f}%")
print(f"            Resgates R$ {resg_exib:,.2f}  |  Aportes R$ {capt_exib:,.2f}  |  Resultado R$ {tot_ganho_exib:+,.2f}\n")

# ── GRUPOS VIRTUAIS ────────────────────────────────────────────────────────────
def get_fundo(cnpj_raw):
    return next((f for f in fundos if f["cnpj_raw"] == cnpj_raw), None)

def consolidar_grupo(nome, cor, cnpjs):
    dts = sorted(set(h["dt"] for c in cnpjs for f in [get_fundo(c)] if f for h in f["historico"]))
    pat_ini_grupo = sum(
        get_fundo(c)["patrim_ini"] for c in cnpjs if get_fundo(c)
    )
    hist_grupo = []
    idx_g = 1.0
    resg_ac_g = capt_ac_g = 0.0
    primeiro = True
    for dt in dts:
        if dt > ultima_dt: continue
        pat = 0.0
        capt_d = resg_d = 0.0
        for c in cnpjs:
            f = get_fundo(c)
            if not f: continue
            if not ativo_em(c, dt): continue
            h = next((x for x in f["historico"] if x["dt"] == dt), None)
            if h:
                pat    += h["patrimonio"]
                capt_d += h.get("capt_ext", 0.0)
                resg_d += h.get("resg_ext", 0.0)
            else:
                # Forward-fill: usa último patrimônio conhecido se a CVM ainda não publicou
                anteriores = [x for x in f["historico"] if x["dt"] <= dt]
                if anteriores:
                    pat += anteriores[-1]["patrimonio"]
        capt_d = round(capt_d, 2); resg_d = round(resg_d, 2)
        resg_ac_g += resg_d; capt_ac_g += capt_d

        if primeiro:
            primeiro = False
        else:
            base_dia = hist_grupo[-1]["patrimonio"] + capt_d - resg_d
            r = (pat / base_dia - 1) if base_dia else 0.0
            idx_g *= (1 + r)
        vd = round(((pat / (hist_grupo[-1]["patrimonio"] + capt_d - resg_d)) - 1) * 100, 6) \
             if hist_grupo and (hist_grupo[-1]["patrimonio"] + capt_d - resg_d) else 0.0
        hist_grupo.append({
            "dt": dt, "patrimonio": round(pat, 2),
            "rent_acum": round((idx_g - 1) * 100, 6), "var_diaria": vd,
            "capt": capt_d, "resg": resg_d,
            "resg_acum": round(resg_ac_g, 2), "capt_acum": round(capt_ac_g, 2),
        })

    if not hist_grupo: return None
    pat_fim_grupo = hist_grupo[-1]["patrimonio"]
    rent_grupo    = hist_grupo[-1]["rent_acum"]
    resg_grupo    = hist_grupo[-1]["resg_acum"]
    capt_grupo    = hist_grupo[-1]["capt_acum"]
    return {
        "nome": nome, "nome_curto": nome, "cnpj": "Grupo virtual", "cnpj_raw": "",
        "color": cor, "incorporado": "",
        "cota_ini": 0, "cota_fim": 0,
        "rent": rent_grupo, "patrim_ini": pat_ini_grupo, "patrim_fim": pat_fim_grupo,
        "ganho": round(pat_fim_grupo + resg_grupo - capt_grupo - pat_ini_grupo, 2),
        "resg_total": resg_grupo, "capt_total": capt_grupo,
        "dt_ini": hist_grupo[0]["dt"], "dt_fim": hist_grupo[-1]["dt"],
        "n_dias": len(hist_grupo), "historico": hist_grupo,
        "virtual": True,
    }

grupo_l = consolidar_grupo("Lagunna + EVEREST", "#00E5B0", ["63662461000140","07152165000128"])
grupo_n = consolidar_grupo("Neblina + Neblina Equity", "#FFD700", ["63110432000175","63105699000174"])
grupos  = [g for g in [grupo_l, grupo_n] if g]
print(f"  Grupo Lagunna+EVEREST:   R$ {grupo_l['patrim_ini']:,.2f} -> R$ {grupo_l['patrim_fim']:,.2f}  |  {grupo_l['rent']:+.4f}%" if grupo_l else "  Grupo L: sem dados")
print(f"  Grupo Neblina+NebEq:     R$ {grupo_n['patrim_ini']:,.2f} -> R$ {grupo_n['patrim_fim']:,.2f}  |  {grupo_n['rent']:+.4f}%\n" if grupo_n else "  Grupo N: sem dados\n")

# ──────────────────────────────────────────────────────────────────────────────
# GERA HTML
# ──────────────────────────────────────────────────────────────────────────────

dados_json  = json.dumps(fundos,     ensure_ascii=False)
grupos_json = json.dumps(grupos,     ensure_ascii=False)
rf_json     = json.dumps(rf_hist,    ensure_ascii=False)
cart_json   = json.dumps(cart_hist,  ensure_ascii=False)
movs_json   = json.dumps([m for m in resgates_lista if m["dt"] <= ultima_dt], ensure_ascii=False)
totais_json = json.dumps({
    "ini": tot_ini, "fim": tot_fim_exib, "ganho": tot_ganho_exib, "rent": tot_rent_exib,
    "resg": resg_exib, "capt": capt_exib,
    "invest": round(tot_ini + capt_exib, 2),
    "dt_ini": fundos[0]["dt_ini"], "dt_fim": ultima_dt,
    "rf_ini": rf_ini, "rf_fim": rf_fim, "rf_rent": rf_rent, "rf_ganho": rf_ganho,
    "cart_rent": cart_rent_exib,
    "cdi_color": CORES["cdi"],
    "cart_color": "#C084FC",
}, ensure_ascii=False)

# ── TIMESTAMP EM HORÁRIO DE BRASÍLIA (BRT = UTC-3) ────────────────────────────
BRT = timezone(timedelta(hours=-3))
gerado_em = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")

HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard CVM 2026</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans',sans-serif;background:#090d18;color:#dde2f0;min-height:100vh;font-size:14px}
a{color:inherit}
header{background:#0c1020;border-bottom:1px solid #1a2035;padding:16px 28px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.logo{font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:700;letter-spacing:.1em;color:#1D9E75;text-transform:uppercase}
.sub{font-size:10px;color:#8892a8;margin-top:3px;font-family:'IBM Plex Mono',monospace}
.gerado{font-size:10px;color:#8892a8;font-family:'IBM Plex Mono',monospace}
main{padding:22px 28px;max-width:1300px;margin:0 auto}
.slbl{font-family:'IBM Plex Mono',monospace;font-size:10px;font-weight:700;color:#8892a8;text-transform:uppercase;letter-spacing:.12em;margin-bottom:12px;padding-bottom:7px;border-bottom:1px solid #1a2035;margin-top:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:8px}
.card{background:#0f1525;border:1px solid #1a2035;border-radius:8px;padding:16px 18px}
.card .lbl{font-size:10px;color:#8892a8;text-transform:uppercase;letter-spacing:.08em;font-family:'IBM Plex Mono',monospace;margin-bottom:6px}
.card .val{font-size:18px;font-weight:600;font-family:'IBM Plex Mono',monospace}
.card .sub{font-size:10px;color:#8892a8;margin-top:4px;font-family:'IBM Plex Mono',monospace}
.pos{color:#1D9E75} .neg{color:#D85A30}
.tab-row{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.tab{font-size:11px;padding:6px 14px;border-radius:6px;border:1px solid #1a2035;background:transparent;color:#8892a8;cursor:pointer;font-family:'IBM Plex Mono',monospace;transition:all .15s}
.tab.active{background:#1a2840;color:#378ADD;border-color:#378ADD}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:12px}
.legend-item{display:flex;align-items:center;gap:6px;font-size:11px;color:#888;font-family:'IBM Plex Mono',monospace}
.legend-sq{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.cbox{background:#0f1525;border:1px solid #1a2035;border-radius:8px;padding:18px 20px;margin-bottom:8px}
.fgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-bottom:8px}
.fc{background:#0f1525;border:1px solid #1a2035;border-radius:8px;padding:16px;cursor:pointer;transition:border-color .15s}
.fc:hover,.fc.active{border-color:#378ADD;background:#0d1828}
.fc-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.fc-nome{font-size:11px;font-weight:600;max-width:175px;line-height:1.5}
.fc-cnpj{font-size:9px;color:#8892a8;margin-top:2px;font-family:'IBM Plex Mono',monospace}
.badge{border-radius:4px;padding:4px 10px;font-size:12px;font-weight:700;font-family:'IBM Plex Mono',monospace;white-space:nowrap}
.fc-row{display:flex;justify-content:space-between;margin-top:5px;font-size:10px}
.fc-lbl{color:#8892a8} .fc-val{font-family:'IBM Plex Mono',monospace}
.dbox{background:#0f1525;border:1px solid #378ADD;border-radius:8px;padding:20px 24px;margin-bottom:8px;display:none}
.dbox.show{display:block}
.dh{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:16px;align-items:flex-start}
.dt{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:700;color:#1D9E75;text-transform:uppercase;letter-spacing:.1em}
.ds{font-size:10px;color:#8892a8;margin-top:3px;font-family:'IBM Plex Mono',monospace}
.mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:16px}
.mbox{background:#090d18;border-radius:6px;padding:10px 12px}
.mlbl{font-size:9px;color:#8892a8;text-transform:uppercase;letter-spacing:.08em;font-family:'IBM Plex Mono',monospace}
.mval{font-size:11px;margin-top:4px;font-family:'IBM Plex Mono',monospace}
.pie-wrap{display:grid;grid-template-columns:220px 1fr;gap:20px;align-items:center}
.pie-info{display:flex;flex-direction:column;gap:10px}
.pie-row{display:flex;align-items:center;gap:10px;font-size:12px}
@media(max-width:600px){main{padding:14px}header{padding:12px 14px}.pie-wrap{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">&#128202; Dashboard CVM &middot; Rentabilidade 2026</div>
    <div class="sub" id="headerSub"></div>
  </div>
  <div class="gerado">Gerado em """ + gerado_em + """ &nbsp;·&nbsp; Última publicação CVM: """ + ultima_dt + """</div>
</header>
<main>
  <div class="slbl">Resumo da carteira</div>
  <div class="cards" id="summaryCards"></div>

  <div class="slbl">Evolucao 2026</div>
  <div class="cbox">
    <div class="tab-row">
      <button class="tab active" onclick="setTab('acum')">Rent. acumulada %</button>
      <button class="tab"        onclick="setTab('patrim')">Patrimonio R$</button>
      <button class="tab"        onclick="setTab('diario')">Variacao diaria %</button>
    </div>
    <div class="legend" id="legend"></div>
    <div style="position:relative;width:100%;height:300px">
      <canvas id="mainChart" role="img" aria-label="Grafico de evolucao dos fundos em 2026"></canvas>
    </div>
  </div>

  <div class="slbl">Fundos individuais &mdash; clique para detalhar</div>
  <div class="fgrid" id="fundosGrid"></div>

  <div class="dbox" id="detailBox">
    <div class="dh">
      <div><div class="dt" id="detTitle"></div><div class="ds" id="detSub"></div></div>
      <div class="tab-row" style="margin-bottom:0">
        <button class="tab active" onclick="setDTab('cota')">Cota</button>
        <button class="tab"        onclick="setDTab('rent')">Rent. acum %</button>
        <button class="tab"        onclick="setDTab('patrim')">Patrimonio R$</button>
        <button class="tab"        onclick="setDTab('diario')">Var. diaria %</button>
      </div>
    </div>
    <div style="position:relative;width:100%;height:240px">
      <canvas id="detChart" role="img" aria-label="Grafico detalhado do fundo selecionado"></canvas>
    </div>
    <div class="mgrid" id="detMeta"></div>
  </div>

  <div id="movsSection" style="display:none">
    <div class="slbl">Resgates e aportes &mdash; <span id="lblMovsTot" style="color:#dde2f0;font-weight:400"></span></div>
    <div class="cbox"><div id="movsBox"></div></div>
  </div>

  <div class="slbl">Composicao da carteira &mdash; <span id="lblDataComp" style="color:#dde2f0;font-weight:400"></span></div>
  <div class="cbox">
    <div class="pie-wrap">
      <div style="position:relative;height:220px">
        <canvas id="pieChart" role="img" aria-label="Composicao da carteira por patrimonio atual"></canvas>
      </div>
      <div class="pie-info" id="pieInfo"></div>
    </div>
  </div>
</main>

<script>
const DADOS  = """ + dados_json  + """;
const GRUPOS = """ + grupos_json + """;
const RF     = """ + rf_json     + """;
const CART   = """ + cart_json   + """;
const MOVS   = """ + movs_json   + """;
const TOTAIS = """ + totais_json + """;

const fmtBRL  = v => 'R$\u00a0' + Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtPct  = v => (v>=0?'+':'')+Number(v).toFixed(4)+'%';
const fmtCota = v => Number(v).toFixed(8);
const fmtQtd  = v => Number(v).toLocaleString('pt-BR',{minimumFractionDigits:3,maximumFractionDigits:3});

document.getElementById('headerSub').textContent =
  'Informe Diario \u00b7 ' + TOTAIS.dt_ini + ' \u2192 ' + TOTAIS.dt_fim + ' \u00b7 4 fundos + Renda Fixa CDI';

// ── CARDS RESUMO ─────────────────────────────────────────────────────────────
(function(){
  const T = TOTAIS;
  const cards = [
    {lbl:'Patrimonio inicial', val:fmtBRL(T.ini),   sub:'em '+T.dt_ini, cls:''},
    {lbl:'Patrimonio atual',   val:fmtBRL(T.fim),   sub:'em '+T.dt_fim, cls:''},
  ];
  cards.push({lbl:'Resgates', val:(T.resg>0?'\u2212':'')+fmtBRL(T.resg),
              sub:MOVS.filter(m=>m.tipo==='resgate'&&!m.interno).length+' resgate(s) no periodo',
              cls:T.resg>0?'neg':''});
  if(T.capt>0) cards.push({lbl:'Aportes', val:'+'+fmtBRL(T.capt), sub:'capital adicionado', cls:'pos'});
  cards.push(
    {lbl:'Resultado R$', val:(T.ganho>=0?'+':'')+fmtBRL(T.ganho), sub:T.resg>0?'ja considera os resgates':'no periodo', cls:T.ganho>=0?'pos':'neg'},
    {lbl:'Rent. carteira', val:fmtPct(T.cart_rent), sub:T.resg>0?'ajustada por fluxo de caixa':'consolidado no periodo', cls:T.cart_rent>=0?'pos':'neg'},
    {lbl:'CDI acumulado', val:fmtPct(T.rf_rent), sub:T.dt_fim, cls:'pos'},
  );
  cards.forEach(c=>{
    document.getElementById('summaryCards').innerHTML +=
      `<div class="card"><div class="lbl">${c.lbl}</div><div class="val ${c.cls}">${c.val}</div><div class="sub">${c.sub}</div></div>`;
  });
})();

// ── LEGENDA ───────────────────────────────────────────────────────────────────
[{nome_curto:'RF CDI',color:TOTAIS.cdi_color},{nome_curto:'Carteira Total',color:TOTAIS.cart_color},...GRUPOS].forEach(f=>{
  document.getElementById('legend').innerHTML +=
    `<span class="legend-item"><span class="legend-sq" style="background:${f.color}${f.virtual?';opacity:0.7':''}"></span>${f.nome_curto}${f.virtual?' <span style="font-size:9px;color:#8892a8">(grupo)</span>':''}</span>`;
});

// ── GRAFICO PRINCIPAL ─────────────────────────────────────────────────────────
let mainChart, curTab='acum';

const ULTIMA_DT = TOTAIS.dt_fim;

const CARTV = CART.filter(h=>h.dt<=ULTIMA_DT);
// Marcadores nos dias em que houve resgate (laranja) ou aporte (verde)
const MK_R = CARTV.map(h=>(h.resg>0||h.capt>0)?4.5:0);
const MK_C = CARTV.map(h=>h.resg>0?'#D85A30':(h.capt>0?'#1D9E75':'rgba(0,0,0,0)'));

function getDS(tab){
  const key = tab==='acum'?'rent_acum':tab==='patrim'?'patrimonio':'var_diaria';
  const marca = {pointRadius:MK_R,pointHoverRadius:MK_R.map(r=>r?7:0),pointBackgroundColor:MK_C,pointBorderColor:MK_C};
  if(tab==='patrim'){
    return [
      Object.assign({label:'Carteira Total',data:CARTV.map(h=>h[key]),borderColor:TOTAIS.cart_color,backgroundColor:TOTAIS.cart_color+'18',fill:true,borderWidth:3,tension:0.1},marca),
    ];
  }
  return [
    {label:'RF CDI',data:RF.filter(h=>h.dt<=ULTIMA_DT).map(h=>h[key]),borderColor:TOTAIS.cdi_color,backgroundColor:'transparent',borderWidth:2,pointRadius:0,borderDash:[6,3],tension:0.1},
    Object.assign({label:'Carteira Total',data:CARTV.map(h=>h[key]),borderColor:TOTAIS.cart_color,backgroundColor:'transparent',borderWidth:3,tension:0.1},marca),
    ...GRUPOS.map(g=>({label:g.nome_curto,data:g.historico.filter(h=>h.dt<=ULTIMA_DT).map(h=>h[key]),borderColor:g.color,backgroundColor:'transparent',borderWidth:2,pointRadius:0,borderDash:[3,3],tension:0.1})),
  ];
}

function fmtY(tab,v){
  if(tab==='patrim') return 'R$'+Number(v/1000).toFixed(0)+'k';
  return Number(v).toFixed(tab==='diario'?4:2)+'%';
}

function renderMain(tab){
  const labels = CART.filter(h=>h.dt<=ULTIMA_DT).map(h=>h.dt.slice(5));
  if(mainChart) mainChart.destroy();
  mainChart = new Chart(document.getElementById('mainChart'),{
    type:'line', data:{labels,datasets:getDS(tab)},
    options:{responsive:true,maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{callbacks:{
        label:ctx=>`  ${ctx.dataset.label}: ${fmtY(tab,ctx.parsed.y)}`,
        afterBody:items=>{
          const h = CARTV[items[0].dataIndex]; if(!h) return '';
          const l = [];
          if(h.resg>0) l.push('\u25cf Resgate: \u2212'+fmtBRL(h.resg));
          if(h.capt>0) l.push('\u25cf Aporte: +'+fmtBRL(h.capt));
          return l;
        }
      }}},
      scales:{
        x:{ticks:{autoSkip:true,maxTicksLimit:10,color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},
        y:{ticks:{color:'#8892a8',font:{size:10},callback:v=>fmtY(tab,v)},grid:{color:'rgba(255,255,255,0.04)'}},
      },
    },
  });
}

function setTab(tab){
  curTab=tab;
  document.querySelectorAll('.cbox .tab-row .tab').forEach((b,i)=>{
    b.classList.toggle('active',['acum','patrim','diario'][i]===tab);
  });
  renderMain(tab);
}
renderMain('acum');

// ── CARDS FUNDOS ──────────────────────────────────────────────────────────────
let activeIdx=null, detChart=null, dTab='cota';

DADOS.forEach((f,i)=>{
  const pc=f.rent>=0?'pos':'neg';
  const qt=f.historico[f.historico.length-1].cotas_qt;
  const card=document.createElement('div');
  card.className='fc';
  card.innerHTML=`
    <div class="fc-top">
      <div><div class="fc-nome">${f.nome}${f.incorporado ? ` <span style="font-size:9px;background:#D85A3022;color:#D85A30;border-radius:3px;padding:2px 6px">ENCERRADO</span>` : ''}</div><div class="fc-cnpj">${f.cnpj}${f.incorporado ? `<br><span style="color:#D85A30">${f.incorporado}</span>` : ''}</div></div>
      <div class="badge ${pc}" style="background:${f.color}22;color:${f.color}">${fmtPct(f.rent)}</div>
    </div>
    <div class="fc-row"><span class="fc-lbl">Cotas atuais</span><span class="fc-val">${fmtQtd(qt)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Cota inicial</span><span class="fc-val">${fmtCota(f.cota_ini)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Cota atual</span><span class="fc-val">${fmtCota(f.cota_fim)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio inicial</span><span class="fc-val">${fmtBRL(f.patrim_ini)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio atual</span><span class="fc-val" style="color:${f.color}">${fmtBRL(f.patrim_fim)}</span></div>
    ${f.resg_total>0?`<div class="fc-row"><span class="fc-lbl">Resgates</span><span class="fc-val neg">\u2212${fmtBRL(f.resg_total)}</span></div>`:''}
    ${f.capt_total>0?`<div class="fc-row"><span class="fc-lbl">Aportes</span><span class="fc-val pos">+${fmtBRL(f.capt_total)}</span></div>`:''}
    <div class="fc-row"><span class="fc-lbl">Resultado</span><span class="fc-val ${pc}">${f.ganho>=0?'+':''}${fmtBRL(f.ganho)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Periodo</span><span class="fc-val">${f.dt_ini} \u2192 ${f.dt_fim}</span></div>`;
  card.onclick=()=>toggleDet(i,card);
  document.getElementById('fundosGrid').appendChild(card);
});

// Cards dos grupos virtuais
GRUPOS.forEach((g,gi) => {
  const pc = g.rent>=0?'pos':'neg';
  const card = document.createElement('div');
  card.className = 'fc';
  card.style.borderColor = g.color+'88';
  card.style.borderStyle = 'dashed';
  card.innerHTML = `
    <div class="fc-top">
      <div>
        <div class="fc-nome">${g.nome} <span style="font-size:9px;background:${g.color}22;color:${g.color};border-radius:3px;padding:2px 6px">GRUPO</span></div>
        <div class="fc-cnpj">Consolidado · apenas visualização</div>
      </div>
      <div class="badge ${pc}" style="background:${g.color}22;color:${g.color}">${fmtPct(g.rent)}</div>
    </div>
    <div class="fc-row"><span class="fc-lbl">Patrimônio inicial</span><span class="fc-val">${fmtBRL(g.patrim_ini)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Patrimônio atual</span><span class="fc-val" style="color:${g.color}">${fmtBRL(g.patrim_fim)}</span></div>
    ${g.resg_total>0?`<div class="fc-row"><span class="fc-lbl">Resgates</span><span class="fc-val neg">\u2212${fmtBRL(g.resg_total)}</span></div>`:''}
    ${g.capt_total>0?`<div class="fc-row"><span class="fc-lbl">Aportes</span><span class="fc-val pos">+${fmtBRL(g.capt_total)}</span></div>`:''}
    <div class="fc-row"><span class="fc-lbl">Resultado</span><span class="fc-val ${pc}">${g.ganho>=0?'+':''}${fmtBRL(g.ganho)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Rentabilidade</span><span class="fc-val ${pc}">${fmtPct(g.rent)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Período</span><span class="fc-val">${g.dt_ini} \u2192 ${g.dt_fim}</span></div>`;
  card.onclick = () => {
    document.querySelectorAll('.fc').forEach(c=>c.classList.remove('active'));
    const box = document.getElementById('detailBox');
    if(activeIdx==='g'+gi){activeIdx=null;box.classList.remove('show');return;}
    activeIdx='g'+gi; card.classList.add('active');
    renderGrupoDet(g); box.classList.add('show');
    box.scrollIntoView({behavior:'smooth',block:'nearest'});
  };
  document.getElementById('fundosGrid').appendChild(card);
});

function renderGrupoDet(g) {
  document.getElementById('detTitle').innerHTML = g.nome + ' <span style="font-size:9px;background:'+g.color+'22;color:'+g.color+';border-radius:3px;padding:2px 6px">GRUPO</span>';
  document.getElementById('detSub').textContent = 'Consolidado · apenas visualização · ' + g.dt_ini + ' \u2192 ' + g.dt_fim;
  const labels = g.historico.map(h=>h.dt.slice(5));
  const data   = g.historico.map(h=>h.rent_acum);
  if(detChart) detChart.destroy();
  detChart = new Chart(document.getElementById('detChart'),{
    type:'line',
    data:{labels,datasets:[{label:g.nome,data,borderColor:g.color,backgroundColor:g.color+'18',fill:true,borderWidth:2,pointRadius:0,tension:0.1}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        x:{ticks:{autoSkip:true,maxTicksLimit:10,color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},
        y:{ticks:{color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},
      },
    },
  });
  const pc=g.rent>=0?'pos':'neg';
  const metaG = [
    {lbl:'Composição',         val: g.nome_curto==='Lagunna + EVEREST'?'Lagunna_78 + EVEREST':'Neblina_78 + Neblina_Equity_78'},
    {lbl:'Apenas visualização',val:'Não entra no total da carteira'},
    {lbl:'Patrimônio inicial', val:fmtBRL(g.patrim_ini)},
    {lbl:'Patrimônio atual',   val:fmtBRL(g.patrim_fim)},
  ];
  if(g.resg_total>0) metaG.push({lbl:'Resgates', val:'\u2212'+fmtBRL(g.resg_total), cls:'neg'});
  if(g.capt_total>0) metaG.push({lbl:'Aportes',  val:'+'+fmtBRL(g.capt_total), cls:'pos'});
  metaG.push(
    {lbl:'Resultado R$',       val:(g.ganho>=0?'+':'')+fmtBRL(g.ganho), cls:pc},
    {lbl:'Rentabilidade',      val:fmtPct(g.rent), cls:pc},
    {lbl:'Período',            val:g.dt_ini+' \u2192 '+g.dt_fim},
  );
  document.getElementById('detMeta').innerHTML=metaG.map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
}

// Card Carteira Total
(function(){
  const T    = TOTAIS;
  const pc   = T.cart_rent>=0?'pos':'neg';
  const card = document.createElement('div');
  card.className = 'fc';
  card.style.borderColor = T.cart_color;
  card.innerHTML = `
    <div class="fc-top">
      <div><div class="fc-nome">Carteira Total</div><div class="fc-cnpj">Consolidado · todos os fundos + RF CDI</div></div>
      <div class="badge ${pc}" style="background:${T.cart_color}22;color:${T.cart_color}">${fmtPct(T.cart_rent)}</div>
    </div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio inicial</span><span class="fc-val">${fmtBRL(T.ini)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio atual</span><span class="fc-val" style="color:${T.cart_color}">${fmtBRL(T.fim)}</span></div>
    ${T.resg>0?`<div class="fc-row"><span class="fc-lbl">Resgates</span><span class="fc-val neg">\u2212${fmtBRL(T.resg)}</span></div>`:''}
    ${T.capt>0?`<div class="fc-row"><span class="fc-lbl">Aportes</span><span class="fc-val pos">+${fmtBRL(T.capt)}</span></div>`:''}
    <div class="fc-row"><span class="fc-lbl">Resultado</span><span class="fc-val ${pc}">${T.ganho>=0?'+':''}${fmtBRL(T.ganho)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Rentabilidade</span><span class="fc-val ${pc}">${fmtPct(T.cart_rent)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Periodo</span><span class="fc-val">${T.dt_ini} \u2192 ${T.dt_fim}</span></div>`;
  card.onclick = () => {
    document.querySelectorAll('.fc').forEach(c=>c.classList.remove('active'));
    const box = document.getElementById('detailBox');
    if(activeIdx==='cart'){activeIdx=null;box.classList.remove('show');return;}
    activeIdx='cart'; card.classList.add('active');
    renderCartDet('rent');
    box.classList.add('show');
    box.scrollIntoView({behavior:'smooth',block:'nearest'});
  };
  document.getElementById('fundosGrid').appendChild(card);
})();

function renderCartDet(tab){
  document.getElementById('detTitle').textContent = 'Carteira Total \u2014 Consolidado';
  document.getElementById('detSub').textContent   = 'Todos os fundos + RF CDI \u00b7 ' + TOTAIS.dt_ini + ' \u2192 ' + TOTAIS.dt_fim;
  const key = tab==='rent'?'rent_acum': tab==='patrim'?'patrimonio':'var_diaria';
  const labels = CART.map(h=>h.dt.slice(5));
  const data   = CART.map(h=>h[key]);
  if(detChart) detChart.destroy();
  detChart = new Chart(document.getElementById('detChart'),{
    type:'line',
    data:{labels,datasets:[{label:'Carteira',data,borderColor:TOTAIS.cart_color,backgroundColor:TOTAIS.cart_color+'18',fill:true,borderWidth:2.5,pointRadius:0,tension:0.1}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        x:{ticks:{autoSkip:true,maxTicksLimit:10,color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},
        y:{ticks:{color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},
      },
    },
  });
  const T=TOTAIS, pc=T.cart_rent>=0?'pos':'neg';
  const metaCart = [
    {lbl:'Composicao',        val:'4 fundos + RF CDI'},
    {lbl:'Patrimonio inicial',val:fmtBRL(T.ini)},
    {lbl:'Patrimonio atual',  val:fmtBRL(T.fim)},
  ];
  if(T.resg>0) metaCart.push({lbl:'Resgates no periodo', val:'\u2212'+fmtBRL(T.resg), cls:'neg'});
  if(T.capt>0) metaCart.push({lbl:'Aportes no periodo',  val:'+'+fmtBRL(T.capt), cls:'pos'});
  if(T.capt>0) metaCart.push({lbl:'Capital investido',   val:fmtBRL(T.invest)});
  metaCart.push(
    {lbl:'Resultado R$',      val:(T.ganho>=0?'+':'')+fmtBRL(T.ganho), cls:pc},
    {lbl:'Rentabilidade',     val:fmtPct(T.cart_rent), cls:pc},
    {lbl:'CDI no periodo',    val:fmtPct(T.rf_rent), cls:'pos'},
    {lbl:'Periodo',           val:T.dt_ini+' \u2192 '+T.dt_fim},
  );
  document.getElementById('detMeta').innerHTML=metaCart.map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
}

function toggleDet(i,card){
  document.querySelectorAll('.fc').forEach(c=>c.classList.remove('active'));
  const box=document.getElementById('detailBox');
  if(activeIdx===i){activeIdx=null;box.classList.remove('show');return;}
  activeIdx=i; card.classList.add('active');
  renderDet(DADOS[i],'cota');
  box.classList.add('show');
  box.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function renderDet(f,tab){
  dTab=tab;
  document.getElementById('detTitle').innerHTML = f.nome + (f.incorporado ? ` <span style="font-size:9px;background:#D85A3022;color:#D85A30;border-radius:3px;padding:2px 6px">ENCERRADO</span>` : '');
  document.getElementById('detSub').innerHTML = f.cnpj + ' \u00b7 ' + f.n_dias + ' dias uteis \u00b7 ' + f.dt_ini + ' \u2192 ' + f.dt_fim + (f.incorporado ? `<br><span style="color:#D85A30;font-size:10px">${f.incorporado}</span>` : '');
  const km={cota:'cota',rent:'rent_acum',patrim:'patrimonio',diario:'var_diaria'};
  const key=km[tab];
  const labels=f.historico.map(h=>h.dt.slice(5));
  const data=f.historico.map(h=>h[key]);
  if(detChart) detChart.destroy();
  detChart=new Chart(document.getElementById('detChart'),{
    type:'line',
    data:{labels,datasets:[{label:tab,data,borderColor:f.color,backgroundColor:f.color+'18',fill:true,borderWidth:2,pointRadius:0,tension:0.1}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        x:{ticks:{autoSkip:true,maxTicksLimit:10,color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},
        y:{ticks:{color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},
      },
    },
  });
  const qt=f.historico[f.historico.length-1].cotas_qt;
  const pc=f.rent>=0?'pos':'neg';
  const metaF = [
    {lbl:'CNPJ',              val:f.cnpj},
    {lbl:'Cotas atuais',      val:fmtQtd(qt)},
    {lbl:'Cota em '+f.dt_ini, val:fmtCota(f.cota_ini)},
    {lbl:'Cota em '+f.dt_fim, val:fmtCota(f.cota_fim)},
    {lbl:'Patrimonio inicial', val:fmtBRL(f.patrim_ini)},
    {lbl:'Patrimonio atual',   val:fmtBRL(f.patrim_fim)},
  ];
  if(f.resg_total>0) metaF.push({lbl:'Resgates', val:'\u2212'+fmtBRL(f.resg_total), cls:'neg'});
  if(f.capt_total>0) metaF.push({lbl:'Aportes',  val:'+'+fmtBRL(f.capt_total), cls:'pos'});
  metaF.push(
    {lbl:'Resultado R$',       val:(f.ganho>=0?'+':'')+fmtBRL(f.ganho), cls:pc},
    {lbl:'Rentabilidade',      val:fmtPct(f.rent), cls:pc},
  );
  document.getElementById('detMeta').innerHTML=metaF.map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
}

function setDTab(tab){
  document.querySelectorAll('#detailBox .tab-row .tab').forEach((b,i)=>{
    b.classList.toggle('active',['cota','rent','patrim','diario'][i]===tab);
  });
  if(activeIdx==='cart') renderCartDet(tab);
  else if(activeIdx!==null) renderDet(DADOS[activeIdx],tab);
}

// ── RESGATES E APORTES ────────────────────────────────────────────────────────
(function(){
  document.getElementById('movsSection').style.display = 'block';
  const ext = MOVS.filter(m=>!m.interno);
  const nR = ext.filter(m=>m.tipo==='resgate').length;
  const nA = ext.filter(m=>m.tipo==='aporte').length;
  document.getElementById('lblMovsTot').textContent = ext.length
    ? [ nR ? nR+' resgate(s) \u00b7 '+fmtBRL(TOTAIS.resg) : '',
        nA ? nA+' aporte(s) \u00b7 '+fmtBRL(TOTAIS.capt) : '' ].filter(Boolean).join('  \u00b7  ')
    : 'nenhum resgate ou aporte no periodo';

  const linhas = MOVS.slice().reverse().map(m=>{
    const neg = m.interno ? (m.sinal < 0) : (m.tipo==='resgate');
    const cor = m.interno ? '#8892a8' : (neg ? '#D85A30' : '#1D9E75');
    const cls = m.interno ? '' : (neg ? 'neg' : 'pos');
    return `<div style="display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid #1a2035${m.interno?';opacity:.6':''}">
      <span style="width:8px;height:8px;border-radius:50%;background:${cor};flex-shrink:0"></span>
      <span style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#8892a8;min-width:88px">${m.dt}</span>
      <span style="display:flex;align-items:center;gap:6px;flex:1;font-size:12px">
        <span style="width:9px;height:9px;border-radius:2px;background:${m.color};flex-shrink:0"></span>${m.fundo}
      </span>
      <span style="font-size:10px;color:#8892a8;text-transform:uppercase;letter-spacing:.06em;font-family:'IBM Plex Mono',monospace">${m.tipo}${m.interno?' (interna)':''}</span>
      <span class="${cls}" style="font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:600;min-width:120px;text-align:right${m.interno?';color:#8892a8':''}">${neg?'\u2212':'+'}${fmtBRL(m.valor)}</span>
    </div>`;
  }).join('');

  const vazio = `<div style="padding:18px 0;font-size:12px;color:#8892a8;line-height:1.7">
      Nenhum resgate ou aporte registrado pela CVM entre ${TOTAIS.dt_ini} e ${TOTAIS.dt_fim}.<br>
      A leitura das colunas <span style="font-family:'IBM Plex Mono',monospace">CAPTC_DIA</span> e
      <span style="font-family:'IBM Plex Mono',monospace">RESG_DIA</span> do Informe Diario esta ativa \u2014
      assim que houver movimentacao, ela aparece aqui automaticamente.
    </div>`;

  const rodape = `<div style="display:flex;justify-content:space-between;align-items:baseline;padding-top:12px;font-size:11px;color:#8892a8;gap:16px">
      <span>Resgates nao contam como prejuizo: saem da base de calculo da rentabilidade. Transferencias internas entre os seus fundos nao entram no total.</span>
      <span style="font-family:'IBM Plex Mono',monospace;white-space:nowrap">Liquido: <span class="${(TOTAIS.capt-TOTAIS.resg)>=0?'pos':'neg'}" style="font-size:13px;font-weight:600">${(TOTAIS.capt-TOTAIS.resg)>=0?'+':'\u2212'}${fmtBRL(Math.abs(TOTAIS.capt-TOTAIS.resg))}</span></span>
    </div>`;

  document.getElementById('movsBox').innerHTML = (MOVS.length ? linhas : vazio) + rodape;
})();

// ── PIZZA ─────────────────────────────────────────────────────────────────────
(function(){
  const dadosAtivos = DADOS.filter(f => f.cnpj_raw !== '07152165000128');
  const ultimaDt = TOTAIS.dt_fim;

  function patrimNaData(f, dt) {
    const h = f.historico.slice().reverse().find(x => x.dt <= dt);
    return h ? h.patrimonio : 0;
  }

  const rfNaData = RF.slice().reverse().find(x => x.dt <= ultimaDt);
  const rfVal = rfNaData ? rfNaData.patrimonio : RF[RF.length-1].patrimonio;

  const labels=[...dadosAtivos.map(f=>f.nome_curto),'RF CDI'];
  const vals=[...dadosAtivos.map(f=>patrimNaData(f, ultimaDt)), rfVal];
  const cores=[...dadosAtivos.map(f=>f.color),TOTAIS.cdi_color];
  const total=vals.reduce((s,v)=>s+v,0);
  const rents=[...dadosAtivos.map(f=>f.rent),TOTAIS.rf_rent];

  document.getElementById('lblDataComp').textContent = ultimaDt;

  new Chart(document.getElementById('pieChart'),{
    type:'doughnut',
    data:{labels,datasets:[{data:vals.map(v=>+v.toFixed(2)),backgroundColor:cores,borderWidth:1,borderColor:'rgba(255,255,255,0.08)'}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'62%',
      plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`  ${ctx.label}: ${fmtBRL(ctx.parsed)}`}}},
    },
  });

  document.getElementById('pieInfo').innerHTML = vals.map((v,i)=>{
    const pct=(v/total*100).toFixed(1);
    const cls=rents[i]>=0?'pos':'neg';
    return `<div class="pie-row">
      <span style="width:10px;height:10px;border-radius:2px;background:${cores[i]};flex-shrink:0"></span>
      <div>
        <div style="font-size:11px;color:#8892a8">${labels[i]}</div>
        <div style="font-size:13px;font-weight:600">${fmtBRL(v)} <span style="font-size:10px;color:#8892a8">(${pct}%)</span></div>
        <div class="${cls}" style="font-size:11px;font-family:'IBM Plex Mono',monospace">${fmtPct(rents[i])}</div>
      </div>
    </div>`;
  }).join('') + `
    <div style="border-top:1px solid #1a2035;margin-top:8px;padding-top:10px;display:flex;align-items:center;gap:10px">
      <span style="width:10px;height:10px;border-radius:50%;background:#dde2f0;flex-shrink:0"></span>
      <div>
        <div style="font-size:11px;color:#8892a8">Total da Carteira</div>
        <div style="font-size:15px;font-weight:700;color:#dde2f0">${fmtBRL(total)}</div>
        <div style="font-size:10px;color:#8892a8;font-family:'IBM Plex Mono',monospace">em ${ultimaDt}</div>
      </div>
    </div>
    <div style="border-top:1px solid #1a2035;margin-top:8px;padding-top:8px">
      <div style="font-size:10px;color:#8892a8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;font-family:'IBM Plex Mono',monospace">Grupos · apenas visualização</div>
      ${GRUPOS.map(g=>{
        const pc=g.rent>=0?'pos':'neg';
        return `<div class="pie-row" style="margin-bottom:6px">
          <span style="width:10px;height:10px;border-radius:2px;background:${g.color};opacity:0.7;flex-shrink:0"></span>
          <div>
            <div style="font-size:11px;color:#8892a8">${g.nome}</div>
            <div style="font-size:13px;font-weight:600">${fmtBRL(g.patrim_fim)}</div>
            <div class="${pc}" style="font-size:11px;font-family:'IBM Plex Mono',monospace">${fmtPct(g.rent)}</div>
          </div>
        </div>`;
      }).join('')}
    </div>`;
})();
</script>
</body>
</html>"""

saida = os.path.join(os.getcwd(), "output", "index.html")
with open(saida, "w", encoding="utf-8") as out:
    out.write(HTML)

print(f"\nDashboard gerado: {saida}")
print("Abrindo no browser...\n")
print("HTML gerado com sucesso")
print("Concluido")
