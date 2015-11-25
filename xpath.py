import sublime
import sublime_plugin
import os
from lxml.sax import ElementTreeContentHandler
from lxml import etree
from xml.sax import make_parser, ContentHandler, SAXParseException#, parseString, handler

change_counters = {}
xml_trees = {}
previous_first_selection = {}
settings = None
parse_error = 'XPath - error parsing XML: '
ns_loc = 'lxml'

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

def lxml_etree_parse_xml_string_with_location(xml_string, line_number_offset):
    parser = make_parser()
    global ns_loc
    
    class ETreeContent(ElementTreeContentHandler):
        _locator = None
        _prefix_hierarchy = []
        _last_action = None
        
        def setDocumentLocator(self, locator):
            self._locator = locator
        
        def _splitPrefixAndGetNamespaceURI(self, fullName):
            prefix = None
            local_name = None
            
            split_pos = fullName.find(':')
            if split_pos > -1:
                prefix = fullName[0:split_pos]
                local_name = fullName[split_pos + 1:]
            else:
                local_name = fullName
            
            return (prefix, local_name, self._getNamespaceURI(prefix))
        
        def _getNamespaceURI(self, prefix):
            for mappings in reversed(self._prefix_hierarchy):
                if prefix in mappings:
                    return mappings[prefix]
            return None
        
        def _getNamespaceMap(self):
            flattened = {}
            for mappings in self._prefix_hierarchy:
                for prefix in mappings:
                    flattened[prefix] = mappings[prefix]
            return flattened
        
        def _getParsePosition(self):
            locator = self._locator or parser
            return str(locator.getLineNumber() - 1 + line_number_offset) + '/' + str(locator.getColumnNumber())
        
        def startElementNS(self, name, tagName, attrs):
            self._recordEndPosition()
            
            self._last_action = 'open'
            # correct missing element and attribute namespaceURIs, using known prefixes and new prefixes declared with this element
            self._prefix_hierarchy.append({})
            
            nsmap = []
            attrmap = []
            for attr_name, attr_value in attrs.items():
                if attr_name[0] == None: # if there is no namespace URI associated with the attribute already
                    if attr_name[1].startswith('xmlns:'): # map the prefix to the namespace URI
                        nsmap.append((attr_name, attr_name[1][len('xmlns:'):], attr_value))
                    elif attr_name[1] == 'xmlns': # map the default namespace URI
                        nsmap.append((attr_name, None, attr_value))
                    elif ':' in attr_name[1]: # separate the prefix from the local name
                        attrmap.append((attr_name, self._splitPrefixAndGetNamespaceURI(attr_name[1]), attr_value))
            
            for ns in nsmap:
                attrs.pop(ns[0]) # remove the xmlns attribute
                self.startPrefixMapping(ns[1], ns[2]) # map the prefix to the URI
            
            for attr in attrmap:
                attrs.pop(attr[0]) # remove the attribute
                attrs[(attr[1][2], attr[1][1])] = attr[2] # re-add the attribute with the correct qualified name
            
            tag = self._splitPrefixAndGetNamespaceURI(tagName)
            name = (tag[2], tag[1])
            
            self._new_mappings = self._getNamespaceMap()
            super().startElementNS(name, tagName, attrs)
            
            current = self._element_stack[-1]
            self._recordPosition(current, 'open_tag_start_pos')
            
        def startPrefixMapping(self, prefix, uri):
            self._prefix_hierarchy[-1][prefix] = uri
            if prefix is None:
                self._default_ns = uri
            # TODO: record all used namespace uri and prefix combinations used in document, to avoid looking them all up again later
        
        def endPrefixMapping(self, prefix):
            self._prefix_hierarchy[-1].pop(prefix)
            if prefix is None:
                self._default_ns = self._getNamespaceURI(None)
        
        def endElementNS(self, name, tagName):
            self._recordEndPosition()
            
            self._last_action = 'close'
            
            current = self._element_stack[-1]
            self._recordPosition(current, 'close_tag_start_pos')
            
            tag = self._splitPrefixAndGetNamespaceURI(tagName)
            name = (tag[2], tag[1])
            super().endElementNS(name, tagName)
            if None in self._prefix_hierarchy[-1]: # re-map default namespace if applicable
                self.endPrefixMapping(None)
            self._prefix_hierarchy.pop()
        
        def _recordPosition(self, node, position_name, position = None):
            position_name = '{' + ns_loc + '}' + position_name
            if position is not None or position_name not in node.attrib.keys():
                node.set(position_name, position or self._getParsePosition())
        
        def _recordEndPosition(self):
            if len(self._element_stack) > 0:
                current = self._element_stack[-1]
                if len(current) == 0: # current element has no children
                    if current.text is None:
                        self._recordPosition(current, 'open_tag_end_pos')
                else: # current element has children
                    if len(current) > 0: # current element has children
                        last_child = current[-1] # get the last child
                        if last_child.tail is None and self._last_action is not None:
                            self._recordPosition(last_child, self._last_action + '_tag_end_pos')
                            if self._last_action == 'close' and last_child.get('{' + ns_loc + '}close_tag_end_pos') == last_child.get('{' + ns_loc + '}open_tag_end_pos'): # self-closing tag, update the start position of the "close tag" to the start position of the open tag
                                self._recordPosition(last_child, 'close_tag_start_pos', last_child.get('{' + ns_loc + '}open_tag_start_pos'))
        
        def characters(self, data):
            self._recordEndPosition()
            super().characters(data)
        
        def endDocument(self):
            self._recordPosition(self.etree.getroot(), 'close_tag_end_pos')
    
    createETree = ETreeContent()
    
    parser.setContentHandler(createETree)
    parser.feed(xml_string)
    
    parser.close()
    
    return createETree.etree

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

