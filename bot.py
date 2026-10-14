"""
Bot de ofertas de afiliado: Shopee + Mercado Livre -> Telegram + Instagram.

Fluxo: busca ofertas -> gera link de afiliado -> monta legenda -> posta -> registra (sem repetir).

Uso:
    python bot.py            # roda uma vez (ideal para agendar)
    python bot.py --loop     # roda em loop a cada INTERVALO_MINUTOS
    python bot.py --teste    # mostra o que seria postado, sem postar
"""
import csv
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

import requests
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv()                      # .env local (no seu computador)
load_dotenv(BASE / "config.env")   # configurações não secretas (na nuvem)
HIST = BASE / "postados.json"

def env(nome, padrao=""):
    return os.getenv(nome, padrao).strip()

# ---------------------------------------------------------------- Shopee
SHOPEE_URL = "https://open-api.affiliate.shopee.com.br/graphql"

def shopee_gql(query, variables=None):
    app_id, secret = env("SHOPEE_APP_ID"), env("SHOPEE_SECRET")
    payload = json.dumps({"query": query, "variables": variables or {}}, separators=(",", ":"))
    ts = str(int(time.time()))
    assinatura = hashlib.sha256((app_id + ts + payload + secret).encode()).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id}, Timestamp={ts}, Signature={assinatura}",
    }
    r = requests.post(SHOPEE_URL, data=payload, headers=headers, timeout=30)
    r.raise_for_status()
    dados = r.json()
    if dados.get("errors"):
        raise RuntimeError(f"Shopee: {dados['errors']}")
    return dados["data"]

def ofertas_shopee(palavra, limite=10):
    q = """query($k:String,$l:Int){
      productOfferV2(keyword:$k, sortType:2, page:1, limit:$l){
        nodes{ itemId productName priceMin priceMax commissionRate
               imageUrl offerLink ratingStar sales priceDiscountRate }
      }}"""
    nodes = shopee_gql(q, {"k": palavra, "l": limite})["productOfferV2"]["nodes"]
    ofertas = []
    for n in nodes:
        ofertas.append({
            "id": f"shopee-{n['itemId']}",
            "loja": "Shopee",
            "titulo": n["productName"],
            "preco": float(n["priceMin"]),
            "desconto": n.get("priceDiscountRate") or 0,
            "imagem": n["imageUrl"],
            "link": n["offerLink"],
            "vendas": n.get("sales") or 0,
            "nota": n.get("ratingStar"),
        })
    return ofertas

# ---------------------------------------------------------------- Mercado Livre
def link_ml(url):
    """Adiciona os parâmetros da sua tag de afiliado (matt_word / matt_tool)."""
    partes = urlparse(url)
    qs = dict(parse_qsl(partes.query))
    qs["matt_word"] = env("ML_MATT_WORD")
    qs["matt_tool"] = env("ML_MATT_TOOL")
    return urlunparse(partes._replace(query=urlencode(qs)))

