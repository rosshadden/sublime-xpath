import sublime
import sublime_plugin
import os
from lxml import etree
from xml.sax import SAXParseException
import re
from .lxml_parser import *
from .sublime_lxml import *
from .sublime_input_quickpanel import QuickPanelFromInputCommand

change_counters = {}
xml_roots = {}
previous_first_selection = {}
settings = None
parse_error = 'XPath - error parsing XML at '
html_cleaning_answer = {}

def settingsChanged():
    """Clear change counters and cached xpath regions for all views, and reparse xml regions for the current view."""
    global change_counters
    global xml_roots
    global previous_first_selection
    change_counters.clear()
    xml_roots.clear()
    previous_first_selection.clear()
    updateStatusToCurrentXPathIfSGML(sublime.active_window().active_view())

def getSGMLRegions(view):
    """Find all xml and html scopes in the specified view."""
    return view.find_by_selector('text.xml, text.html - text.html.markdown') # TODO: include html or xml code regions in markdown, maybe using scope 'markup.raw.block.fenced.markdown' and checking for a language after the ```

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
    namespaces = None
    line_number_offset = view.rowcol(region_scope.begin())[0]
    change_count = view.change_count()
    stop = lambda: change_count < view.change_count() # stop parsing if the document is modified
    if view.is_read_only():
        stop = None # no need to check for modifications if the view is read only
    try:
        tree, namespaces = lxml_etree_parse_xml_string_with_location(xml_string, line_number_offset, stop)
    except SAXParseException as e:
        global parse_error
        text = 'line ' + str(e.getLineNumber() + line_number_offset) + ', column ' + str(e.getColumnNumber() + 1) + ' - ' + e.getMessage()
        view.set_status('xpath_error', parse_error + text)
    
    return (tree, namespaces)

def ensureTreeCacheIsCurrent(view):
    """If the document has been modified since the xml was parsed, parse it again to recreate the trees."""
    global change_counters
    new_count = view.change_count()
    old_count = change_counters.get(view.id(), None)
    
    global xml_roots
    if old_count is None or new_count > old_count:
        change_counters[view.id()] = new_count
        view.set_status('xpath', 'XML being parsed...')
        view.erase_status('xpath_error')
        
        xml_roots[view.id()] = []
        for tree, namespaces in buildTreesForView(view):
            root = None
            if tree is not None:
                root = tree.getroot()
            xml_roots[view.id()].append(root)
        
        view.erase_status('xpath')
        global previous_first_selection
        previous_first_selection[view.id()] = None
    return xml_roots[view.id()]

class GotoXmlParseErrorCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args):
        view = self.view
        
        global parse_error
        detail = view.get_status('xpath_error')[len(parse_error + 'line '):].split(' - ')[0].split(', column ')
        point = view.text_point(int(detail[0]) - 1, int(detail[1]) - 1)
        
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
            unique_prefix = next((prefix for prefix in namespaces.keys() if namespaces[prefix] == (tag[0], node.prefix)), None) # find the first prefix in the map that relates to this uri
            if unique_prefix is not None:
                tag = (tag[0], tag[1], unique_prefix + ':' + tag[1]) # ensure that the path we display can be used to query the element
        
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
    
    roots = {}
    for node in nodes:
        tree = node.getroottree()
        root = tree.getroot()
        roots.setdefault(root, []).append(node)
    
    paths = []
    for root in roots.keys():
        for node in roots[root]:
            namespaces = None
            if show_namespace_prefixes_from_query:
                namespaces = namespace_map_for_tree(root.getroottree())
            
            paths.append(getNodePath(node, namespaces, root))
    
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
        roots = ensureTreeCacheIsCurrent(view)
        if roots is not None:
            
            cursors = []
            for result in getSGMLRegionsContainingCursors(view):
                cursors.append(result[2])
            results = getNodesAtPositions(view, roots, cursors)
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
        
        roots = ensureTreeCacheIsCurrent(view)
        if roots is not None:
            
            cursors = []
            for result in getSGMLRegionsContainingCursors(view):
                cursors.append(result[2])
            results = getNodesAtPositions(view, roots, cursors)
            
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
                move_cursors_to_nodes(view, getUniqueItems(new_nodes_under_cursors), position_type, None)
    
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
        global xml_roots
        global previous_first_selection
        change_counters.pop(view.id(), None)
        xml_roots.pop(view.id(), None)
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
    

