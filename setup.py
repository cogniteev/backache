from setuptools import setup, find_packages

module_name = 'backache'
description = "Resource Transformation Cache"
root_url = 'https://github.com/cogniteev/' + module_name

# Extract version from module __init__.py
init_file = '{}/__init__.py'.format(module_name.replace('-', '_').lower())
__version__ = None
with open(init_file) as istr:
    for l in istr:
        if l.startswith('__version__ = '):
            exec(l)
            break
version = '.'.join(map(str, __version__))
setup(
    name=module_name,
    version=version,
    description='Docido software development kit for Python',
    author='Cogniteev',
    author_email='tech@cogniteev.com',
    url=root_url,
    download_url=root_url + '/archive/v' + version + '.tar.gz',
    license='Apache license version 2.0',
    keywords='cogniteev docido',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Topic :: Software Development :: Libraries',
        'Topic :: Internet :: WWW/HTTP :: Indexing/Search',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Operating System :: OS Independent',
        'Natural Language :: English',
    ],
    packages=find_packages(exclude=['*.tests']),
    zip_safe=True,
    install_requires=[
        'pymongo==2.7.2',
        'redis>=2.10.3',
        'setuptools>=0.6',
    ],
    entry_points="""
    """
)
