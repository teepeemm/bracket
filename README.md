
This repository analyzes elimination tournaments in Wikipedia,
and is the source for a forthcoming paper.
If you're not as programmatically inclined,
you can use a 
[GUI with JavaScript](https://sites.und.edu/timothy.prescott/bracket/)

There are two main novel contributions of this repository:
1. The various tournaments in `tourneys.json`
2. The name normalization in `university.py`

I've tried to be consistent on how to handle renaming and merging,
but may not have entirely succeeded.
It's also possible that a .txt file was downloaded
under slightly different conditions in `tourneys.json`.

To run script this yourself, you will need the Python module pywikibot
(available via pip).  You will also need numpy and pandas.

From start to finish, the script takes about 30 (wild guess) minutes.
But it saves its results along the way,
so if you get bored you can interrupt and restart the process.
You can also do this if Pywikibot's throttling starts to become too onerous.

There are a large number of files created along the way that are .gitignored:
* {group}/{tournament}/{year}.txt: the content of that year's entry in Wikipedia
* {group}/{tournament}/None.txt: same as above,
but all the tournaments are on one page 
* [group/[tournament/]]state.csv Each (normalized) university and its state
* [group/[tournament/]]winloss.csv The matrix of counts of seed <row> defeating seed <column>
* {group}/{tournament}/winlossplot.tex
* {group}/{tournament}/winlossprobs.tex

Reseeding files:
* [group/[tournament/]]reseed.csv How much each university should be reseeded
* [group/]reseed_filtered.csv Same as reseed, but trimmed down
so that points unplotted by TeX don't appear (it had trouble with the file size)
* [group/]reseed_approx.csv Same as reseed, but a linear approximation of its components
* [group/[tournament/]]state_reseed.csv Same as reseed, but grouped by state
* [group/[tournament/]]tz_reseed.csv Same as reseed, but grouped by timezone
