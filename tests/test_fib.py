import itertools

import fake_coro


@fake_coro.fake_coro
def fib():
    a, b = 1, 1
    while True:
        fake_coro.yield_(a)
        a, b = b, a + b


def test_fib():
    gen = fib()
    assert list(itertools.islice(gen, 5)) == [1, 1, 2, 3, 5]
