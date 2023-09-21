import functools
from enum import Enum

from structlog import get_logger

L = get_logger(__name__)

routables = []


class HandlerType(Enum):
    CALL_FACTORY = "_payload_factory"
    CALL_PAYLOAD = "_call_payload"
    CALL_RESULT_FACTORY = "_call_result_factory"
    CALL_RESULT_PAYLOAD = "_call_result"


def handler(action, handler: HandlerType):
    def decorator(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            return func(*args, **kwargs)

        setattr(inner, str(handler), action)
        # inner._payload_factory = action
        if func.__name__ not in routables:
            routables.append(func.__name__)
        return inner

    return decorator


def create_route_map(obj, handler: HandlerType):
    routes = {}
    for attr_name in routables:
        try:
            attr = getattr(obj, attr_name)
            action = getattr(attr, str(handler))

            if action not in routes:
                routes[action] = {}

            routes[action] = attr

        except AttributeError:
            continue
    L.debug("Routes for object %s are %s", obj, routes)
    return routes
