# Bot de ofertas — Shopee + Mercado Livre → Telegram + Instagram

## Instalação
```
pip install -r requirements.txt
cp .env.example .env     # preencha suas chaves
python bot.py --teste    # confere as legendas sem postar
python bot.py            # posta uma rodada
python bot.py --loop     # posta a cada INTERVALO_MINUTOS e responde comentários/directs a cada 5 min
python bot.py --responder  # só responde comentários e directs
python bot.py --vitrine    # só regera a página da bio
```

## Configurando cada parte

**Shopee** — no painel affiliate.shopee.com.br, abra a seção Open API e copie App ID e Secret.
Se a Open API não aparecer, sua conta ainda não tem acesso (vem com níveis mais altos).

**Mercado Livre** — gere um link qualquer no painel de afiliados e copie os valores de
`matt_word` e `matt_tool` para o .env. Sem token da API do ML, cole as ofertas no
`ml_ofertas.csv` (título, preço, desconto, URL da imagem, link de afiliado).

**Telegram** — crie o bot no @BotFather, adicione-o como administrador do seu canal e
coloque `@seucanal` em TELEGRAM_CHAT_ID.

**Instagram** — precisa de conta Profissional (Criador ou Empresa) ligada a uma Página do
Facebook e um app em developers.facebook.com com a permissão `instagram_content_publish`.
Pegue o IG_USER_ID e um token de longa duração. Permissões: `instagram_content_publish`,
`instagram_manage_comments` e `instagram_manage_messages` (e `pages_messaging` no Login do Facebook).

## Link clicável no Instagram
O Instagram não deixa link clicável na legenda, e a API não aceita link sticker na Story. Então:

1. **Comente QUERO → link no direct.** O bot lê os comentários dos posts e manda o link de
   afiliado por mensagem privada (e responde "Te mandei no direct!" no post).
2. **Story respondida → link no direct.** Quem responde a Story com QUERO recebe o link da
   última Story; quem manda um número (ex.: "12") recebe a oferta nº 12.
3. **Vitrine na bio.** Cada oferta ganha um número. `vitrine/index.html` lista todas com botão
   de compra e busca por número. Publique de graça no GitHub Pages ou Netlify e coloque o
   endereço na bio.
4. **Story com link sticker (manual).** Com `STORY_MODO=manual`, o bot manda para o seu
   Telegram a arte pronta + o link. No app: postar a imagem → sticker "Link" → colar.

**Story automática:** a arte (1080x1920, com foto, preço e desconto) precisa de uma URL pública;
crie uma chave grátis no imgbb e coloque em IMGBB_API_KEY. Sem ela, vai a foto simples do produto.

## Rodar sozinho
- **PC/servidor Linux:** `crontab -e` → `0 9-22 * * * cd /caminho/afiliados-bot && python bot.py`
- **Grátis na nuvem:** GitHub Actions agendado ou um VPS pequeno.

## Boas práticas
- Não compre pelo próprio link e não poste em excesso (antifraude dos dois programas).
- Deixe "preço sujeito a alteração" e identifique que é link de afiliado.
- O arquivo `postados.json` evita repetir a mesma oferta; `ofertas.json` guarda os números.
- O direct só pode ser enviado uma vez por comentário e em até 7 dias; respostas de story,
  em até 24h. O `--loop` já verifica a cada 5 minutos.
