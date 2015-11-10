import sublime
import sublime_plugin
import os
from itertools import takewhile
from lxml.sax import ElementTreeContentHandler
from lxml import etree
from xml.sax import make_parser, ContentHandler#, parseString, handler

changeCounters = {}
XPaths = {}
settings = None

def settingsChanged():
    """Clear change counters and cached xpath regions for all views, and recalculate xpath regions for the current view."""
    global changeCounters
    global XPaths
    changeCounters.clear()
    XPaths.clear()
    updateStatusIfSGML(sublime.active_window().active_view())

def addPath(view, start, end, path):
    """Add the supplied xpath array to the cache for the view."""
    global XPaths
    XPaths[view.id()].append([sublime.Region(start, end), path[:]])

def clearPathsForView(view):
    """Clear all cached xpaths for the specified view."""
    global XPaths
    XPaths.pop(view.id(), None)

def getSGMLRegions(view):
    """Find all xml and html scopes in the specified view."""
    return view.find_by_selector('text.xml') + view.find_by_selector('text.html')

def getSGMLRegionsContainingCursors(view):
    """Find the SGML region(s) that the cursor(s) are in for the specified view."""
    allRegions = getSGMLRegions(view)
    cursor_regions = []
    for region in allRegions:
        containsCursor = False
        for cursor in view.sel():
            if region.contains(cursor):
                containsCursor = True
                break
        if containsCursor:
            cursor_regions.append(region)
    return cursor_regions

def buildPathsForView(view):
    """Clear and recreate a cache of all xpaths for the XML in the specified view."""
    clearPathsForView(view)
    global XPaths
    XPaths[view.id()] = []
    
    for region in getSGMLRegions(view):
        buildPathsForViewRegion(view, region)

def buildPathsForViewRegion(view, region_scope):
    """Create a cache of all xpaths for the XML in the specified view region."""
    path = ['']
    levelCounters = [{}]
    firstIndexInXPath = 1
    
    tagRegions = [region for region in view.find_by_selector('entity.name.tag.') if region_scope.contains(region)] # find all entity name tags within the specified scope
    position = 0
    
    global settings
    settings = sublime.load_settings('xpath.sublime-settings')
    settings.clear_on_change('reparse')
    settings.add_on_change('reparse', settingsChanged)
    wanted_attributes = settings.get('attributes_to_include', [])
    all_attributes = bool(settings.get('show_all_attributes', False))
    case_sensitive = bool(settings.get('case_sensitive', True))
    
    if not case_sensitive:
        wanted_attributes = [element.lower() for element in wanted_attributes]
    
    for region in tagRegions:
        prevChar = view.substr(sublime.Region(region.begin() - 1, region.begin()))
        tagName = view.substr(region)
        
        if prevChar == '<':
            addPath(view, position, region.begin(), path)
            
            # check last char before end of tag, to see if it is self closing or not...
            tagScope = view.find('>', region.end(), sublime.LITERAL).end()
            selfEndingTag = view.substr(tagScope - 2) == '/'
            
            position = tagScope
            
            attributes = []
            attr_pos = region.end() + 1
            attr_namespace = ''
            attr_name = ''
            while attr_pos < tagScope:
                scope_name = view.scope_name(attr_pos)
                scope_region = view.extract_scope(attr_pos)
                
                attr_pos = scope_region.end() + 1
                if 'entity.other.attribute-name' in scope_name:
                    scope_text = view.substr(scope_region)
                    if scope_text.endswith(':'):
                        attr_namespace = scope_text#[0:-1]
                        attr_pos -= 1
                    elif scope_text.startswith(':'):
                        attr_name = scope_text[1:]
                    else:
                        attr_name = scope_text
                elif 'string.quoted.' in scope_name:
                    scope_text = view.substr(scope_region)
                    if (all_attributes or
                        (    case_sensitive and (attr_namespace         + attr_name         in wanted_attributes or '*:' + attr_name         in wanted_attributes or attr_namespace         + '*' in wanted_attributes)) or
                        (not case_sensitive and (attr_namespace.lower() + attr_name.lower() in wanted_attributes or '*:' + attr_name.lower() in wanted_attributes or attr_namespace.lower() + '*' in wanted_attributes))
                    ):
                        attributes.append('@' + attr_namespace + attr_name + ' = ' + scope_text)
                    attr_namespace = ''
                    attr_name = ''
            
            if len(attributes) > 0:
                attributes = '[' + ' and '.join(attributes) + ']'
            else:
                attributes = ''
            
            level = len(levelCounters) - 1
            checkTag = tagName
            if not case_sensitive:
                checkTag = checkTag.lower()
            levelCounters[level][checkTag] = levelCounters[level].setdefault(checkTag, firstIndexInXPath - 1) + 1
            tagIndexAtCurrentLevel = levelCounters[level].get(checkTag)
            path.append(tagName + '[' + str(tagIndexAtCurrentLevel) + ']' + attributes)
            
            addPath(view, region.begin(), position, path)
            if selfEndingTag:
                path.pop()
            else:
                levelCounters.append({})
        elif prevChar == '/':
            addPath(view, position, region.begin(), path)
            addPath(view, region.begin(), region.end() + 1, path)
            path.pop()
            levelCounters.pop()
            position = region.end() + 1
        
    addPath(view, position, region_scope.end(), path)

