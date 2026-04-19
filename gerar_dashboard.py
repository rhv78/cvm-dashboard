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
                ultima[c] = {"dt": dt, "cota": vl}
        for c, v in ultima.items():
            print(f"    {fmt_cnpj(c)}: cota {v['cota']:.8f} em {v['dt']}")
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
df = df.dropna(subset=["VL_QUOTA_F","DT_COMPTC"]).sort_values("DT_COMPTC")

datas_todas = sorted(df["DT_COMPTC"].unique())

# Fator CDI diário por data
fator_cdi = {dt: taxa_diaria_cdi(dt) for dt in datas_todas}

cdi_idx = {}; acum = 1.0
for dt in datas_todas:
    if dt >= "2026-01-01":          # acumula somente a partir do ano-base
        acum *= (1+fator_cdi[dt])
    cdi_idx[dt] = acum

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
    dt_ini   = df_f["DT_COMPTC"].iloc[0]

    if cnpj_raw in cota_base_dez25 and cota_base_dez25[cnpj_raw]["cota"] > 0:
        cota_ini = cota_base_dez25[cnpj_raw]["cota"]
        print(f"  Base: cota de dez/2025 = {cota_ini:.8f}")
    else:
        cota_ini = cota_map[dt_ini]
        print(f"  Base: primeira cota de 2026 = {cota_ini:.8f}")

    hist = []
    if cnpj_raw in cota_base_dez25:
        qt_dez = cotas_em(cnpj_raw, "2025-12-31")
        hist.append({
            "dt": "2025-12-31",
            "cota": round(cota_ini, 8),
            "cotas_qt": qt_dez,
            "patrimonio": round(cota_ini * qt_dez, 2),
            "rent_acum": 0.0,
            "var_diaria": 0.0,
        })
    for dt in datas_todas:
        if dt not in cota_map: continue
        c    = cota_map[dt]
        qt   = cotas_em(cnpj_raw, dt)
        if qt == 0.0: continue
        pat  = round(c * qt, 2)
        ra   = round((c/cota_ini-1)*100, 6) if cota_ini else 0.0
        if hist and hist[-1]["cota"] and hist[-1]["cota"] != 0:
            vd = round((c/hist[-1]["cota"]-1)*100, 6)
        else:
            vd = 0.0
        hist.append({"dt":dt,"cota":round(c,8),"cotas_qt":qt,"patrimonio":pat,"rent_acum":ra,"var_diaria":vd})

    if not hist: continue

    dt_fim      = hist[-1]["dt"]
    dt_ini_exib = "2025-12-31" if cnpj_raw in cota_base_dez25 else dt_ini
    cota_fim    = hist[-1]["cota"]
    rent_final  = round((cota_fim/cota_ini-1)*100, 6) if cota_ini else 0.0
    qt_ini      = cotas_em(cnpj_raw, dt_ini)
    patrim_ini  = round(cota_ini * qt_ini, 2)
    patrim_fim  = hist[-1]["patrimonio"]
    ganho       = round(patrim_fim - patrim_ini, 2)

    fundos.append({
        "cnpj": fmt_cnpj(cnpj_raw), "cnpj_raw": cnpj_raw,
        "nome": nome, "nome_curto": NOMES_FUNDOS.get(cnpj_raw, cnpj_raw[:6]),
        "color": CORES.get(cnpj_raw,"#aaa"),
        "cota_ini": cota_ini, "cota_fim": cota_fim,
        "rent": rent_final, "patrim_ini": patrim_ini, "patrim_fim": patrim_fim,
        "ganho": ganho, "dt_ini": dt_ini_exib, "dt_fim": dt_fim,
        "n_dias": len(hist), "historico": hist,
        "incorporado": "Incorporado ao Lagunna_78 em 18/03/2026" if cnpj_raw == "07152165000128" else "",
    })

    print(f"  OK  {fmt_cnpj(cnpj_raw)}  {nome[:40]}")
    print(f"      Rent: {rent_final:+.4f}%  |  Patrim: R$ {patrim_ini:,.2f} -> R$ {patrim_fim:,.2f}  |  Resultado: R$ {ganho:+,.2f}\n")

