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

SVG - Unchanged

![Unchanged circle SVG](images/unchanged_circle.svg)

PNG - Unchanged

![Unchanged circle PNG](images/unchanged_circle.png)

## Numbered Lists

### Unchanged

This list is present in both versions without any modifications.

1. Alpha: this item does not change
2. Beta: this item also stays the same
3. Gamma: the final item is also unchanged

### Removed

This entire section and its list are present only in the before version.

1. This list will be completely removed
2. None of these items survive to the after version
3. The entire section disappears in the next revision

### Bit That Stays the Same

...just so that the removed and added sub-sections are not paired as a substitution.

### Mixed Changes

This section exists in both versions but the list has several types of changes.

1. This item will stay the same throughout both versions
2. This item will be completely removed from the list
3. This item is unchanged; it separates the deletion above from the replacements below
4. This item will be fully replaced with entirely different content
5. This item will have just one word altered
6. This item will also be kept in the list without any changes

### Flat to Correct Numbering

This list uses repeated "1." numbering, while the after version uses correct sequential numbers.

1. First item in this list
1. Second item in this list
1. Third item in this list
1. Fourth item in this list

### Random to Different Random Numbering

This list uses one arbitrary numbering scheme; the after version uses a different arbitrary scheme.

3. First item in this list
1. Second item in this list
5. Third item in this list
2. Fourth item in this list

## Unordered Lists

### Unchanged

This list is present in both versions without any modifications.

- Alpha: this item does not change
- Beta: this item also stays the same
- Gamma: the final item is also unchanged

### Removed

This entire section and its list are present only in the before version.

- This list will be completely removed
- None of these items survive to the after version
- The entire section disappears in the next revision

### Bit That Stays the Same

...just so that the removed and added sub-sections are not paired as a substitution.

### Mixed Changes

This section exists in both versions but the list has several types of changes.

- This item will stay the same throughout both versions
- This item will be completely removed from the list
- This item is unchanged; it separates the deletion above from the replacements below
- This item will be fully replaced with entirely different content
- This item will have just one word altered
- This item will also be kept in the list without any changes

## Line Blocks

### Unchanged

This line block is identical in both versions.

| This line is unchanged throughout both versions.
| This line is also identical in before and after.
| This final line remains the same as well.

### Removed

This entire section and its line block are present only in the before version.

| This line block will be completely removed.
| None of these lines survive to the after version.
| The entire section disappears in the next revision.

### Bit That Stays the Same

...just so that the removed and added sub-sections are not paired as a substitution.

### Mixed Changes

This line block exists in both versions but has internal changes.

| This line will stay the same throughout both versions.
| This line will be completely removed from the line block.
| This line is unchanged; it separates the deletion above from the replacements below.
| This line will be fully replaced with entirely different content.
| This line will have just one word altered.
| This final line will also be kept without any changes.