def plugin_loaded():
    """When the plugin is loaded, clear all variables and cache xpaths for current view if applicable."""
    global settings
    settings = sublime.load_settings('xpath.sublime-settings')
    settings.clear_on_change('reparse')
    settings.add_on_change('reparse', settingsChanged)
    sublime.set_timeout_async(settingsChanged, 10)
    
    register_xpath_extensions()

def get_all_namespaces_in_tree(tree):
    # find all namespaces in the document, so that the same prefixes can be used for the xpath
    # if the same prefix is used multiple times for different URIs, add a numeric suffix and increment it each time
    # xpath 1.0 doesn't support the default namespace, it needs to be mapped to a prefix
    global ns_loc
    getNamespaces = etree.XPath('//namespace::*')
    return getUniqueItems([ns for ns in getNamespaces(tree) if ns[1] != ns_loc])

def get_results_for_xpath_query_multiple_trees(query, tree_contexts, root_namespaces, **additional_variables):
    """Given a query string and a dictionary of document trees and their context elements, compile the xpath query and execute it for each document."""
    matches = []
    global settings
    variables = settings.get('variables', {})
    for key in additional_variables:
        variables[key] = additional_variables[key]
    
    for tree in tree_contexts.keys():
        namespaces = root_namespaces.get(tree.getroot(), {})
        variables['contexts'] = tree_contexts[tree]
        context = None
        if len(tree_contexts[tree]) > 0:
            context = tree_contexts[tree][0]
        matches += get_results_for_xpath_query(query, tree, context, namespaces, **variables)
        
    return matches
    
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
    items_changed = 0
    for item in history:
        if item[1] == oldkey:
            item[1] = newkey
            items_changed += 1
    if items_changed > 0:
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

def namespace_map_from_contexts(contexts):
    root_namespaces = {}
    for node in contexts:
        root = None
        if isinstance(node, etree._ElementTree):
            root = node.getroot()
        else:
            root = node.getroottree().getroot()
        if root not in root_namespaces.keys():
            root_namespaces[root] = namespace_map_for_tree(root.getroottree())
    
    return root_namespaces

def namespace_map_for_tree(tree):
    global settings
    defaultNamespacePrefix = settings.get('default_namespace_prefix', 'default')
    namespaces = unique_namespace_prefixes(get_all_namespaces_in_tree(tree), defaultNamespacePrefix)
    return namespaces

class SelectResultsFromXpathQueryCommand(sublime_plugin.TextCommand): # example usage from python console: sublime.active_window().active_view().run_command('select_results_from_xpath_query', { 'xpath': '//*', 'goto_element': 'names' })
    def run(self, edit, **kwargs):
        contexts = get_context_nodes_from_cursors(self.view)
        nodes = get_results_for_xpath_query_multiple_trees(kwargs['xpath'], contexts, namespace_map_from_contexts(contexts))
        
        global settings
        goto_element = settings.get('goto_element', 'open')
        goto_attribute = settings.get('goto_attribute', 'value')
        if goto_element == 'none':
            goto_element = 'open'
        if goto_attribute == 'none':
            goto_attribute = 'value'
        
        if 'goto_element' in kwargs:
            goto_element = kwargs['goto_element']
        if 'goto_attribute' in kwargs:
            goto_attribute = kwargs['goto_attribute']
        
        total_selections, total_results = move_cursors_to_nodes(self.view, nodes, goto_element, goto_attribute)
        if total_results == total_selections:
            sublime.status_message(str(total_results) + ' nodes selected')
        else:
            sublime.status_message(str(total_selections) + ' nodes selected out of ' + str(total_results))
        add_to_xpath_query_history_for_key(get_history_key_for_view(self.view), kwargs['xpath'])

