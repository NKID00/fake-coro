import pytest

from fake_coro import fake_coro, yield_


@fake_coro
def func1():
    self = yield_()
    next(self)

@fake_coro
def func2():
    self = yield_()
    self.close()

@fake_coro
def func3():
    self = yield_()
    self.throw(ZeroDivisionError)


def test_race_condition():
    coro = func1()
    next(coro)
    with pytest.raises(ValueError, match='fake coroutine already executing'):
        coro.send(coro)
    with pytest.raises(StopIteration):
        next(coro)

    coro = func2()
    next(coro)
    with pytest.raises(ValueError, match='fake coroutine already executing'):
        coro.send(coro)

    coro = func3()
    next(coro)
    with pytest.raises(ValueError, match='fake coroutine already executing'):
        coro.send(coro)
