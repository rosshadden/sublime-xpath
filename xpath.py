import sublime
import sublime_plugin
import os
from lxml import etree
from xml.sax import SAXParseException
import re
from .lxml_parser import *
from .sublime_lxml import *

change_counters = {}
xml_trees = {}
previous_first_selection = {}
settings = None
parse_error = 'XPath - error parsing XML: '
html_cleaning_answer = {}

def settingsChanged():
    """Clear change counters and cached xpath regions for all views, and reparse xml regions for the current view."""
    global change_counters
    global xml_trees
    global previous_first_selection
    change_counters.clear()
    xml_trees.clear()
    previous_first_selection.clear()
    updateStatusToCurrentXPathIfSGML(sublime.active_window().active_view())

def getSGMLRegions(view):
    """Find all xml and html scopes in the specified view."""
    return view.find_by_selector('text.xml') + view.find_by_selector('text.html') # TODO: exclude text.html.markdown, but allow include html or xml code regions in markdown

def containsSGML(view):
    """Return True if the view contains XML or HTML syntax."""
    return len(getSGMLRegions(view)) > 0

def getSGMLRegionsContainingCursors(view):
    """Find the SGML region(s) that the cursor(s) are in for the specified view."""
    cursors = [cursor for cursor in view.sel()] # can't use `view.sel()[:]` because it gives an error `TypeError: an integer is required`
    regions = getSGMLRegions(view)
    for region_index, region in enumerate(regions):
        cursors_to_remove = []
        for cursor in cursors:
            if region.contains(cursor):
                yield (region, region_index, cursor)
                cursors_to_remove.append(cursor)
            elif region.begin() > cursor.end(): # cursor before this region
                cursors_to_remove.append(cursor)
            elif cursor.begin() > region.end(): # found all cursors in this region
                break
        if region_index < len(regions) - 1: # no point removing cursors from those left to find if no regions left to search through
            for cursor in cursors_to_remove:
                cursors.remove(cursor)
            if len(cursors) == 0:
                break

def isCursorInsideSGML(view):
    """Return True if at least one cursor is within XML or HTML syntax."""
    return next(getSGMLRegionsContainingCursors(view), None) is not None

def buildTreesForView(view):
    """Create an xml tree for each XML region in the specified view."""
    trees = []
    for region in getSGMLRegions(view):
        trees.append(buildTreeForViewRegion(view, region))
    return trees

def buildTreeForViewRegion(view, region_scope):
    """Create an xml tree for the XML in the specified view region."""
    xml_string = view.substr(region_scope)
    tree = None
    line_number_offset = view.rowcol(region_scope.begin())[0]
    try:
        tree = lxml_etree_parse_xml_string_with_location(xml_string, line_number_offset)
    except SAXParseException as e:
        global parse_error
        text = str(e.getLineNumber() - 1 + line_number_offset) + ':' + str(e.getColumnNumber()) + ' - ' + e.getMessage()
        view.set_status('xpath_error', parse_error + text)
    
    return tree

def ensureTreeCacheIsCurrent(view):
    """If the document has been modified since the xml was parsed, parse it again to recreate the trees."""
    global change_counters
    new_count = view.change_count()
    old_count = change_counters.get(view.id(), None)
    
    global xml_trees
    if old_count is None or new_count > old_count:
        change_counters[view.id()] = new_count
        view.set_status('xpath', 'XML being parsed...')
        view.erase_status('xpath_error')
        trees = buildTreesForView(view)
        view.erase_status('xpath')
        xml_trees[view.id()] = trees
        global previous_first_selection
        previous_first_selection[view.id()] = None
    return xml_trees[view.id()]

class GotoXmlParseErrorCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args):
        view = self.view
        
        global parse_error
        detail = view.get_status('xpath_error')[len(parse_error):].split(' - ')[0].split(':')
        
        point = view.text_point(int(detail[0]), int(detail[1]))
        
        view.sel().clear()
        view.sel().add(point)
        
        view.show_at_center(point)
    def is_enabled(self, **args):
        global parse_error
        return containsSGML(self.view) and self.view.get_status('xpath_error').startswith(parse_error)
    def is_visible(self, **args):
        return containsSGML(self.view)

