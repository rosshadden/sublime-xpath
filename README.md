Sublime Text 3 - XPath Plugin
============

- Copy XPath at cursor(s) to clipboard.
- Updates status bar text to XPath of current line.
- Jump selection to relative tag - previous or next sibling, parent, open or close tag

Settings:

- option to show only hierarchy in status bar, instead of exact xpath.
- optionally show attributes in the path (user can set preference to show all attributes or specify which attributes to show). **Note that this is ignored if only the hierarchy is shown.**
- option to ignore case when determining tag index and whether an attribute matches one defined in the preferences.
- option to copy only unique xpaths to the clipboard when there are multiple selections.

Potential future improvements:
- optimise writes, especially non-structure-altering changes

