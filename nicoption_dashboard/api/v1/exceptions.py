from rest_framework import status
from rest_framework.exceptions import APIException


class HistoryProviderError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "دریافت تاریخچه قیمت ناموفق بود."
    default_code = "history_provider_error"


class OrderBookCatalogProviderError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "دریافت فهرست جریان سفارش‌ها ناموفق بود."
    default_code = "order_book_catalog_provider_error"


class OrderBookNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "نماد انتخاب‌شده در فهرست جاری بازار پیدا نشد."
    default_code = "order_book_not_found"


class OrderBookProviderError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "دریافت جریان سفارش‌ها ناموفق بود."
    default_code = "order_book_provider_error"


class CoveredScoreServiceError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "محاسبه امتیاز کاوردکال ناموفق بود."
    default_code = "covered_score_service_error"
