import pytest

from fake_coro import fake_coro, yield_


@fake_coro
def func():
    yield_(1)
    yield_(3)
    yield_(5)


def test_for():
    for i, j in zip(func(), range(1, 10, 2)):
        assert i == j