def getXPathOfNodes(nodes, args):
    global ns_loc
    
    include_indexes = not getBoolValueFromArgsOrSettings('show_hierarchy_only', args, False)
    unique = getBoolValueFromArgsOrSettings('copy_unique_path_only', args, True)
    include_attributes = include_indexes or getBoolValueFromArgsOrSettings('show_attributes_in_hierarchy', args, False)
    show_namespace_prefixes_from_query = getBoolValueFromArgsOrSettings('show_namespace_prefixes_from_query', args, False)
    case_sensitive = getBoolValueFromArgsOrSettings('case_sensitive', args, False)
    all_attributes = getBoolValueFromArgsOrSettings('show_all_attributes', args, False)
    
    global settings
    wanted_attributes = settings.get('attributes_to_include', [])
    if not case_sensitive:
        wanted_attributes = [attrib.lower() for attrib in wanted_attributes]
    
    def getTagNameWithMappedPrefix(node, namespaces):
        tag = getTagName(node)
        if show_namespace_prefixes_from_query and tag[0] is not None: # if the element belongs to a namespace
            prefix = next((prefix for prefix in namespaces.keys() if namespaces[prefix] == tag[0]), None) # find the first prefix in the map that relates to this uri
            if prefix is not None:
                tag = (tag[0], tag[1], prefix + ':' + tag[1]) # ensure that the path we display can be used to query the element
        
        if not case_sensitive:
            tag = (tag[0], tag[1].lower(), tag[2].lower())
        
        return tag
    
    def getNodePathPart(node, namespaces):
        tag = getTagNameWithMappedPrefix(node, namespaces)
        
        output = tag[2]
        
        if include_indexes:
            siblings = node.itersiblings(preceding = True)
            index = 1
            
            def compare(sibling):
                sibling_tag = getTagNameWithMappedPrefix(sibling, namespaces)
                return sibling_tag == tag # namespace uri, prefix and tag name must all match
            
            for sibling in siblings:
                if compare(sibling):
                    index += 1
            
            # if there are no previous sibling matches, check next siblings to see if we should index this node
            multiple = index > 1
            if not multiple:
                siblings = node.itersiblings()
                for sibling in siblings:
                    if compare(sibling):
                        multiple = True
                        break
            
            if multiple:
                output += '[' + str(index) + ']'
        
        if include_attributes:
            attributes_to_show = []
            for attr_name in node.attrib:
                include_attribue = False
                if not attr_name.startswith('{' + ns_loc + '}'):
                    if all_attributes:
                        include_attribute = True
                    else:
                        if not case_sensitive:
                            attr_name = attr_name.lower()
                        attr = attr_name.split(':')
                        include_attribute = attr_name in wanted_attributes 
                        if not include_attribue and len(attr) == 2:
                            include_attribue = attr[0] + ':*' in wanted_attributes or '*:' + attr[1] in wanted_attributes
                    
                    if include_attribute:
                        attributes_to_show.append('@' + attr_name + ' = "' + node.get(attr_name) + '"')
            
            if len(attributes_to_show) > 0:
                output += '[' + ' and '.join(attributes_to_show) + ']'
        
        return output
    
    def getNodePathSegments(node, namespaces, root):
        while node != root:
            yield getNodePathPart(node, namespaces)
            node = node.getparent()
        yield getNodePathPart(node, namespaces)
        yield ''
    
    def getNodePath(node, namespaces, root):
        return '/'.join(reversed(list(getNodePathSegments(node, namespaces, root))))
    
    
    defaultNamespacePrefix = settings.get('default_namespace_prefix', 'default')
    
    roots = {}
    for node in nodes:
        tree = node.getroottree()
        root = tree.getroot()
        roots.setdefault(root, []).append(node)
    
    namespaces = {}
    for root in roots:
        nsmap = None
        if show_namespace_prefixes_from_query:
            nsmap = makeNamespacePrefixesUniqueWithNumericSuffix(get_all_namespaces_in_tree(root.getroottree()), defaultNamespacePrefix)
        namespaces[root] = nsmap
    
    paths = []
    for root in roots.keys():
        for node in roots[root]:
            paths.append(getNodePath(node, namespaces[root], root))
    
    if unique:
        paths = list(getUniqueItems(paths))
    
    return paths

def getExactXPathOfNodes(nodes):
    args = { 'show_namespace_prefixes_from_query': True, 'show_hierarchy_only': False, 'case_sensitive': True } # ensure the exact node path is returned
    return getXPathOfNodes(nodes, args)