def getXPathIndexesAtPositions(view, positions):
    """Given a sorted array of regions, return the indexes of the xpath strings that relate to each region. Requires that the xpaths have been cached already for the specified view."""
    global XPaths
    count = len(positions)
    current = 0
    matches = []
    for index, path in enumerate(XPaths[view.id()]):
        if path[0].intersects(positions[current]) or path[0].begin() == positions[current].begin():
            matches.append(index)
            current += 1
            if current == count:
                break
    return matches

def getXPathAtPositions(view, positions):
    """Given a sorted array of regions, return the xpath nodes that relate to each region."""
    global XPaths
    matches = []
    for index in getXPathIndexesAtPositions(view, positions):
        matches.append(XPaths[view.id()][index][1])
    return matches

def getXPathStringAtPositions(view, positions, includeIndexes, includeAttributes):
    """Given a sorted array of regions, return the xpath strings that relate to each region."""
    global XPaths
    matches = []
    for match in getXPathAtPositions(view, positions):
        if includeIndexes and includeAttributes:
            matches.append('/'.join(match))
        else:
            hierarchy = []
            for part in match:
                begin = part.find('[')
                end = part.find(']', begin) + len(']')
                index = part[begin:end]
                attributes = part[end:]
                part = part[0:begin]
                
                if includeIndexes:
                    part += index
                if includeAttributes:
                    part += attributes
                
                hierarchy.append(part)
            matches.append('/'.join(hierarchy))
            
    return matches

def containsSGML(view):
    """Return True if the view contains XML or HTML syntax."""
    return len(getSGMLRegions(view)) > 0

def isCursorInsideSGML(view):
    """Return True if at least one cursor is within XML or HTML syntax."""
    return len(getSGMLRegionsContainingCursors(view)) > 0

def updateStatusIfSGML(view):
    """Update the status bar with the relevant xpath at the cursor."""
    if isCursorInsideSGML(view):
        updateStatus(view)
    else:
        view.erase_status('xpath')

def ensureXpathCacheIsCurrent(view):
    """If the document has been modified since the xpaths were cached, recreate the cache."""
    global changeCounters
    newCount = view.change_count()
    oldCount = changeCounters.get(view.id(), None)
    if oldCount is None or newCount > oldCount:
        changeCounters[view.id()] = newCount
        view.set_status('xpath', 'XPath being calculated...')
        buildPathsForView(view)
        view.erase_status('xpath')

def updateStatus(view):
    """If the XML has changed since the xpaths were cached, recreate the cache. Updates the status bar with the xpath at the location of the first selection in the view."""
    if len(view.sel()) == 0: # no point doing any work as there is no cursor selection
        view.erase_status('xpath')
        return
    ensureXpathCacheIsCurrent(view)
    
    includeIndexes = not getBoolValueFromArgsOrSettings('show_hierarchy_only', None, False)
    response = getXPathStringAtPositions(view, [view.sel()[0]], includeIndexes, includeIndexes or getBoolValueFromArgsOrSettings('show_attributes_in_hierarchy', None, False))
    if len(response) == 1 and len(response[0]) > 0: # if there is an xpath at the cursor position, and it is not empty
        showPath = response[0]
        intro = 'XPath'
        if len(view.sel()) > 1:
            intro = intro + ' (at first selection)'
        
        text = intro + ': ' + showPath
        maxLength = 234 # if status message is longer than this, sublime text 3 shows nothing in the status bar at all, so unfortunately we have to truncate it...
        if len(text) > maxLength:
            append = ' (truncated)'
            text = text[0:maxLength - len(append)] + append
        view.set_status('xpath', text)
    else:
        view.erase_status('xpath')

