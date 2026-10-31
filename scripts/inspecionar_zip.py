"""Diagnostico do liquidos.zip da ANP. NAO escreve nada no repositorio.

Motivo: o run #19 (2026-10-31) mostrou que o Liquidos_Vendas_Atual.csv encolheu
de ~116 meses para 33 (terminando em 2026-09). A hipotese e que a ANP moveu o
historico para outro(s) membro(s) do mesmo zip -- ha referencia publica a um
`Liquidos_Vendas_Historico_2007_a_2017.csv` --, que o pipeline hoje ignora:
`_extrair_do_zip` so procura o membro `*Liquidos_Vendas_Atual.csv`.

Antes de decidir entre "ler tambem os historicos" e "costurar com o data.js
anterior", este script responde o que de fato esta dentro do zip hoje: quais
membros existem, que cabecalho cada um tem, em que encoding, qual delimitador,
quantas linhas e que faixa de meses cobre -- e se, juntos, cobrem a serie do
data.js atual sem buraco.

Uso:
    python scripts/inspecionar_zip.py [--max-membros N] [--saida relatorio.md]

Este script e read-only por construcao: baixa, le em streaming e imprime. Nao
importa update_dashboard, nao chama escrever_data_js, nao toca em data.js.
"""
import argparse
import csv
import io
import json
import sys
import time
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parents[1]
URL_ZIP = ("https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
           "arquivos/mdpg/liquidos.zip")
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36")}
TIMEOUT = 300
TENTATIVAS = 3
CANDIDATOS = ("utf-8-sig", "cp1252", "latin-1")

# Amostra para farejar encoding e delimitador sem carregar o membro inteiro.
AMOSTRA = 1 << 20   # 1 MiB


def baixar_zip() -> bytes:
    ultima = None
    for i in range(TENTATIVAS):
        if i:
            espera = 10 * 2 ** (i - 1)
            print(f"[diag] tentativa {i + 1}/{TENTATIVAS} em {espera}s ({ultima})", flush=True)
            time.sleep(espera)
        try:
            r = requests.get(URL_ZIP, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.content
        except Exception as exc:                      # noqa: BLE001
            ultima = str(exc)[:160]
    raise RuntimeError(f"ANP indisponivel apos {TENTATIVAS} tentativas ({ultima})")


def farejar_encoding(amostra: bytes) -> str:
    """Encoding do membro, a partir de uma amostra.

    A amostra pode cortar um caractere multibyte no fim, o que faria uma
    decodificacao valida parecer invalida. Por isso tenta aparar ate 3 bytes do
    final antes de descartar o candidato -- 3 e o maximo que falta para fechar
    um caractere UTF-8 de 4 bytes.
    """
    for enc in CANDIDATOS:
        for corte in range(4):
            try:
                (amostra[:len(amostra) - corte]).decode(enc)
                return enc
            except UnicodeDecodeError:
                continue
    return "latin-1"   # nunca falha


def farejar_delimitador(linha: str) -> str:
    return max(";,\t|", key=linha.count)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().replace('"', " ").replace("-", " ").split())


def achar_coluna(cabecalho, raiz):
    for i, nome in enumerate(cabecalho):
        if raiz in _norm(nome):
            return i
    return None


def parece_cabecalho(campos) -> bool:
    """Linha de cabecalho tem texto onde dado teria numero.

    Ha relato publico de um membro historico SEM cabecalho nativo. Confundir
    dado com cabecalho perderia uma linha e, pior, daria a impressao de que o
    layout e outro.
    """
    if not campos:
        return False
    try:
        int(campos[0].strip().strip('"'))
    except ValueError:
        return True
    return False