def updateStatusToCurrentXPathIfSGML(view):
    """Update the status bar with the relevant xpath at the first cursor."""
    status = None
    if isCursorInsideSGML(view):
        if not getBoolValueFromArgsOrSettings('only_show_xpath_if_saved', None, False) or not view.is_dirty() or view.is_read_only():
            trees = ensureTreeCacheIsCurrent(view)
            if trees is None: # don't hide parse errors by overwriting status
                return
            else:
                # use cache of previous first selection if it exists
                global previous_first_selection
                prev = previous_first_selection[view.id()]
                
                current_first_sel = view.sel()[0]
                nodes = []
                if prev is not None and regionIntersects(prev[0], sublime.Region(current_first_sel.begin(), current_first_sel.begin()), False): # current first selection matches xpath region from previous first selection
                    nodes.append(prev[1])
                else: # current first selection doesn't match xpath region from previous first selection or is not cached
                    results = getNodesAtPositions(view, trees, [current_first_sel]) # get nodes at first selection
                    if len(results) > 0:
                        result = results[0]
                        previous_first_selection[view.id()] = (sublime.Region(result[2], result[3]), result[0]) # cache node and xpath region
                        nodes.append(result[0])
                
                # calculate xpath of node
                xpaths = getXPathOfNodes(nodes, None)
                if len(xpaths) == 1:
                    xpath = xpaths[0]
                    intro = 'XPath'
                    if len(view.sel()) > 1:
                        intro = intro + ' (at first selection)'
                    
                    text = intro + ': ' + xpath
                    maxLength = 234 # if status message is longer than this, sublime text 3 shows nothing in the status bar at all, so unfortunately we have to truncate it...
                    if len(text) > maxLength:
                        append = ' (truncated)'
                        text = text[0:maxLength - len(append)] + append
                    status = text
    
    if status is None:
        view.erase_status('xpath')
    else:
        view.set_status('xpath', status)

def copyXPathsToClipboard(view, args):
    """Copy the XPath(s) at the cursor(s) to the clipboard."""
    if isCursorInsideSGML(view):
        trees = ensureTreeCacheIsCurrent(view)
        if trees is not None:
            
            cursors = []
            for result in getSGMLRegionsContainingCursors(view):
                cursors.append(result[2])
            results = getNodesAtPositions(view, trees, cursors)
            paths = getXPathOfNodes([result[0] for result in results], args)
            
            if len(paths) > 0:
                sublime.set_clipboard(os.linesep.join(paths))
                message = str(len(paths)) + ' xpath(s) copied to clipboard'
            else:
                message = 'no xpath at cursor to copy to clipboard'
        else:
            message = 'xml is not valid, unable to copy xpaths to clipboard'
    else:
        message = 'xpath not copied to clipboard - ensure syntax is set to xml or html'
    sublime.status_message(message)

class CopyXpathCommand(sublime_plugin.TextCommand): # example usage from python console: sublime.active_window().active_view().run_command('copy_xpath', { 'show_hierarchy_only': True })
    def run(self, edit, **args):
        """Copy XPath(s) at cursor(s) to clipboard."""
        view = self.view
        
        copyXPathsToClipboard(view, args)
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self, **args):
        return containsSGML(self.view)

class XpathCommand(CopyXpathCommand):
    """To retain legacy use of this command. It has now been renamed to CopyXpathCommand, to make it's purpose more clear."""
    pass

class GotoRelativeCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args): # example usage from python console: sublime.active_window().active_view().run_command('goto_relative', {'direction': 'prev'})
        """Move cursor(s) to specified relative tag(s)."""
        view = self.view
        
        trees = ensureTreeCacheIsCurrent(view)
        if trees is not None:
            
            cursors = []
            for result in getSGMLRegionsContainingCursors(view):
                cursors.append(result[2])
            results = getNodesAtPositions(view, trees, cursors)
            
            new_nodes_under_cursors = []
            for result in results:
                allFound = True
                desired_node = getRelativeNode(result[0], args['direction'])
                if desired_node is None:
                    allFound = False
                    break
                else:
                    new_nodes_under_cursors.append(desired_node)
            
            if not allFound:
                message = args['direction'] + ' node not found'
                if len(cursors) > 1:
                    message += ' for at least one selection'
                sublime.status_message(message)
            else:
                non_open_positions = ['close', 'content', 'entire', 'names']
                position_type = 'open'
                if args['direction'] in non_open_positions:
                    position_type = args['direction']
                move_cursors_to_nodes(view, getUniqueItems(new_nodes_under_cursors), position_type)
    
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self):
        return containsSGML(self.view)
    def description(self, args):
        if args['direction'] in ('open', 'close'):
            descr = 'tag'
        elif args['direction'] in ('prev', 'previous', 'next'):
            descr = 'sibling'
        elif args['direction'] in ('parent'):
            descr = 'element'
        else:
            return None
        
        return 'Goto ' + args['direction'] + ' ' + descr