class RerunLastXpathQueryAndSelectResultsCommand(sublime_plugin.TextCommand): # example usage from python console: sublime.active_window().active_view().run_command('rerun_last_xpath_query_and_select_results', { 'global_query_history': False })
    def run(self, edit, **args):
        global_history = getBoolValueFromArgsOrSettings('global_query_history', args, True)
        
        keys = [get_history_key_for_view(self.view)]
        if global_history:
            keys = None
        
        # TODO: preserve original $contexts variable (xpaths of all context nodes) with history, and restore here?
        history = get_xpath_query_history_for_keys(keys)
        if len(history) == 0:
            sublime.status_message('no previous query to re-run')
        else:
            self.view.run_command('select_results_from_xpath_query', { 'xpath': history[-1] })
    
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    
    def is_visible(self):
        return containsSGML(self.view)

class CleanTagSoupCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args):
        self.view.set_status('xpath_clean', 'Cleaning tag soup...')
        # if no arguments are supplied, find the first SGML region containing a cursor that is invalid and clean that.
        if args is None or 'regions' not in args:
            found = False
            roots = ensureTreeCacheIsCurrent(self.view)
            for result in getSGMLRegionsContainingCursors(self.view):
                if roots[result[1]] is None:
                    args = { 'regions': [(result[0].begin(), result[0].end())] }
                    found = True
                    break
            if not found:
                self.view.erase_status('xpath_clean')
                sublime.status_message('Unable to find any SGML tag soup regions to fix.')
                return
        
        # clean all html regions specified, in reverse order, because otherwise the offsets will change after tidying the region before it! i.e. args['regions'] must be in ascending position order
        for region_tuple in reversed(args['regions']):
            region_scope = sublime.Region(region_tuple[0], region_tuple[1])
            tag_soup = self.view.substr(region_scope)
            xml_string = clean_html(tag_soup)
            self.view.replace(edit, region_scope, xml_string)
        
        self.view.erase_status('xpath_clean')
        sublime.status_message('Tag soup cleaned successfully.')
    
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    
    def is_visible(self):
        return containsSGML(self.view)

def get_context_nodes_from_cursors(view):
    """Get nodes under the cursors for the specified view."""
    roots = ensureTreeCacheIsCurrent(view)
    
    invalid_trees = []
    
    regions_cursors = {}
    for result in getSGMLRegionsContainingCursors(view):
        if roots[result[1]] is None:
            invalid_trees.append(result[0])
        regions_cursors.setdefault(result[1], []).append(result[2])
    
    if len(invalid_trees) > 0:
        invalid_trees = [region_scope for region_scope in invalid_trees if view.match_selector(region_scope.begin(), 'text.html - text.html.markdown')]
        if len(invalid_trees) > 0:
            print('XPath: Asking about cleaning HTML for view', 'id', view.id(), 'file_name', view.file_name(), 'regions', invalid_trees)
            if sublime.ok_cancel_dialog('XPath: The HTML is not well formed, and cannot be parsed by the XML parser. Would you like it to be cleaned?', 'Yes'):
                view.run_command('clean_tag_soup', { 'regions': [(region.begin(), region.end()) for region in invalid_trees] })
                roots = ensureTreeCacheIsCurrent(view)
                updateStatusToCurrentXPathIfSGML(view)
                invalid_trees = []
    
    contexts = {}
    
    if len(invalid_trees) > 0: # show error if any of the XML regions containing the cursor is invalid
        sublime.error_message('The XML cannot be parsed, therefore it is not currently possible to execute XPath queries on the document.  Please see the status bar for parsing errors.')
    else:
        for region_index in regions_cursors.keys():
            root = roots[region_index]
            if root is not None:
                contexts[root.getroottree()] = [item[0] for item in getNodesAtPositions(view, [root], regions_cursors[region_index])]
        
    return contexts

