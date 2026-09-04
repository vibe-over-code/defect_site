"""Проверка позиций домена в обычной выдаче Google.

Пример:
    python check_google_positions.py --domain example.ru
    python check_google_positions.py --domain example.ru --query "материалы для дефектолога"

Парсер предназначен для ручных редких проверок. Google может показать CAPTCHA
или персонализированную выдачу, поэтому результаты не являются официальной
SEO-статистикой.
"""

import argparse
import json
import os
import sys
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, build_opener, ProxyHandler, urlopen


HTTP_OPENER = None


def open_request(request, timeout=20):
    if HTTP_OPENER is not None:
        return HTTP_OPENER.open(request, timeout=timeout)
    return urlopen(request, timeout=timeout)


DEFAULT_QUERIES = [
    'Инструменты дефектолога',
    'материалы для дефектолога',
    'материалы для логопеда',
    'рабочие листы для дефектолога',
]


class GoogleLinkParser(HTMLParser):
    """Достаёт внешние ссылки из HTML-выдачи Google."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href', '')
        if href.startswith('/url?'):
            href = parse_qs(urlparse(href).query).get('q', [''])[0]
        if href.startswith(('http://', 'https://')):
            self.links.append(href)


def normalize_host(value):
    value = value.strip().lower()
    if '://' in value:
        value = urlparse(value).netloc
    return value.split(':', 1)[0].removeprefix('www.')


def same_domain(url, domain):
    host = normalize_host(urlparse(url).netloc)
    return host == domain or host.endswith('.' + domain)


def clean_links(links):
    result = []
    seen = set()
    for link in links:
        link = link.split('#', 1)[0]
        # Исключаем служебные ссылки Google и повторяющиеся URL.
        host = normalize_host(urlparse(link).netloc)
        if not host or host in {'google.com', 'google.ru', 'youtube.com'}:
            continue
        if link not in seen:
            seen.add(link)
            result.append(link)
    return result


def check_query(query, domain, pages):
    url = (
        'https://www.google.com/search?q=' + quote_plus(query)
        + '&num=' + str(pages * 10) + '&hl=ru&gl=ru&filter=0'
    )
    request = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 Chrome/131 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    })
    with open_request(request, timeout=20) as response:
        html = response.read().decode('utf-8', errors='replace')
    if 'captcha' in html.lower() or '/sorry/' in response.geturl():
        raise RuntimeError('Google запросил CAPTCHA')
    parser = GoogleLinkParser()
    parser.feed(html)
    links = clean_links(parser.links)
    for position, link in enumerate(links, 1):
        if same_domain(link, domain):
            return position, link
    return None, None


def check_query_api(query, domain, pages, api_key, search_engine_id):
    """Проверяет выдачу через официальный Google Custom Search API."""
    found_position = None
    found_link = None
    for page in range(pages):
        start = page * 10 + 1
        url = (
            'https://www.googleapis.com/customsearch/v1?key=' + quote_plus(api_key)
            + '&cx=' + quote_plus(search_engine_id)
            + '&q=' + quote_plus(query) + '&num=10&start=' + str(start)
        )
        request = Request(url, headers={'Accept': 'application/json'})
        with open_request(request, timeout=20) as response:
            payload = json.loads(response.read().decode('utf-8'))
        if 'error' in payload:
            message = payload['error'].get('message', 'ошибка Google API')
            raise RuntimeError(message)
        for offset, item in enumerate(payload.get('items', []), start):
            link = item.get('link', '')
            if same_domain(link, domain):
                return offset, link
    return found_position, found_link


def main():
    parser = argparse.ArgumentParser(description='Проверка позиций сайта в Google')
    parser.add_argument('--domain', required=True, help='домен, например example.ru')
    parser.add_argument('--query', action='append', help='запрос; можно указать несколько раз')
    parser.add_argument('--pages', type=int, default=3, choices=range(1, 11),
                        help='сколько страниц выдачи проверять (по 10 результатов)')
    parser.add_argument('--delay', type=float, default=3,
                        help='пауза между запросами в секундах')
    parser.add_argument('--api-key', default=os.environ.get('GOOGLE_API_KEY'),
                        help='ключ Google Custom Search API (или GOOGLE_API_KEY)')
    parser.add_argument('--cx', default=os.environ.get('GOOGLE_CX'),
                        help='ID поисковой системы (или GOOGLE_CX)')
    parser.add_argument('--proxy', default=os.environ.get('GOOGLE_PROXY'),
                        help='HTTP-прокси (или GOOGLE_PROXY), например http://user:pass@host:port')
    args = parser.parse_args()
    global HTTP_OPENER
    if args.proxy:
        HTTP_OPENER = build_opener(ProxyHandler({'http': args.proxy, 'https': args.proxy}))
    domain = normalize_host(args.domain)
    queries = args.query or DEFAULT_QUERIES

    print(f'Домен: {domain}\n')
    for index, query in enumerate(queries):
        try:
            if bool(args.api_key) != bool(args.cx):
                raise RuntimeError('нужно задать и --api-key, и --cx')
            if args.api_key and args.cx:
                position, link = check_query_api(
                    query, domain, args.pages, args.api_key, args.cx
                )
            else:
                position, link = check_query(query, domain, args.pages)
            if position:
                print(f'{query}: позиция {position} ({link})')
            else:
                print(f'{query}: не найден в первых {args.pages * 10} результатах')
        except Exception as error:
            print(f'{query}: ошибка — {error}', file=sys.stderr)
        if index < len(queries) - 1:
            time.sleep(max(0, args.delay))


if __name__ == '__main__':
    main()