def getBoolValueFromArgsOrSettings(key, args, default):
    """Retrieve the value for the given key from the args if present, otherwise the settings if present, otherwise use the supplied default."""
    if args is None or not key in args:
        global settings
        return bool(settings.get(key, default))
    else:
        return args[key]

def getUniqueItems(items):
    """Return the items without any duplicates, preserving order."""
    unique = []
    for item in items:
        if item not in unique:
            unique.append(item)
            yield item

class XpathListener(sublime_plugin.EventListener):
    def on_selection_modified_async(self, view):
        updateStatusToCurrentXPathIfSGML(view)
    def on_activated_async(self, view):
        updateStatusToCurrentXPathIfSGML(view)
    def on_post_save_async(self, view):
        if getBoolValueFromArgsOrSettings('only_show_xpath_if_saved', None, False):
            updateStatusToCurrentXPathIfSGML(view)
    def on_pre_close(self, view):
        global change_counters
        global xml_trees
        global previous_first_selection
        change_counters.pop(view.id(), None)
        xml_trees.pop(view.id(), None)
        previous_first_selection.pop(view.id(), None)
        
        if view.file_name() is None: # if the file has no filename associated with it
            #if not getBoolValueFromArgsOrSettings('global_query_history', None, True): # if global history isn't enabled
            #    remove_key_from_xpath_query_history(get_history_key_for_view(view))
            #else:
            change_key_for_xpath_query_history(get_history_key_for_view(view), 'global')

def register_xpath_extensions():
    # http://lxml.de/extensions.html
    ns = etree.FunctionNamespace(None)
    
    def applyFuncToTextForItem(item, func):
        if isinstance(item, etree._Element):
            return func(item.xpath('string(.)'))
        else:
            return func(str(item))
    
    # TODO: xpath 1 functions deal with lists by just taking the first node
    #     - maybe we can provide optional arg to return nodeset by applying to all
    def applyTransformFuncToTextForItems(nodes, func):
        """If a nodeset is given, apply the transformation function to each item."""
        if isinstance(nodes, list):
            return [applyFuncToTextForItem(item, func) for item in nodes]
        else:
            return applyFuncToTextForItem(nodes, func)
    
    def applyFilterFuncToTextForItems(nodes, func):
        """If a nodeset is given, filter out items whose transformation function returns False.  Otherwise, return the value from the predicate."""
        if isinstance(nodes, list):
            return [item for item in nodes if applyFuncToTextForItem(item, func)]
        else:
            return applyFuncToTextForItem(nodes, func)
    
    def printValueAndReturnUnchanged(context, nodes, title = None):
        print_value = nodes
        if isinstance(nodes, list):
            if len(nodes) > 0 and isinstance(nodes[0], etree._Element):
                paths = getExactXPathOfNodes(nodes)
                print_value = paths
        
        if title is None:
            title = ''
        else:
            title = title + ':'
        print('XPath:', title, 'context_node', getExactXPathOfNodes([context.context_node])[0], 'eval_context', context.eval_context, 'values', print_value)
        return nodes
    
    ns['upper-case'] = lambda context, nodes: applyTransformFuncToTextForItems(nodes, str.upper)
    ns['lower-case'] = lambda context, nodes: applyTransformFuncToTextForItems(nodes, str.lower)
    ns['ends-with'] = lambda context, nodes, ending: applyFilterFuncToTextForItems(nodes, lambda item: item.endswith(ending))
    #ns['trim'] = lambda context, nodes: applyTransformFuncToTextForItems(nodes, str.strip) # according to the XPath 1.0 spec, the built in normalize-space function will trim the text on both sides, making this unnecessary http://www.w3.org/TR/xpath/#function-normalize-space
    ns['print'] = printValueAndReturnUnchanged
    
    def xpathRegexFlagsToPythonRegexFlags(xpath_regex_flags):
        flags = 0
        if 's' in xpath_regex_flags:
            flags = flags | re.DOTALL
        if 'm' in xpath_regex_flags:
            flags = flags | re.MULTILINE
        if 'i' in xpath_regex_flags:
            flags = flags | re.IGNORECASE
        if 'x' in xpath_regex_flags:
            flags = flags | re.VERBOSE
        
        return flags
    
    ns['tokenize'] = lambda context, item, pattern, xpath_regex_flags = None: applyFuncToTextForItem(item, lambda text: re.split(pattern, text, maxsplit = 0, flags = xpathRegexFlagsToPythonRegexFlags(xpath_regex_flags)))
    ns['matches'] = lambda context, item, pattern, xpath_regex_flags = None: applyFuncToTextForItem(item, lambda text: re.search(pattern, text, flags = xpathRegexFlagsToPythonRegexFlags(xpath_regex_flags)) is not None)
    # replace
    # avg
    # min
    # max
    # abs
    # ? adjust-dateTime-to-timezone, current-dateTime, day-from-dateTime, month-from-dateTime, days-from-duration, months-from-duration, etc.
    # insert-before, remove, subsequence, index-of, distinct-values, reverse, unordered, empty, exists
    # 

