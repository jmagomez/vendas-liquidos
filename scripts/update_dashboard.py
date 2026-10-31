"""Atualiza data.js do dashboard: baixa o CSV de vendas de combustíveis
líquidos da ANP (Liquidos_Vendas_Atual.csv), agrega por mês, companhia,
UF de destino, mercado destinatário e produto, e grava data.js compacto."""
import csv
import hashlib
import io
import statistics
import time
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import data_js
import leitura
import membros as mod_membros
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
TIMEOUT = 300       # o arquivo tem ~200 MB; 300s cobre folgado uma ANP lenta
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36")}


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def _extrair_do_zip(blob):
    """Todos os membros da familia de vendas, em ordem de nome.

    Ate out/2026 bastava o _Atual: ele trazia a serie inteira. A ANP
    encurtou essa janela para 33 meses e moveu o resto para membros
    historicos do MESMO zip (ver scripts/membros.py e o run #19).
    Ignora-los significaria publicar 33 meses no lugar de 225.
    """
    zf = zipfile.ZipFile(io.BytesIO(blob))
    achados = [n for n in sorted(zf.namelist())
               if mod_membros.e_membro_de_vendas(n)]
    if not achados:
        raise RuntimeError(
            f"nenhum membro Liquidos_Vendas_* no zip ({zf.namelist()[:10]})")
    print(f"[update] membros de vendas no zip: {achados}")
    return [(n, zf.read(n)) for n in achados]


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
            if blob[:2] == b"PK":          # é zip: extrai os membros
                return _extrair_do_zip(blob)
            # Servidor devolveu o CSV direto: so o _Atual, que hoje cobre
            # 33 meses. Nao da para sustentar a serie com ele sozinho; quem
            # barra e o teto de meses herdados, com mensagem explicita.
            return [(ALVO_CSV, blob)]
        except Exception as exc:
            ultima_falha = f"zip: {str(exc)[:120]}"
        try:
            return [(ALVO_CSV, _get(URL_CSV))]
        except Exception as exc:
            ultima_falha = f"{ultima_falha} | csv: {str(exc)[:120]}"
    raise RuntimeError(f"ANP indisponível após {TENTATIVAS} tentativas ({ultima_falha})")


# Posicoes das colunas no CSV da ANP. A ANP nao documenta um layout estavel,
# entao lemos por indice, conferimos o cabecalho e validamos cada linha (ver
# `agregar`): se uma coluna for inserida ou reordenada, a rotina cai em vez de
# gravar numeros errados em silencio. Cabecalho lido do proprio arquivo em
# 2026-08:
# "Ano";"Mes";"Agente Regulado";"Codigo do Produto";"Nome do Produto";
# "Descricao do Produto";"Regiao Origem";"UF Origem";"Regiao Destinatario";
# "UF Destino";"Mercado Destinatario";"Quantidade de Produto (mil m3)"
#
# Usamos a coluna 4 ("Nome do Produto": Diesel B, Gasolina C, Etanol Hidratado,
# Oleo Comb.) e nao a 5 ("Descricao do Produto"), que separa comum/aditivada e
# multiplicaria as combinacoes sem responder nenhuma pergunta que o dashboard faca.
COL_ANO, COL_MES, COL_COMP, COL_PROD, COL_UF, COL_MKT, COL_QTD = 0, 1, 2, 4, 9, 10, 11
N_COLUNAS_MIN = 12

# Conferencia do cabecalho por conteudo, e nao so por contagem. Contar colunas
# pega insercao no fim; nao pega REORDENACAO entre duas colunas numericas -- ano
# e mes trocados, por exemplo, passariam por toda a validacao por linha (os dois
# sao inteiros pequenos) e produziriam uma serie inteira deslocada. Comparamos
# uma raiz de cada nome esperado, sem acento e sem pontuacao, para nao quebrar a
# rotina por causa de um "(mil m3)" que virou "(mil m³)".
CABECALHO_ESPERADO = {
    COL_ANO: "ano",
    COL_MES: "mes",
    COL_COMP: "agente",
    COL_PROD: "nome do produto",
    COL_UF: "uf destino",
    COL_MKT: "mercado",
    COL_QTD: "quantidade",
}

