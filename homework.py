import logging
import os
import sys
import time

import requests
import vk_api
from dotenv import load_dotenv

from exceptions import (
    APIResponseError,
    JSONParsingError,
    PractikumAPIError
)


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


def check_tokens():
    """Проверяет, что все необходимые токены заданы и не пустые."""
    required_tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'VK_TOKEN': VK_TOKEN,
        'VK_USER_ID': VK_USER_ID
    }
    missing = [
        name for name, val in required_tokens.items()
        if not val or not str(val).strip()
    ]

    if missing:
        logging.critical(
            f'Ошибка конфигурации! Не найдены следующие токены: '
            f'{",".join(missing)}'
        )
        return False

    try:
        int(VK_USER_ID)
    except (TypeError, ValueError):
        logging.critical('Ошибка конфигурации! VK_USER_ID должен быть числом.')
        return False

    return True


def send_message(vk, message):
    """Отправляет сообщение пользователю через VK API."""
    try:
        vk.messages.send(
            user_id=int(VK_USER_ID),
            message=message,
            random_id=int(time.time())
        )
        logging.debug(f'Сообщение успешно отправлено в VK: {message}')
    except Exception as error:
        logging.error(f"Ошибка отправки: {error}")


def get_api_answer(timestamp):
    """Делает запрос к API.
    Возвращает ответ, приведенный к типам данных Python.
    """
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != 200:
            raise APIResponseError(
                f'Эндпоинт вернул код {response.status_code}'
            )
        return response.json()
    except requests.RequestException as error:
        raise PractikumAPIError(f'Ошибка при запросе к API: {error}')
    except ValueError as error:
        raise JSONParsingError(
            f'Ответ от API не удалось преобразовать в JSON: {error}'
        )


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарем')

    if 'homeworks' not in response:
        raise KeyError('В ответе отсутствует ключ "homeworks"')

    if 'current_date' not in response:
        raise KeyError('В ответе отсутствует ключ "current_date"')

    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Значение под ключом "homeworks" не является списком')

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError(
            'В данных домашней работы отсутствует ключ "homework_name"'
        )
    if 'status' not in homework:
        raise KeyError('В данных домашней работы отсутствует ключ "status"')
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус домашней работы: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)
    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
    except Exception as error:
        logging.critical(f'Не удалось подключиться к VK API: {error}')
        sys.exit(1)

    timestamp = int(time.time()) - 30 * 24 * 60 * 60
    last_error = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(vk, message)
            else:
                logging.debug('В ответе отсутствуют статусы домашних работ')

            timestamp = response.get('current_date', timestamp)
            last_error = ''

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            if message != last_error:
                send_message(vk, message)
                last_error = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
