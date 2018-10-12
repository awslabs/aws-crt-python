import setuptools
import os
import sys

if sys.platform == 'darwin':
    os.environ['LDFLAGS'] = '-framework Security'
    os.environ['CFLAGS'] = '-fsanitize=address -g'

_aws_crt_python = setuptools.Extension(
    '_aws_crt_python',
    language = 'c',
    define_macros = [
        ('MAJOR_VERSION', '1'),
        ('MINOR_VERSION', '0'),
    ],
    include_dirs = ['/usr/local/include', os.getenv('AWS_C_INSTALL') + '/include'],
    library_dirs = ['/usr/local/lib', os.getenv('AWS_C_INSTALL') + '/lib'],
    libraries = ['aws-c-common', 'aws-c-io', 'aws-c-mqtt'],
    sources = ['source/module.c', 'source/io.c', 'source/mqtt.c'],
    extra_compile_args=['-O0'],
)

setuptools.setup(
    name="aws_mqtt_python",
    version="0.0.1",
    author="Example Author",
    author_email="author@example.com",
    description="A small example package",
    long_description_content_type="text/markdown",
    url="https://github.com/your/butt",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    ext_modules = [_aws_crt_python],
)
