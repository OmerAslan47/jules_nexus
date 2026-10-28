import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

def test_module_syntax():
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
    for f in os.listdir(src_dir):
        if f.endswith('.py'):
            with open(os.path.join(src_dir, f), 'r', encoding='utf-8', errors='ignore') as fp:
                code = fp.read()
                compile(code, f, 'exec')
