def f(**kwargs):
    print(kwargs)


def g(*args):
    print(args)


def h(something: bool, **kwargs):
    print(something)
    print(kwargs)
    i(something, **kwargs)


def i(something: bool, **kwargs):
    print(something)
    print(kwargs)


def test_args():
    g(1, "a", False)


def test_kwargs():
    f(x=1, y="a", z=False)


def test_arg_kwargs():
    h(True, x=1, y="a", z=False)
