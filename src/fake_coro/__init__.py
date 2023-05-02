'''Coroutines emulated with threads.'''

from __future__ import annotations
from typing import Callable, Any, Iterable, Mapping, Union, Optional
from types import TracebackType
from queue import Queue
from dataclasses import dataclass
import functools
import threading
import enum
import inspect

__all__ = ['FakeCoroutine', 'fake_coro', 'yield_', 'await_']


@enum.unique
class _CoStatus(enum.Enum):
    CREATED = enum.auto()
    RUNNING = enum.auto()
    YIELDED = enum.auto()
    STOPPED = enum.auto()


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
                self._status = _CoStatus.STOPPED
                self._queue_yield_raise.put(_CoOpRaise(exc))
                return
        else:
            self._queue_next_throw.put(_CoOpRaise(
                RuntimeError('unexpected result from fake coroutine')))
            return
        try:
            raise StopIteration(func(*args, **kwargs))
        except BaseException as exc:  # pylint: disable=broad-exception-caught
            self._status = _CoStatus.STOPPED
            self._queue_yield_raise.put(_CoOpRaise(exc))

    def __iter__(self) -> FakeCoroutine:
        return self

    def __next__(self) -> Any:
        return self.send(None)

    def send(self, arg: Any) -> Any:
        '''send `arg` into fake coroutine, return next yielded value or raise
        StopIteration.'''
        with self._lock:
            if self._status == _CoStatus.RUNNING:
                raise ValueError('fake coroutine already executing')
            if self._status == _CoStatus.STOPPED:
                raise StopIteration()
            if self._status == _CoStatus.CREATED and arg is not None:
                raise TypeError("can't send non-None value to a just-started"
                                " fake coroutine")
            self._status = _CoStatus.RUNNING
            self._queue_next_throw.put(_CoOpNext(arg))
            result = self._queue_yield_raise.get()
            if isinstance(result, _CoOpYield):
                return result.value
            if isinstance(result, _CoOpRaise):
                raise result.value
            raise RuntimeError('unexpected result from fake coroutine')

    def close(self) -> None:
        '''close() -> raise GeneratorExit inside fake coroutine.'''
        self.throw(GeneratorExit())

    def __del__(self) -> None:
        if self._status in [_CoStatus.CREATED,
                            _CoStatus.YIELDED]:
            self.close()

    def throw(self, exc: Union[BaseException, type],
              value: Optional[BaseException] = None,
              # pylint: disable=invalid-name
              tb: Optional[TracebackType] = None) -> Any:
        '''throw(value)
        throw(type[,value[,tb]])

        Raise exception in fake coroutine, return next yielded value or raise
        StopIteration.'''
        with self._lock:
            if self._status == _CoStatus.RUNNING:
                raise ValueError('fake coroutine already executing')
            if self._status == _CoStatus.STOPPED:
                raise StopIteration()
            if not isinstance(tb, Optional[TracebackType]):  # type: ignore
                raise TypeError(
                    'throw() third argument must be a traceback object')
            if isinstance(exc, BaseException):
                if value is not None:
                    raise TypeError(
                        'instance exception may not have a separate value')
                value = exc.with_traceback(tb)
            elif isinstance(exc, type):
                if value is None:
                    value = exc()
                value = value.with_traceback(tb)
            else:
                raise TypeError(
                    f'exceptions must be classes or instances deriving from'
                    f'BaseException, not {type(value)}')
            self._status = _CoStatus.RUNNING
            self._queue_next_throw.put(_CoOpThrow(value))
            result = self._queue_yield_raise.get()
            if isinstance(result, _CoOpYield):
                return result.value
            if isinstance(result, _CoOpRaise):
                raise result.value
            raise RuntimeError('unexpected result from fake coroutine')


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
def yield_(value: Any = None) -> Any:
    '''Yields from the current fake coroutine with or without a value and
    optionally receives the value sent by the caller.

    A `RuntimeError` will be raised when called outside a fake coroutine.'''

    context = _current_context()
    context._status = _CoStatus.YIELDED
    context._queue_yield_raise.put(_CoOpYield(value))
    result = context._queue_next_throw.get()
    if isinstance(result, _CoOpNext):
        return result.value
    if isinstance(result, _CoOpThrow):
        raise result.value
    else:
        raise RuntimeError('unexpected result from fake coroutine')


def await_(coro: FakeCoroutine) -> Any:
    context = _current_context()
