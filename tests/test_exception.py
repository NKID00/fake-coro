import pytest

import traceback

from fake_coro import fake_coro, yield_


@fake_coro
def func1():
    yield_(1)
    return 2


@fake_coro
def func2():
    with pytest.raises(GeneratorExit):
        yield_()


@fake_coro
def func3():
    raise StopIteration('what?')


@fake_coro
def func4():
    try:
        yield_()
    except GeneratorExit:
        1 / 0


@fake_coro
def func5():
    try:
        yield_()
    except ZeroDivisionError:
        yield_(1)
    else:
        yield_(2)


def test_exception():
    with pytest.raises(TypeError, match='too many positional arguments'):
        coro = func1(1)

    coro = func1()
    with pytest.raises(ZeroDivisionError,
                       match='this is the correct exception'):
        coro.throw(ZeroDivisionError('this is the correct exception'))
    with pytest.raises(StopIteration):
        next(coro)

    coro = func1()
    with pytest.raises(ZeroDivisionError):
        coro.throw(ZeroDivisionError)
    with pytest.raises(StopIteration):
        next(coro)

    coro = func1()
    with pytest.raises(ZeroDivisionError):
        coro.throw(ZeroDivisionError, 1)

    coro = func1()
    with pytest.raises(TypeError):
        coro.throw(int)

    coro = func1()
    assert next(coro) == 1
    try:
        next(coro)
    except StopIteration as result:
        assert result.value == 2
    else:
        pytest.fail('StopIteration is not raised')

    coro = func1()
    next(coro)
    with pytest.raises(ZeroDivisionError,
                       match='this is another exception'):
        coro.throw(ZeroDivisionError('this is another exception'))
    with pytest.raises(StopIteration):
        coro.throw(ZeroDivisionError('this is yet another exception'))

    coro = func2()
    coro.close()
    coro.close()

    coro = func2()
    next(coro)
    coro.close()
    with pytest.raises(StopIteration):
        next(coro)
    coro.close()

    coro = func3()
    try:
        next(coro)
    except RuntimeError:
        result = traceback.format_exc()
        assert 'StopIteration: what?' in result
        assert ('The above exception was the direct cause of the following'
                ' exception:') in result
        assert 'fake coroutine raised StopIteration' in result
    else:
        pytest.fail('RuntimeError is not raised')

    coro = func4()
    next(coro)
    with pytest.raises(ZeroDivisionError):
        coro.close()
    coro.close()

    coro = func5()
    next(coro)
    assert coro.throw(ZeroDivisionError) == 1

    coro = func5()
    next(coro)
    assert next(coro) == 2

    coro = func5()
    next(coro)
    with pytest.raises(KeyError):
        coro.throw(KeyError)
