import contextvars
import logging


request_id_var = contextvars.ContextVar('request_id', default='-')
request_user_id_var = contextvars.ContextVar('request_user_id', default='-')
request_org_id_var = contextvars.ContextVar('request_org_id', default='-')
request_path_var = contextvars.ContextVar('request_path', default='-')


class RequestContextLogFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        record.request_user_id = request_user_id_var.get()
        record.request_org_id = request_org_id_var.get()
        record.request_path = request_path_var.get()
        return True
