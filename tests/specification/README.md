# Specification Test

This document is a specification test for the [AOUSD](https://www.aousd.org) website.
Following this is a link to the [Math Tests](#math-tests) section.

It exists to test common setups across multiple AOUSD repos 
and to ensure we reduce the risk of regressions.

It is also a quick testbed for functionality.

1. [Inlined](Inlined.md)

# Math Tests

This section tests some math formatting.

## Latex Double Dollar Signs


$$\left( \sum_{k=1}^n a_k b_k \right)^2 \leq \left( \sum_{k=1}^n a_k^2 \right) \left( \sum_{k=1}^n b_k^2 \right)$$

This is a block that starts on the next line

$$
\left( \sum_{k=1}^n a_k b_k \right)^2 \leq \left( \sum_{k=1}^n a_k^2 \right) \left( \sum_{k=1}^n b_k^2 \right)
$$

Testing aligned math with a new line after


$$
\begin{aligned}
C_1 = (appended: [10, 50], prepended: [10], deleted: [50])\\ 
C_2 = (appended: [10, 50], prepended: [10], deleted: [])\\ 
C_3 = (appended: [10, 50], prepended: [], deleted: [])\\  
C_4 = (appended: [10, 50], prepended: [], deleted: [50])\\ 
C_5 = (appended: [10, 50], prepended: [10, 50], deleted: [50])\\ 
C_6 = (appended: [10, 50], prepended: [10, 50], deleted: [10, 50])\\ 
C_1 \cong C_2 \cong C_3 \cong C_4 \cong C_5 \cong C_6
\end{aligned}
$$

Testing math without a newline
A single list operation `L` is either “explicit” or “composable”.
$$
L \equiv E | C
$$


## CodeBlock

```math
\left( \sum_{k=1}^n a_k b_k \right)^2 \leq \left( \sum_{k=1}^n a_k^2 \right) \left( \sum_{k=1}^n b_k^2 \right)
```

Here's another test with some extra characters

$$
\begin{aligned}
\bigsqcup\langle L_0, …, L_n\rangle &\cong \bigsqcup\langle L_0, …, L_n \smallsetminus I^\prime\rangle\\
\bigsqcup\langle A, I^\prime, B, C, I^\prime\rangle &\cong \bigsqcup\langle A, B, C\rangle
\end{aligned}
$$

## Inline math 

This sentence uses `$` delimiters to show math inline: $\sqrt{3x-1}+(1+x)^2$

And another using the Github `$`and backtick delimitter $`\sqrt{3x-1}+(1+x)^2`$

Testing mathtt and mathrm

```math
\mathtt{foo}
\mathrm{bar}
```
