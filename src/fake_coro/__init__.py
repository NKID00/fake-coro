'''Coroutines emulated with threads.

This module provides fake coroutines that are not coroutines but act like
coroutines.

>>> from fake_coro import fake_coro, yield_
>>> @fake_coro
... def fib(limit):
...     a, b = 1, 1
...     while a < limit:
...         yield_(a)
...         a, b = b, a + b
>>> list(fib(10))
[1, 1, 2, 3, 5, 8]

Other features of classic coroutines are also supported:

>>> @fake_coro
... def my_coro():
...     return 42
>>> next(my_coro())
Traceback (most recent call last):
  ...
StopIteration: 42

Also .send, .throw and .close:

>>> @fake_coro
... def average():
...     total = count = 0
...     num = yield_()
...     while True:
...         total += num
...         count += 1
...         num = yield_(total / count)
>>> coro = average()
>>> next(coro)
>>> coro.send(1)
1.0
>>> coro.send(6)
3.5
>>> coro.close()
>>> coro.send(7)
Traceback (most recent call last):
  ...
StopIteration

And sub-coroutines:

>>> from fake_coro import yield_from
>>> @fake_coro
... def chain(*iterables):
...     for iterable in iterables:
...         yield_from(iterable)
>>> list(chain(range(3), range(5)))
[0, 1, 2, 0, 1, 2, 3, 4]

Fake coroutines are implemented by threads and obviously perform much worse
than native classic coroutines.  However, normal functions invoked by fake
coroutines can also yield like coroutines:

>>> @fake_coro
... def foo():
...     bar()
...     yield_(2)
>>> def bar():
...     yield_(1)  # bar is not a coroutine but can yield!
>>> list(foo())
[1, 2]
'''

from __future__ import annotations
from typing import Callable, Any, Iterable, Mapping, Union, Optional, Generator
from types import TracebackType
from queue import Queue
from dataclasses import dataclass
import functools
import threading
import enum
import inspect

__all__ = ['FakeCoroutine', 'fake_coro', 'yield_', 'yield_from']


@enum.unique
class _CoStatus(enum.Enum):
    CREATED = enum.auto()
    RUNNING = enum.auto()
    SUSPENDED = enum.auto()
    CLOSED = enum.auto()


@dataclass
class _CoOpNext:
    value: Any


@dataclass
class _CoOpThrow:
    value: BaseException


@dataclass
class _CoOpYield:
    value: Any


@dataclass
class _CoOpRaise:
    value: BaseException


_thread_local = threading.local()


class FakeCoroutine:
    '''Represents a fake coroutine.

    This class is intended for internal use and should not be instantiate
    directly, use `fake_coro` instead.'''

    def __init__(self, func: Callable, args: Iterable[Any],
                 kwargs: Mapping[str, Any]) -> None:
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._status = _CoStatus.CREATED
        self._queue_next_throw: Queue[
            Union[_CoOpNext, _CoOpThrow]] = Queue(1)
        self._queue_yield_raise: Queue[
            Union[_CoOpYield, _CoOpRaise]] = Queue(1)
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._entrypoint,
            args=(self, func, args, kwargs), daemon=True)
        self._thread.start()

    def _entrypoint(self, context: FakeCoroutine, func: Callable,
                    args: Iterable[Any], kwargs: Mapping[str, Any]):
        # pylint: disable=protected-access
        _thread_local.context = context  # type: ignore
        result = self._queue_next_throw.get()
        if isinstance(result, _CoOpNext):
            pass
        elif isinstance(result, _CoOpThrow):
            try:
                raise result.value
                # pylint: disable=broad-exception-caught
            except BaseException as exc:
                self._status = _CoStatus.CLOSED
                self._queue_yield_raise.put(_CoOpRaise(exc))
                return
        else:  # pragma: no cover
            self._queue_yield_raise.put(_CoOpRaise(
                RuntimeError('unexpected result from fake coroutine')))
            return
        try:
            return_value = func(*args, **kwargs)
        except StopIteration as exc:
            try:
                raise RuntimeError('fake coroutine raised'
                                   ' StopIteration') from exc
            except RuntimeError as exc1:
                self._status = _CoStatus.CLOSED
                self._queue_yield_raise.put(_CoOpRaise(exc1))
                return
        except BaseException as exc:  # pylint: disable=broad-exception-caught
            self._status = _CoStatus.CLOSED
            self._queue_yield_raise.put(_CoOpRaise(exc))
            return
        try:
            raise StopIteration(return_value)
        except StopIteration as exc:
            self._status = _CoStatus.CLOSED
            self._queue_yield_raise.put(_CoOpRaise(exc))

    def __iter__(self) -> FakeCoroutine:
        return self

    def __next__(self) -> Any:
        return self.send(None)

    def send(self, arg: Any) -> Any:
        '''send `arg` into fake coroutine, return next yielded value or raise
        StopIteration.'''
        if self._status == _CoStatus.RUNNING:
            raise ValueError('fake coroutine already executing')
        if self._status == _CoStatus.CLOSED:
            raise StopIteration()
        if self._status == _CoStatus.CREATED and arg is not None:
            raise TypeError("can't send non-None value to a just-started"
                            " fake coroutine")
        with self._lock:
            self._status = _CoStatus.RUNNING
            self._queue_next_throw.put(_CoOpNext(arg))
            result = self._queue_yield_raise.get()
            if isinstance(result, _CoOpYield):
                return result.value
            if isinstance(result, _CoOpRaise):
                raise result.value
            raise RuntimeError(  # pragma: no cover
                'unexpected result from fake coroutine')

    def close(self) -> None:
        '''raise GeneratorExit inside fake coroutine.'''
        if self._status == _CoStatus.RUNNING:
            raise ValueError('fake coroutine already executing')
        if self._status in [_CoStatus.CREATED,
                            _CoStatus.SUSPENDED]:
            try:
                self.throw(GeneratorExit())
            except (StopIteration, GeneratorExit):
                pass

    def __del__(self) -> None:  # pragma: no cover
        self.close()

    def throw(self, exc: Union[BaseException, type],
              value: Optional[BaseException] = None,
              # pylint: disable=invalid-name
              tb: Optional[TracebackType] = None) -> Any:
        '''throw(value)
        throw(type[,value[,tb]])

        Raise exception in fake coroutine, return next yielded value or raise
        StopIteration.'''
        if self._status == _CoStatus.RUNNING:
            raise ValueError('fake coroutine already executing')
        if self._status == _CoStatus.CLOSED:
            raise StopIteration()
        if tb is not None and not isinstance(tb, TracebackType):
            raise TypeError(
                'throw() third argument must be a traceback object')
        if isinstance(exc, BaseException):
            if value is not None:
                raise TypeError(
                    'instance exception may not have a separate value')
            value = exc.with_traceback(tb)
        elif isinstance(exc, type):
            if not issubclass(exc, BaseException):
                raise TypeError('exceptions must be classes or instances'
                                ' deriving from BaseException, not type')
            if value is None:
                value = exc()
            else:
                value = exc(value)
        else:
            raise TypeError(
                f'exceptions must be classes or instances deriving from'
                f' BaseException, not {type(exc).__name__}')
        with self._lock:
            self._status = _CoStatus.RUNNING
            self._queue_next_throw.put(_CoOpThrow(value))
            result = self._queue_yield_raise.get()
            if isinstance(result, _CoOpYield):
                return result.value
            if isinstance(result, _CoOpRaise):
                raise result.value
            raise RuntimeError(  # pragma: no cover
                'unexpected result from fake coroutine')