def getBoolValueFromArgsOrSettings(key, args, default):
    """Retrieve the value for the given key from the args if present, otherwise the settings if present, otherwise use the supplied default."""
    if args is None or not key in args:
        global settings
        settings = sublime.load_settings('xpath.sublime-settings')
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

def copyXPathsToClipboard(view, includeIndexes, includeAttributes, unique):
    """Copy the XPath(s) at the cursor(s) to the clipboard."""
    if containsSGML(view):
        ensureXpathCacheIsCurrent(view)
        paths = getXPathStringAtPositions(view, view.sel(), includeIndexes, includeAttributes)
        if unique:
            paths = getUniqueItems(paths)
        
        paths = [path for path in paths if len(path) > 0] # ignore blank paths
        if len(paths) > 0:
            sublime.set_clipboard(os.linesep.join(paths))
            message = 'xpath(s) copied to clipboard'
        else:
            message = 'no xpath at cursor to copy to clipboard'
    else:
        message = 'xpath not copied to clipboard - ensure syntax of text under cursor is set to xml or html'
    sublime.status_message(message)

class XpathCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args):
        """Copy XPath(s) at cursor(s) to clipboard."""
        view = self.view
        
        includeIndexes = not getBoolValueFromArgsOrSettings('show_hierarchy_only', args, False)
        unique = getBoolValueFromArgsOrSettings('copy_unique_path_only', args, True)
        includeAttributes = includeIndexes or getBoolValueFromArgsOrSettings('show_attributes_in_hierarchy', args, False)
        
        copyXPathsToClipboard(view, includeIndexes, includeIndexes or includeAttributes, unique)
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self, **args):
        return containsSGML(self.view)

class GotoRelativeCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args): # example usage from python console: sublime.active_window().active_view().run_command('goto_relative', {'direction': 'prev'})
        """Move cursor(s) to specified relative tag(s)."""
        view = self.view
        
        ensureXpathCacheIsCurrent(view)
        
        foundPaths = []
        allFound = True
        for selection in view.sel():
            foundPath = self.find_node(selection, args['direction'])
            if foundPath is not None:
                foundPaths.append(foundPath)
            else:
                allFound = False
                break
        
        if not allFound:
            message = args['direction'] + ' node not found'
            if len(view.sel()) > 1:
                message += ' for at least one selection'
            sublime.status_message(message)
        else:
            view.sel().clear()
            for foundPath in foundPaths:
                view.sel().add(foundPath)
            view.show(foundPaths[0]) # scroll to first selection if not already visible
    
    def find_node(self, relative_to, direction):
        """Given a direction/relative to search and a region to start from, find the relevant node."""
        view = self.view
        
        global XPaths
        
        xpathIndexes = getXPathIndexesAtPositions(view, [relative_to])
        if len(xpathIndexes) == 0: # if there is no xpath at the specified position, it's probably not a XML/HTML region
            return None
        currentPos = xpathIndexes[0]
        currentPath = XPaths[view.id()][currentPos][1]
        parentPath = '/'.join(currentPath[0:-1])
        currentPath = '/'.join(currentPath)
        if len(currentPath) == 0: # if the xpath is blank, (aka no node) there can be no related nodes...
            return None
        
        if direction in ('next', 'close'):
            search = XPaths[view.id()][currentPos:] # search from current position down to the end of the document
        else: # prev, parent or open
            search = XPaths[view.id()][0:currentPos + 1] # search from current position up to the top of the document
            search = search[::-1]
        
        foundPaths = takewhile(lambda p: '/'.join(p[1]).startswith(parentPath), search)
        if direction == 'next':
            foundPath = next((p for p in foundPaths if '/'.join(p[1]) != parentPath and not '/'.join(p[1]).startswith(currentPath)), None) # not the parent node and not a descendant of the current node
        elif direction == 'prev':
            foundPath = None
            wantedPath = None
            for path in foundPaths:
                p = '/'.join(path[1])
                if not p.startswith(parentPath + '/'): # if it isn't a descendant of the parent, ignore it
                    pass
                elif wantedPath is not None:
                    if p == wantedPath: # if it is the same sibling we have already found
                        foundPath = path
                    elif not p.startswith(wantedPath):
                        break
                elif not p.startswith(currentPath):
                    foundPath = path
                    wantedPath = '/'.join(foundPath[1])
        elif direction in ('open', 'close', 'parent'):
            if direction == 'parent':
                wantedPath = parentPath
            else:
                wantedPath = currentPath
            foundPaths = list(p for p in foundPaths if '/'.join(p[1]) == wantedPath)
            if len(foundPaths) > 0:
                foundPath = foundPaths[-1] # the last node (open and parent are in reverse order, remember...)
            else:
                foundPath = None
        
        if foundPath is None:
            return None
        else:
            return sublime.Region(foundPath[0].begin(), foundPath[0].end() - 1)
    
    #def want_event(self):
    #    return True
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self):
        return containsSGML(self.view)
    def description(self, args):
        if args['direction'] in ('open', 'close'):
            descr = 'tag'
        elif args['direction'] in ('prev', 'next'):
            descr = 'sibling'
        elif args['direction'] in ('parent'):
            descr = 'element'
        else:
            return None
        
        return 'Goto ' + args['direction'] + ' ' + descr


