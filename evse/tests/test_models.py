import orjson
import pytest
from model_payload_factories import Charger


def test_charger_dump():
    charger = Charger("charger_id", 2)
    print(orjson.dumps(charger))
    assert orjson.dumps(charger)