def fake_coro(func: Callable) -> Callable[..., FakeCoroutine]:
    '''Create a fake coroutine, which is emulated with threads.

    Fake coroutines are thread-safe but are not intended for multi-processing
    context.'''
    @functools.wraps(func)
    def inner(*args, **kwargs) -> FakeCoroutine:
        # checks whether arguments match the signature
        inspect.signature(func).bind(*args, **kwargs)
        return FakeCoroutine(func, args, kwargs)
    return inner


def _current_context() -> FakeCoroutine:
    '''Either retrieves the current fake coroutine or raises a
    `RuntimeError`.'''

    try:
        return _thread_local.context
    except AttributeError:
        # pylint: disable=raise-missing-from
        raise RuntimeError('not in fake coroutine')


# pylint: disable=protected-access
def yield_(*value: Any) -> Any:
    '''Yields the value or None and receives another value or None sent by the
    caller.

    A `RuntimeError` will be raised when called outside a fake coroutine.'''
    if len(value) == 0:
        value_or_none = None
    elif len(value) == 1:
        value_or_none = value[0]
    else:
        value_or_none = value
    context = _current_context()
    context._status = _CoStatus.SUSPENDED
    context._queue_yield_raise.put(_CoOpYield(value_or_none))
    result = context._queue_next_throw.get()
    context._status = _CoStatus.RUNNING
    if isinstance(result, _CoOpNext):
        return result.value
    if isinstance(result, _CoOpThrow):
        raise result.value
    raise RuntimeError(  # pragma: no cover
        'unexpected result from fake coroutine')


# pylint: disable=protected-access
def yield_from(coro: Union[Iterable, Generator, FakeCoroutine]) -> Any:
    '''Yields from the coroutine or fake coroutine until it stops.

    A `RuntimeError` will be raised when called outside a fake coroutine.'''
    context = _current_context()
    coro = iter(coro)
    try:
        yield_value = next(coro)
    except StopIteration as exc:
        return exc.value
    while True:
        context._status = _CoStatus.SUSPENDED
        context._queue_yield_raise.put(_CoOpYield(yield_value))
        result = context._queue_next_throw.get()
        context._status = _CoStatus.RUNNING
        if isinstance(result, _CoOpNext):
            try:
                if result.value is None:
                    yield_value = next(coro)
                else:
                    yield_value = coro.send(result.value)  # type: ignore
            except StopIteration as exc:
                return exc.value
        if isinstance(result, _CoOpThrow):
            if hasattr(coro, 'throw'):
                try:
                    yield_value = coro.throw(result.value)  # type: ignore
                except StopIteration as exc:
                    return exc.value
            else:
                raise result.value