class XpathListener(sublime_plugin.EventListener):
    def on_selection_modified_async(self, view):
        updateStatusIfSGML(view)
    def on_activated_async(self, view):
        updateStatusIfSGML(view)
    def on_pre_close(self, view):
        clearPathsForView(view)

def plugin_loaded():
    """When the plugin is loaded, clear all variables and cache xpaths for current view if applicable."""
    sublime.set_timeout_async(settingsChanged, 10)

def lxml_etree_parse_xml_string_with_location(xmlString):
    parser = make_parser()
    
    class LocationAwareElement(etree.ElementBase):
        start_tag_pos = None
        end_tag_pos = None
        
        def _init(self):
            super()._init()
            
            if '{lxml}start_tag_pos' in self.attrib.keys():
                self.start_tag_pos = self.get('{lxml}start_tag_pos') # it should be possible to pop these attributes so that they don't appear in the final DOM... but doing so seems to not work, despite keeping the element proxy alive
                self.end_tag_pos = self.get('{lxml}end_tag_pos')
    
    etree_parser = etree.XMLParser()
    lookup = etree.ElementDefaultClassLookup(element=LocationAwareElement)
    etree_parser.set_element_class_lookup(lookup)
    
    class ETreeContent(ElementTreeContentHandler):
        _locator = None
        _prefix_hierarchy = []
        
        proxy_cache = None
        
        def __init__(self):
            super().__init__(makeelement=etree_parser.makeelement)
        
        def setDocumentLocator(self, locator):
            self._locator = locator
        
        def _splitPrefixAndGetNamespaceURI(self, fullName):
            prefix = None
            local_name = None
            
            split_pos = fullName.find(':')
            if split_pos > -1:
                prefix = fullName[0:split_pos]
                local_name =  fullName[split_pos + 1:]
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
            return str(locator.getLineNumber()) + '/' + str(locator.getColumnNumber())
        
        def startElementNS(self, name, tagName, attrs):
            # correct missing element and attribute namespaceURIs, using known prefixes and new prefixes declared with this element
            self._prefix_hierarchy.append({})
            
            nsmap = []
            attrmap = []
            for attrName, attrValue in attrs.items():
                if attrName[0] == None: # if there is no namespace URI associated with the attribute already
                    if attrName[1].startswith('xmlns:'): # map the prefix to the namespace URI
                        nsmap.append((attrName, attrName[1][len('xmlns:'):], attrValue))
                    elif attrName[1] == 'xmlns': # map the default namespace URI
                        nsmap.append((attrName, None, attrValue))
                    elif ':' in attrName[1]: # separate the prefix from the local name
                        attrmap.append((attrName, self._splitPrefixAndGetNamespaceURI(attrName[1]), attrValue))
            
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
            current.set('{lxml}start_tag_pos', self._getParsePosition())
            
        def startPrefixMapping(self, prefix, uri):
            self._prefix_hierarchy[-1][prefix] = uri
            if prefix is None:
                self._default_ns = uri
        
        def endPrefixMapping(self, prefix):
            self._prefix_hierarchy[-1].pop(prefix)
            if prefix is None:
                self._default_ns = self._getNamespaceURI(None)
        
        def endElementNS(self, name, tagName):
            current = self._element_stack[-1]
            current.set('{lxml}end_tag_pos', self._getParsePosition())
            
            tag = self._splitPrefixAndGetNamespaceURI(tagName)
            name = (tag[2], tag[1])
            super().endElementNS(name, tagName)
            if None in self._prefix_hierarchy[-1]: # re-map default namespace if applicable
                self.endPrefixMapping(None)
            self._prefix_hierarchy.pop()
        
        def endDocument(self):
            self.proxy_cache = list(self.etree.iter())
    
    createETree = ETreeContent()
    
    #parser.setFeature(handler.feature_namespace_prefixes, True) # xml.sax._exceptions.SAXNotSupportedException: expat does not report namespace prefixes
    parser.setContentHandler(createETree)
    parser.feed(xmlString) # using feed does not call the setDocumentLocator method of the handler
    
    #parseString(bytes(xmlString, 'UTF-8'), parser) # AttributeError: 'ExpatParser' object has no attribute 'processingInstruction'
    #parseString(bytes(xmlString, 'UTF-8'), createETree) # if using parseString then using the handler method directly is necessary, because the parser gives the above error
    
    parser.close()
    
    return (createETree.etree, createETree.proxy_cache)