# TODO: consider subclassing etree.ElementBase and adding as methods to that
def getSpecificNodePosition(node, position_name):
    """Given a node and a position name, return the row and column that relates to the node's position."""
    global ns_loc
    row, col = node.get('{' + ns_loc + '}' + position_name).split('/')
    return (int(row), int(col))

def getNodeTagRange(node, position_type):
    """Given a node and position type (open or close), return the rows and columns that relate to the node's position."""
    begin = getSpecificNodePosition(node, position_type + '_tag_start_pos')
    end = getSpecificNodePosition(node, position_type + '_tag_end_pos')
    return (begin, end)

def getNodeTagRegion(view, node, position_type):
    """Given a view, a node and a position type (open or close), return the region that relates to the node's position."""
    begin, end = getNodeTagRange(node, position_type)
    
    begin = view.text_point(begin[0], begin[1])
    end = view.text_point(end[0], end[1])
    
    return sublime.Region(begin, end)

def getNodePosition(view, node):
    """Given a view and a node, return the regions that represent the positions of the open and close tags."""
    open_pos = getNodeTagRegion(view, node, 'open')
    close_pos = getNodeTagRegion(view, node, 'close')
    
    return (open_pos, close_pos)

def getNodePositions(view, node):
    """Generator for distinct positions within this node."""
    open_pos, close_pos = getNodePosition(view, node)
    
    pos = open_pos.begin()
    
    for child in node.iterchildren():
        child_open_pos, child_close_pos = getNodePosition(view, child)
        yield (node, pos, child_open_pos.begin(), True)
        pos = child_close_pos.end()
        yield (child, child_open_pos.begin(), pos, len(child) == 0)
    
    yield (node, pos, close_pos.end(), True)

def regionIntersects(outer, inner, include_beginning):
    return outer.intersects(inner) or (include_beginning and outer.contains(inner.begin()))