# Numero de campos por linha em data.js["rows"]; contrato compartilhado.
CAMPOS = data_js.CAMPOS

ANO_MIN, ANO_MAX = 2000, 2100
# Fração máxima de linhas descartadas antes de considerar que o layout mudou.
TOLERANCIA_DESCARTE = 0.01

# --- Deteccao de mes ainda nao consolidado pela ANP -------------------------
# O Liquidos_Vendas_Atual.csv passa a listar o mes corrente assim que o primeiro
# agente entrega sua declaracao, muito antes do prazo regulatorio de envio. Em
# 2026-09-05 o arquivo trazia 2026-08 com 71 mil m3 de tres distribuidoras
# pequenas -- 0,6% de um mes normal, sem Vibra, Ipiranga ou Raizen. As travas
# antigas nao pegavam: elas defendem contra o histórico ENCOLHER, e um mes novo
# incompleto faz o contrário, ADICIONA linhas e um mes. Passavam com folga.
#
# Um mes da ponta e considerado nao consolidado quando o volume OU o numero de
# agentes declarantes fica abaixo de uma fracao da mediana dos meses anteriores.
# Mediana, e nao media, para que um mes parcial ja detectado nao contamine a
# referencia do seguinte.
JANELA_BASE = 12
FATOR_PARCIAL = 0.60
# Quantos meses da ponta podem ser marcados antes de assumirmos que o problema
# nao e a ponta em formacao, e sim o arquivo inteiro.
MAX_MESES_PARCIAIS = 3
# Queda maxima tolerada num mes que JA estava no arquivo anterior. A ANP revisa
# meses fechados, mas na casa de 0,1% (2026-06 foi de 11.507 para 11.515 entre
# duas rodadas). 10% esta muito acima do ruido de revisao e muito abaixo de um
# truncamento real.
QUEDA_MAX_MES_FECHADO = 0.10


def _normalizar(texto: str) -> str:
    """Minusculas, sem acento e sem pontuacao — para comparar nomes de coluna."""
    import unicodedata
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().replace('"', " ").replace("-", " ").split())


def conferir_cabecalho(cabecalho):
    """Levanta se alguma coluna esperada nao estiver onde deveria."""
    erros = []
    for pos, raiz in CABECALHO_ESPERADO.items():
        achado = _normalizar(cabecalho[pos]) if pos < len(cabecalho) else ""
        if raiz not in achado:
            erros.append(f"col {pos}: esperado ~'{raiz}', achado '{cabecalho[pos] if pos < len(cabecalho) else ''}'")
    if erros:
        raise RuntimeError(
            "cabeçalho da ANP não confere — layout mudou; data.js NÃO foi alterado. "
            + " | ".join(erros)
        )


def agregar(conteudo: bytes, stats: dict | None = None):
    """Agrega por (ano-mês, companhia, UF de destino, mercado destinatário, produto).

    Cada linha é validada antes de entrar na soma. Sem isso, uma mudança de
    layout da ANP (coluna nova, reordenação) produziria um data.js com números
    errados e nenhum sinal de erro — o pior desfecho possível para um dashboard
    que roda sozinho todo mês.
    """
    # Encoding DETECTADO, nao assumido. O run #17 (2026-10-28) caiu com
    # "MÃªs" porque a ANP passou a gravar o CSV em UTF-8 e aqui havia
    # encoding="latin-1" fixo. Ver scripts/leitura.py.
    conteudo_txt, enc = leitura.decodificar(conteudo)
    print(f"[update] encoding detectado: {enc}")
    r = csv.reader(io.StringIO(conteudo_txt), delimiter=";")

    primeira = next(r, None)
    if primeira is None:
        raise RuntimeError("CSV da ANP veio vazio")

    # O membro historico 2007-2016 nao tem cabecalho e tem 11 colunas, com
    # UF/mercado/quantidade deslocados um a esquerda. Le-lo com as
    # constantes do layout novo daria numero errado sem erro nenhum.
    if not mod_membros.parece_cabecalho(primeira):
        if len(primeira) != mod_membros.N_COLUNAS_11:
            raise RuntimeError(
                f"membro sem cabecalho com {len(primeira)} colunas, esperado "
                f"{mod_membros.N_COLUNAS_11}. Layout desconhecido; data.js NAO "
                "foi alterado.")
        L = mod_membros.LAYOUT_11
        return _somar(_com_primeira(primeira, r), L["ano"], L["mes"], L["comp"],
                      L["uf"], L["mkt"], L["prod"], L["qtd"],
                      mod_membros.N_COLUNAS_11, enc, stats)

    cabecalho = primeira
    if len(cabecalho) < N_COLUNAS_MIN:
        raise RuntimeError(
            f"CSV da ANP tem {len(cabecalho)} colunas, esperado >= {N_COLUNAS_MIN}. "
            f"Layout mudou? Cabeçalho: {cabecalho}"
        )
    leitura.conferir_sem_mojibake(cabecalho, enc, "cabecalho")
    conferir_cabecalho(cabecalho)
    return _somar(r, COL_ANO, COL_MES, COL_COMP, COL_UF, COL_MKT, COL_PROD,
                  COL_QTD, N_COLUNAS_MIN, enc, stats)