def getTagNameWithPrefix(node):
    tag = node.tag.split('}')[-1]
    
    if node.prefix:
        tag = node.prefix + ':' + tag
    
    return tag

def collapseWhitespace(text, maxlen):
    return (text or '').strip().replace('\n', ' ').replace('\t', ' ').replace('  ', ' ')[0:maxlen]

def getNodeLocation(node):
    global namespace_start_tag
    ns = node.nsmap[namespace_start_tag].split('/')
    col = int(ns[-1]) + 1
    row = int(ns[-3])
    return (row, col)

def getElementXMLPreview(node, maxlen):
    """Generate the xml string for the given node, up to the specified number of characters."""
    # NOTE: we can't use built in tostring method because it repeats all xmlns attributes unnecessarily
    # response = etree.tostring(node, encoding='unicode')
    
    # add opening tag
    tagName = getTagNameWithPrefix(node)
    response = '<' + tagName
    # add attributes
    for attrib in node.attrib:
        splitNS = attrib.split('}')
        localName = splitNS[-1]
        prefix = ''
        if len(splitNS) == 2:
            splitNS[0] = splitNS[0][len('{'):]
            if splitNS[0] == 'lxml':
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
    
    global namespace_start_tag
    for ns in differences:
        if ns != namespace_start_tag:
            response += ' xmlns'
            if ns is not None:
                response += ':' + ns
            response += '="' + node.nsmap[ns] + '"'
    
    # if no children and no text, is probably self closing
    if len(node) == 0 and node.text is None:
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
        
        response += '</' + tagName + '>'
        
    return response[0:maxlen]

def makeNamespacePrefixesUniqueWithNumericSuffix(items, replaceNoneWith, start = 1):
    flattened = {}
    for item in items:
        flattened.setdefault(item[0] or replaceNoneWith, []).append(item[1])
    
    unique = {}
    for key in flattened.keys():
        if len(flattened[key]) == 1:
            unique[key] = flattened[key][0]
        else:
            index = start
            for item in flattened[key]:
                unique[key + str(index)] = item
                index += 1
    return unique

def get_results_for_xpath_query(view, query, from_root):
    matches = []
    
    getNamespaces = etree.XPath('//namespace::*')
    
    global settings
    settings = sublime.load_settings('xpath.sublime-settings')
    defaultNamespacePrefix = settings.get('default_namespace_prefix', 'default')
    
    # parse each region as XML
    for region in getSGMLRegionsContainingCursors(view):
        xmlString = view.substr(region)
        tree, proxy_cache = lxml_etree_parse_xml_string_with_location(xmlString) # TODO: parse xml only when document is opened or modified, not every time an xpath query is made
        
        # find all namespaces in the document, so that the same prefixes can be used for the xpath
        # if the same prefix is used multiple times for different URIs, add a numeric suffix and increment it each time
        # xpath 1.0 doesn't support the default namespace, it needs to be mapped to a prefix
        global namespace_start_tag
        namespaces = [ns for ns in getUniqueItems(getNamespaces(tree)) if ns[0] != namespace_start_tag]
        nsmap = makeNamespacePrefixesUniqueWithNumericSuffix(namespaces, defaultNamespacePrefix, 1)
        
        try:
            xpath = etree.XPath(query, namespaces = nsmap)
        except Exception as e:
            sublime.status_message(str(e)) # show parsing error in status bar
            return None
        
        contexts = []
        
        if from_root:
            contexts.append(tree)
        else:
            # allow starting the search from the element at the cursor position - i.e. set the context nodes
            for cursor in (r for r in view.sel() if region.contains(r)):
                # TODO: include default namespace prefixes where applicable
                contextPath = '/'.join(getXPathStringAtPositions(view, [cursor], True, False)[0].split('/')[2:]) # ignore root element when searching path
                contextElement = tree.find(contextPath)
                contexts.append(contextElement)
        
        for context in contexts:
            matches += xpath(context)
    
    if not from_root: # if multiple contexts were used, get unique items only
        # TODO: only get unique items if a nodeset
        matches = getUniqueItems(matches)
    
    return matches

