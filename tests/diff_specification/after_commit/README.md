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

SVG - Removed

PNG - Removed

SVG - Added

![Added cross SVG](images/added_cross.svg)

PNG - Added

![Added cross PNG](images/added_cross.png)

SVG - Unchanged

![Unchanged circle SVG](images/unchanged_circle.svg)

PNG - Unchanged

![Unchanged circle PNG](images/unchanged_circle.png)

SVG - Changed format(caption) only

![Change format(caption: NEW) circle SVG](images/unchanged_circle.svg)

PNG - Changed format(caption) only

![Change format(caption: NEW) circle PNG](images/unchanged_circle.png)

SVG - Changed path(filename) only

![Changed path(filename) star SVG](images/changed_path-filename-dst_star.svg)

PNG - Changed path(filename) only

![Changed path(filename) star PNG](images/changed_path-filename-dst_star.png)

SVG - Changed path(directory), format(caption)

![Changed path(directory), format(caption: NEW) trapezoid SVG](figures/changed_path-dir_trapezoid.svg)

PNG - Changed path(directory), format(caption)

![Changed path(directory), format(caption: NEW) trapezoid PNG](figures/changed_path-dir_trapezoid.png)

SVG - Changed binary only

![Changed binary pentagon-to-square SVG](images/changed_binary_pentagon-to-square.svg)

PNG - Changed binary only

![Changed binary pentagon-to-square PNG](images/changed_binary_pentagon-to-square.png)

SVG - Changed binary, format(caption)

![Changed binary, format(caption: NEW) triangle-to-diamond SVG](images/changed_binary_triangle-to-diamond.svg)

PNG - Changed binary, format(caption)

![Changed binary, format(caption: NEW) triangle-to-diamond PNG](images/changed_binary_triangle-to-diamond.png)

SVG - Changed binary, path(subfolder added)

![Changed binary, path(add subfolder) hexagon-to-chevron SVG](images/sub/changed_binary_path-subdir_hexagon-to-chevron.svg)

PNG - Changed binary, path(subfolder added)

![Changed binary, path(add subfolder) hexagon-to-chevron PNG](images/sub/changed_binary_path-subdir_hexagon-to-chevron.png)

SVG - Changed binary, path(folder and filename), format(caption)

![Changed binary, path(all), format(alt path: NEW) parallelogram-to-chevron SVG](assets/images/changed_binary_path-all_octagon.svg)

PNG - Changed binary, path(folder and filename), format(caption)

![Changed binary, path(all), format(alt path: NEW) parallelogram-to-chevron PNG](assets/images/changed_binary_path-all_octagon.png)

## Numbered Lists

### Unchanged

This list is present in both versions without any modifications.

1. Alpha: this item does not change
2. Beta: this item also stays the same
3. Gamma: the final item is also unchanged

### Bit That Stays the Same

...just so that the removed and added sub-sections are not paired as a substitution.

### Added

This entire section and its list appear only in the after version.

1. This list did not exist in the previous version
2. All of these items are brand new additions
3. The entire section was inserted during this revision

### Mixed Changes

This section exists in both versions but the list has several types of changes.

1. This item will stay the same throughout both versions
2. This item is unchanged; it separates the deletion above from the replacements below
3. This item replaces the old third entry with completely new text
4. This item will have just one word modified
5. This item will also be kept in the list without any changes
6. This brand new item was added to the end of the list

### Flat to Correct Numbering

This list uses repeated "1." numbering, while the after version uses correct sequential numbers.

1. First item in this list
2. Second item in this list
3. Third item in this list
4. Fourth item in this list

### Random to Different Random Numbering

This list uses one arbitrary numbering scheme; the after version uses a different arbitrary scheme.

4. First item in this list
2. Second item in this list
1. Third item in this list
6. Fourth item in this list

## Unordered Lists

### Unchanged

This list is present in both versions without any modifications.

- Alpha: this item does not change
- Beta: this item also stays the same
- Gamma: the final item is also unchanged

### Bit That Stays the Same

...just so that the removed and added sub-sections are not paired as a substitution.

### Added

This entire section and its list appear only in the after version.

- This list did not exist in the previous version
- All of these items are brand new additions
- The entire section was inserted during this revision

### Mixed Changes