def _com_primeira(primeira, resto):
    yield primeira
    yield from resto


def _somar(linhas, c_ano, c_mes, c_comp, c_uf, c_mkt, c_prod, c_qtd,
           n_min, enc, stats):
    """Soma as linhas ja decodificadas, com os indices do layout do membro."""
    agg = defaultdict(float)
    COL_ANO, COL_MES, COL_COMP = c_ano, c_mes, c_comp
    COL_UF, COL_MKT, COL_PROD, COL_QTD = c_uf, c_mkt, c_prod, c_qtd
    N_COLUNAS_MIN = n_min
    r = linhas
    total = descartadas = negativas = 0
    soma_negativa = 0.0
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
        # Quantidades negativas sao estornos/devolucoes que a propria ANP
        # publica: ~185 linhas em 116 meses, somando -11 mil m3 contra 1,3
        # milhao de volume total, distribuidas por todos os anos. Sao dado
        # legitimo e entram na soma; so ficam contadas para o log, porque um
        # SALTO nessa contagem seria sinal de outra coisa.
        if qtd < 0:
            negativas += 1
            soma_negativa += qtd
        agg[(f"{ano}-{mes:02d}", row[COL_COMP], row[COL_UF],
             row[COL_MKT], row[COL_PROD])] += qtd

    if not total:
        raise RuntimeError("CSV da ANP não tem linhas de dados")
    if descartadas > total * TOLERANCIA_DESCARTE:
        raise RuntimeError(
            f"{descartadas}/{total} linhas ({descartadas / total:.1%}) invalidas — "
            f"o layout da ANP provavelmente mudou. Motivos: {dict(motivos)}"
        )
    if descartadas:
        print(f"[update] {descartadas}/{total} linhas descartadas: {dict(motivos)}")
    if negativas:
        print(f"[update] {negativas} linhas com quantidade negativa "
              f"(estornos, {soma_negativa:,.1f} mil m³) — mantidas na soma")
    print(f"[update] {total} linhas lidas, {len(agg)} combinacoes")
    # Rotulos das dimensoes. O cabecalho pode estar limpo e os nomes de
    # agente corrompidos: nenhuma trava de VOLUME pega isso, porque o
    # volume nao muda quando so o rotulo corrompe -- e "RaÃ­zen" ao lado
    # de "Raízen" conta o mesmo agente duas vezes e derruba o HHI.
    leitura.conferir_sem_mojibake(
        {c for _, c, _, _, _ in agg} | {u for _, _, u, _, _ in agg}
        | {k for _, _, _, k, _ in agg} | {p for _, _, _, _, p in agg},
        enc, "dimensoes (agente/UF/mercado/produto)")
    if stats is not None:
        stats.update(linhas=total, descartadas=descartadas,
                     negativas=negativas, combinacoes=len(agg),
                     encoding=enc)
    return agg