# TODO: consider subclassing tree? and moving function to that class
def getNodesAtPositions(view, trees, positions):
    """Given a sorted list of trees and non-overlapping positions, return the nodes that relate to each position - efficiently, without searching through unnecessary children and stop once all are found."""
    
    def relevance(span, start_index, max_index, include_beginning):
        """Look through all sorted positions from the starting index to the max, to find those that match the span. If there is a gap, stop looking."""
        found_one = False
        for index in range(start_index, max_index + 1):
            if regionIntersects(span, positions[index], include_beginning):
                yield index
                found_one = True
            elif found_one: # if we have found something previously, there is no need to check positions after this non-match, because they are sorted
                break
            elif index > start_index + 1 and not found_one: # if we haven't found anything, there is no need to check positions after start_index + 1, because they are sorted
                break
    
    def matchSpan(span, start_index, max_index, include_beginning):
        """Return the indexes that match the span, as well as the first index that was found and the last index that was found."""
        matches = list(relevance(span, start_index, max_index, include_beginning))
        if len(matches) > 0:
            start_index = matches[0]
            max_index = matches[-1]
        
        return (matches, start_index, max_index)
    
    def getMatches(node, next_match_index, max_index, final_matches):
        """Check the node and it's children for all matches within the specified range.""" 
        spans = getNodePositions(view, node)
        
        found_match_at_last_expected_position_in_node = False
        for span_node, pos_start, pos_end, is_final in spans:
            matches, first_match_index, last_match_index = matchSpan(sublime.Region(pos_start, pos_end), next_match_index, max_index, span_node == node)
            
            if len(matches) > 0: # if matches were found
                if last_match_index == max_index: # if the last index that matched is the maximum index that could match inside this node
                    found_match_at_last_expected_position_in_node = True # it could be the last match inside this node
                if is_final:
                    final_matches.append((span_node, matches, pos_start, pos_end, span_node == node))
                    next_match_index = last_match_index # the next index to search is the last index that matched
                else:
                    next_match_index = getMatches(span_node, first_match_index, last_match_index, final_matches) # the next index to search is the last index that matched
            elif found_match_at_last_expected_position_in_node: # no match this time. If we have previously found the match at the last expected position within this node, then it was the last match in the node
                break # stop looking for further matches
        
        return next_match_index
    
    matches = []
    start_match_index = 0
    last_match_index = len(positions) - 1
    for tree in trees:
        if tree is not None:
            root = tree.getroot()
            get_matches_in_tree = True
            if len(trees) > 1: # if there is only one tree, we can skip the optimization check, because we know for sure the matches will be in the tree
                open_pos, close_pos = getNodePosition(view, root)
                root_matches, start_match_index, last_match_index = matchSpan(open_pos.cover(close_pos), start_match_index, last_match_index)
                get_matches_in_tree = len(root_matches) > 0 # determine if it is worth checking this tree
            if get_matches_in_tree: # skip the tree if it doesn't participate in the match (saves iterating through all children of root element unnecessarily)
                start_match_index = getMatches(root, start_match_index, last_match_index, matches)
    
    return matches

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
        paths = getUniqueItems(paths)
    
    return paths

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
                if prev is not None and regionIntersects(prev[0], sublime.Region(current_first_sel.begin(), current_first_sel.begin()), prev[2]): # current first selection matches xpath region from previous first selection
                    nodes.append(prev[1])
                else: # current first selection doesn't match xpath region from previous first selection or is not cached
                    results = getNodesAtPositions(view, trees, [current_first_sel]) # get nodes at first selection
                    if len(results) > 0:
                        result = results[0]
                        previous_first_selection[view.id()] = (sublime.Region(result[2], result[3]), result[0], result[4]) # cache node and xpath region
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

def move_cursors_to_nodes(view, nodes, position_type):
    cursors = []
    
    for node in nodes:
        if isinstance(node, etree._ElementUnicodeResult): # if the node is an attribute or text node etc.
            node = node.getparent() # get the parent
        pos = getNodeTagRegion(view, node, position_type)
        tag = getTagName(node)[2]
        
        chars_before_tag = len('<')
        if position_type == 'close' and not isTagSelfClosing(node):
            chars_before_tag += len('/')
        # select only the tag name with the prefix
        cursors.append(sublime.Region(pos.begin() + chars_before_tag, pos.begin() + chars_before_tag + len(tag)))
    
    view.sel().clear()
    view.sel().add_all(cursors)
    
    view.show(cursors[0]) # scroll to show the first selection, if it is not already visible

def getRelativeNode(relative_to, direction):
    def return_specific(node):
        yield node
    generator = None
    if direction == 'next':
        generator = relative_to.itersiblings()
    elif direction in ('prev', 'previous'):
        generator = relative_to.itersiblings(preceding = True)
    elif direction in ('open', 'close'):
        generator = return_specific(relative_to) # return self
    elif direction == 'parent':
        generator = return_specific(relative_to.getparent())
    
    if generator is None:
        raise StandardError('Unknown direction "' + direction + '"')
    else:
        return next(generator, None)

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
                position_type = 'open'
                if args['direction'] == 'close':
                    position_type = 'close'
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
    return unique

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

def plugin_loaded():
    """When the plugin is loaded, clear all variables and cache xpaths for current view if applicable."""
    global settings
    settings = sublime.load_settings('xpath.sublime-settings')
    settings.clear_on_change('reparse')
    settings.add_on_change('reparse', settingsChanged)
    sublime.set_timeout_async(settingsChanged, 10)

# TODO: move to Element subclass?
def getTagName(node):
    items = node.tag.split('}')
    namespace = None
    local_name = items[-1]
    full_name = local_name
    if len(items) == 2:
        namespace = items[0][len('{'):]
        if node.prefix is not None:
            full_name = node.prefix + ':' + full_name
    
    return (namespace, local_name, full_name)

