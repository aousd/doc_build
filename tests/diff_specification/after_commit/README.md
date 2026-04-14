# Introduction

This document is used to test the diff rendering pipeline.
It contains content that will be compared against an "after" version.

## Unchanged Section

This paragraph remains identical in both versions of the document.
It should pass through the diff pipeline with no markup applied.

## Modified Paragraphs

This is a paragraph with some **different** words that have been updated.

A speedy red fox leaps over the tired old dog.

A longer sentence with additional words added here.

## Headers

### This Subsection Title Has Been Renamed

The content inside this subsection has some minor edits applied to it.

## Code Blocks

Here is an updated Python function:

```python
def greet(name, greeting="Hello"):
    return f"{greeting}, {name}!"

print(greet("World"))
```

## Math Blocks

This equation is unchanged in both versions:

$$
E = mc^2
$$

This equation will be modified:

$$
f(x) = (x + 1)^2
$$

## Inline Math

In the range $0 \le x \le 2$, the function $f(x) = \sqrt{x}$ is monotonically increasing.

## Sections

This paragraph will remain.

Another anchor paragraph that stays unchanged.

This is a brand new paragraph inserted into the document.

This paragraph will also remain at the end.

## Images

An SVG image that does not change:

![Blue circle](images/unchanged.svg)

A PNG image that does not change:

![Blue box](images/unchanged.png)
