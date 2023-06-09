import pytest

from fake_coro import fake_coro, yield_, yield_from


@fake_coro
def tree(iterable, level=0):
    for item in iterable:
        if isinstance(item, int):
            yield_(str(item), level)
        else:
            yield_from(tree(item, level + 1))


def to_str(arg):
    item, level = arg
    return '.' * level + item


@fake_coro
def func1():
    yield_(-1)
    yield_from(range(10))


@fake_coro
def func2(coro):
    result = yield_from(coro)
    return result

@fake_coro
def func3():
    try:
        yield_()
    except ZeroDivisionError:
        return 42


def test_yield_from(capfd):
    iterable = [0, 1, [[2, 3, 4], [[5, 6], 7], 8], [[[9]]]]
    print('\n'.join(map(to_str, tree(iterable))))
    captured = capfd.readouterr()
    assert captured.out == (
        '0\n'
        '1\n'
        '..2\n'
        '..3\n'
        '..4\n'
        '...5\n'
        '...6\n'
        '..7\n'
        '.8\n'
        '...9\n'
    )

    coro = tree(iterable)
    next(coro)
    next(coro)
    next(coro)
    with pytest.raises(ZeroDivisionError):
        coro.throw(ZeroDivisionError)

    coro = func1()
    assert next(coro) == -1
    assert coro.send(None) == 0
    assert next(coro) == 1
    with pytest.raises(RuntimeError):
        coro.throw(StopIteration)
    with pytest.raises(StopIteration):
        next(coro)

    coro = func2(range(0))
    with pytest.raises(StopIteration):
        next(coro)

    coro = func2(range(1))
    next(coro)
    with pytest.raises(AttributeError, match=(
            "range_iterator' object has no attribute 'send'")):
        coro.send(1)
    with pytest.raises(StopIteration):
        coro.send(1)
    
    coro = func2(func3())
    next(coro)
    with pytest.raises(StopIteration, match='42'):
        coro.throw(ZeroDivisionError)
