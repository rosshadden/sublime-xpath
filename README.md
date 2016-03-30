Sublime Text - XPath Plugin
============

## Features:

- Updates status bar text to XPath of first selection.
- [Copy XPath at cursor(s) to clipboard.](#copy_xpath_demo)
- Jump selection to relative tag - previous or next sibling, parent, or self. Why "self", you might ask? Because it is also possible to select the open tag, the close tag, both the opening and closing tag, the attributes in the open tag, and the entire tag contents - optionally including the tag itself.  This works for multiple selections as well, of course.
- Query XML and (X)HTML documents by XPath 1.0 expression.
  - with syntax highlighting and [intelligent auto-completion](#autocomplete_demo).
  - with a custom `print` function that can be used as a debugging aid by logging nodesets etc. to the console.
  - display results in real-time (i.e. as you type the query, fitting in perfectly with Sublime's other actions). (With an option to customize this, if desired.)
  - [move the cursor to the highlighted result.](#cursor_to_highlighted_result_demo)
  - [reference multiple context nodes](#multiple_contexts_demo) (at cursor positions) by using the `$contexts` variable.
  - [Execute a query and select all the corresponding nodes in the document.](#select_all_results_demo) (There is an entry in the command palette to re-run the previous query and select all results, but please note that it doesn't preserve the context nodes at the moment.)
  - with history, optionally globally or per document.
  - optionally normalize whitespace when displaying text results (via a setting).
  - define custom variables in the settings file.
- Show XML well-formedness parse errors, and move the cursor to the location where the error occurred.
- [Tidy HTML or "tag soup" into valid XML.](#clean_tag_soup_demo)

## Settings:

See [default settings](https://github.com/rosshadden/sublime-xpath/blob/master/xpath.sublime-settings) for details and default values.

- `show_hierarchy_only` - Whether to show only hierarchy in status bar, instead of exact xpath. i.e. `/Root/Node` instead of `/Root/Node[3]`
- `show_all_attributes` - Whether to show all attributes in the path.  If false, will use a provided whitelist.
- `case_sensitive` - Whether to ignore case when determining tag index and whether an attribute matches one defined in the whitelist.  Ignored for when querying an xpath.
- `copy_unique_path_only` - Whether to copy only unique xpaths to the clipboard when there are multiple selections.
- `attributes_to_include` - Specific attributes or namespaces to include in the XPath.
- `show_attributes_in_hierarchy` - Whether or not to include attributes when in hierarchy mode. (If `show_all_attributes` is false and the `attributes_to_include` whitelist is empty, this will have no effect.)
- `live_mode` - whether to show the results of the xpath query while it is being typed. If false, will only show the results after the user presses enter in the input box.
- `default_namespace_prefix` - the prefix to use when the xml document contains a default namespace with no prefix. e.g. `<test xmlns="http://uri/">` XPath 1.0 doesn't support blank prefixes, so, for convenience, this plugin can set one for you.
- `show_namespace_prefixes_from_query` - in case of blank namespace prefixes (see `default_namespace_prefix`) or multiple namespace URIs being referenced from the same prefix, the plugin will automatically make them unique, so that you can easily use them in a query.  If this is turned on, the xpaths that are shown in the status bar and copied to the clipboard will be directly queryable by this plugin. If this is turned off, element names in the path will reflect those in the source document.
- `only_show_xpath_if_saved` - whether or not to only show the current xpath in the status bar if the view is not dirty. This could be useful to save wasting CPU cycles (from constant parsing) when editing a document, for example.
- `max_results_to_show` - the maximum number of results to show from the xpath query.  Set to <= 0 for no limit.  Useful to speed up display of results when there are lots.
- `normalize_whitespace_in_preview` - whether or not to normalize whitespace for text results in the preview.  Defaults to `false`, because there are situations when it is important to see exact results.
- `variables` - a dictionary of custom variables, which can be used when writing an XPath query expression.
- `auto_completion_triggers` - characters that, when typed while entering an XPath expression, will automatically show autocompletions. If empty, autocompletion can still be triggered manually.
- `intelligent_auto_complete` - whether or not to include intelligent autocompletion suggestions from the document.
- `goto_element` - when an element is selected via an XPath query, which aspect of it the cursor should move to. Possible values are:
  - `open` - Select the name of the element in the open tag.
  - `close` - Select the name of the element in the close tag.
  - `names` - Select the name of the element in both the open and the close tag.
  - `open_attributes` - Select all the attributes in the open tag.
  - `content` - Select the content of the element.
  - `entire` - Select the entire element i.e. it's open tag, contents and close tag.
  - `none` - Do not move the cursor.
- `goto_attribute` - when an attribute is selected via an XPath query, which aspect of it the cursor should move to. Possible values are:
  - `name` - Select the name of the attribute.
  - `value` - Select the value (inside the quotes) of the attribute.
  - `entire` - Select the name and the value of the attribute.
  - `element` - Select the element that the attribute belongs to, using the `goto_element` rules.
  - `none` - Do not move the cursor.

No key bindings are set by default, but an example sublime-keymap file is included, to show the available commands and arguments. [See this documentation](http://docs.sublimetext.info/en/latest/customization/key_bindings.html) for more details about keybindings in ST3.

<a name="demos"></a>
## Demonstrations

- <a name="autocomplete_demo"></a>Autocompletion in action
  ![Autocompletion in action](https://cloud.githubusercontent.com/assets/11882719/12841929/245cdbd4-cbf8-11e5-8da0-26119e5213ab.gif "A demonstration of the Sublime XPath plugin, with it's intelligent auto completion")
- <a name="cursor_to_highlighted_result_demo"></a>Move cursor to a single highlighted result
  ![Move cursor to result](https://cloud.githubusercontent.com/assets/11882719/13141364/9d22053e-d63f-11e5-853a-3d2089e81664.gif "A demonstration of the Sublime XPath plugin, moving the cursor to the highlighted result")
- <a name="select_all_results_demo"></a>Example usage of selecting all the results of the previous XPath query
  ![Move cursor](https://cloud.githubusercontent.com/assets/11882719/13170898/4c3f511c-d6f8-11e5-98bd-9eeac5f71b13.gif "A demonstration of the Sublime XPath plugin, with it's cursor movement/selection helpers")
- <a name="copy_xpath_demo"></a>Copying the XPath(s) of the node(s) under the cursor(s) to the clipboard
  ![Copy XPath to clipboard](https://cloud.githubusercontent.com/assets/11882719/13170773/2dee3008-d6f7-11e5-9b93-b1c5da70cd5b.gif "A demonstration of the Sublime XPath plugin, copying the XPaths at the cursors to the clipboard")
- <a name="multiple_contexts_demo"></a>Working with multiple context nodes
  ![Multiple context nodes](https://cloud.githubusercontent.com/assets/11882719/13171045/3053e99e-d6f9-11e5-8f58-2a8cb2d7e131.gif "A demonstration of the Sublime XPath plugin, working with multiple context nodes")
- <a name="clean_tag_soup_demo"></a>Clean badly formed HTML / tag soup
  ![Clean tag soup](https://cloud.githubusercontent.com/assets/11882719/13172607/a4e74172-d701-11e5-9ff2-0aa7b9f56799.gif "A demonstration of the Sublime XPath plugin, cleaning bad HTML tag soup so that it can be queried")

## Installation

The recommended way to install the Sublime Text XPath plugin is via [Package Control](https://packagecontrol.io/packages/xpath). Package Control will install the plugin on your system and keep it up to date.

1. [Ensure Package Control is installed.](https://packagecontrol.io/installation)
1. In Sublime Text, open the `Preferences` menu, and select `Package Control`.
1. Select `Package Control: Install Package`.
1. Start typing `xpath`. When you see it, select it.
1. Wait for it to install.
1. Restart Sublime Text to be sure everything is loaded properly.
1. Enjoy!

## Troubleshooting

### CDATA Nodes

When working with XML documents, you are probably used to the Document Object Model (DOM), where CDATA nodes are separate to text nodes.  XPath sees `text()` nodes as all adjacent CDATA and text node siblings together.
If you really need to work with separate text and CDATA nodes in XPath, you will need to ensure that an XML comment separates the nodes in the source document.

Example:

    <hello><![CDATA[world]]>foobar</hello>
    <hello><![CDATA[world]]><!-- separator, so that the CDATA and text nodes are non-adjacent -->foobar</hello>

The XPath `/hello[1]/text()` on the first example will return a single text node: `worldfoobar`.  On the second example, it will return two text nodes: `world` and `foobar`.

### Namespaces

XPath 1.0 does not have the concept of a default namespace.  Therefore, if a node in the XML document being queried defines a default namespace, that namespace should be mapped to a prefix in the XPath query expression for easier access.
See the included `example_xml_ns.xml` file for more details.

### Nodes before the root element

Note that due to the way ElementTree (the Python XML module) works, comments, processing instructions or doctypes that come before the root node of the document won't be navigatable by this plugin.

## Potential future improvements:

Feature requests, bug reports/fixes and usability suggestions are always welcome.

In no particular order, here are some ideas of how this plugin could be made even more awesome:

- Optimize for when modifications to the underlying XML document are made by the user, especially changes that don't alter the document structure. Currently, the whole document is re-parsed on every tiny little change (i.e. every character press while typing). (although many changes in quick succession means it will abort an in-progress parse to start again with the latest changes included.)
- Integrate with the awesome [BracketHighlighter plugin](https://packagecontrol.io/packages/BracketHighlighter)? For efficiency - as we have already stored the location of each tag - and it will get round the large distance between tags limitation that BH has.  It could also remove some duplicate navigation functionality when both plugins are installed.
- Allow defining custom XPath functions in the sublime-settings file.
- Allow defining variables as (absolute) XPath expressions that would get evaluated into a nodeset.

## Contributors

- Ross Hadden (@rosshadden)
- Keith Hall (@keith-hall)
- @BrutalSimplicity
