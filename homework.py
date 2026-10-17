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
    PractikumAPIError,
)


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD_IN_SECONDS = 600
RETRY_PERIOD = RETRY_PERIOD_IN_SECONDS
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    handlers=(
        logging.FileHandler('bot_debug.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    )
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет, что все необходимые токены заданы и не пустые."""
    required_tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'VK_TOKEN': VK_TOKEN,
        'VK_USER_ID': VK_USER_ID
    }
    missing = [
        name for name, token_value in required_tokens.items()
        if not token_value or not str(token_value).strip()
    ]

    if missing:
        missing_tokens_str = ','.join(missing)
        logger.critical(
            f'Ошибка конфигурации! Не найдены следующие токены: '
            f'{missing_tokens_str}'
        )
        return False

    try:
        int(VK_USER_ID)
    except (TypeError, ValueError):
        logger.exception('Ошибка конфигурации! VK_USER_ID должен быть числом.')
        return False

    return True


def send_message(vk, message):
    """Отправляет сообщение пользователю через VK API."""
    user_id = int(VK_USER_ID)
    random_id = int(time.time())

    try:
        vk.messages.send(
            user_id=user_id,
            message=message,
            random_id=random_id
        )
    except vk_api.VkApiError as error:
        logger.error(f'Ошибка отправки: {error}')
        return False
    else:
        logger.debug(f'Сообщение успешно отправлено в VK: {message}')
        return True


def get_api_answer(timestamp):
    """Делает запрос к API.

    Возвращает ответ, приведенный к типам данных Python.
    """
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != requests.codes.ok:
            response_text = response.text
            raise APIResponseError(
                f'Эндпоинт вернул код {response.status_code}\n'
                f'Адрес запроса: {ENDPOINT}\n'
                f'Параметры: {payload}\n'
                f'Тело ответа: {response_text}'
            )
        return response.json()
    except requests.RequestException as error:
        raise PractikumAPIError(
            f'Ошибка при запросе к API: {error}'
        ) from error
    except ValueError as error:
        raise JSONParsingError(
            f'Ответ от API не удалось преобразовать в JSON: {error}'
        )


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        actual_type = type(response)
        raise TypeError(
            f'Ответ API не является словарем! '
            f'Ожидался тип dict, но получен тип: {actual_type}')

    if 'homeworks' not in response:
        raise KeyError('В ответе отсутствует ключ "homeworks"')

    if 'current_date' not in response:
        raise KeyError('В ответе отсутствует ключ "current_date"')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        actual_type = type(homeworks)
        raise TypeError(
            f'Значение под ключом "homeworks" не является списком!'
            f'Ожидался тип list, но получен: {actual_type}'
        )

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
        logger.critical(f'Не удалось подключиться к VK API: {error}')
        sys.exit(1)

    timestamp = int(time.time()) - 30 * 24 * 60 * 60
    last_error = ''
    while True:
        try:
            response_data = get_api_answer(timestamp)
            homeworks = check_response(response_data)
            if not homeworks:
                logger.debug('В ответе отсутствуют статусы домашних работ')
                timestamp = response_data.get('current_date', timestamp)
                continue
            for homework in homeworks:
                message = parse_status(homework)
                send_message(vk, message)

            timestamp = response_data.get('current_date', timestamp)
            last_error = ''

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != last_error and send_message(vk, message):
                last_error = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
