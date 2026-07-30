"""Atualiza data.js do dashboard: baixa o CSV de vendas de combustíveis
líquidos da ANP (Liquidos_Vendas_Atual.csv), agrega por mês, companhia,
UF de destino e mercado destinatário, e grava data.js compacto."""
import csv
import io
import zipfile
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

URL_ZIP = ("https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
           "arquivos/mdpg/liquidos.zip")
URL_CSV = ("https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
           "arquivos/mdpg/liquidos.zip/Liquidos_Vendas_Atual.csv")
ALVO_CSV = "Liquidos_Vendas_Atual.csv"
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data.js"

TENTATIVAS = 4
ESPERA_BASE = 10.0  # segundos; dobra a cada tentativa
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36")}


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=900)
    r.raise_for_status()
    return r.content


def _extrair_do_zip(blob):
    zf = zipfile.ZipFile(io.BytesIO(blob))
    for nome in zf.namelist():
        if nome.lower().endswith(ALVO_CSV.lower()):
            return zf.read(nome)
    raise RuntimeError(f"{ALVO_CSV} não encontrado no zip ({zf.namelist()[:10]})")


def baixar():
    """Baixa o CSV: preferindo o pacote liquidos.zip; fallback na URL direta.
    Retry com backoff exponencial."""
    ultima_falha = None
    for tentativa in range(TENTATIVAS):
        if tentativa:
            espera = ESPERA_BASE * 2 ** (tentativa - 1)
            print(f"[update] tentativa {tentativa + 1}/{TENTATIVAS} em {espera:.0f}s ({ultima_falha})")
            time.sleep(espera)
        try:
            blob = _get(URL_ZIP)
            if blob[:2] == b"PK":          # é zip: extrai o CSV
                return _extrair_do_zip(blob)
            return blob                    # servidor devolveu o CSV direto
        except Exception as exc:
            ultima_falha = f"zip: {str(exc)[:120]}"
        try:
            return _get(URL_CSV)
        except Exception as exc:
            ultima_falha += f" | csv: {str(exc)[:120]}"
    raise RuntimeError(f"ANP indisponível após {TENTATIVAS} tentativas ({ultima_falha})")


# Posições das colunas usadas no CSV da ANP. O arquivo não tem cabeçalho
# estável documentado, então lemos por índice — mas cada linha é validada
# (ver `agregar`). Se a ANP inserir ou reordenar uma coluna, a validação
# derruba a rotina em vez de gravar um data.js silenciosamente errado.
COL_ANO, COL_MES, COL_COMP, COL_UF, COL_MKT, COL_QTD = 0, 1, 2, 9, 10, 11
N_COLUNAS_MIN = 12

ANO_MIN, ANO_MAX = 2000, 2100
# Fração máxima de linhas descartadas antes de considerar que o layout mudou.
TOLERANCIA_DESCARTE = 0.01


def agregar(conteudo: bytes):
    """Agrega por (ano-mês, companhia, UF de destino, mercado destinatário).

    Cada linha é validada antes de entrar na soma. Sem isso, uma mudança de
    layout da ANP (coluna nova, reordenação) produziria um data.js com números
    errados e nenhum sinal de erro — o pior desfecho possível para um dashboard
    que roda sozinho todo mês.
    """
    agg = defaultdict(float)
    texto = io.TextIOWrapper(io.BytesIO(conteudo), encoding="latin-1")
    r = csv.reader(texto, delimiter=";")

    cabecalho = next(r, None)
    if cabecalho is None:
        raise RuntimeError("CSV da ANP veio vazio")
    if len(cabecalho) < N_COLUNAS_MIN:
        raise RuntimeError(
            f"CSV da ANP tem {len(cabecalho)} colunas, esperado >= {N_COLUNAS_MIN}. "
            f"Layout mudou? Cabeçalho: {cabecalho}"
        )

    total = descartadas = 0
    motivos = defaultdict(int)
    for row in r:
        total += 1
        if len(row) < N_COLUNAS_MIN:
            descartadas += 1
            motivos["colunas de menos"] += 1
            continue
        try:
            ano = int(row[COL_ANO])
            mes = int(row[COL_MES])
            qtd = float(row[COL_QTD].replace(",", "."))
        except ValueError:
            descartadas += 1
            motivos["campo não numérico"] += 1
            continue
        if not (ANO_MIN <= ano <= ANO_MAX):
            descartadas += 1
            motivos["ano fora da faixa"] += 1
            continue
        if not (1 <= mes <= 12):
            descartadas += 1
            motivos["mês fora de 1-12"] += 1
            continue
        agg[(f"{ano}-{mes:02d}", row[COL_COMP], row[COL_UF], row[COL_MKT])] += qtd

    if not total:
        raise RuntimeError("CSV da ANP não tem linhas de dados")
    if descartadas > total * TOLERANCIA_DESCARTE:
        raise RuntimeError(
            f"{descartadas}/{total} linhas ({descartadas / total:.1%}) invalidas — "
            f"o layout da ANP provavelmente mudou. Motivos: {dict(motivos)}"
        )
    if descartadas:
        print(f"[update] {descartadas}/{total} linhas descartadas: {dict(motivos)}")
    print(f"[update] {total} linhas lidas, {len(agg)} combinacoes")
    return agg


def carregar_anterior():
    """Lê o data.js atual, para comparar antes de sobrescrever."""
    if not OUT.exists():
        return None
    try:
        bruto = OUT.read_text(encoding="utf-8").strip()
        return json.loads(bruto.removeprefix("window.VENDAS = ").rstrip(";\n"))
    except Exception as exc:  # noqa: BLE001
        print(f"[update] aviso: nao consegui ler o data.js anterior ({exc})")
        return None


def conferir_contra_anterior(novo, anterior):
    """Barra regressões silenciosas.

    A ANP já publicou arquivo truncado. Sem esta checagem, um download parcial
    sobrescreveria anos de histórico e a rotina terminaria com sucesso.
    """
    if not anterior:
        return
    meses_antes, meses_agora = len(anterior["months"]), len(novo["months"])
    if meses_agora < meses_antes:
        raise RuntimeError(
            f"regressao: {meses_agora} meses no arquivo novo contra {meses_antes} no atual "
            f"(ultimo antes: {anterior['months'][-1]}, agora: {novo['months'][-1]}). "
            "Arquivo da ANP provavelmente veio truncado; data.js NAO foi alterado."
        )
    linhas_antes, linhas_agora = len(anterior["rows"]) // 5, len(novo["rows"]) // 5
    if linhas_agora < linhas_antes * 0.95:
        raise RuntimeError(
            f"regressao: {linhas_agora} combinacoes contra {linhas_antes} no atual "
            f"(queda de {1 - linhas_agora / linhas_antes:.1%}). data.js NAO foi alterado."
        )


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
    return {"months": months, "comps": comps, "ufs": ufs, "mkts": mkts,
            "rows": rows,
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d")}


def escrever_data_js(data):
    OUT.write_text("window.VENDAS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")


def main():
    anterior = carregar_anterior()
    conteudo = baixar()
    print(f"[update] download ok ({len(conteudo)/1e6:.0f} MB)")
    agg = agregar(conteudo)
    data = gerar_data_js(agg)
    conferir_contra_anterior(data, anterior)   # levanta antes de escrever
    escrever_data_js(data)
    total = sum(agg.values())
    print(f"[update] {len(data['rows']) // 5} combinações | {data['months'][0]} a {data['months'][-1]} | "
          f"total {total:,.0f} mil m³ | data.js atualizado")


if __name__ == "__main__":
    main()