def agregar_membros(membros, stats: dict | None = None):
    """Agrega todos os membros de vendas do zip num unico cubo.

    Cada membro e validado isoladamente (encoding, cabecalho ou layout de
    11 colunas, mojibake, linhas invalidas) e depois conferido contra os
    outros: nenhum pode ter buraco interno, e dois nao podem trazer o
    mesmo mes -- somar o mesmo mes duas vezes o DOBRA, e nenhuma trava de
    volume pegaria isso, porque o total so cresce.
    """
    agg = defaultdict(float)
    cobertura, encodings = {}, {}
    acum = {"linhas": 0, "descartadas": 0, "negativas": 0}
    for nome, conteudo in membros:
        print(f"[update] --- {nome} ({len(conteudo) / 1e6:.0f} MB)")
        s: dict = {}
        parcial = agregar(conteudo, s)
        meses = sorted({k[0] for k in parcial})
        mod_membros.conferir_contiguidade(nome, meses)
        print(f"[update]     {meses[0]} a {meses[-1]} ({len(meses)} meses)")
        cobertura[nome] = meses
        encodings[nome] = s.get("encoding")
        for c in acum:
            acum[c] += s.get(c, 0)
        for k, v in parcial.items():
            agg[k] += v
    mod_membros.conferir_sem_sobreposicao(cobertura)
    if stats is not None:
        stats.update(
            **acum,
            combinacoes=len(agg),
            encoding=(next(iter(encodings.values()), None)
                      if len(encodings) == 1 else encodings),
            cobertura={n: [m[0], m[-1]] for n, m in cobertura.items()},
        )
    return agg


def classificar_meses(agg):
    """Devolve os meses da ponta que a ANP ainda nao consolidou.

    So a PONTA da serie e avaliada: a varredura vai do ultimo mes para tras e
    para no primeiro mes fechado. Um colapso real no meio da serie -- greve de
    caminhoneiros, mudanca regulatoria -- e dado de verdade e nao pode ser
    reclassificado como "mes incompleto" por uma heuristica de volume.
    """
    vol = defaultdict(float)
    agentes = defaultdict(set)
    for (ym, comp, _, _, _), q in agg.items():
        vol[ym] += q
        agentes[ym].add(comp)

    meses = sorted(vol)
    parciais = []
    for i in range(len(meses) - 1, 0, -1):
        janela = meses[max(0, i - JANELA_BASE):i]
        if len(janela) < 3:            # historico curto demais para julgar
            break
        vol_base = statistics.median(vol[m] for m in janela)
        ag_base = statistics.median(len(agentes[m]) for m in janela)
        m = meses[i]
        pouco_volume = vol_base > 0 and vol[m] < FATOR_PARCIAL * vol_base
        poucos_agentes = ag_base > 0 and len(agentes[m]) < FATOR_PARCIAL * ag_base
        if not (pouco_volume or poucos_agentes):
            break
        print(f"[update] {m} não consolidado: {vol[m]:,.0f} mil m³ "
              f"({vol[m] / vol_base:.1%} da mediana dos {len(janela)} meses anteriores), "
              f"{len(agentes[m])} agentes contra mediana de {ag_base:.0f}")
        parciais.append(m)

    if len(parciais) > MAX_MESES_PARCIAIS:
        raise RuntimeError(
            f"{len(parciais)} meses seguidos abaixo do limiar ({', '.join(reversed(parciais))}). "
            "Isso não é a ponta em formação — é o arquivo da ANP inteiro suspeito. "
            "data.js NÃO foi alterado."
        )
    return sorted(parciais)


def carregar_anterior():
    """Lê o data.js atual, para comparar antes de sobrescrever."""
    return data_js.carregar(OUT)


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
    # O arquivo anterior pode ter sido gerado antes de o produto entrar na chave.
    # Comparar 5 campos com 6 daria uma "queda" inventada, entao o passo vem do
    # proprio arquivo lido; sem a marca, assume o formato antigo.
    passo_antes = len(data_js.campos_de(anterior))
    passo_agora = len(data_js.campos_de(novo))
    linhas_antes = len(anterior["rows"]) // passo_antes
    linhas_agora = len(novo["rows"]) // passo_agora
    if passo_antes != passo_agora:
        print(f"[update] esquema mudou ({passo_antes} -> {passo_agora} campos por linha); "
              f"comparacao de combinacoes fica so informativa "
              f"({linhas_antes} -> {linhas_agora})")
    elif linhas_agora < linhas_antes * 0.95:
        raise RuntimeError(
            f"regressao: {linhas_agora} combinacoes contra {linhas_antes} no atual "
            f"(queda de {1 - linhas_agora / linhas_antes:.1%}). data.js NAO foi alterado."
        )
    conferir_meses_fechados(novo, anterior)