def ofertas_ml_api(palavra, limite=10):
    """Busca pela API do ML. Exige ML_ACCESS_TOKEN (a busca pública pode ser bloqueada sem token)."""
    token = env("ML_ACCESS_TOKEN")
    if not token:
        return []
    r = requests.get(
        "https://api.mercadolibre.com/sites/MLB/search",
        params={"q": palavra, "limit": limite, "condition": "new"},
        headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code != 200:
        print(f"[ML] API respondeu {r.status_code} — usando só o ml_ofertas.csv")
        return []
    ofertas = []
    for it in r.json().get("results", []):
        original = it.get("original_price") or it["price"]
        ofertas.append({
            "id": f"ml-{it['id']}",
            "loja": "Mercado Livre",
            "titulo": it["title"],
            "preco": float(it["price"]),
            "desconto": round(100 * (1 - it["price"] / original)) if original else 0,
            "imagem": (it.get("thumbnail") or "").replace("-I.jpg", "-O.jpg"),
            "link": link_ml(it["permalink"]),
            "vendas": 0, "nota": None,
        })
    return ofertas

def ofertas_ml_csv():
    """Ofertas que você colou manualmente (link já gerado no painel de afiliados)."""
    arq = BASE / "ml_ofertas.csv"
    if not arq.exists():
        return []
    ofertas = []
    with open(arq, encoding="utf-8") as f:
        for l in csv.DictReader(f):
            if not l.get("link"):
                continue
            ofertas.append({
                "id": "ml-" + hashlib.md5(l["link"].encode()).hexdigest()[:10],
                "loja": "Mercado Livre",
                "titulo": l["titulo"], "preco": float(l["preco"].replace(",", ".")),
                "desconto": int(l.get("desconto") or 0),
                "imagem": l["imagem"], "link": l["link"], "vendas": 0, "nota": None,
            })
    return ofertas

# ---------------------------------------------------------------- Legendas
def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def legenda_telegram(o):
    linhas = [f"🔥 <b>{o['titulo'][:120]}</b>", ""]
    if o["desconto"]:
        linhas.append(f"🏷️ {o['desconto']}% OFF")
    linhas.append(f"💰 <b>{brl(o['preco'])}</b>")
    if o["nota"]:
        linhas.append(f"⭐ {float(o['nota']):.1f}  |  {o['vendas']} vendidos")
    linhas += ["", f"🛒 {o['loja']}: {o['link']}", "", "<i>Preço sujeito a alteração.</i>"]
    return "\n".join(linhas)

def legenda_instagram(o):
    # No feed o link não é clicável: o seguidor comenta e recebe o link no direct,
    # ou pega pelo número na vitrine do link da bio.
    palavra = env("PALAVRA_COMENTARIO", "QUERO")
    tags = env("INSTAGRAM_HASHTAGS", "#achadinhos #promocao #oferta")
    desc = f"🏷️ {o['desconto']}% OFF\n" if o["desconto"] else ""
    artigo = 'na' if o['loja'] == 'Shopee' else 'no'
    return (f"🔥 {o['titulo'][:150]}\n\n{desc}💰 {brl(o['preco'])} {artigo} {o['loja']}\n\n"
            f"💬 Comente {palavra} que eu te mando o link no direct!\n"
            f"🔗 Ou procure o nº {o.get('numero', '')} no link da bio.\n\n"
            f"Link de afiliado. Preço sujeito a alteração.\n\n{tags}")

# ---------------------------------------------------------------- Imagens
# Fotos enviadas pelo Telegram ficam guardadas como "tg:<file_id>".
def imagem_bytes(o):
    img = o["imagem"]
    if img.startswith("tg:"):
        token = env("TELEGRAM_BOT_TOKEN")
        info = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                            params={"file_id": img[3:]}, timeout=30).json()["result"]
        return requests.get(f"https://api.telegram.org/file/bot{token}/{info['file_path']}", timeout=60).content
    return requests.get(img, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).content

def imagem_publica(o):
    """URL pública da foto (o Instagram exige). Fotos do Telegram sobem para o imgbb."""
    if o.get("imagem_url"):
        return o["imagem_url"]
    if not o["imagem"].startswith("tg:"):
        return o["imagem"]
    chave = env("IMGBB_API_KEY")
    if not chave:
        raise RuntimeError("para postar fotos do Telegram no Instagram, cadastre IMGBB_API_KEY")
    import base64
    r = requests.post("https://api.imgbb.com/1/upload", data={
        "key": chave, "image": base64.b64encode(imagem_bytes(o))}, timeout=60)
    r.raise_for_status()
    o["imagem_url"] = r.json()["data"]["url"]
    return o["imagem_url"]

# ---------------------------------------------------------------- Postagem
def postar_telegram(o):
    token = env("TELEGRAM_BOT_TOKEN")
    chat = carregar_json(BASE / "canal.json", {}).get("id") or env("TELEGRAM_CHAT_ID")
    foto = o["imagem"][3:] if o["imagem"].startswith("tg:") else o["imagem"]
    r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={
        "chat_id": chat, "photo": foto,
        "caption": legenda_telegram(o), "parse_mode": "HTML"}, timeout=30)
    r.raise_for_status()

