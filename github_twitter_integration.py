import os
import json
import tweepy
import requests
from tweepy.errors import TweepyException, Forbidden, Unauthorized
from github import Github
import re
import tempfile
import time

# Configuração das APIs
github_token = os.environ['GITHUB_TOKEN']
twitter_bearer_token = os.environ['TWITTER_BEARER_TOKEN']
twitter_client_id = os.environ['TWITTER_CLIENT_ID']
twitter_client_secret = os.environ['TWITTER_CLIENT_SECRET']
twitter_access_token = os.environ['TWITTER_ACCESS_TOKEN']
twitter_access_token_secret = os.environ['TWITTER_ACCESS_TOKEN_SECRET']

# Inicialização dos clientes
g = Github(github_token)

# Autenticação do Twitter V2
client = tweepy.Client(
    bearer_token=twitter_bearer_token,
    consumer_key=twitter_client_id,
    consumer_secret=twitter_client_secret,
    access_token=twitter_access_token,
    access_token_secret=twitter_access_token_secret
)

# Autenticação do Twitter V1.1 (apenas para upload de mídia)
auth = tweepy.OAuthHandler(twitter_client_id, twitter_client_secret)
auth.set_access_token(twitter_access_token, twitter_access_token_secret)
api = tweepy.API(auth)

# Logging das credenciais (parcialmente ocultas)
print(f"Twitter Client ID: {twitter_client_id[:5]}...")
print(f"Twitter Access Token: {twitter_access_token[:5]}...")

# Obter informações do evento do GitHub
event_name = os.environ['GITHUB_EVENT_NAME']
repository = os.environ['GITHUB_REPOSITORY']
event_path = os.environ['GITHUB_EVENT_PATH']

with open(event_path, 'r') as f:
    event_data = json.load(f)

def count_positive_reactions(issue):
    reactions = issue.get_reactions()
    return reactions.totalCount

def truncate_text(text, max_length=280):
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            temp_file.write(response.content)
            return temp_file.name
    return None

def extract_image_urls(content):
    pattern = r'!\[.*?\]\((.*?)\)'
    return re.findall(pattern, content)

def post_tweet(text, media_id=None):
    try:
        if media_id:
            response = client.create_tweet(text=truncate_text(text), media_ids=[media_id])
        else:
            response = client.create_tweet(text=truncate_text(text))
        print(f"Tweet posted successfully: {response.data['id']}")
    except Forbidden as e:
        print(f"Forbidden error: You don't have permission to perform this action. Error: {e}")
    except Unauthorized as e:
        print(f"Unauthorized error: Please check your credentials. Error: {e}")
    except TweepyException as e:
        print(f"Error posting tweet: {e}")

def process_issue(issue):
    # Verificar se a issue foi editada
    if issue.updated_at > issue.created_at:
        print("Issue was edited. Skipping.")
        return

    # Extrair URLs de imagens do conteúdo
    image_urls = extract_image_urls(issue.body)

    # Verificar se há imagens
    if not image_urls:
        print("Issue doesn't contain images. Skipping.")
        return

    # Monitorar reações
    max_wait_time = 3600  # 1 hora
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        if count_positive_reactions(issue) >= 1:
            # Extrair o conteúdo de texto, removendo qualquer referência à imagem
            content = re.sub(r'!\[.*?\]\(.*?\)', '', issue.body).strip() if issue.body else "No description provided."

            # Baixar a primeira imagem
            image_path = download_image(image_urls[0])
            if image_path:
                # Upload da mídia
                media = api.media_upload(image_path)

                # Postar o tweet
                post_tweet(content, media.media_id)

                os.unlink(image_path)  # Remover o arquivo temporário
            else:
                print("Failed to download image")
                post_tweet(content)  # Posta sem imagem se falhar o download

            return

        time.sleep(60)  # Esperar 1 minuto antes de verificar novamente

    print("No positive reactions after waiting period. Skipping.")

def main():
    if event_name == 'issues':
        repo = g.get_repo(repository)
        issue_number = event_data['issue']['number']
        issue = repo.get_issue(number=issue_number)
        process_issue(issue)
    else:
        print(f"Unhandled event type: {event_name}")

if __name__ == "__main__":
    main()