def conferir_meses_fechados(novo, anterior):
    """Nenhum mes ja consolidado pode encolher nem voltar a ser parcial.

    As checagens de contagem (meses, combinacoes) so enxergam o agregado: a ANP
    pode republicar o arquivo com um mes antigo pela metade e o total continuar
    dentro da tolerancia. Aqui a comparacao e mes a mes, que e onde o estrago
    apareceria primeiro.
    """
    vol_antes = data_js.volume_por_mes(anterior)
    vol_agora = data_js.volume_por_mes(novo)
    idx_agora = {m: i for i, m in enumerate(novo["months"])}
    parciais_agora = set(novo.get("parciais") or [])
    parciais_antes = set(anterior.get("parciais") or [])
    # Num arquivo antigo (sem a marca) nao da para saber se a ultima ponta ja
    # estava incompleta; entao ela fica fora desta comparacao.
    ultimo_antes = anterior["months"][-1] if anterior["months"] else None

    quedas, reabertos = [], []
    for i, mes in enumerate(anterior["months"]):
        if mes in parciais_antes or (not parciais_antes and mes == ultimo_antes):
            continue
        j = idx_agora.get(mes)
        if j is None:
            raise RuntimeError(
                f"regressao: mês {mes} sumiu do arquivo novo. data.js NÃO foi alterado."
            )
        if mes in parciais_agora:
            reabertos.append(mes)
            continue
        antes, agora = vol_antes[i], vol_agora[j]
        if antes > 0 and agora < antes * (1 - QUEDA_MAX_MES_FECHADO):
            quedas.append(f"{mes}: {antes:,.0f} -> {agora:,.0f} ({agora / antes - 1:+.1%})")

    if reabertos:
        raise RuntimeError(
            f"regressao: mês(es) já consolidado(s) voltaram a ficar incompletos "
            f"({', '.join(reabertos)}). Arquivo da ANP suspeito; data.js NÃO foi alterado."
        )
    if quedas:
        raise RuntimeError(
            f"regressao: mês(es) fechado(s) encolheram acima de {QUEDA_MAX_MES_FECHADO:.0%} "
            f"({' | '.join(quedas)}). data.js NÃO foi alterado."
        )


def gerar_data_js(agg, fonte: dict | None = None):
    parciais = classificar_meses(agg)
    months = sorted({k[0] for k in agg})
    comps = sorted({k[1] for k in agg})
    ufs = sorted({k[2] for k in agg})
    mkts = sorted({k[3] for k in agg})
    prods = sorted({k[4] for k in agg})
    mi = {v: i for i, v in enumerate(months)}
    ci = {v: i for i, v in enumerate(comps)}
    ui = {v: i for i, v in enumerate(ufs)}
    ki = {v: i for i, v in enumerate(mkts)}
    pi = {v: i for i, v in enumerate(prods)}
    rows = []
    for (ym, c, u, k, p), q in agg.items():
        qi = round(q * data_js.ESCALA)  # mil m³ com 4 casas, como inteiro
        if qi:
            rows.extend([mi[ym], ci[c], ui[u], ki[k], pi[p], qi])
    completos = [m for m in months if m not in set(parciais)]
    return {"months": months, "comps": comps, "ufs": ufs, "mkts": mkts,
            "prods": prods, "campos": CAMPOS, "rows": rows,
            # Meses que a ANP ainda nao fechou. O dashboard os desenha marcados e
            # os tira de toda media, acumulado e comparacao; o e-mail nao usa
            # nenhum deles como manchete.
            "parciais": parciais,
            "ultimo_completo": completos[-1] if completos else None,
            # Proveniencia: qual arquivo da ANP produziu estes numeros. Sem isso
            # nao da para reproduzir nem auditar uma rodada passada -- e quando
            # um numero do painel for contestado, a pergunta vai ser exatamente
            # essa. Com o hash gravado, o historico do git vira trilha de
            # auditoria: cada commit do data.js diz de que arquivo ele veio.
            "fonte": fonte,
            "updated": datetime.now(UTC).strftime("%Y-%m-%d")}