def plugin_loaded():
    """When the plugin is loaded, clear all variables and cache xpaths for current view if applicable."""
    global settings
    settings = sublime.load_settings('xpath.sublime-settings')
    settings.clear_on_change('reparse')
    settings.add_on_change('reparse', settingsChanged)
    sublime.set_timeout_async(settingsChanged, 10)
    
    register_xpath_extensions()

def makeNamespacePrefixesUniqueWithNumericSuffix(items, replaceNoneWith, start = 1):
    # TODO: docstring, about how it requires unique items
    flattened = {}
    for item in items:
        flattened.setdefault(item[0] or replaceNoneWith, []).append(item[1])
    
    unique = {}
    for key in flattened.keys():
        if len(flattened[key]) == 1:
            unique[key] = flattened[key][0]
        else: # find next available number. we can't just append the number, because it is possible that a namespace with the new prefix already exists
            index = start
            for item in flattened[key]: # for each item that has the same prefix but a different namespace
                while True:
                    try_key = key + str(index)
                    if try_key in unique.keys(): # if the key we are trying already exists
                        index += 1 # try again with the next index
                    else:
                        break # the key we are trying is new
                unique[key + str(index)] = item
                index += 1 # update the next key to try
    return unique

def get_all_namespaces_in_tree(tree):
    # find all namespaces in the document, so that the same prefixes can be used for the xpath
    # if the same prefix is used multiple times for different URIs, add a numeric suffix and increment it each time
    # xpath 1.0 doesn't support the default namespace, it needs to be mapped to a prefix
    global ns_loc
    getNamespaces = etree.XPath('//namespace::*')
    return getUniqueItems([ns for ns in getNamespaces(tree) if ns[1] != ns_loc])

def get_results_for_xpath_query(query, tree_contexts, print_contexts):
    """Given a query string and a dictionary of document trees and their context elements, compile the xpath query and execute it for each document."""
    matches = []
    is_nodeset = None
    
    global settings
    defaultNamespacePrefix = settings.get('default_namespace_prefix', 'default')
    
    for tree in tree_contexts.keys():
        nsmap = makeNamespacePrefixesUniqueWithNumericSuffix(get_all_namespaces_in_tree(tree), defaultNamespacePrefix, 1)
        
        try:
            xpath = etree.XPath(query, namespaces = nsmap)
        except Exception as e:
            sublime.status_message(str(e)) # show parsing error in status bar
            return (None, None)
    
        is_nodeset, results = execute_xpath_query(tree, xpath, tree_contexts[tree], print_contexts)
        if results is not None:
            matches += results
    
    return is_nodeset, matches

def execute_xpath_query(tree, xpath, contexts = None, print_contexts = False):
    """Execute the precompiled xpath query on the tree and return the results."""
    
    try:
        context_node = tree
        if contexts is not None and len(contexts) > 0:
            context_node = contexts[0] # set the context node to the first node in the selection, if there is one, otherwise to the tree itself
        else:
            print_contexts = False
        
        variables = settings.get('variables', None)
        if variables is None or not isinstance(variables, dict):
            variables = {}
        variables['contexts'] = contexts # set the $contexts variable to the context nodes
        
        result = xpath(context_node, **variables)
        if print_contexts: # only print contexts after the function is evaluated, as maybe it has an error
            print('XPath: $contexts set to', getExactXPathOfNodes(contexts))
        if isinstance(result, list):
            return (True, result)
        else:
            return (False, [result])
    except Exception as e:
        sublime.status_message(str(e)) # show parsing error in status bar
        return (False, None)

def get_xpath_query_history_for_keys(keys):
    """Return all previously used xpath queries with any of the given keys, in order.  If keys is None, return history across all keys."""
    history_settings = sublime.load_settings('xpath_query_history.sublime-settings')
    history = [item[0] for item in history_settings.get('history', []) if keys is None or item[1] in keys]
    return list(reversed(list(getUniqueItems(reversed(history))))) # get the latest unique items

