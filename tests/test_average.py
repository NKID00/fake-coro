import pytest

from fake_coro import fake_coro, yield_


@fake_coro
def average():
    total, count = 0, 0
    num = yield_()
    while True:
        total += num
        count += 1
        num = yield_(total / count)


def test_average():
    coro = average()
    next(coro)
    assert coro.send(1) == pytest.approx(1)
    assert coro.send(5) == pytest.approx((1 + 5) / 2)
    assert coro.send(6) == pytest.approx((1 + 5 + 6) / 3)