def escrever_data_js(data):
    data_js.escrever(OUT, data)


def resumir_fonte(membros, stats: dict, herdados=None) -> dict:
    """Identidade dos arquivos da ANP que produziram esta rodada.

    Com varios membros, `sha256` passa a ser o hash dos hashes: continua
    sendo uma chave unica da rodada, e `membros` guarda o detalhe de cada
    arquivo. Quando ha um membro so, `sha256` e `bytes` seguem sendo os
    dele -- a proveniencia das rodadas antigas continua comparavel.
    """
    if isinstance(membros, (bytes, bytearray)):      # compat: um arquivo so
        membros = [(ALVO_CSV, bytes(membros))]
    # 16 hex bastam para identificar a versao do arquivo; o hash inteiro so
    # engordaria o data.js, que ja tem 7 MB.
    detalhe = [{"nome": n, "sha256": hashlib.sha256(b).hexdigest()[:16],
                "bytes": len(b)} for n, b in membros]
    junto = "|".join(d["sha256"] for d in detalhe).encode()
    return {
        "sha256": (detalhe[0]["sha256"] if len(detalhe) == 1
                   else hashlib.sha256(junto).hexdigest()[:16]),
        "bytes": sum(d["bytes"] for d in detalhe),
        "membros": detalhe,
        # Meses que vieram do artefato anterior porque a fonte nao os traz
        # mais. Sem isto, um numero herdado seria indistinguivel de um
        # numero revalidado nesta rodada.
        "herdados": list(herdados or []),
        "baixado_em": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **stats,
    }


def main():
    anterior = carregar_anterior()
    membros = baixar()
    if isinstance(membros, (bytes, bytearray)):   # compat com rodada de 1 arquivo
        membros = [(ALVO_CSV, bytes(membros))]
    total_bytes = sum(len(b) for _, b in membros)
    print(f"[update] download ok ({total_bytes / 1e6:.0f} MB em "
          f"{len(membros)} membro(s))")
    stats: dict = {}
    agg = agregar_membros(membros, stats)
    # Lacuna interior da fonte (hoje: 2017, ausente de todos os membros de
    # vendas do zip). Estreita de proposito — ver scripts/membros.py.
    herdados = mod_membros.herdar_lacunas(agg, anterior)
    if herdados:
        print(f"[update] {len(herdados)} mes(es) HERDADOS do artefato anterior "
              f"(a fonte nao os traz): {', '.join(herdados)}")
    fonte = resumir_fonte(membros, stats, herdados)
    print(f"[update] fonte sha256:{fonte['sha256']} ({fonte['bytes']:,} bytes)")
    data = gerar_data_js(agg, fonte)
    data["herdados"] = herdados
    conferir_contra_anterior(data, anterior)   # levanta antes de escrever
    escrever_data_js(data)

    parciais = set(data["parciais"])
    fechados = {k: v for k, v in agg.items() if k[0] not in parciais}
    total = sum(fechados.values())
    por_produto = defaultdict(float)
    for (_, _, _, _, p), q in fechados.items():
        por_produto[p] += q
    print(f"[update] {len(data['rows']) // len(CAMPOS)} combinações | "
          f"{data['months'][0]} a {data['months'][-1]} | "
          f"último mês fechado: {data['ultimo_completo']} | "
          f"total {total:,.0f} mil m³ (só meses fechados)")
    if parciais:
        print(f"[update] meses marcados como não consolidados: {', '.join(sorted(parciais))} "
              "— excluídos de médias, acumulados e do e-mail")
    for p, q in sorted(por_produto.items(), key=lambda x: -x[1]):
        print(f"[update]   {p}: {q:,.0f} mil m³ ({q / total:.1%})")


if __name__ == "__main__":
    main()