def collapseWhitespace(text, maxlen):
    text = (text or '').strip()[0:maxlen + 1].replace('\n', ' ').replace('\t', ' ')
    append = ''
    if len(text) > maxlen:
        append = '...'
    while '  ' in text:
        text = text.replace('  ', ' ')
    return text[0:maxlen - len(append)] + append

def isTagSelfClosing(node):
    """If the start and end tag positions are the same, then it is self closing."""
    open_pos = getNodeTagRange(node, 'open')
    close_pos = getNodeTagRange(node, 'close')
    return open_pos == close_pos

def getElementXMLPreview(node, maxlen):
    """Generate the xml string for the given node, up to the specified number of characters."""
    # NOTE: we can't use built in tostring method because it repeats all xmlns attributes unnecessarily and will include our location attributes
    # response = etree.tostring(node, encoding='unicode')
    # 
    # # TODO: allow a maxlen of -1 to mean infinite
    
    global ns_loc
    
    # add opening tag
    tag_name = getTagName(node)[2]
    response = '<' + tag_name
    # add attributes
    for attrib in node.attrib:
        splitNS = attrib.split('}')
        localName = splitNS[-1]
        prefix = ''
        if len(splitNS) == 2:
            splitNS[0] = splitNS[0][len('{'):]
            if splitNS[0] == ns_loc:
                continue
            for prefix in node.nsmap:
                if node.nsmap[prefix] == splitNS[0]:
                    prefix += ':'
                    break
                
        response += ' ' + prefix + localName + '="' + node.get(attrib) + '"'
    
    # add namespaces that were not on the parent element
    parent = node.getparent()
    differences = None
    if parent is not None:
        differences = set(node.nsmap).difference(set(parent.nsmap))
    else:
        differences = node.nsmap
    
    for ns in differences:
        if node.nsmap[ns] != ns_loc: # ignore our lxml node position namespace
            response += ' xmlns'
            if ns is not None:
                response += ':' + ns
            response += '="' + node.nsmap[ns] + '"'
    
    if isTagSelfClosing(node):
        response += ' />'
    else:
        # end of open tag
        response += '>'
        # add text
        remaining_size = maxlen - len(response)
        if remaining_size > 0 and node.text is not None:
            response += collapseWhitespace(node.text, remaining_size) # remove whitespace
        
        # loop through children
        for child in node.iterchildren():
            remaining_size = maxlen - len(response)
            if remaining_size <= 0:
                break
            else:
                response += getElementXMLPreview(child, remaining_size) + collapseWhitespace(child.tail, remaining_size) # remove whitespace
        
        remaining_size = maxlen - len(response)
        if remaining_size > 0:
            response += '</' + tag_name + '>'
    
    return response[0:maxlen]

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

def get_results_for_xpath_query(view, query, from_root):
    """Execute the specified xpath query on all SGML regions that contain a cursor, and return the results."""
    matches = []
    is_nodeset = None
    
    global settings
    defaultNamespacePrefix = settings.get('default_namespace_prefix', 'default')
    
    trees = ensureTreeCacheIsCurrent(view)
    if trees is not None:
        
        regions_cursors = {}
        for result in getSGMLRegionsContainingCursors(view):
            regions_cursors.setdefault(result[1], []).append(result[2])
        
        for region_index in regions_cursors.keys():
            tree = trees[region_index]
            
            nsmap = makeNamespacePrefixesUniqueWithNumericSuffix(get_all_namespaces_in_tree(tree), defaultNamespacePrefix, 1)
            
            try:
                xpath = etree.XPath(query, namespaces = nsmap)
            except Exception as e:
                sublime.status_message(str(e)) # show parsing error in status bar
                return None
            
            contexts = []
            
            if from_root:
                contexts.append(tree)
            else:
                # allow starting the search from the element(s) at the cursor position(s) - i.e. set the context nodes
                for node in getNodesAtPositions(view, [tree], regions_cursors[region_index]):
                    contexts.append(node[1])
            
            for context in contexts:
                try:
                    result = xpath(context)
                    if isinstance(result, list):
                        is_nodeset = True
                        
                        matches += result
                    else:
                        is_nodeset = False
                        matches.append(result)
                except Exception as e:
                    sublime.status_message(str(e)) # show parsing error in status bar
                    return None
        
        if not from_root and is_nodeset: # if multiple contexts were used, get unique items only
            matches = getUniqueItems(matches)
        
    return (is_nodeset, matches)

