import pytest

from fake_coro import fake_coro, yield_


@fake_coro
def func():
    self = yield_()
    next(self)


def test_race_condition():
    coro = func()
    next(coro)
    coro.send(coro)
