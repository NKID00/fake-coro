![workflow status](https://img.shields.io/github/actions/workflow/status/NKID00/fake-coro/test.yaml) ![codecov](https://codecov.io/gh/NKID00/fake-coro/branch/master/graph/badge.svg?token=JENJTW0BLG)

This module provides fake coroutines that are not coroutines but act like coroutines.

```
>>> from fake_coro import fake_coro, yield_
>>> @fake_coro
... def fib(limit):
...     a, b = 1, 1
...     while a < limit:
...         yield_(a)
...         a, b = b, a + b
>>> list(fib(10))
[1, 1, 2, 3, 5, 8]
```

Other features of classic coroutines are also supported:

```
>>> @fake_coro
... def my_coro():
...     return 42
>>> next(my_coro())
Traceback (most recent call last):
  ...
StopIteration: 42
```

Also `.send`, `.throw` and `.close`:

```
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
```

And sub-coroutines:

```
>>> from fake_coro import yield_from
>>> @fake_coro
... def chain(*iterables):
...     for iterable in iterables:
...         yield_from(iterable)
>>> list(chain(range(3), range(5)))
[0, 1, 2, 0, 1, 2, 3, 4]
```

Fake coroutines are implemented by threads and obviously perform much worse than native classic coroutines. However, normal functions invoked by fake coroutines can also yield like coroutines:

```
>>> @fake_coro
... def foo():
...     bar()
...     yield_(2)
>>> def bar():
...     yield_(1)  # bar is not a coroutine but can yield!
>>> list(foo())
[1, 2]
```