if not fundos:
    print("ERRO: nenhum fundo processado.")
    input("\nPressione Enter para fechar..."); sys.exit(1)

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
    h_ev_17 = next((h for h in reversed(f_everest["historico"]) if h["dt"] <= "2026-03-17"), None)
    h_la_17 = next((h for h in reversed(f_lagunna["historico"]) if h["dt"] <= "2026-03-17"), None)
    h_la_18 = next((h for h in f_lagunna["historico"] if h["dt"] >= "2026-03-18"), None)

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
cart_hist.append({"dt": "2025-12-31", "patrimonio": round(pat_ini_cart, 2), "rent_acum": 0.0, "var_diaria": 0.0})
for i, dt in enumerate(datas_todas):
    if dt < dt_base: continue
    pat_fundos = 0.0
    for f in fundos:
        qt = cotas_em(f["cnpj_raw"], dt)
        if qt == 0.0:
            continue
        h = next((x for x in f["historico"] if x["dt"] == dt), None)
        if h:
            pat_fundos += h["patrimonio"]
        else:
            anteriores = [x for x in f["historico"] if x["dt"] <= dt]
            if anteriores:
                pat_fundos += anteriores[-1]["patrimonio"]
    pat_rf  = round(VALOR_RF_CDI * cdi_idx[dt], 2)
    pat_tot = round(pat_fundos + pat_rf, 2)
    ra      = round((pat_tot / tot_ini - 1) * 100, 6) if tot_ini else 0.0
    vd      = round((pat_tot / cart_hist[-1]["patrimonio"] - 1) * 100, 6) if cart_hist and cart_hist[-1]["patrimonio"] else 0.0
    cart_hist.append({"dt": dt, "patrimonio": pat_tot, "rent_acum": ra, "var_diaria": vd})

cart_rent = cart_hist[-1]["rent_acum"] if cart_hist else 0.0

cart_na_ultima = next((h for h in reversed(cart_hist) if h["dt"] <= ultima_dt), cart_hist[-1] if cart_hist else None)
tot_fim_exib   = cart_na_ultima["patrimonio"] if cart_na_ultima else tot_fim
tot_ganho_exib = round(tot_fim_exib - tot_ini, 2)
tot_rent_exib  = round((tot_fim_exib / tot_ini - 1) * 100, 6) if tot_ini else 0
cart_rent_exib = cart_na_ultima["rent_acum"] if cart_na_ultima else cart_rent
print(f"  CARTEIRA  R$ {tot_ini:,.2f} -> R$ {tot_fim:,.2f}  |  Rent: {cart_rent:+.4f}%\n")

# ── GRUPOS VIRTUAIS ────────────────────────────────────────────────────────────
def get_fundo(cnpj_raw):
    return next((f for f in fundos if f["cnpj_raw"] == cnpj_raw), None)

