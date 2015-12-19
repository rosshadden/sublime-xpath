Sublime Text - XPath Plugin
============

## Features:

- Copy XPath at cursor(s) to clipboard.
- Updates status bar text to XPath of current line.
- Jump selection to relative tag - previous or next sibling, parent, open or close tag. It is also possible to select the entire tag contents, optionally including the tag itself.  This works for multiple selections as well, of course.
- Query XML and (X)HTML documents by XPath 1.0 expression.
  - with syntax highlighting
  - with a custom `print` function that can be used as a debugging aid by logging nodesets etc. to the console
  - option to display results or select the nodes in the document
  - optionally normalize whitespace when displaying text results (via a setting)
  - with history, optionally globally or per document
- Show XML well-formedness parse errors, and move the cursor to the location where the error occurred.
- Tidy HTML files into valid XML. (currently only accessible when the XML parser cannot parse the document (or via the python console for advanced users))

## Settings:

See [default settings](https://github.com/rosshadden/sublime-xpath/blob/master/xpath.sublime-settings) for details and default values.

- `show_hierarchy_only` - Whether to show only hierarchy in status bar, instead of exact xpath.
- `show_all_attributes` - Whether to show all attributes in the path.  If false, will use a provided whitelist.
- `case_sensitive` - Whether to ignore case when determining tag index and whether an attribute matches one defined in the whitelist.  Ignored for when querying an xpath.
- `copy_unique_path_only` - Whether to copy only unique xpaths to the clipboard when there are multiple selections.
- `attributes_to_include` - Specific attributes or namespaces to include in the XPath.
- `show_attributes_in_hierarchy` - Whether or not to include attributes when in hierarchy mode. (If `show_all_attributes` is false and the `attributes_to_include` whitelist is empty, this will have no effect.)
- `live_mode` - whether to show the results of the xpath query while it is being typed. If false, will only show the results after the user presses enter in the input box.
- `show_query_results` - whether or not to show the results of the xpath query. If false, the cursor will move directly to all results.  If the xpath query does not return a nodeset, the results are always displayed, regardless of this setting.
- `relative_mode` - whether or not to perform the xpath query using the cursors as the context nodes. If false, the context will be the document root.  Therefore, to use this, it is best to disable `live_mode`.
- `default_namespace_prefix` - the prefix to use when the xml document contains a default namespace with no prefix. e.g. `<test xmlns="http://uri/">` XPath 1.0 doesn't support blank prefixes, so, for convenience, this plugin can set one for you.
- `show_namespace_prefixes_from_query` - in case of blank namespace prefixes (see `default_namespace_prefix`) or multiple namespace URIs being referenced from the same prefix, the plugin will automatically make them unique, so that you can easily use them in a query.  If this is turned on, the xpaths that are shown in the status bar and copied to the clipboard will be directly queryable by this plugin. If this is turned off, element names in the path will reflect those in the source document.
- `only_show_xpath_if_saved` - whether or not to only show the current xpath in the status bar if the view is not dirty. This could be useful to save wasting CPU cycles (from constant parsing) when editing a document, for example.
- `max_results_to_show` - the maximum number of results to show from the xpath query.  Set to <= 0 for no limit.  Useful to speed up display of results when there are lots.
- `normalize_whitespace_in_preview` - whether or not to normalize whitespace for text results in the preview.  Defaults to `false`, because there are situations when it is important to see exact results.

## Potential future improvements:

- Optimize writes, especially non-structure-altering changes.

## Contributors

- Ross Hadden (@rosshadden)
- Keith Hall (@keith-hall)
- @BrutalSimplicity
