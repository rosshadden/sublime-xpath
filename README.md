Sublime Text - XPath Plugin
============

## Features:

- Copy XPath at cursor(s) to clipboard.
- Updates status bar text to XPath of current line.
- Jump selection to relative tag - previous or next sibling, parent, open or close tag.


## Settings:

See [default settings](https://github.com/rosshadden/sublime-xpath/blob/master/xpath.sublime-settings) for details and default values.

- `show_hierarchy_only` - Whether to show only hierarchy in status bar, instead of exact xpath.
- `show_all_attributes` - Whether to show attributes in the path.  Can show all of them, or a provided whitelist.
> This is ignored if only the hierarchy is shown.
- `case_sensitive` - Whether to ignore case when determining tag index and whether an attribute matches one defined in the preferences.
- `copy_unique_path_only` - Whether to copy only unique xpaths to the clipboard when there are multiple selections.
- `attributes_to_include` - Specific attributes or namespaces to include in the XPath.


## Potential future improvements:

- Optimize writes, especially non-structure-altering changes.


## Contributors

- Ross Hadden (@rosshadden)
- Keith Hall (@keith-hall)
