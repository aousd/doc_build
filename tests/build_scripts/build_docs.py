#! /usr/bin/env python3

from doc_build.doc_builder import DocBuilder


class MyDocBuilder(DocBuilder):
    pass


if __name__ == "__main__":
    MyDocBuilder().process_argparser()
