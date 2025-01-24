import sys
import os

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(repo_root)

from doc_builder import DocBuilder

class MyDocBuilder(DocBuilder):
    pass

if __name__ == "__main__":
    MyDocBuilder().process_argparser()