class QueryXpathCommand(QuickPanelFromInputCommand): # example usage from python console: sublime.active_window().active_view().run_command('query_xpath', { 'prefill_query': '//prefix:LocalName', 'live_mode': True })
    max_results_to_show = None
    contexts = None
    previous_input = None # remember previous query so that when the user next runs this command, it will be prepopulated
    
    def cache_context_nodes(self):
        """Cache context nodes to allow live mode to work with them."""
        context_nodes = get_context_nodes_from_cursors(self.view)
        self.contexts = (self.view.change_count(), context_nodes, namespace_map_from_contexts(context_nodes))
        for root in context_nodes:
            print('XPath context nodes: ', getExactXPathOfNodes(context_nodes[root]))
    
    def run(self, edit, **args):
        self.cache_context_nodes()
        if len(self.contexts[1].keys()) == 0: # if there are no context nodes, don't proceed to show the xpath input panel
            return
        super().run(edit, **args)
    
    def parse_args(self):
        self.arguments['initial_value'] = self.get_value_from_args('prefill_query', self.previous_input)
        if self.arguments['initial_value'] is None:
            global_history = getBoolValueFromArgsOrSettings('global_query_history', self.arguments, True)
            keys = [get_history_key_for_view(self.view)]
            if global_history:
                keys = None
            history = get_xpath_query_history_for_keys(keys)
            
            if len(history) > 0:
                self.arguments['initial_value'] = history[-1]
        # if previous input is blank, or specifically told to, use path of first cursor. even if live mode enabled, cursor won't move much when activating this command
        if getBoolValueFromArgsOrSettings('prefill_path_at_cursor', self.arguments, False) or not self.arguments['initial_value']:
            global previous_first_selection
            prev = previous_first_selection.get(self.view.id(), None)
            if prev is not None:
                xpaths = getExactXPathOfNodes([prev[1]]) # ensure the path matches this node and only this node
                self.arguments['initial_value'] = xpaths[0]
        
        self.arguments['label'] = 'enter xpath'
        self.arguments['syntax'] = 'xpath.sublime-syntax'
        
        global settings
        self.max_results_to_show = int(self.get_value_from_args('max_results_to_show', settings.get('max_results_to_show', 1000)))
        
        self.arguments['async'] = getBoolValueFromArgsOrSettings('live_query_async', self.arguments, True)
        self.arguments['delay'] = int(settings.get('live_query_delay', 0))
        self.arguments['live_mode'] = getBoolValueFromArgsOrSettings('live_mode', self.arguments, True)
        
        self.arguments['normalize_whitespace_in_preview'] = getBoolValueFromArgsOrSettings('normalize_whitespace_in_preview', self.arguments, False)
        self.arguments['auto_completion_triggers'] = settings.get('auto_completion_triggers', '/')
        self.arguments['intelligent_auto_complete'] = getBoolValueFromArgsOrSettings('intelligent_auto_complete', self.arguments, True)
        
        
        if 'goto_element' not in self.arguments:
            self.arguments['goto_element'] = settings.get('goto_element', 'open')
        if 'goto_attribute' not in self.arguments:
            self.arguments['goto_attribute'] = settings.get('goto_attribute', 'value')
        
        super().parse_args()
    
    def get_query_results(self, query):
        results = None
        status_text = None
        if len(query) == 0:
            status_text = 'No query entered'
        else:
            if self.contexts[0] != self.view.change_count(): # if the document has changed since the context nodes were cached
                self.cache_context_nodes()
            
            try:
                results = get_results_for_xpath_query_multiple_trees(query, self.contexts[1], self.contexts[2])
            except Exception as e:
                status_text = str(e)
            
            if status_text is None: # if there was no error
                status_text = str(len(results)) + ' result'
                if len(results) != 1:
                    status_text += 's'
                status_text += ' from query'
                if self.max_results_to_show > 0 and len(results) > self.max_results_to_show:
                    status_text += ' (showing first ' + str(self.max_results_to_show) + ')'
                    results = results[0:self.max_results_to_show]
        self.view.set_status('xpath_query', status_text or '')
        return results
    
    def get_items_from_input(self):
        return self.get_query_results(self.current_value)
    
    def get_items_to_show_in_quickpanel(self):
        results = self.items
        if results is None:
            return None
        
        # truncate each xml result at 70 chars so that it appears (more) correctly in the quick panel
        maxlen = 70
        
        show_text_preview = None
        if self.arguments['normalize_whitespace_in_preview']:
            show_text_preview = lambda result: collapseWhitespace(str(result), maxlen)
        else:
            show_text_preview = lambda result: str(result)[0:maxlen]
        
        unique_types_in_result = getUniqueItems((type(item) for item in results))
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
        
        return [show_preview(item) for item in results]
        
    def quickpanel_selection_changed(self, selected_index):
        if selected_index > -1: # quick panel wasn't cancelled
            move_cursors_to_nodes(self.view, [self.items[selected_index]], self.arguments['goto_element'], self.arguments['goto_attribute'])
            #self.view.window().focus_view(self.view) # focus the view to try getting the cursor positions to update while the quick panel is open
            #if self.input_panel is not None:
            #    self.input_panel.window().focus_view(self.input_panel)
    
    def commit_input(self):
        self.previous_input = self.current_value
        add_to_xpath_query_history_for_key(get_history_key_for_view(self.view), self.current_value)
    
    def command_complete(self, cancelled):
        self.view.erase_status('xpath_query')
        super().command_complete(cancelled)
    
    def show_input_panel(self, initial_value):
        super().show_input_panel(initial_value)
        if len(self.arguments['auto_completion_triggers'] or '') > 0:
            self.input_panel.settings().set('auto_complete_triggers', [ {'selector': 'query.xml.xpath - string', 'characters': self.arguments['auto_completion_triggers']} ])
    
    def on_query_completions(self, prefix, locations): # moved from .sublime-completions file here - https://github.com/SublimeTextIssues/Core/issues/819
        flags = sublime.INHIBIT_WORD_COMPLETIONS
        if self.arguments['intelligent_auto_complete']:
            flags = 0
        return (completions_for_xpath_query(self.input_panel, prefix, locations, self.contexts[1], self.contexts[2], settings.get('variables', {}), self.arguments['intelligent_auto_complete']), flags)
    
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    
    def is_visible(self):
        return containsSGML(self.view)

