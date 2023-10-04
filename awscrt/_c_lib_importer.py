"""
Our python files MUST import _awscrt like this:
```
from awscrt._c_lib_importer import _awscrt
```

to ensure that _awscrt.init_c_library_with_python_stuff(...)
is called before any other C function.

Unfortunately, we can get circular dependencies when the "python stuff" is defined
in another file that also needs to import _c_lib_importer.
If this happens to you, hack around it like this:
```
# putting this import at end of file to work around circular dependency
from awscrt._c_lib_importer import _awscrt  # noqa
```

But this should be rare, importing at the start of the
file should work in most cases.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
from awscrt.exceptions import AwsCrtError


_awscrt.init_c_library_with_python_stuff(AwsCrtError)
