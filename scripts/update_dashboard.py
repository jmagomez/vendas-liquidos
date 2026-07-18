"""Atualiza data.js do dashboard: baixa o CSV de vendas de combustíveis
líquidos da ANP (Liquidos_Vendas_Atual.csv), agrega por mês, companhia,
UF de destino e mercado destinatário, e grava data.js compacto."""
import csv
import io
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = ("https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
       "arquivos/mdpg/liquidos.zip/Liquidos_Vendas_Atual.csv")
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data.js"

TENTATIVAS = 4
ESPERA_BASE = 10.0  # segundos; dobra a cada tentativa
HEADERS = {"User-Agent": "Mozilla/5.0 (dashboard-updater)"}


def baixar():
    """Baixa o CSV (~140 MB) com retry e backoff exponencial."""
    ultima_falha = None
    for tentativa in range(TENTATIVAS):
        if tentativa:
            espera = ESPERA_BASE * 2 ** (tentativa - 1)
            print(f"[update] tentativa {tentativa + 1}/{TENTATIVAS} em {espera:.0f}s ({ultima_falha})")
            time.sleep(espera)
        try:
            r = requests.get(URL, headers=HEADERS, timeout=600)
            r.raise_for_status()
            return r.content
        except requests.RequestException as exc:
            ultima_falha = str(exc)[:200]
    raise RuntimeError(f"ANP indisponível após {TENTATIVAS} tentativas ({ultima_falha})")


def agregar(conteudo: bytes):
    agg = defaultdict(float)
    texto = io.TextIOWrapper(io.BytesIO(conteudo), encoding="latin-1")
    r = csv.reader(texto, delimiter=";")
    next(r)  # cabeçalho
    for row in r:
        ym = f"{row[0]}-{int(row[1]):02d}"
        agg[(ym, row[2], row[9], row[10])] += float(row[11].replace(",", "."))
    return agg


def gerar_data_js(agg):
    months = sorted({k[0] for k in agg})
    comps = sorted({k[1] for k in agg})
    ufs = sorted({k[2] for k in agg})
    mkts = sorted({k[3] for k in agg})
    mi = {v: i for i, v in enumerate(months)}
    ci = {v: i for i, v in enumerate(comps)}
    ui = {v: i for i, v in enumerate(ufs)}
    ki = {v: i for i, v in enumerate(mkts)}
    rows = []
    for (ym, c, u, k), q in agg.items():
        qi = round(q * 10000)  # mil m³ com 4 casas, como inteiro
        if qi:
            rows.extend([mi[ym], ci[c], ui[u], ki[k], qi])
    data = {"months": months, "comps": comps, "ufs": ufs, "mkts": mkts,
            "rows": rows,
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    OUT.write_text("window.VENDAS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    return data


def main():
    conteudo = baixar()
    print(f"[update] download ok ({len(conteudo)/1e6:.0f} MB)")
    agg = agregar(conteudo)
    data = gerar_data_js(agg)
    total = sum(agg.values())
    print(f"[update] {len(data['rows']) // 5} combinações | {data['months'][0]} a {data['months'][-1]} | "
          f"total {total:,.0f} mil m³ | data.js atualizado")


if __name__ == "__main__":
    main()