def completions_for_xpath_query(view, prefix, locations, contexts, namespaces, variables, intelligent):
    def completions_axis_specifiers():
        completions = ['ancestor', 'ancestor-or-self', 'attribute', 'child', 'descendant', 'descendant-or-self', 'following', 'following-sibling', 'namespace', 'parent', 'preceding', 'preceding-sibling', 'self']
        return [(completion + '\taxis', completion + '::') for completion in completions]

    def completions_node_types():
        completions = ['text', 'node']
        #completions += ['comment', 'processing-instruction'] # commented out because these nodes are ignored during our xml parsing and tree building process
        return [(completion + '\tnode type', completion + '()') for completion in completions]

    def completions_functions():
        funcs = {
            'nodeset': ['last', 'position', 'count', 'local-name', 'namespace-uri', 'name'],
            'string': ['string', 'concat', 'starts-with', 'contains', 'substring-before', 'substring-after', 'substring', 'string-length', 'normalize-space', 'translate'],
            'boolean': ['boolean', 'not', 'true', 'false', 'lang'],
            'number': ['number', 'sum', 'floor', 'ceiling', 'round'],
            'XPath 2.0': ['upper-case', 'lower-case', 'ends-with', 'tokenize', 'matches'],
            'Custom': ['print']
        }
        for key in funcs.keys():
            for completion in funcs[key]:
                yield (completion + '\t' + key + ' functions', completion + '($1)')
    
    completions = []
    
    variables['contexts'] = None
    variable_completions = [[key + '\tvariable', key] for key in sorted(variables.keys()) if key.startswith(prefix)]
    
    prev_chars = []
    positions = []
    for location in locations:
        if view.match_selector(location, 'string'): # if in a string, nothing to suggest
            continue
        pos = locations[0] - len(prefix)
        positions.append(pos)
        prev_char = view.substr(pos - 1)
        if prev_char not in prev_chars:
            prev_chars.append(prev_char)
    
    if len(positions) == 0:
        return None # no locations suitable for suggestions
    
    include_generics = False
    include_xpath = False
    if len(prev_chars) == 1:
        if prev_chars[0] == '$': # if user is typing a variable
            completions = variable_completions
        else:
            include_xpath = len(locations) == 1
            include_generics = True
            if prev_chars[0] == '@': # if user is typing an attribute
                include_generics = False
    
    if include_generics or include_xpath:
        subqueries = parse_xpath_query_for_completions(view, positions[0])
        
        if include_xpath and intelligent:
            # analyse relevant part of xpath query, and guess what user might want to type, i.e. suggest attributes that are present on the relevant elements when prefix starts with '@' etc.
            # execute previous complete query parts, so that we have the right context nodes for the current sub-expression
            
            if contexts is not None:
                # execute an xpath query to get all possible values
                exec_query = subqueries[-1] + '*'
                if prefix != '':
                    exec_query += '[starts-with(name(), $_prefix)]'
                
                # determine if any queries can be skipped, due to using an absolute path
                relevant_queries = 0
                for subquery in reversed(subqueries[0:-1]):
                    relevant_queries += 1
                    if subquery != '' and subquery[0] in ('/', '$'):
                        break
                
                start_index = len(subqueries) - relevant_queries - 1
                subqueries = subqueries[start_index:]
                
                #print('XPath: completion context queries:', subqueries[0:-1], 'completion query:', exec_query, 'prefix:', prefix)
                
                # TODO: check all trees, not just the first one
                tree = list(contexts.keys())[0]
                completion_contexts = contexts[tree]
                
                xpath_variables = variables.copy()
                xpath_variables['contexts'] = contexts[tree]
                xpath_variables['expression_contexts'] = None
                xpath_variables['_prefix'] = prefix
                
                for query in subqueries[0:-1] + [exec_query]:
                    if query != '':
                        if query[0] not in ('$', '/', '('):
                            query = '$expression_contexts/' + query
                        xpath_variables['expression_contexts'] = completion_contexts
                        try:
                            completion_contexts = get_results_for_xpath_query(query, tree, None, namespaces[tree.getroot()], **xpath_variables)
                            # TODO: if result is not a node, break out as we can't offer any useful suggestions (currently we just get an exception: Non-Element values not supported at this point - got 'example string') when it tries $expression_contexts/*
                        except Exception as e: # xpath query invalid, just show static contexts
                            completion_contexts = None
                            print('XPath completions error', 'query', query, 'exception', e)
                            break
                
                if completion_contexts is not None:
                    for result in completion_contexts:
                        if isinstance(result, etree._Element): # if it is an Element, add a completion with the full name of the element
                            ns, localname, fullname = getTagName(result)
                            if ns is not None: # ensure we get the prefix that we have mapped to the namespace for the query
                                root = result.getroottree().getroot()
                                fullname = next((nsprefix for nsprefix in namespaces[root].keys() if namespaces[root][nsprefix] == (ns, result.prefix))) + ':' + localname # find the first prefix in the map that relates to this uri
                            completions.append((fullname + '\tElement', fullname))
                        elif isinstance(result, etree._ElementUnicodeResult): # if it is an attribute, add a completion with the name of the attribute
                            if prev_char == '@' or result.is_attribute:
                                global ns_loc
                                if not result.attrname.startswith('{' + ns_loc + '}'):
                                    completions.append((result.attrname + '\tAttribute', result.attrname)) # NOTE: can get the value with: result.getparent().get(result.attrname)
                        else: # debug, are we missing something we could suggest?
                            #completions.append((str(result) + '\t' + str(type(result)), str(result)))
                            pass
                    
                    completions = list(getUniqueItems(completions))
        
        if include_generics:
            generics = []
            if ':' not in subqueries[-1].split('/')[-1]: # if no namespace or axis operator used in the last location step of the subquery
                generics += completions_axis_specifiers()
                generics += completions_node_types()
            if subqueries[-1] == '': # XPath 1.0 functions and variables can only be used at the beginning of a sub-expression
                generics += list(completions_functions())
                generics += [('$' + item[0], '\\$' + item[1]) for item in variable_completions] # add possible variables
            
            completions += [completion for completion in generics if completion[0].startswith(prefix)]
        
    return completions