def consolidar_grupo(nome, cor, cnpjs):
    dts = sorted(set(h["dt"] for c in cnpjs for f in [get_fundo(c)] if f for h in f["historico"]))
    pat_ini_grupo = sum(
        get_fundo(c)["patrim_ini"] for c in cnpjs if get_fundo(c)
    )
    hist_grupo = []
    for dt in dts:
        if dt > ultima_dt: continue
        pat = 0.0
        for c in cnpjs:
            f = get_fundo(c)
            if not f: continue
            qt = cotas_em(c, dt)
            if qt == 0.0: continue
            h = next((x for x in f["historico"] if x["dt"] == dt), None)
            if h: pat += h["patrimonio"]
        ra = round((pat / pat_ini_grupo - 1) * 100, 6) if pat_ini_grupo else 0.0
        vd = round((pat / hist_grupo[-1]["patrimonio"] - 1) * 100, 6) if hist_grupo and hist_grupo[-1]["patrimonio"] else 0.0
        hist_grupo.append({"dt": dt, "patrimonio": round(pat, 2), "rent_acum": ra, "var_diaria": vd})

    if not hist_grupo: return None
    pat_fim_grupo = hist_grupo[-1]["patrimonio"]
    rent_grupo    = hist_grupo[-1]["rent_acum"]
    return {
        "nome": nome, "nome_curto": nome, "cnpj": "Grupo virtual", "cnpj_raw": "",
        "color": cor, "incorporado": "",
        "cota_ini": 0, "cota_fim": 0,
        "rent": rent_grupo, "patrim_ini": pat_ini_grupo, "patrim_fim": pat_fim_grupo,
        "ganho": round(pat_fim_grupo - pat_ini_grupo, 2),
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
totais_json = json.dumps({
    "ini": tot_ini, "fim": tot_fim_exib, "ganho": tot_ganho_exib, "rent": tot_rent_exib,
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
  <div class="gerado">Gerado em """ + gerado_em + """</div>
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
  const pct = ((T.fim/T.ini)-1)*100;
  [
    {lbl:'Patrimonio inicial', val:fmtBRL(T.ini),   sub:'em '+T.dt_ini, cls:''},
    {lbl:'Patrimonio atual',   val:fmtBRL(T.fim),   sub:'em '+T.dt_fim, cls:''},
    {lbl:'Resultado R$', val:(T.ganho>=0?'+':'')+fmtBRL(T.ganho), sub:fmtPct(pct)+' no periodo', cls:T.ganho>=0?'pos':'neg'},
    {lbl:'Rent. carteira', val:fmtPct(T.cart_rent), sub:'consolidado no periodo', cls:T.cart_rent>=0?'pos':'neg'},
    {lbl:'CDI acumulado', val:fmtPct(T.rf_rent), sub:T.dt_fim, cls:'pos'},
  ].forEach(c=>{
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

function getDS(tab){
  const key = tab==='acum'?'rent_acum':tab==='patrim'?'patrimonio':'var_diaria';
  if(tab==='patrim'){
    return [
      {label:'Carteira Total',data:CART.filter(h=>h.dt<=ULTIMA_DT).map(h=>h[key]),borderColor:TOTAIS.cart_color,backgroundColor:TOTAIS.cart_color+'18',fill:true,borderWidth:3,pointRadius:0,tension:0.1},
    ];
  }
  return [
    {label:'RF CDI',data:RF.filter(h=>h.dt<=ULTIMA_DT).map(h=>h[key]),borderColor:TOTAIS.cdi_color,backgroundColor:'transparent',borderWidth:2,pointRadius:0,borderDash:[6,3],tension:0.1},
    {label:'Carteira Total',data:CART.filter(h=>h.dt<=ULTIMA_DT).map(h=>h[key]),borderColor:TOTAIS.cart_color,backgroundColor:'transparent',borderWidth:3,pointRadius:0,tension:0.1},
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
      plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`  ${ctx.dataset.label}: ${fmtY(tab,ctx.parsed.y)}`}}},
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
  document.getElementById('detMeta').innerHTML=[
    {lbl:'Composição',         val: g.nome_curto==='Lagunna + EVEREST'?'Lagunna_78 + EVEREST':'Neblina_78 + Neblina_Equity_78'},
    {lbl:'Apenas visualização',val:'Não entra no total da carteira'},
    {lbl:'Patrimônio inicial', val:fmtBRL(g.patrim_ini)},
    {lbl:'Patrimônio atual',   val:fmtBRL(g.patrim_fim)},
    {lbl:'Resultado R$',       val:(g.ganho>=0?'+':'')+fmtBRL(g.ganho), cls:pc},
    {lbl:'Rentabilidade',      val:fmtPct(g.rent), cls:pc},
    {lbl:'Período',            val:g.dt_ini+' \u2192 '+g.dt_fim},
  ].map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
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
  document.getElementById('detMeta').innerHTML=[
    {lbl:'Composicao',        val:'4 fundos + RF CDI'},
    {lbl:'Patrimonio inicial',val:fmtBRL(T.ini)},
    {lbl:'Patrimonio atual',  val:fmtBRL(T.fim)},
    {lbl:'Resultado R$',      val:(T.ganho>=0?'+':'')+fmtBRL(T.ganho), cls:pc},
    {lbl:'Rentabilidade',     val:fmtPct(T.cart_rent), cls:pc},
    {lbl:'CDI no periodo',    val:fmtPct(T.rf_rent), cls:'pos'},
    {lbl:'Periodo',           val:T.dt_ini+' \u2192 '+T.dt_fim},
  ].map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
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
  document.getElementById('detMeta').innerHTML=[
    {lbl:'CNPJ',              val:f.cnpj},
    {lbl:'Cotas atuais',      val:fmtQtd(qt)},
    {lbl:'Cota em '+f.dt_ini, val:fmtCota(f.cota_ini)},
    {lbl:'Cota em '+f.dt_fim, val:fmtCota(f.cota_fim)},
    {lbl:'Patrimonio inicial', val:fmtBRL(f.patrim_ini)},
    {lbl:'Patrimonio atual',   val:fmtBRL(f.patrim_fim)},
    {lbl:'Resultado R$',       val:(f.ganho>=0?'+':'')+fmtBRL(f.ganho), cls:pc},
    {lbl:'Rentabilidade',      val:fmtPct(f.rent), cls:pc},
  ].map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
}

function setDTab(tab){
  document.querySelectorAll('#detailBox .tab-row .tab').forEach((b,i)=>{
    b.classList.toggle('active',['cota','rent','patrim','diario'][i]===tab);
  });
  if(activeIdx==='cart') renderCartDet(tab);
  else if(activeIdx!==null) renderDet(DADOS[activeIdx],tab);
}

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
