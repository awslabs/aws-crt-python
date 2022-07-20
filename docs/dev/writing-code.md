# Writing code in aws-crt-python

`aws-crt-python` provides "language bindings", allowing Python to use the
C libraries which make up the AWS SDK Common Runtime (CRT).

This is not easy code to write. You must know Python. You must know C.
You must learn how the aws-c libraries do error handling and memory management,
you must learn how the Python C-API does error handling and memory management,
and you must mix the two styles together. This code is multithreaded and asynchronous.
Buckle up.

### Table of Contents

*   [Required Reading](#required-reading)
*   [Writing Python Code](#writing-python-code)
    *   [General](#general-python-rules)
        *   [Naming Conventions](#python-naming-conventions)
        *   [Use Type Hints](#use-type-hints)
    *   [Forward and Backward Compatibility](#forward-and-backward-compatibility)
        *   [Functions with Lots of Arguments](#functions-with-lots-of-arguments)
        *   [Use `None` for Optional Arguments](#use-none-as-the-default-value-for-optional-arguments)
        *   [Callback Signatures](#callback-signatures)
        *   [Be Careful When Adding](#be-careful-when)
    *   [Asynchronous APIs](#asynchronous-apis)
*   [Lifetime Management](#lifetime-management)
*   [Writing C Code](#writing-c-code)

## Required Reading

*   [Coding Guidelines for the aws-c Libraries](https://github.com/awslabs/aws-c-common#coding-guidelines) - TODO: FLESH THIS OUT MORE
*   [Extending Python with C](https://docs.python.org/3/extending/extending.html) -
    Tutorial from python.org. Worth reading in full.
*   [Python/C API Reference Manual](https://docs.python.org/3/c-api/index.html) -
    Docs from python.org. Choice bits are listed below.
    *   [Exception Handling](https://docs.python.org/3/c-api/exceptions.html)
    *   [Reference Counting](https://docs.python.org/3/c-api/refcounting.html)
    *   [Format strings: Python -> C](https://docs.python.org/3/c-api/arg.html) -
        Used by [PyArg_ParseTuple()](https://docs.python.org/3/c-api/arg.html#c.PyArg_ParseTuple)
    *   [Format strings: C -> Python](https://docs.python.org/3/c-api/arg.html#c.Py_BuildValue) -
        Used by [Py_BuildValue()](https://docs.python.org/3/c-api/arg.html#c.Py_BuildValue),
        [PyObject_CallMethod()](https://docs.python.org/3/c-api/call.html#c.PyObject_CallMethod),
        [PyObject_CallFunction()](https://docs.python.org/3/c-api/call.html#c.PyObject_CallFunction)
    *   [The Global Interpreter Lock (GIL)](https://docs.python.org/3/c-api/init.html#thread-state-and-the-global-interpreter-lock)


# Writing Python Code

Follow these conventions unless you have a very convincing reason not to.
We acknowledge that our existing code isn't 100% consistent at following them.
Some features we recommend now weren't available in older versions of
Python that we used to support. Some conventions are due to lessons learned
when we had a hard time making changes to something without breaking its API.
And sometimes naming is inconsistent because the code had different authors
and our conventions weren't written down yet. But going forward
let's do it right.

## General Python Rules

### Python Naming Conventions

*   Modules (files and folders) - `lowercase`
    *   Smoosh words together, if it's not too confusing.
    *   Example - `awscrt.eventstream` (NOT `aws_crt.event_stream`)
*   Classes - `UpperCamelCase`
    *   For acronyms three letters or longer, only capitalize the first letter
        *   Example: `TlsContext` (NOT `TLSContext`)
    *   Don't repeat words in the full path.
        *   Example: `awscrt.mqtt.Client` (NOT `awscrt.mqtt.MqttClient`)
*   Member variables - `snake_case`
*   Functions - `snake_case()`
*   Anything private - prefix with underscore
*   Constants and Enum values - `ALL_CAPS`
    *   Example: `MessageType.PING`
*   Time values - suffix with `_ms`, `_sec`, etc

### Use Type Hints

Use [type hints](https://docs.python.org/3/library/typing.html) in your APIs.
They help users and make it easier to write documentation.
Sadly, most of our existing code isn't using type hints because it was written
back when we supported older versions of Python
(TODO: add type hints to all our APIs).
Because type hints are newer, pay close attention in the docs before you use a feature,
to ensure it's available in our minimum supported Python version.
(TODO: add CI tests that would catch such errors)

## Forward and Backward compatibility

We need to design our APIs so that they don't break when we inevitably
add a few more configuration options to a class.
Follow these rules so we can gracefully alter the API without breaking it.

### Functions with Lots of Arguments

For functions with a lot of configuration options,
such as class `__init__()` functions, use one of the techniques below.
Complex functions inevitably get more optional arguments added over time.
Sometimes an argument even changes from required to optional.

TECHNIQUE 1 - Use [keyword-only](https://docs.python.org/3/tutorial/controlflow.html#keyword-only-arguments) arguments.
These let you introduce more arguments over time,
and they let you change an argument from required to optional.
They can also make user code more clear (i.e. `do_a_thing(ignore_errors=True)` vs `do_a_thing(True)`).
Example:
```py
class Client:
    def __init__(self, *,
                 hostname: str,  # this is required, but must be passed by keyword
                 port: int,  # again, required
                 bootstrap: ClientBootstrap = None,  # optional
                 connect_timeout_ms: int = None):  # optional
```

TECHNIQUE 2 - Use an "options class", and pass that as the only argument.
It's easy to build these as a [dataclass](https://docs.python.org/3/library/dataclasses.html).
Example:
```py
@dataclass
class ClientOptions:
    hostname: str
    port: int
    bootstrap: ClientBootstrap = None
    connect_timeout_ms: int = None

class Client:
    def __init__(self, options: ClientOptions):
```

The jury's currently out on which technique is better. Keyword arguments are graceful,
but "options classes" let us easily nest one set of options inside another set of options.

### Use `None` as the Default Value for Optional Arguments

Note in the examples above that `connect_timeout_ms` had a default value of `=None`,
instead of something concrete like `=5000`. This is a common in Python,
and a good practice besides. Default values sometimes change.
There are many aws-crt language bindings, and the fewer places something is hardcoded,
the easier it is to change. Ideally, all language bindings use `None` or similar
to represent "defaults please", which results in passing `0` or `NULL` down to C to
represent "defaults please", and then in a single location in C we set the actual default.

In documentation, just say "a default value is used" instead of writing in the actual value,
because the odds are good that the documentation will get out of sync with reality.

### Callback Signatures

Similar to how we build `__init__()` functions so that more options can be added over time,
we need to build callbacks so that more info can be passed to them in the future.

Public callbacks should take a single argument, which is built as a `dataclass`.
This gives us freedom to add members to the class in the future.

Example:
```py
@dataclass
class Message:
    topic: str
    payload: bytes

class Client:
    def __init__(self, *,
                 ...,
                 on_message_received: Callable[[Message], None] = None,
                 ...)

# and then user code looks like:
def my_on_message_received_callback(msg):
    print(f'Yay I got a Message: {msg}')
```

NOTE: Most of our existing code uses a different pattern for callbacks.
Instead of a single `dataclass` argument, multiple arguments are passed by keyword.
In documentation, we instruct the user to add `**kwargs` as the last argument in their function,
so that we are free to add more arguments over time without breaking user code.
This is weirder and more fragile than passing a single object.
Don't use this pattern unless you're adding to a class where it's already in use.

### Be careful when adding

1)  When adding arguments to a function that is NOT using keyword-only arguments,
    you MUST add new arguments to the end of the argument list.
    Otherwise you may break user code that passes arguments by position.

2)  When adding new members to a `dataclass`, you MUST add new members at the end.
    Otherwise you may break user code that initializes the class using positional arguments.
    (in Python 3.10+ there's a `kw_only` feature for `dataclass`,
    but we can't use it since we support older Python versions)

## Asynchronous APIs

TODO: document when to use future vs callback

# Lifetime Management

TODO: Write me.
Talk about Garbage Collector vs Reference Counting. Have pictures.
Talk about capsules. Talk about NativeResource. Warn about cycles.
Talk about how our tests can and cannot check for leaks.
Talk about which classes require a `close()` function, and which don't.

# Writing C Code

TODO: Write me.
Suggest writing as little C code as possible.
Recommend error-handling strategies.
Talk about the allocators (tracked vs untracked)
Talk about logging. Consider making it easier to turn on logging.
Talk about sloppy shutdown.