def remove_item_from_xpath_query_history(key, query):
    """If the given query exists in the history for the given key, remove it."""
    history_settings = sublime.load_settings('xpath_query_history.sublime-settings')
    history = history_settings.get('history', [])
    item = [query, key]
    if item in history:
        history.remove(item)
        history_settings.set('history', history)
        #sublime.save_settings('xpath_query_history.sublime-settings')
   
# def remove_key_from_xpath_query_history(key):
#     view_history = get_xpath_query_history_for_keys([key])
#     for item in view_history:
#         remove_item_from_xpath_query_history(key, item)
#     return view_history

def add_to_xpath_query_history_for_key(key, query):
    """Add the specified query to the history for the given key."""
    # if it exists in the history for the view already, move the item to the bottom (i.e. make it the most recent item in the history) by removing and re-adding it
    remove_item_from_xpath_query_history(key, query)
    
    history_settings = sublime.load_settings('xpath_query_history.sublime-settings')
    history = history_settings.get('history', [])
    history.append([query, key])
    
    # if there are more than the specified maximum number of history items, remove the excess
    global settings
    max_history = settings.get('max_query_history', 100)
    history = history[-max_history:]
    
    history_settings.set('history', history)
    sublime.save_settings('xpath_query_history.sublime-settings')

def change_key_for_xpath_query_history(oldkey, newkey):
    """For all items in the history with the given oldkey, change the key to the specified newkey."""
    history_settings = sublime.load_settings('xpath_query_history.sublime-settings')
    history = history_settings.get('history', [])
    for item in history:
        if item[1] == oldkey:
            item[1] = newkey
    history_settings.set('history', history)
    sublime.save_settings('xpath_query_history.sublime-settings')

def get_history_key_for_view(view):
    """Return the key used to store history items that relate to the specified view."""
    key = view.file_name()
    if key is None:
        key = 'buffer_' + str(view.id())
    return key

class ShowXpathQueryHistoryCommand(sublime_plugin.TextCommand):
    history = None
    def run(self, edit, **args):
        global_history = getBoolValueFromArgsOrSettings('global_query_history', args, True)
        
        keys = None
        if not global_history:
            keys = [get_history_key_for_view(self.view)]
        
        self.history = get_xpath_query_history_for_keys(keys)
        if len(self.history) == 0:
            sublime.status_message('no query history to show')
        else:
            self.view.window().show_quick_panel(self.history, self.history_selection_done, 0, len(self.history) - 1, self.history_selection_changed)
    def history_selection_done(self, selected_index):
        if selected_index > -1:
            #add_to_xpath_query_history_for_key(get_history_key_for_view(self.view), self.history[selected_index])
            sublime.active_window().active_view().run_command('query_xpath', { 'prefill_path_at_cursor': False, 'prefill_query': self.history[selected_index] })
    def history_selection_changed(self, selected_index):
        if not getBoolValueFromArgsOrSettings('live_mode', None, True):
            self.history_selection_done(selected_index)
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self):
        return containsSGML(self.view)

class RerunLastXpathQueryCommand(sublime_plugin.TextCommand): # example usage from python console: sublime.active_window().active_view().run_command('rerun_last_xpath_query', { 'global_query_history': False, 'show_query_results': False })
    def run(self, edit, **args):
        global_history = getBoolValueFromArgsOrSettings('global_query_history', args, True)
        
        keys = [get_history_key_for_view(self.view)]
        if global_history:
            keys = None
        
        history = get_xpath_query_history_for_keys(keys)
        if len(history) == 0:
            sublime.status_message('no previous query to re-run')
        else:
            if args is None:
                args = {}
            args['xpath'] = history[-1]
            sublime.active_window().active_view().run_command('query_xpath', args)
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self):
        return containsSGML(self.view)

class CleanHtmlCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args):
        sublime.status_message('Cleaning HTML...')
        # TODO: if no arguments are supplied, find the first html region containing a cursor and clean that.
        
        # clean all html regions specified, in reverse order, because otherwise the offsets will change after tidying the region before it!
        for region_tuple in reversed(args['regions']):
            region_scope = sublime.Region(region_tuple[0], region_tuple[1])
            tag_soup = self.view.substr(region_scope)
            xml_string = clean_html(tag_soup)
            self.view.replace(edit, region_scope, xml_string)
        
        sublime.status_message('HTML cleaned successfully.')

