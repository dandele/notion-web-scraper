import os
import requests
from bs4 import BeautifulSoup
import time
from notion_client import Client  # Importa il client di Notion

# Definisci gli headers per la richiesta HTTP
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/86.0.4240.183 Safari/537.36'
}

# Inizializza il client di Notion utilizzando le variabili d'ambiente
notion = Client(auth=os.getenv('NOTION_SECRET_KEY'))
database_id = os.getenv('DATABASE_ID')

# Lista per memorizzare tutti gli articoli
all_articles = []

def get_existing_links(notion, database_id):
    existing_links = set()
    try:
        # Notion API ha un limite di 100 risultati per query; usiamo il cursore per paginare
        response = notion.databases.query(
            database_id=database_id,
            page_size=100
        )
        results = response.get('results', [])
        for page in results:
            # Assumiamo che "Link" sia il nome della proprietà contenente l'URL
            link_property = page['properties'].get('Link')
            if link_property and link_property['type'] == 'rich_text':
                rich_text = link_property.get('rich_text', [])
                if rich_text:
                    link = rich_text[0]['text']['content']
                    existing_links.add(link)
        # Gestione della paginazione
        while response.get('has_more'):
            response = notion.databases.query(
                database_id=database_id,
                start_cursor=response.get('next_cursor'),
                page_size=100
            )
            results = response.get('results', [])
            for page in results:
                link_property = page['properties'].get('Link')
                if link_property and link_property['type'] == 'rich_text':
                    rich_text = link_property.get('rich_text', [])
                    if rich_text:
                        link = rich_text[0]['text']['content']
                        existing_links.add(link)
    except Exception as e:
        print(f'Errore durante il recupero dei link esistenti da Notion: {e}')
    return existing_links

# Funzione per ottenere gli articoli da una pagina specifica
def get_articles_from_page(url):
    response = requests.get(url, headers=headers)
    articles = []

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')

        # Trova il contenitore generale degli articoli
        grid_container = soup.find('div', class_='grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3')

        if grid_container:
            # Trova tutti i contenitori degli articoli
            article_divs = grid_container.find_all('div', class_='transparent h-full cursor-pointer overflow-hidden rounded-lg flex flex-col border')

            for article in article_divs:
                # Trova il link all'articolo
                link_tag = article.find('a', href=True)
                if link_tag:
                    link = link_tag['href']
                    if not link.startswith('http'):
                        link = 'https://www.superhuman.ai' + link
                else:
                    link = None

                # Trova il titolo dell'articolo
                title_tag = article.find('h2')
                if title_tag:
                    article_title = title_tag.get_text(strip=True)
                else:
                    article_title = None

                if link and article_title:
                    articles.append({'article_title': article_title, 'link': link})
        else:
            print('Contenitore degli articoli non trovato.')
    else:
        print(f'Errore nella richiesta: {response.status_code}')

    return articles

# Funzione per estrarre il contenuto e il titolo del prompt dall'articolo
def get_content_from_article(link):
    article_response = requests.get(link, headers=headers)
    if article_response.status_code == 200:
        article_soup = BeautifulSoup(article_response.content, 'html.parser')

        # Inizializza le variabili
        content = 'Contenuto non trovato.'
        prompt_title = 'Titolo del prompt non trovato.'

        # Trova il div con style contenente 'padding:14px;'
        content_div = article_soup.find('div', style=lambda value: value and 'padding:14px;' in value)
        if content_div:
            # Trova il titolo del prompt
            # Il titolo del prompt è nel <h2> precedente al content_div
            previous_sibling = content_div.find_previous_sibling('div')
            if previous_sibling:
                h2_tag = previous_sibling.find('h2')
                if h2_tag:
                    prompt_title = h2_tag.get_text(strip=True)
            # Trova il tag <pre>
            pre_tag = content_div.find('pre')
            if pre_tag:
                # Trova il tag <code>
                code_tag = pre_tag.find('code')
                if code_tag:
                    # Estrai il testo del prompt
                    content = code_tag.get_text(strip=True)
        else:
            # Se non trovato, prova con un altro selettore
            # Ad esempio, cerchiamo un div con classi specifiche
            content_div = article_soup.find('div', class_='leading-relaxed')
            if content_div:
                # Trova tutti i paragrafi e uniscili
                paragraphs = content_div.find_all('p')
                content = '\n'.join([p.get_text(strip=True) for p in paragraphs])
                prompt_title = 'Titolo del prompt non applicabile.'
            else:
                content = 'Contenuto non trovato.'
                prompt_title = 'Titolo del prompt non trovato.'

        return content, prompt_title
    else:
        return f'Errore nella richiesta dell\'articolo: {article_response.status_code}', 'Titolo del prompt non trovato.'

# Funzione per inserire i dati nel database Notion
def add_to_notion(article_title, link, prompt_title, content):
    try:
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties={
                "Prompt Title": {  # Deve essere di tipo Title
                    "title": [
                        {
                            "text": {
                                "content": prompt_title
                            }
                        }
                    ]
                },
                "Link": {  # Deve essere di tipo Rich Text o URL
                    "rich_text": [
                        {
                            "text": {
                                "content": link
                            }
                        }
                    ]
                },
                "Titolo": {  # Deve essere di tipo Rich Text
                    "rich_text": [
                        {
                            "text": {
                                "content": article_title
                            }
                        }
                    ]
                },
                "Contenuto": {  # Deve essere di tipo Rich Text
                    "rich_text": [
                        {
                            "text": {
                                "content": content
                            }
                        }
                    ]
                }
            }
        )
        print('Pagina aggiunta a Notion.')
    except Exception as e:
        print(f'Errore durante l\'inserimento su Notion: {e}')

def main():
    # Recupera gli URL esistenti da Notion
    existing_links = get_existing_links(notion, database_id)
    print(f'Numero di link già presenti in Notion: {len(existing_links)}')

    # Inizializza l'URL base
    base_url = 'https://www.superhuman.ai/archive?page='

    page = 1
    while True:
        print(f'\nScraping della pagina {page}...\n')
        page_url = base_url + str(page)
        articles = get_articles_from_page(page_url)
        if not articles:
            print('Nessun articolo trovato sulla pagina. Fine della paginazione.')
            break
        all_articles.extend(articles)
        page += 1
        time.sleep(2)  # Pausa tra le richieste

    # Rimuovi eventuali duplicati
    unique_articles = [article for article in all_articles if article['link'] not in existing_links]

    print(f'\nNumero totale di nuovi articoli da aggiungere: {len(unique_articles)}\n')

    if unique_articles:
        # Itera su ciascun articolo e ottieni il contenuto
        for article in unique_articles:
            article_title = article['article_title']
            link = article['link']

            print(f'Titolo Articolo: {article_title}')
            print(f'Link: {link}')

            if link:
                content, prompt_title = get_content_from_article(link)
                print('Titolo del Prompt estratto:')
                print(prompt_title)
                print('Contenuto estratto:')
                print(content)
            else:
                print('Link non valido.')
                content = 'Link non valido.'
                prompt_title = 'Titolo del prompt non trovato.'

            # Inserisci i dati nel database Notion
            add_to_notion(article_title, link, prompt_title, content)

            print('---------------------')
            time.sleep(2)  # Pausa tra le richieste
    else:
        print('Nessun nuovo prompt trovato. Nessuna azione da eseguire.')

if __name__ == '__main__':
    main()