def inspecionar_membro(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict:
    out = {
        "nome": info.filename,
        "bytes_comprimido": info.compress_size,
        "bytes": info.file_size,
        "modificado": "%04d-%02d-%02d %02d:%02d" % info.date_time[:5],
    }
    if not info.filename.lower().endswith((".csv", ".txt")):
        out["tipo"] = "nao-tabular (ignorado)"
        return out

    with zf.open(info) as fh:
        amostra = fh.read(AMOSTRA)
    enc = farejar_encoding(amostra)
    primeira = amostra.decode(enc, errors="replace").splitlines()[0] if amostra else ""
    delim = farejar_delimitador(primeira)
    out.update(encoding=enc, delimitador=repr(delim))

    with zf.open(info) as fh:
        texto = io.TextIOWrapper(fh, encoding=enc, newline="")
        r = csv.reader(texto, delimiter=delim)
        primeira_linha = next(r, None)
        if primeira_linha is None:
            out["tipo"] = "vazio"
            return out

        tem_cabecalho = parece_cabecalho(primeira_linha)
        cabecalho = primeira_linha if tem_cabecalho else []
        out["tem_cabecalho"] = tem_cabecalho
        out["n_colunas"] = len(primeira_linha)
        out["cabecalho"] = cabecalho if tem_cabecalho else ["(sem cabecalho)"] + primeira_linha

        if tem_cabecalho:
            i_ano = achar_coluna(cabecalho, "ano")
            i_mes = achar_coluna(cabecalho, "mes")
            i_prod = achar_coluna(cabecalho, "nome do produto")
            i_qtd = achar_coluna(cabecalho, "quantidade")
        else:
            # Sem cabecalho, assume o layout do _Atual (COL_PROD=4, COL_QTD=11)
            # so para o diagnostico. Se os produtos listados abaixo nao fizerem
            # sentido, o membro tem OUTRO layout -- e isso e justamente o que
            # este relatorio precisa revelar.
            i_ano, i_mes, i_prod, i_qtd = 0, 1, 4, 11
        out["colunas_localizadas"] = {"ano": i_ano, "mes": i_mes,
                                      "nome do produto": i_prod, "quantidade": i_qtd,
                                      "assumido": not tem_cabecalho}

        meses = set()
        por_ano = Counter()
        produtos = Counter()
        linhas = invalidas = 0
        # Linha de dado que ficou na primeira posicao quando nao ha cabecalho.
        linhas_iter = r if tem_cabecalho else _com_primeira(primeira_linha, r)
        for campos in linhas_iter:
            linhas += 1
            try:
                ano = int(campos[i_ano])
                mes = int(campos[i_mes])
                if not (1900 <= ano <= 2100 and 1 <= mes <= 12):
                    raise ValueError
            except (ValueError, IndexError, TypeError):
                invalidas += 1
                continue
            meses.add(f"{ano}-{mes:02d}")
            por_ano[ano] += 1
            if i_prod is not None and i_prod < len(campos):
                produtos[campos[i_prod]] += 1

    out.update(
        linhas=linhas,
        linhas_sem_ano_mes=invalidas,
        meses=len(meses),
        primeiro_mes=min(meses) if meses else None,
        ultimo_mes=max(meses) if meses else None,
        buracos=sorted(_buracos(meses))[:12],
        linhas_por_ano=dict(sorted(por_ano.items())),
        produtos=dict(produtos.most_common(10)),
    )
    out["_meses"] = sorted(meses)
    return out


def _com_primeira(primeira, resto):
    yield primeira
    yield from resto


def _buracos(meses: set) -> set:
    """Meses ausentes entre o primeiro e o ultimo da cobertura."""
    if not meses:
        return set()
    ordenados = sorted(meses)
    a0, m0 = map(int, ordenados[0].split("-"))
    a1, m1 = map(int, ordenados[-1].split("-"))
    esperados = {f"{a}-{m:02d}"
                 for a in range(a0, a1 + 1)
                 for m in range(1, 13)
                 if (a, m) >= (a0, m0) and (a, m) <= (a1, m1)}
    return esperados - meses


def familia(nome: str) -> str:
    """Familia do membro, a partir do nome: Liquidos_<Familia>_...

    O zip traz bases DIFERENTES -- Vendas, Entregas (distribuidor, fornecedor,
    historico) e Importacao --, com outro grao e outras colunas. A primeira
    versao deste relatorio somou a cobertura de todas e concluiu que nao faltava
    nenhum mes; faltava 2017 na familia que importa. Cobertura so faz sentido
    DENTRO de uma familia.
    """
    base = nome.rsplit("/", 1)[-1]
    partes = base.split("_")
    return partes[1].lower() if len(partes) > 1 else base.lower()


def meses_do_data_js() -> list:
    caminho = BASE / "data.js"
    if not caminho.exists():
        return []
    bruto = caminho.read_text(encoding="utf-8").strip()
    return json.loads(bruto.removeprefix("window.VENDAS = ").rstrip(";\n"))["months"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-membros", type=int, default=50)
    ap.add_argument("--saida", default="")
    args = ap.parse_args()

    blob = baixar_zip()
    print(f"[diag] zip baixado: {len(blob):,} bytes", flush=True)
    if blob[:2] != b"PK":
        print("[diag] ATENCAO: a resposta nao e um zip (servidor devolveu o CSV direto?)")
        return 1

    zf = zipfile.ZipFile(io.BytesIO(blob))
    infos = zf.infolist()[: args.max_membros]
    print(f"[diag] {len(zf.infolist())} membro(s) no zip\n", flush=True)

    linhas_md = ["# Diagnostico do liquidos.zip da ANP", "",
                 f"- zip: {len(blob):,} bytes", f"- membros: {len(zf.infolist())}", ""]
    cobertura = {}
    for info in infos:
        d = inspecionar_membro(zf, info)
        fam = familia(d["nome"])
        cobertura.setdefault(fam, set()).update(d.pop("_meses", []))
        d["familia"] = fam
        print(f"--- {d['nome']}", flush=True)
        for k, v in d.items():
            if k != "nome":
                print(f"    {k}: {v}", flush=True)
        print(flush=True)
        linhas_md += [f"## `{d['nome']}`", ""]
        linhas_md += [f"- **{k}**: `{v}`" for k, v in d.items() if k != "nome"]
        linhas_md += [""]

    atuais = set(meses_do_data_js())
    vendas = cobertura.get("vendas", set())
    faltando = sorted(atuais - vendas)
    resumo = ["## Cobertura POR FAMILIA", "",
              "Vendas, Entregas e Importacao sao bases diferentes, com outro grao e",
              "outras colunas. Somar a cobertura das tres esconde buraco na que",
              "importa — foi o que a primeira versao deste relatorio fez.", ""]
    for fam in sorted(cobertura):
        meses = cobertura[fam]
        if not meses:
            continue
        resumo.append(
            f"- **{fam}**: {len(meses)} meses ({min(meses)} a {max(meses)}), "
            f"buracos: `{sorted(_buracos(meses))[:14]}`")
    resumo += [
        "",
        "## A serie do dashboard (familia `vendas`)",
        "",
        f"- meses cobertos pelos membros de vendas: **{len(vendas)}**"
        + (f" ({min(vendas)} a {max(vendas)})" if vendas else ""),
        f"- meses no data.js atual: **{len(atuais)}**",
        f"- meses do data.js que a familia `vendas` NAO cobre: **{len(faltando)}**"
        + (f" ({faltando[:14]})" if faltando else " — a fonte cobre toda a serie"),
        "",
        "**Leitura:** se a ultima linha for 0, da para derivar o historico inteiro",
        "da fonte a cada rodada, lendo todos os membros de vendas em vez de so o",
        "`_Atual`. Se for > 0, esses meses existem no artefato e em nenhum membro",
        "da fonte: ou vem herdados do data.js anterior, marcados na proveniencia,",
        "ou somem da serie.",
        "",
    ]
    print("\n".join(resumo), flush=True)
    linhas_md += resumo

    if args.saida:
        Path(args.saida).write_text("\n".join(linhas_md), encoding="utf-8")
        print(f"[diag] relatorio escrito em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
