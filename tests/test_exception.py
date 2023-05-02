import pytest

from fake_coro import fake_coro, yield_


@fake_coro
def func():
    yield_(1)
    return 2


def test_exception():
    with pytest.raises(ValueError):
        coro = func(1)

    coro = func()
    with pytest.raises(ZeroDivisionError,
                       match='this is the correct exception'):
        coro.throw(ZeroDivisionError('this is the correct exception'))
    with pytest.raises(StopIteration):
        next(coro)
    
    coro = func()
    assert next(coro) == 1
    try:
        next(coro)
    except StopIteration as exc:
        assert exc.value == 2
    else:
        pytest.fail('StopIteration is not raised')
    
    coro = func()
    next(coro)
    with pytest.raises(ZeroDivisionError,
                       match='this is another exception'):
        coro.throw(ZeroDivisionError('this is another exception'))
    with pytest.raises(StopIteration):
        coro.throw(ZeroDivisionError('this is yet another exception'))