class QueryXpathCommand(sublime_plugin.TextCommand): # example usage from python console: sublime.active_window().active_view().run_command('query_xpath', { 'xpath': '//prefix:LocalName', 'show_query_results': True })
    input_panel = None
    results = None # results from query
    previous_input = '' # remember previous query so that when the user next runs this command, it will be prepopulated
    show_query_results = None # whether to show the results of the query, so the user can pick *one* to move the cursor to. If False, cursor will automatically move to all results. Has no effect if result of query is not a node set.
    selected_index = None
    live_mode = None
    relative_mode = None
    pending = []
    
    def run(self, edit, **args):
        self.show_query_results = args is None or getBoolValueFromArgsOrSettings('show_query_results', args, True)
        self.live_mode = args is None or getBoolValueFromArgsOrSettings('live_mode', args, True)
        self.relative_mode = args is None or getBoolValueFromArgsOrSettings('relative_mode', args, False) # TODO: cache context nodes now? to allow live mode to work with it
        
        if args is not None and 'xpath' in args: # if an xpath is supplied, query it
            self.process_results_for_query(args['xpath'])
        else: # show an input prompt where the user can type their xpath query
            # if previous input is blank, or specifically told to, use path of first cursor. even if live mode enabled, cursor won't move much when activating this command
            prefill = self.previous_input
            if getBoolValueFromArgsOrSettings('prefill_path_at_cursor', args, False) or not self.previous_input:
                global previous_first_selection
                prev = previous_first_selection.get(self.view.id(), None)
                if prev is not None:
                    xpaths = getXPathOfNodes([prev[1]], { 'show_namespace_prefixes_from_query': True, 'show_hierarchy_only': False, 'case_sensitive': True }) # ensure the path matches this node and only this node
                    prefill = xpaths[0]
            
            self.input_panel = self.view.window().show_input_panel('enter xpath', prefill, self.xpath_input_done, self.change, self.cancel)
    
    def change(self, value):
        """When the xpath query is changed, after a short delay (so that it doesn't query unnecessarily while the xpath is still being typed), execute the expression."""
        def cb():
            if self.pending.pop() == value:
                self.process_results_for_query(value)
                if self.input_panel is not None:
                    self.input_panel.window().focus_view(self.input_panel)
        
        if self.live_mode and self.show_query_results:
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
        if not self.live_mode:
            self.process_results_for_query(value)
        else:
            self.close_quick_panel()
    
    def process_results_for_query(self, query):
        if len(query) > 0:
            self.results = get_results_for_xpath_query(self.view, query, not self.relative_mode)
            if self.results is not None:
                if self.results[0] and len(self.results[1]) == 0:
                    sublime.status_message('no results found matching xpath expression "' + query + '"')
                else:
                    sublime.status_message('') # clear status message as it is out of date now
                    if self.show_query_results or not self.results[0]: # also show results if results is not a node set, as we can't "go to" them...
                        self.show_results_for_query()
                    else:
                        self.goto_results_for_query()
    
    def close_quick_panel(self):
        sublime.active_window().run_command('hide_overlay', { 'cancel': True }) # close existing quick panel
    
    def show_results_for_query(self):
        self.close_quick_panel()
        
        # truncate each xml result at 70 chars so that it appears (more) correctly in the quick panel
        maxlen = 70
        
        show_text_preview = lambda result: str(result)[0:maxlen]
        
        if self.results[0]:
            result_unique_type_count = len(getUniqueItems([type(item) for item in self.results[1]]))
            
            show_element_preview = lambda e: [getTagName(e)[2], collapseWhitespace(e.text, maxlen), getElementXMLPreview(e, maxlen)]
            def show_preview(item):
                if isinstance(item, etree._Element):
                    return show_element_preview(item)
                else:
                    show = show_text_preview(item)
                    if result_unique_type_count > 1: # if some items are elements (where we show 3 lines) and some are other node types (where we show 1 line), we need to return 3 lines to ensure Sublime will show the results correctly
                        show = [show, '', '']
                    return show
            
            list_comp = [show_preview(item) for item in self.results[1]]
        else:
            list_comp = [show_text_preview(result) for result in self.results[1]]
        self.view.window().show_quick_panel(list_comp, self.xpath_selection_done, sublime.KEEP_OPEN_ON_FOCUS_LOST, -1, self.xpath_selection_changed)
        
    def xpath_selection_changed(self, selected_index):
        self.xpath_selection_done(selected_index)
    
    def xpath_selection_done(self, selected_index):
        if selected_index > -1: # quick panel wasn't cancelled
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
