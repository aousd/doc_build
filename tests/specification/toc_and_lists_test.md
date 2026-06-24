# TOC width and list depth test

This file tests two LaTeX issues:

1. TOC number column overflow with double-digit section numbers (issue #97)
2. Deep list nesting beyond 4 levels (issue #98)

## TOC overflow test sections

The following sections have double-digit numbers that will overflow the default
TOC number column width.

# Section 1

Content for section 1.

## Section 1.1

Content for section 1.1.

## Section 1.2

Content for section 1.2.

# Section 2

Content for section 2.

## Section 2.1

Content for section 2.1.

# Section 3

Content for section 3.

## Section 3.1

Content for section 3.1.

# Section 4

Content for section 4.

## Section 4.1

Content for section 4.1.

# Section 5

Content for section 5.

## Section 5.1

Content for section 5.1.

# Section 6

Content for section 6.

## Section 6.1

Content for section 6.1.

# Section 7

Content for section 7.

## Section 7.1

Content for section 7.1.

# Section 8

Content for section 8.

## Section 8.1

Content for section 8.1.

# Section 9

Content for section 9.

## Section 9.1

Content for section 9.1.

# Section 10

Content for section 10.

## Section 10.1

Content for section 10.1.

## Section 10.2

Content for section 10.2.

### Section 10.2.1

Content for section 10.2.1.

# Section 11

Content for section 11.

## Section 11.1

Content for section 11.1.

# Section 12

Content for section 12.

## Section 12.1

Content for section 12.1.

## Section 12.2

Content for section 12.2.

### Section 12.2.1

Content for section 12.2.1.

### Section 12.2.2

Content for section 12.2.2.

# Section 13

Content for section 13.

## Section 13.1

Content for section 13.1.

# Section 14

Content for section 14.

# Section 15

Content for section 15.

## Section 15.1

Content for section 15.1.

## Section 15.2

Content for section 15.2.

# Section 16

Content for section 16.

# Section 17

Content for section 17.

## Section 17.1

Content for section 17.1.

# Section 18

Content for section 18.

# Section 19

Content for section 19.

## Section 19.1

Content for section 19.1.

# Section 20

Content for section 20.

## Section 20.1

Content for section 20.1.

### Section 20.1.1

Content for section 20.1.1.

# Foreword {.unnumbered}

This is a simulated ISO foreword that should appear in the TOC without a
section number and without extra left padding.

# Deep list nesting test

This section tests list nesting beyond 4 levels, which causes a "Too deeply
nested" error in default LaTeX.

- Level 1 item
    - Level 2 item
        - Level 3 item
            - Level 4 item
                - Level 5 item (this should fail without enumitem)
                    - Level 6 item
                        - Level 7 item

1. Ordered level 1
    1. Ordered level 2
        1. Ordered level 3
            1. Ordered level 4
                1. Ordered level 5 (this should also fail)
                    1. Ordered level 6
