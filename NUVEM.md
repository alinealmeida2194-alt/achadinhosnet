# Rodar na nuvem de graça (GitHub)

O bot roda sozinho no GitHub Actions: posta de hora em hora (9h–22h) e responde
comentários/directs a cada 10 minutos. A vitrine da bio fica no GitHub Pages.

## 1. Criar o repositório
1. Crie uma conta em github.com.
2. Clique em **New repository**, dê um nome (ex.: `achadinhos`) e marque **Public**
   (repositório público = Actions e Pages grátis, sem limite de minutos).
3. Envie os arquivos deste projeto para ele (inclusive a pasta `.github`).

## 2. Cadastrar as chaves (nunca no código!)
No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
Crie só as que for usar:

| Nome | O que é |
|---|---|
| TELEGRAM_BOT_TOKEN | token do @BotFather |
| TELEGRAM_CHAT_ID | `@seucanal` |
| TELEGRAM_ADMIN_CHAT_ID | seu chat pessoal (só para story manual) |
| SHOPEE_APP_ID / SHOPEE_SECRET | painel de afiliados Shopee → Open API |
| ML_MATT_WORD / ML_MATT_TOOL | da sua tag de afiliado do Mercado Livre |
| ML_ACCESS_TOKEN | opcional, token da API do ML |
| IG_USER_ID / IG_ACCESS_TOKEN | do app da Meta |
| IG_MENSAGENS_ID | ID da Página do Facebook (para os directs) |
| IMGBB_API_KEY | grátis em api.imgbb.com (arte da story) |

## 3. Ajustar as configurações
Edite o arquivo `config.env` direto no site do GitHub (palavras-chave, desconto mínimo,
quantos posts por rodada, modo da story etc.).

## 4. Ligar
- Aba **Actions** → se pedir, clique em "I understand… enable workflows".
- Abra **Postar ofertas** → **Run workflow** para testar na hora.
- Erros aparecem clicando na execução (bolinha vermelha).

## 5. Vitrine da bio
**Settings → Pages → Source: Deploy from a branch → main / (root) → Save.**
O endereço da vitrine será `https://SEU-USUARIO.github.io/achadinhosnet/vitrine/`.
Coloque esse link na bio do Instagram.

## Observações
- Os horários do GitHub podem atrasar alguns minutos.
- O token do Instagram de longa duração vence em ~60 dias: renove e atualize o secret.
- Se o repositório ficar 60 dias sem nenhuma alteração, o GitHub pausa os agendamentos —
  como o bot salva o histórico a cada post, isso normalmente não acontece.
