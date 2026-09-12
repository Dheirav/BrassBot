# Rules

`Brass-Birmingham-Rulebook-2018.11.20.pdf` is the official Roxley rulebook,
version 2018.11.20, fetched on 2026-09-12 from
`http://files.roxley.com/Brass-Birmingham-Rulebook-2018.11.20-highlights.pdf`
(Roxley's own file host; plain HTTP because the certificate on that subdomain
does not match its name). Roxley describe it as a living document, so a newer
revision may exist at <https://roxley.com/products/brass-birmingham>.

The `.txt` beside it is `pdftotext -layout` output of the same file, kept so a
rule can be found with `grep` without opening the PDF. The rulebook is set in
three columns, so a passage's lines are interleaved with its neighbours' in the
text; read the PDF for the final word and use the text to find the page.

`../rules_reference_eog.txt` is the Esoteric Order of Gamers summary, v1.2
(July 2019). It is a third-party condensation, useful for a quick answer, and
not the rules themselves.

## Passages this project has had to look up

**Coal is sold to the market once, when the mine is built** (page 9):

> Coal and iron cubes may only be sold to their Markets during the action when
> their Industry tile is built. They are never sold to their Markets in later
> turns.

A coal mine sells only if connected to a merchant space at that moment; an iron
works always sells. A link built later does not trigger a sale. An empty market
changes only what a buyer pays (£8 coal, £6 iron, page 8), never whether a mine
sells.