def postar_instagram(o):
    ig, token = env("IG_USER_ID"), env("IG_ACCESS_TOKEN")
    api = f"https://{env('GRAPH_HOST', 'graph.instagram.com')}/{env('GRAPH_VERSION', 'v21.0')}/{ig}"
    r = requests.post(f"{api}/media", data={
        "image_url": imagem_publica(o), "caption": legenda_instagram(o), "access_token": token}, timeout=60)
    r.raise_for_status()
    criacao = r.json()["id"]
    for _ in range(10):  # espera o Instagram processar a imagem
        s = requests.get(f"https://{env('GRAPH_HOST', 'graph.instagram.com')}/{env('GRAPH_VERSION', 'v21.0')}/{criacao}",
                         params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        time.sleep(5)
    r = requests.post(f"{api}/media_publish", data={"creation_id": criacao, "access_token": token}, timeout=60)
    r.raise_for_status()
    return r.json().get("id")  # id do post, usado para responder comentários

# ---------------------------------------------------------------- Comente e receba o link
OFERTAS = BASE / "ofertas.json"
RESPONDIDOS = BASE / "comentarios_respondidos.json"

def carregar_json(arq, padrao):
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        return padrao

def salvar_json(arq, dados):
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

def responder_comentarios():
    """Lê comentários dos posts recentes e manda o link no direct (resposta privada)."""
    token, versao = env("IG_ACCESS_TOKEN"), env("GRAPH_VERSION", "v21.0")
    host = env("GRAPH_HOST", "graph.instagram.com")
    remetente = env("IG_MENSAGENS_ID") or env("IG_USER_ID")
    palavra = env("PALAVRA_COMENTARIO", "QUERO").lower()
    ofertas = [o for o in carregar_json(OFERTAS, []) if o.get("ig_media_id")][-30:]
    feitos = set(carregar_json(RESPONDIDOS, []))
    enviados = 0
    for o in ofertas:
        r = requests.get(f"https://{host}/{versao}/{o['ig_media_id']}/comments",
                         params={"fields": "id,text", "access_token": token}, timeout=30)
        if r.status_code != 200:
            print(f"[Comentários] erro {r.status_code} no post {o['ig_media_id']}")
            continue
        for c in r.json().get("data", []):
            if c["id"] in feitos:
                continue
            feitos.add(c["id"])
            if palavra and palavra not in c.get("text", "").lower():
                continue
            texto = (f"Oi! 😊 Aqui está o link de {o['titulo'][:80]} "
                     f"por {brl(o['preco'])}:\n{o['link']}\n\nPreço sujeito a alteração.")
            m = requests.post(f"https://{host}/{versao}/{remetente}/messages", json={
                "recipient": {"comment_id": c["id"]},
                "message": {"text": texto}}, params={"access_token": token}, timeout=30)
            if m.status_code == 200:
                enviados += 1
                if env("RESPONDER_NO_POST", "sim") == "sim":
                    requests.post(f"https://{host}/{versao}/{c['id']}/replies",
                                  data={"message": "Te mandei no direct! 📩", "access_token": token},
                                  timeout=30)
            else:
                print(f"[Direct] falhou ({m.status_code}): {m.text[:200]}")
            time.sleep(3)
    salvar_json(RESPONDIDOS, sorted(feitos))
    print(f"Comentários verificados. Links enviados no direct: {enviados}")

def responder_directs():
    """Responde quem mandou mensagem/respondeu a Story: com um número envia aquela oferta,
    com a palavra-chave envia a oferta da última Story."""
    import re
    token, versao = env("IG_ACCESS_TOKEN"), env("GRAPH_VERSION", "v21.0")
    host = env("GRAPH_HOST", "graph.instagram.com")
    conta = env("IG_MENSAGENS_ID") or env("IG_USER_ID")
    palavra = env("PALAVRA_COMENTARIO", "QUERO").lower()
    ofertas = carregar_json(OFERTAS, [])
    if not ofertas:
        return
    por_numero = {str(o["numero"]): o for o in ofertas}
    ultima_story = next((o for o in reversed(ofertas) if o.get("story")), ofertas[-1])
    feitos = set(carregar_json(RESPONDIDOS, []))
    r = requests.get(f"https://{host}/{versao}/{conta}/conversations", params={
        "platform": "instagram", "fields": "messages.limit(5){id,message,from}",
        "access_token": token}, timeout=30)
    if r.status_code != 200:
        print(f"[Direct] não consegui ler as conversas ({r.status_code}): {r.text[:200]}")
        return
    enviados = 0
    for conv in r.json().get("data", []):
        for msg in conv.get("messages", {}).get("data", []):
            if msg["id"] in feitos or msg.get("from", {}).get("id") == conta:
                continue
            feitos.add(msg["id"])
            texto = (msg.get("message") or "").lower()
            achou = re.search(r"\d+", texto)
            o = por_numero.get(achou.group()) if achou else None
            if not o and palavra in texto:
                o = ultima_story
            if not o:
                continue
            requests.post(f"https://{host}/{versao}/{conta}/messages", json={
                "recipient": {"id": msg["from"]["id"]},
                "message": {"text": f"Aqui está 😊 {o['titulo'][:80]} por {brl(o['preco'])}:\n{o['link']}"}},
                params={"access_token": token}, timeout=30)
            enviados += 1
            time.sleep(2)
    salvar_json(RESPONDIDOS, sorted(feitos))
    print(f"Directs verificados. Links enviados: {enviados}")

def story_para_postar_manual(o, caminho_arte):
    """Manda a arte + link para o SEU Telegram, para postar a Story com link sticker no app."""
    token, admin = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_ADMIN_CHAT_ID")
    with open(caminho_arte, "rb") as f:
        requests.post(f"https://api.telegram.org/bot{token}/sendDocument", data={
            "chat_id": admin,
            "caption": f"📲 Story pronta (nº {o['numero']})\n\nCopie o link para o sticker:\n{o['link']}"},
            files={"document": (f"story_{o['numero']}.jpg", f, "image/jpeg")}, timeout=60).raise_for_status()

# ---------------------------------------------------------------- Vitrine (link da bio)
def gerar_vitrine():
    """Gera vitrine/index.html com as ofertas numeradas e botão de compra."""
    from html import escape
    ofertas = list(reversed(carregar_json(OFERTAS, [])))[: int(env("VITRINE_MAX", "60"))]
    nome = escape(env("VITRINE_TITULO", "Achadinhos"))
    cards = "\n".join(f"""
  <a class="card" href="{escape(o['link'])}" target="_blank" rel="nofollow sponsored noopener">
    <span class="num">nº {o['numero']}</span>
    {f'<img src="{escape(o["imagem"])}" alt="" loading="lazy">' if o.get('imagem') else ''}
    <span class="t">{escape(o['titulo'][:90])}</span>
    <span class="p">{brl(o['preco'])}{f' <s>-{o["desconto"]}%</s>' if o['desconto'] else ''}</span>
    <span class="b">Comprar {'na' if o['loja'] == 'Shopee' else 'no'} {escape(o['loja'])}</span>
  </a>""" for o in ofertas)
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{nome}</title>
<style>
body{{margin:0;font-family:system-ui,sans-serif;background:#f4f4f6;color:#111}}
header{{padding:20px 16px 8px;text-align:center}}h1{{margin:0;font-size:22px}}
input{{width:100%;box-sizing:border-box;padding:12px;border-radius:12px;border:1px solid #ccc;font-size:16px;margin-top:12px}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;padding:12px 16px 40px;max-width:900px;margin:auto}}
.card{{background:#fff;border-radius:14px;padding:10px;text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:6px;position:relative;box-shadow:0 1px 3px #0001}}
.card img{{width:100%;aspect-ratio:1;object-fit:contain}}
.num{{position:absolute;top:8px;left:8px;background:#111;color:#fff;font-size:12px;padding:3px 8px;border-radius:99px}}
.t{{font-size:13px;line-height:1.3}}.p{{font-weight:700;font-size:17px}}.p s{{color:#0a7f3f;text-decoration:none;font-size:13px}}
.b{{background:#EE4D2D;color:#fff;text-align:center;padding:8px;border-radius:10px;font-size:13px;font-weight:600;margin-top:auto}}
footer{{text-align:center;font-size:12px;color:#666;padding-bottom:24px}}
</style></head><body>
<header><h1>{nome}</h1><input id="q" placeholder="Digite o número ou nome do produto" inputmode="search"></header>
<main id="lista">{cards}
</main>
<footer>Links de afiliado. Preços sujeitos a alteração.</footer>
<script>
document.getElementById('q').addEventListener('input',e=>{{const v=e.target.value.toLowerCase().replace('nº','').trim();
document.querySelectorAll('.card').forEach(c=>{{c.style.display=c.textContent.toLowerCase().includes(v)?'':'none'}})}});
</script></body></html>"""
    pasta = BASE / "vitrine"
    pasta.mkdir(exist_ok=True)
    (pasta / "index.html").write_text(html, encoding="utf-8")
    return pasta / "index.html"

# ---------------------------------------------------------------- Stories
def _fonte(tamanho, negrito=True):
    from PIL import ImageFont
    nomes = (["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"] if negrito
             else ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf"])
    for n in nomes:
        try:
            return ImageFont.truetype(n, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()

def _quebrar(draw, texto, fonte, largura, max_linhas=3):
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if draw.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] = linhas[-1].rstrip(".,") + "…"
    return linhas

def arte_story(o, foto_bytes=None):
    """Monta uma arte 1080x1920 para Stories e devolve o caminho do JPG."""
    from io import BytesIO
    from PIL import Image, ImageDraw
    W, H = 1080, 1920
    cor = env("STORY_COR", "#EE4D2D" if o["loja"] == "Shopee" else "#2D3277")
    img = Image.new("RGB", (W, H), cor)
    d = ImageDraw.Draw(img)

    # cartão branco com a foto do produto
    d.rounded_rectangle((80, 300, W - 80, 1200), radius=48, fill="white")
    dados_foto = imagem_bytes(o) if foto_bytes is None else foto_bytes
    foto = Image.open(BytesIO(dados_foto)).convert("RGB")
    foto.thumbnail((820, 820))
    img.paste(foto, ((W - foto.width) // 2, 340 + (820 - foto.height) // 2))

    # topo
    d.text((W // 2, 230), f"ACHADINHO {o['loja'].upper()}", font=_fonte(64), fill="white", anchor="mm")

    # selo de desconto
    if o["desconto"]:
        d.ellipse((W - 330, 250, W - 60, 520), fill="#FFD400")
        d.text((W - 195, 360), f"{o['desconto']}%", font=_fonte(84), fill="#111", anchor="mm")
        d.text((W - 195, 435), "OFF", font=_fonte(48), fill="#111", anchor="mm")

    # título e preço
    y = 1275
    for linha in _quebrar(d, o["titulo"], _fonte(52, False), W - 160):
        d.text((W // 2, y), linha, font=_fonte(52, False), fill="white", anchor="mm")
        y += 66
    d.text((W // 2, y + 90), brl(o["preco"]), font=_fonte(130), fill="white", anchor="mm")

    # chamada (o link sticker não é aceito pela API, então a chamada leva ao Telegram/bio)
    padrao = ("Toque no link acima ↑" if env("STORY_MODO", "automatico") == "manual"
              else f"Responda {env('PALAVRA_COMENTARIO', 'QUERO')} e receba o link")
    chamada = env("STORY_CHAMADA", padrao).replace("{numero}", str(o.get("numero", "")))
    d.rounded_rectangle((120, 1700, W - 120, 1820), radius=60, fill="white")
    d.text((W // 2, 1760), chamada, font=_fonte(40), fill=cor, anchor="mm")

    caminho = BASE / "stories" / f"{o['id']}.jpg"
    caminho.parent.mkdir(exist_ok=True)
    img.save(caminho, "JPEG", quality=90)
    return caminho

def hospedar_imagem(caminho):
    """O Instagram exige uma URL pública. Usa o imgbb (grátis) se IMGBB_API_KEY estiver no .env."""
    chave = env("IMGBB_API_KEY")
    if not chave:
        return None
    import base64
    r = requests.post("https://api.imgbb.com/1/upload",
                      data={"key": chave, "image": base64.b64encode(caminho.read_bytes()),
                            "expiration": 86400}, timeout=60)
    r.raise_for_status()
    return r.json()["data"]["url"]

def postar_story(o):
    ig, token = env("IG_USER_ID"), env("IG_ACCESS_TOKEN")
    versao = env("GRAPH_VERSION", "v21.0")
    url_img = None
    try:
        url_img = hospedar_imagem(arte_story(o))
    except Exception as e:
        print(f"[Story] não deu para montar a arte ({e}); usando a foto do produto")
    url_img = url_img or imagem_publica(o)
    r = requests.post(f"https://{env('GRAPH_HOST', 'graph.instagram.com')}/{versao}/{ig}/media", data={
        "image_url": url_img, "media_type": "STORIES", "access_token": token}, timeout=60)
    r.raise_for_status()
    criacao = r.json()["id"]
    for _ in range(10):
        s = requests.get(f"https://{env('GRAPH_HOST', 'graph.instagram.com')}/{versao}/{criacao}",
                         params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        time.sleep(5)
    r = requests.post(f"https://{env('GRAPH_HOST', 'graph.instagram.com')}/{versao}/{ig}/media_publish",
                      data={"creation_id": criacao, "access_token": token}, timeout=60)
    r.raise_for_status()

# ---------------------------------------------------------------- Fila pelo Telegram
# Você manda para o SEU bot (no privado): foto + legenda com nome, preço e link de afiliado.
# Ex.: "Fone Bluetooth R$ 89,90 -35% https://s.shopee.com.br/abc"
FILA = BASE / "fila.json"
FILA_OFFSET = BASE / "fila_offset.json"

def _tg(metodo, **dados):
    token = env("TELEGRAM_BOT_TOKEN")
    return requests.post(f"https://api.telegram.org/bot{token}/{metodo}", data=dados, timeout=30).json()

def _ler_oferta(texto):
    import re
    links = re.findall(r"https?://\S+", texto)
    if not links:
        return None, "Não achei o link. Mande a foto com legenda: nome, R$ preço e o link de afiliado."
    link = links[-1].rstrip(").,")
    preco = re.search(r"R\$\s*([\d.]*\d(?:,\d{1,2})?)", texto)
    if not preco:
        return None, "Não achei o preço. Escreva assim: R$ 89,90"
    valor = float(preco.group(1).replace(".", "").replace(",", "."))
    desc = re.search(r"(\d{1,2})\s*%", texto)
    remover = links + [preco.group(0)] + ([desc.group(0)] if desc else [])
    titulo = texto
    for trecho in remover:
        titulo = titulo.replace(trecho, " ")
    for lixo in [r"(?i)confira\s+", r"(?i)com\s+de\s+desconto!?", r"(?i)somente\s*\.?",
                 r"(?i)encontre na shopee agora!?", r"(?i)por apenas", r"(?i)no mercado livre!?",
                 r"(?i)na shopee!?", r"(?i)\bOFF\b"]:
        titulo = re.sub(lixo, " ", titulo)
    titulo = re.sub(r"\s+", " ", titulo.replace(" - ", " ")).strip(" -|:!.")
    titulo = re.sub(r"(?i)\s+(por|de|com|a partir de)$", "", titulo).strip() or "Oferta imperdível"
    l = link.lower()
    loja = ("Shopee" if "shopee" in l or "shp.ee" in l else
            "Mercado Livre" if "mercadoli" in l or "meli.la" in l or "mlb" in l else "Loja")
    return {"id": "fila-" + hashlib.md5(link.encode()).hexdigest()[:10], "loja": loja,
            "titulo": titulo[:150], "preco": valor, "desconto": int(desc.group(1)) if desc else 0,
            "link": link, "vendas": 0, "nota": None, "manual": True}, None

def _info_canal():
    alvo = carregar_json(BASE / "canal.json", {}).get("id") or env("TELEGRAM_CHAT_ID")
    r = _tg("getChat", chat_id=alvo)
    if not r.get("ok"):
        return {"erro": r.get("description")}
    c = r["result"]
    eu = (_tg("getMe").get("result") or {}).get("id")
    m = _tg("getChatMember", chat_id=alvo, user_id=eu)
    return {"titulo": c.get("title"), "usuario": c.get("username"), "tipo": c.get("type"),
            "bot_no_canal": (m.get("result") or {}).get("status") or m.get("description")}

def receber_fila():
    """Lê as mensagens novas do seu bot e coloca as ofertas na fila."""
    if not env("TELEGRAM_BOT_TOKEN"):
        return
    admin = env("TELEGRAM_ADMIN_CHAT_ID")
    if not admin.lstrip("-").isdigit():
        admin = ""  # valor inválido (ex.: colaram o token): volta a informar o ID
    offset = carregar_json(FILA_OFFSET, {"offset": 0})["offset"]
    resp = _tg("getUpdates", offset=offset, timeout=0, allowed_updates='["message","my_chat_member","channel_post"]')
    # diagnóstico salvo no repositório (sem o token), para saber se o Telegram respondeu
    salvar_json(BASE / "status_telegram.json", {
        "quando": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "ok": resp.get("ok"), "erro": resp.get("description"),
        "mensagens_novas": len(resp.get("result", []) or []),
        "admin_cadastrado": bool(admin),
        "bot": (_tg("getMe").get("result") or {}).get("username"),
        "canal_configurado": _info_canal()})
    if not resp.get("ok"):
        print(f"[Telegram] erro: {resp.get('description')}")
    fila = carregar_json(FILA, [])
    for up in resp.get("result", []):
        offset = up["update_id"] + 1
        # o bot foi adicionado/removido de um canal: guarda o canal automaticamente
        mcm = up.get("my_chat_member")
        if mcm and mcm["chat"]["type"] == "channel":
            status = mcm["new_chat_member"]["status"]
            nome = mcm["chat"].get("title")
            if status == "administrator":
                salvar_json(BASE / "canal.json", {"id": mcm["chat"]["id"], "titulo": nome})
                if admin:
                    _tg("sendMessage", chat_id=admin, text=f"✅ Conectado ao canal \"{nome}\". As ofertas vão ser postadas lá!")
            elif admin:
                _tg("sendMessage", chat_id=admin, text=f"⚠️ Não sou mais administrador do canal \"{nome}\".")
            continue
        post = up.get("channel_post")
        if post and not carregar_json(BASE / "canal.json", {}).get("id"):
            salvar_json(BASE / "canal.json", {"id": post["chat"]["id"], "titulo": post["chat"].get("title")})
            continue
        msg = up.get("message")
        if not msg or msg["chat"]["type"] != "private":
            continue
        chat = str(msg["chat"]["id"])
        if not admin:
            _tg("sendMessage", chat_id=chat, text=(
                f"Seu ID é {chat}\n\nCadastre no GitHub o secret TELEGRAM_ADMIN_CHAT_ID com esse "
                "número. Depois disso é só me mandar as ofertas aqui."))
            continue
        if chat != admin:
            continue  # só você pode mandar ofertas
        texto = (msg.get("caption") or msg.get("text") or "").strip()
        if texto in ("/fila", "/start"):
            _tg("sendMessage", chat_id=chat, text=f"📦 {len(fila)} oferta(s) na fila.\n\nPara adicionar: "
                "mande a foto do produto com legenda: nome, R$ preço, % de desconto (opcional) e o link.")
            continue
        if texto == "/limpar":
            fila = []
            _tg("sendMessage", chat_id=chat, text="🗑️ Fila esvaziada.")
            continue
        oferta, erro = _ler_oferta(texto)
        if erro:
            _tg("sendMessage", chat_id=chat, text=f"⚠️ {erro}")
            continue
        if msg.get("photo"):
            oferta["imagem"] = "tg:" + msg["photo"][-1]["file_id"]
        elif msg.get("document", {}).get("mime_type", "").startswith("image/"):
            oferta["imagem"] = "tg:" + msg["document"]["file_id"]
        else:
            _tg("sendMessage", chat_id=chat, text="⚠️ Faltou a foto. Mande a foto do produto com o texto na legenda.")
            continue
        if any(f["id"] == oferta["id"] for f in fila):
            _tg("sendMessage", chat_id=chat, text="Essa oferta já está na fila 👍")
            continue
        fila.append(oferta)
        _tg("sendMessage", chat_id=chat, text=(
            f"✅ Na fila: {oferta['titulo'][:60]} — {brl(oferta['preco'])} ({oferta['loja']})\n"
            f"📦 {len(fila)} oferta(s) aguardando. Será postada no próximo horário."))
    salvar_json(FILA, fila)
    salvar_json(FILA_OFFSET, {"offset": offset})
    # ainda não conectado a um canal? manda para você um botão que adiciona o bot certo
    aviso = BASE / "aviso_canal.json"
    if admin and not carregar_json(BASE / "canal.json", {}).get("id") and not aviso.exists():
        info = _info_canal()
        if not str(info.get("bot_no_canal", "")).startswith(("administrator", "creator")):
            eu = (_tg("getMe").get("result") or {}).get("username")
            res = _tg("sendMessage", chat_id=admin,
                text="📢 Falta só me colocar no seu canal. Toque no botão abaixo, escolha o seu canal e confirme \"Adicionar como administrador\".",
                reply_markup=json.dumps({"inline_keyboard": [[{
                    "text": "➕ Adicionar ao meu canal",
                    "url": f"https://t.me/{eu}?startchannel&admin=post_messages"}]]}))
            salvar_json(aviso, {"enviado": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                                "ok": res.get("ok"), "erro": res.get("description"),
                                "admin_digitos": len(admin)})

# ---------------------------------------------------------------- Execução
def carregar_hist():
    try:
        return set(json.loads(HIST.read_text()))
    except Exception:
        return set()

def coletar():
    palavras = [p.strip() for p in env("PALAVRAS_CHAVE", "fone bluetooth").split(",") if p.strip()]
    palavra = random.choice(palavras)
    print(f"Buscando: {palavra}")
    ofertas = []
    if env("SHOPEE_APP_ID"):
        try:
            ofertas += ofertas_shopee(palavra)
        except Exception as e:
            print(f"[Shopee] erro: {e}")
    if env("ML_MATT_WORD"):
        ofertas += ofertas_ml_api(palavra)
    ofertas += ofertas_ml_csv()
    desc_min = int(env("DESCONTO_MINIMO", "0"))
    return [o for o in ofertas if o["desconto"] >= desc_min and o["imagem"]]

def rodar(teste=False):
    hist = carregar_hist()
    if not teste:
        try:
            receber_fila()
        except Exception as e:
            print(f"[Fila] erro: {e}")
    fila = [o for o in carregar_json(FILA, []) if o["id"] not in hist]
    qtd = int(env("POSTS_POR_RODADA", "3"))
    # primeiro o que você mandou pelo Telegram (na ordem), depois as buscas automáticas
    lote = fila[:qtd]
    if len(lote) < qtd and (env("SHOPEE_APP_ID") or env("ML_ACCESS_TOKEN") or (BASE / "ml_ofertas.csv").exists()):
        novas = [o for o in coletar() if o["id"] not in hist]
        novas.sort(key=lambda o: (o["desconto"], o["vendas"]), reverse=True)
        lote += novas[: qtd - len(lote)]
    if not lote:
        print("Nenhuma oferta nova.")
    registro = carregar_json(OFERTAS, [])
    proximo = max([r["numero"] for r in registro] or [0]) + 1
    modo_story = env("STORY_MODO", "automatico")  # automatico | manual | nao
    for o in lote:
        o["numero"] = proximo
        if teste:
            print("\n--- TELEGRAM ---\n" + legenda_telegram(o))
            print("\n--- INSTAGRAM ---\n" + legenda_instagram(o))
            try:
                print(f"\n--- STORY --- arte salva em {arte_story(o)}")
            except Exception as e:
                print(f"\n--- STORY --- não deu para montar a arte: {e}")
            proximo += 1
            continue
        try:
            if env("TELEGRAM_BOT_TOKEN"):
                postar_telegram(o)
            if env("IG_ACCESS_TOKEN") and env("IG_FEED", "sim") == "sim":
                o["ig_media_id"] = postar_instagram(o)
            if modo_story == "automatico" and env("IG_ACCESS_TOKEN"):
                postar_story(o)
                o["story"] = True
            elif modo_story == "manual" and env("TELEGRAM_ADMIN_CHAT_ID"):
                story_para_postar_manual(o, arte_story(o))
                o["story"] = True
            hist.add(o["id"])
            HIST.write_text(json.dumps(sorted(hist)))
            salvo = {k: o.get(k) for k in ("numero", "id", "loja", "titulo", "preco", "desconto",
                                             "link", "ig_media_id", "story")}
            # a vitrine precisa de uma imagem pública
            salvo["imagem"] = o.get("imagem_url") or ("" if o["imagem"].startswith("tg:") else o["imagem"])
            if not salvo["imagem"] and env("IMGBB_API_KEY"):
                try:
                    salvo["imagem"] = imagem_publica(o)
                except Exception:
                    pass
            registro.append(salvo)
            salvar_json(OFERTAS, registro)
            salvar_json(FILA, [f for f in carregar_json(FILA, []) if f["id"] != o["id"]])
            proximo += 1
            print(f"Postado nº {o['numero']}: {o['titulo'][:60]}")
            time.sleep(20)  # espaço entre posts, evita parecer spam
        except Exception as e:
            detalhe = str(e)
            if hasattr(e, "response") and e.response is not None:
                detalhe += " | " + e.response.text[:300]
            detalhe = detalhe.replace(env("TELEGRAM_BOT_TOKEN") or "§", "***")
            print(f"Erro ao postar {o['id']}: {detalhe}")
            salvar_json(BASE / "status_postagem.json", {
                "quando": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "oferta": o["titulo"][:60], "erro": detalhe})
    if not teste and registro:
        print(f"Vitrine atualizada: {gerar_vitrine()}")

def status_instagram():
    """Confere se o token do Instagram funciona e salva o resultado (sem o token)."""
    host, versao = env("GRAPH_HOST", "graph.instagram.com"), env("GRAPH_VERSION", "v21.0")
    r = requests.get(f"https://{host}/{versao}/me", params={
        "fields": "user_id,username,account_type", "access_token": env("IG_ACCESS_TOKEN")}, timeout=30)
    d = r.json()
    salvar_json(BASE / "status_instagram.json", {
        "quando": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "ok": r.status_code == 200, "usuario": d.get("username"), "tipo": d.get("account_type"),
        "id_api": d.get("user_id") or d.get("id"),
        "id_cadastrado_confere": str(d.get("user_id") or d.get("id")) == env("IG_USER_ID"),
        "erro": (d.get("error") or {}).get("message")})

def atender_instagram():
    if not env("IG_ACCESS_TOKEN"):
        return
    try:
        status_instagram()
    except Exception as e:
        print(f"[Instagram] erro no teste: {e}")
    for f in (responder_comentarios, responder_directs):
        try:
            f()
        except Exception as e:
            print(f"[{f.__name__}] erro: {e}")

if __name__ == "__main__":
    if "--loop" in sys.argv:
        # posta a cada INTERVALO_MINUTOS e responde comentários/directs a cada 5 min
        ultimo_post = 0
        while True:
            if time.time() - ultimo_post >= 60 * int(env("INTERVALO_MINUTOS", "60")):
                rodar()
                ultimo_post = time.time()
            atender_instagram()
            time.sleep(300)
    elif "--responder" in sys.argv:
        try:
            receber_fila()
        except Exception as e:
            print(f"[Fila] erro: {e}")
        atender_instagram()
    elif "--vitrine" in sys.argv:
        print(gerar_vitrine())
    else:
        rodar(teste="--teste" in sys.argv)
