class APIResponseError(Exception):
    """Вызывается, если эндпоинт API возвращает статус, отличный от 200."""


class JSONParsingError(Exception):
    """Вызывается, если ответ API невозможно преобразовать в JSON или он пуст."""


class PractikumAPIError(Exception):
    """Вызывается при любых сетевых сбоях во время запроса к Практикуму."""
