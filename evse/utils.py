import functools
from enum import Enum

from structlog import get_logger

logger = get_logger(__name__)

routables = []


class HandlerType(Enum):
    """
    Define types of handlers that can exist.

    A message that originates from a CS can be interacted with before it is sent
    and after the response is received.

    A message that originates from a CSMS can not be interacted before it's received.
    We can handle it after it is received, and after we send a response.

    Handlers can be linked to an abstraction and a handler.
    """

    BEFORE_CALL_REQUEST_FROM_CP = "request_from_cp"
    ON_CALL_RESPONSE_FROM_CSMS = "response_from_csms"
    ON_CALL_REQUEST_FROM_CSMS = "request_from_csms"
    AFTER_CALL_RESPONSE_FROM_CP = "response_from_cs"


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
    logger.debug(f"Routes for {handler} are {routes}")
    return routes
