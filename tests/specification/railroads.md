```
pandoc -F doc_build/filters/filter_railroad.py tests/specification/railroads.md -o tests/artifacts/railroad.pdf --metadata-file tests/specification/build_paths.yaml --pdf-engine xelatex -V monofont=Menlo
```

```peg
VariantSelection <- LeftCurlyBrace (Space)? VariantSetName ↵
                    Assignment (VariantName)? (Space)? RightCurlyBrace
```

```peg
VariantSelection <- A / B / C
```

```peg
VariantSelection <- A / B ↵ ABC / C
```

```peg
VariantSelection <- (B) ↵ (A)
```

```peg
NonCrlfUtf8Character <- !CrLf Utf8Character
```

```peg
NonCrlfUtf8Character <- !(CrLf) Utf8Character
```

```peg
MultilineSingleQuoteContents <- Escaped / !(SingleQuote) Utf8Character
```

```peg
PrimElements <- PrimName (&(ForwardSlash PrimName) ↵
                ForwardSlash PrimName)* (VariantSelections)? /  
                
                PrimName (&(VariantSelections PrimName) ↵
                VariantSelections PrimName)* (VariantSelections)?
```

```peg
PrimElements <- (ForwardSlash PrimName ↵ ForwardSlash PrimName)* 
```