class queryXpathCommand(sublime_plugin.TextCommand): # example usage from python console: sublime.active_window().active_view().run_command('query_xpath', { 'xpath': '//prefix:LocalName', 'show_query_results': True })
    input_panel = None
    results = None # results from query
    previous_input = '' # remember previous query so that when the user next runs this command, it will be prepopulated
    show_query_results = None # whether to show the results of the query, so the user can pick *one* to move the cursor to. If False, cursor will automatically move to all results. Has no effect if result of query is not a node set.
    selected_index = None
    live_mode = None
    pending = []
    
    def run(self, edit, **args):
        self.show_query_results = args is None or getBoolValueFromArgsOrSettings('show_query_results', args, True)
        self.live_mode = args is None or getBoolValueFromArgsOrSettings('live_mode', args, True)
        if args is not None and 'xpath' in args: # if an xpath is supplied, query it
            self.process_results_for_query(args['xpath'])
        else: # show an input prompt where the user can type their xpath query
            self.input_panel = self.view.window().show_input_panel('enter xpath', self.previous_input, self.xpath_input_done, self.change, self.cancel)
    
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
            settings = sublime.load_settings('xpath.sublime-settings')
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
            self.results = get_results_for_xpath_query(self.view, query, True)
            
            if self.results is not None:
                if len(self.results) == 0:
                    sublime.status_message('no results found matching xpath expression "' + query + '"')
                else:
                    sublime.status_message('') # clear status message as it is out of date now
                    if self.show_query_results: # TODO: also show results if results is not a node set, as we can't "go to" them...
                        self.show_results_for_query()
                    else:
                        self.goto_results_for_query()
    
    def close_quick_panel(self):
        sublime.active_window().run_command('hide_overlay', { 'cancel': True }) # close existing quick panel
    
    def show_results_for_query(self):
        self.close_quick_panel()
        
        #if len(self.results) == 1:
        #    sublime.status_message('one result found')
        #    self.xpath_selection_done(0) # go directly to the single result
        #else:
        # truncate each xml result at 70 chars so that it appears (more) correctly in the quick panel
        
        maxlen = 70
        self.view.window().show_quick_panel([[getTagNameWithPrefix(e), collapseWhitespace(e.text, maxlen), getElementXMLPreview(e, maxlen)] for e in self.results], self.xpath_selection_done, sublime.KEEP_OPEN_ON_FOCUS_LOST, -1, self.xpath_selection_changed)
        
    def xpath_selection_changed(self, selected_index):
        self.xpath_selection_done(selected_index)
    
    def xpath_selection_done(self, selected_index):
        if selected_index > -1: # quick panel wasn't cancelled
            self.goto_results_for_query(selected_index)
        # TODO: close input box if it is open
    
    def goto_results_for_query(self, specific_index = None):
        global namespace_start_tag
        
        cursors = []
        
        results = self.results
        if specific_index is not None and specific_index > -1:
            results = [results[specific_index]]
        
        for node in results:
            row, col = node.start_tag_pos.split('/')
            
            char_index = self.view.text_point(int(row) - 1, int(col))
            char_index_end = char_index #+ len(getTagNameWithPrefix(node))
            
            cursors.append(sublime.Region(char_index, char_index_end))
            
            #print(node.getroottree().getelementpath(node))
        
        self.view.sel().clear()
        self.view.sel().add_all(cursors)
        
        self.view.show(cursors[0])
        
        if specific_index is None or specific_index == -1:
            self.results = None
    
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self):
        return containsSGML(self.view)