This section exists in both versions but the list has several types of changes.

- This item will stay the same throughout both versions
- This item is unchanged; it separates the deletion above from the replacements below
- This item replaces the old third entry with completely new text
- This item will have just one word modified

- This item contains a blockquote that will be modified:

    > This blockquote content comes from the after version.

- This item contains a code block that will be modified:

    ```python
    result = new_function()
    ```

- This item contains a blockquote with a nested code block that will be modified:

    > Text before the nested code block.
    >
    > ```python
    > nested = new_nested()
    > ```
    >
    > Text after the nested code block.

- This item will also be kept in the list without any changes
- This brand new item was added to the end of the list

## Block Quotes

### Unchanged

This blockquote is identical in both versions.

> This blockquote paragraph is unchanged throughout both versions.
>
> This second paragraph is also identical in before and after.

### Bit That Stays the Same

...just so that the removed and added sub-sections are not paired as a substitution.

### Added

This entire section and its blockquote appear only in the after version.

> This blockquote did not exist in the previous version.
>
> All of these paragraphs are brand new additions.

### Changed Block Quote With Code Block

This blockquote contains a nested code block and will be modified.

> Some introductory text before the code.
>
> ```python
> result = new_function()
> ```
>
> Some concluding text after the code.

### Mixed Changes

This blockquote exists in both versions but has internal changes.

> This paragraph will stay the same throughout both versions.
>
> This paragraph is unchanged; it separates the deletion above from the replacements below.
>
> This paragraph replaces the old fourth entry with completely new text.
>
> This paragraph will have just one word modified.
>
> This final paragraph will also be kept without any changes.

## Line Blocks

### Unchanged

This line block is identical in both versions.

| This line is unchanged throughout both versions.
| This line is also identical in before and after.
| This final line remains the same as well.

### Bit That Stays the Same

...just so that the removed and added sub-sections are not paired as a substitution.

### Added

This entire section and its line block appear only in the after version.

| This line block did not exist in the previous version.
| All of these lines are brand new additions.
| The entire section was inserted during this revision.

### Mixed Changes

This line block exists in both versions but has internal changes.

| This line will stay the same throughout both versions.
| This line is unchanged; it separates the deletion above from the replacements below.
| This line replaces the old fourth entry with completely new text.
| This line will have just one word modified.
| This final line will also be kept without any changes.

## Deeply Nested Structures

### Multi-Level Bulleted List

A two-level list where only one sub-item changes.

- Top-level item A: unchanged throughout both versions
- Top-level item B: has sub-items that will change
    - Sub-item B1: this sub-item is unchanged
    - Sub-item B2: this sub-item has been modified
    - Sub-item B3: this sub-item is also unchanged
- Top-level item C: unchanged throughout both versions

### Nested Block Quotes

A blockquote that contains another blockquote; only the inner one changes.

> This outer paragraph is unchanged.
>
> > This inner blockquote paragraph has been modified.
>
> This other outer paragraph is also unchanged.

### List Inside Block Quote

A blockquote that contains a bulleted list; only one list item changes.

> This introductory paragraph is unchanged.
>
> - This list item is unchanged throughout both versions.
> - This list item has been modified.
> - This list item is also unchanged.

### Block Quote Inside Nested List

A blockquote three levels deep (list item > sub-item > blockquote); only the quote text changes.

- This top-level item is unchanged.
- This item has nested sub-items:
    - This sub-item is unchanged.
    - This sub-item has a blockquote that will change:

        > The after version of this deeply nested blockquote.

    - This sub-item is also unchanged.
- This last top-level item is also unchanged.

### Four-Level Mixed List

A four-level mixed list (bullet > numbered > bullet > numbered) where only the deepest item changes.

- Top-level bullet A: unchanged throughout both versions
- Top-level bullet B: has a numbered sub-list
    1. Numbered B1: unchanged
    2. Numbered B2: has a bullet sub-sub-list
        - Bullet B2a: unchanged
        - Bullet B2b: has a numbered sub-sub-sub-list
            1. Deepest item: unchanged
            2. Deepest item: this one has been modified
            3. Deepest item: also unchanged
        - Bullet B2c: unchanged
    3. Numbered B3: unchanged
- Top-level bullet C: unchanged throughout both versions