class QueryXpathCommand(sublime_plugin.TextCommand): # example usage from python console: sublime.active_window().active_view().run_command('query_xpath', { 'xpath': '//prefix:LocalName', 'show_query_results': True })
    input_panel = None
    results = None # results from query
    previous_input = '' # remember previous query so that when the user next runs this command, it will be prepopulated
    show_query_results = None # whether to show the results of the query, so the user can pick *one* to move the cursor to. If False, cursor will automatically move to all results. Has no effect if result of query is not a node set.
    live_mode = None
    max_results_to_show = None
    pending = []
    most_recent_query = None
    contexts = None
    print_contexts = None
    
    def cache_context_nodes(self):
        """Cache context nodes to allow live mode to work with them."""
        trees = ensureTreeCacheIsCurrent(self.view)
        
        invalid_trees = []
        
        regions_cursors = {}
        for result in getSGMLRegionsContainingCursors(self.view):
            if trees[result[1]] is None:
                invalid_trees.append(result[0])
            regions_cursors.setdefault(result[1], []).append(result[2])
        
        if len(invalid_trees) > 0:
            invalid_trees = [region_scope for region_scope in invalid_trees if self.view.match_selector(region_scope.begin(), 'text.html') and not self.view.match_selector(region_scope.begin(), 'text.html.markdown')]
            if len(invalid_trees) > 0:
                print('XPath: Asking about cleaning HTML for view', 'id', self.view.id(), 'file_name', self.view.file_name(), 'regions', invalid_trees)
                if sublime.ok_cancel_dialog('XPath: The HTML is not well formed, and cannot be parsed by the XML parser. Would you like it to be cleaned?', 'Yes'):
                    self.view.run_command('clean_html', { 'regions': [(region.begin(), region.end()) for region in invalid_trees] })
                    trees = ensureTreeCacheIsCurrent(self.view)
                    updateStatusToCurrentXPathIfSGML(self.view)
        
        # TODO: show error if any of the XML regions containing the cursor is invalid?
        
        self.contexts = (self.view.change_count(), {})
        for region_index in regions_cursors.keys():
            tree = trees[region_index]
            if tree is not None:
                self.contexts[1][tree] = [item[0] for item in getNodesAtPositions(self.view, [tree], regions_cursors[region_index])]
        
        self.print_contexts = True
    
    def run(self, edit, **args):
        self.pending = []
        self.most_recent_query = None
        self.show_query_results = getBoolValueFromArgsOrSettings('show_query_results', args, True)
        self.live_mode = getBoolValueFromArgsOrSettings('live_mode', args, True)
        
        self.cache_context_nodes()
        
        global settings
        if 'max_results_to_show' in args:
            self.max_results_to_show = int(args['max_results_to_show'])
        else:
            self.max_results_to_show = settings.get('max_results_to_show', 1000)
        
        if args is not None and 'xpath' in args: # if an xpath is supplied, query it
            self.process_results_for_query(args['xpath'])
        else: # show an input prompt where the user can type their xpath query
            prefill = self.previous_input
            if args is not None and 'prefill_query' in args:
                prefill = args['prefill_query']
            else:
                global_history = getBoolValueFromArgsOrSettings('global_query_history', args, True)
                keys = [get_history_key_for_view(self.view)]
                if global_history:
                    keys = None
                history = get_xpath_query_history_for_keys(keys)
                
                if len(history) > 0:
                    prefill = history[-1]
                # if previous input is blank, or specifically told to, use path of first cursor. even if live mode enabled, cursor won't move much when activating this command
                if getBoolValueFromArgsOrSettings('prefill_path_at_cursor', args, False) or not prefill:
                    global previous_first_selection
                    prev = previous_first_selection.get(self.view.id(), None)
                    if prev is not None:
                        xpaths = getExactXPathOfNodes([prev[1]]) # ensure the path matches this node and only this node
                        prefill = xpaths[0]
            
            self.input_panel = self.view.window().show_input_panel('enter xpath', prefill, self.xpath_input_done, self.change, self.cancel)
            self.input_panel.set_syntax_file('xpath.sublime-syntax')
            self.input_panel.settings().set('gutter', False)
    
    def change(self, value):
        """When the xpath query is changed, after a short delay (so that it doesn't query unnecessarily while the xpath is still being typed), execute the expression."""
        def cb():
            if self.pending.pop() == value:
                self.process_results_for_query(value)
                self.most_recent_query = value
                if self.input_panel is not None:
                    self.input_panel.window().focus_view(self.input_panel)
        
        if self.live_mode:
            self.pending.append(value)
            
            global settings
            delay = settings.get('live_query_timeout', 0)
            async = settings.get('live_query_async', True)
            
            if async:
                sublime.set_timeout_async(cb, delay)
            elif delay == 0:
                cb()
            else:
                sublime.set_timeout(cb, delay)
        
    def cancel(self):
        self.input_panel = None
    
    def xpath_input_done(self, value):
        self.input_panel = None
        self.previous_input = value
        add_to_xpath_query_history_for_key(get_history_key_for_view(self.view), self.previous_input)
        if not self.live_mode:
            self.process_results_for_query(value)
        else:
            self.close_quick_panel()
    
    def process_results_for_query(self, query):
        if len(query) > 0:
            if self.contexts[0] != self.view.change_count(): # if the document has changed since the context nodes were cached
                self.cache_context_nodes()
            self.results = get_results_for_xpath_query(query, self.contexts[1], self.print_contexts)
            self.print_contexts = False
            if self.results[0] is not None:
                if self.results[0] and len(self.results[1]) == 0:
                    sublime.status_message('no results found matching xpath expression "' + query + '"')
                else:
                    sublime.status_message('') # clear status message as it is out of date now
                    if self.show_query_results or not self.results[0]: # also show results if results is not a node set, as we can't "go to" them...
                        if self.max_results_to_show > 0 and len(self.results[1]) > self.max_results_to_show:
                            print('XPath: query results truncated, showing first ' + str(self.max_results_to_show) + ' results of ' + str(len(self.results[1])) + ' for query: ' + query)
                            self.results = (self.results[0], self.results[1][0:self.max_results_to_show])
                        self.show_results_for_query()
                    else:
                        self.goto_results_for_query()
    
    def close_quick_panel(self):
        sublime.active_window().run_command('hide_overlay', { 'cancel': True }) # close existing quick panel
    
    def show_results_for_query(self):
        self.close_quick_panel()
        
        # truncate each xml result at 70 chars so that it appears (more) correctly in the quick panel
        maxlen = 70
        
        show_text_preview = None
        if getBoolValueFromArgsOrSettings('normalize_whitespace_in_preview', None, False):
            show_text_preview = lambda result: collapseWhitespace(str(result), maxlen)
        else:
            show_text_preview = lambda result: str(result)[0:maxlen]
        
        if self.results[0]:
            unique_types_in_result = getUniqueItems((type(item) for item in self.results[1]))
            next(unique_types_in_result, None)
            muliple_types_in_result = next(unique_types_in_result, None) is not None
            
            show_element_preview = lambda e: [getTagName(e)[2], collapseWhitespace(e.text, maxlen), getElementXMLPreview(self.view, e, maxlen)]
            def show_preview(item):
                if isinstance(item, etree._Element):
                    return show_element_preview(item)
                else:
                    show = show_text_preview(item)
                    if muliple_types_in_result: # if some items are elements (where we show 3 lines) and some are other node types (where we show 1 line), we need to return 3 lines to ensure Sublime will show the results correctly
                        show = [show, '', '']
                    return show
            
            list_comp = [show_preview(item) for item in self.results[1]]
        else:
            list_comp = [show_text_preview(result) for result in self.results[1]]
        self.view.window().show_quick_panel(list_comp, self.xpath_selection_done, sublime.KEEP_OPEN_ON_FOCUS_LOST, -1, self.xpath_selection_changed)
        
    def xpath_selection_changed(self, selected_index):
        if (selected_index > -1): # quick panel wasn't cancelled
            self.goto_results_if_relevant(selected_index)
    
    def xpath_selection_done(self, selected_index):
        if (selected_index > -1): # quick panel wasn't cancelled
            if self.most_recent_query is not None and self.most_recent_query != '':
                add_to_xpath_query_history_for_key(get_history_key_for_view(self.view), self.most_recent_query)
            self.goto_results_if_relevant(selected_index)
            self.input_panel = None
            sublime.active_window().run_command('hide_panel', { 'cancel': True }) # close input panel
    
    def goto_results_if_relevant(self, selected_index):
        if self.results[0]:
            self.goto_results_for_query(selected_index)
    
    def goto_results_for_query(self, specific_index = None):
        cursors = []
        
        results = self.results[1]
        if specific_index is not None and specific_index > -1:
            results = [results[specific_index]]
        
        move_cursors_to_nodes(self.view, results, 'open')
        
        if specific_index is None or specific_index == -1:
            self.results = None
    
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self):
        return containsSGML(self.view)
