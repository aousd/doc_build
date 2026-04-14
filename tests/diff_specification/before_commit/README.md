# Introduction

This document is used to test the diff rendering pipeline.
It contains content that will be compared against an "after" version.

## Unchanged Section

This paragraph remains identical in both versions of the document.
It should pass through the diff pipeline with no markup applied.

## Modified Paragraphs

This is a paragraph with some words that will be changed.

The quick brown fox jumps over the lazy dog.

A short sentence.

## Headers

### This Subsection Title Will Change

The content inside this subsection also has some minor edits.

## Code Blocks

Here is a Python function:

```python
def greet(name):
    return f"Hello, {name}!"
```

## Math Blocks

This equation is unchanged in both versions:

$$
E = mc^2
$$

This equation will be modified:

$$
f(x) = x^2 + 2x + 1
$$

## Inline Math

In the range $0 \le x \le 1$, the function $f(x) = x^2$ is monotonically increasing.

## Sections

This paragraph will remain.

This entire paragraph will be deleted from the document.

Another anchor paragraph that stays unchanged.

This paragraph will also remain at the end.

## Images

An SVG image that does not change:

![Blue circle](images/unchanged.svg)

A PNG image that does not change:

![Blue box](images/unchanged.png)
