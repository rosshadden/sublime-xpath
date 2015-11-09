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
namespace_start_tag = 'START_TAG_POS'

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
    
    class ETreeContent(ElementTreeContentHandler):
        locator = None
        
        prefix_hierarchy = []
        
        def setDocumentLocator(self, locator):
            self.locator = locator
        
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
            for mappings in reversed(self.prefix_hierarchy):
                if prefix in mappings:
                    return mappings[prefix]
            return None
        
        def _getNamespaceMap(self):
            flattened = {}
            for mappings in self.prefix_hierarchy:
                for prefix in mappings:
                    flattened[prefix] = mappings[prefix]
            return flattened
        
        def _getParsePosition(self):
            locator = self.locator or parser
            return (locator.getLineNumber(), locator.getColumnNumber())
        
        def startElementNS(self, name, tagName, attrs):
            # correct missing element and attribute namespaceURIs, using known prefixes and new prefixes declared with this element
            self.prefix_hierarchy.append({})
            
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
            
            global namespace_start_tag
            pos = self._getParsePosition()
            self.startPrefixMapping(namespace_start_tag, 'http://lxml/line/' + str(pos[0]) + '/col/' + str(pos[1])) # note that due to the way lxml element proxies work, we can't store the column number without making it a part of the document
            
            self._new_mappings = self._getNamespaceMap()
            
            super().startElementNS(name, tagName, attrs)
            
        def startPrefixMapping(self, prefix, uri):
            self.prefix_hierarchy[-1][prefix] = uri
            if prefix is None:
                self._default_ns = uri
        
        def endPrefixMapping(self, prefix):
            self.prefix_hierarchy[-1].pop(prefix)
            if prefix is None:
                self._default_ns = self._getNamespaceURI(None)
        
        def endElementNS(self, name, tagName):
            tag = self._splitPrefixAndGetNamespaceURI(tagName)
            name = (tag[2], tag[1])
            super().endElementNS(name, tagName)
            if None in self.prefix_hierarchy[-1]: # re-map default namespace if applicable
                self.endPrefixMapping(None)
            self.prefix_hierarchy.pop()
    
    createETree = ETreeContent()
    
    #parser.setFeature(handler.feature_namespace_prefixes, True) # xml.sax._exceptions.SAXNotSupportedException: expat does not report namespace prefixes
    parser.setContentHandler(createETree)
    parser.feed(xmlString) # using feed does not call the setDocumentLocator method of the handler
    
    #parseString(bytes(xmlString, 'UTF-8'), parser) # AttributeError: 'ExpatParser' object has no attribute 'processingInstruction'
    #parseString(bytes(xmlString, 'UTF-8'), createETree) # if using parseString then using the handler method directly is necessary, because the parser gives the above error
    
    parser.close()
    
    return createETree.etree

class queryXpathCommand(sublime_plugin.TextCommand): # example usage from python console: sublime.active_window().active_view().run_command('query_xpath', { 'xpath': '//prefix:LocalName', 'show_query_results': True })
    input_panel = None
    results = None # results from query
    previous_input = '' # remember previous query so that when the user next runs this command, it will be prepopulated
    show_query_results = None # whether to show the results of the query, so the user can pick *one* to move the cursor to. If False, cursor will automatically move to all results. Has no effect if result of query is not a node set.
    selected_index = None
    live_mode = None
    
    def run(self, edit, **args):
        self.show_query_results = args is None or getBoolValueFromArgsOrSettings('show_query_results', args, True)
        self.live_mode = args is None or getBoolValueFromArgsOrSettings('live_mode', args, True)
        if args is not None and 'xpath' in args: # if an xpath is supplied, query it
            self.process_results_for_query(args['xpath'])
        else: # show an input prompt where the user can type their xpath query
            self.input_panel = self.view.window().show_input_panel('enter xpath', self.previous_input, self.xpath_input_done, self.change, self.cancel)
    
    def change(self, value):
        if self.live_mode and self.show_query_results:
            # TODO: maybe set a timeout so that it doesn't query unnecessarily while the xpath is still being typed
            self.process_results_for_query(value)
            if self.input_panel is not None:
                self.input_panel.window().focus_view(self.input_panel)
        
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
            self.results = self.get_results_for_query(query)
            
            if self.results is not None:
                if len(self.results) == 0:
                    sublime.status_message('no results found matching xpath expression "' + query + '"')
                else:
                    sublime.status_message('') # clear status message as it is out of date now
                    if self.show_query_results: # TODO: also show results if results is not a node set, as we can't "go to" them...
                        self.show_results_for_query()
                    else:
                        self.goto_results_for_query()
        
    def get_results_for_query(self, query):
        matches = []
        
        getNamespaces = etree.XPath('//namespace::*')
        
        global settings
        settings = sublime.load_settings('xpath.sublime-settings')
        defaultNamespacePrefix = settings.get('default_namespace_prefix', 'default')
        
        # parse each region as XML
        for region in getSGMLRegionsContainingCursors(self.view):
            xmlString = self.view.substr(region)
            tree = lxml_etree_parse_xml_string_with_location(xmlString) # TODO: parse xml only when document is opened or modified, not every time an xpath query is made
            
            # find all namespaces in the document, so that the same prefixes can be used for the xpath
            # TODO: if the same prefix is used multiple times for different URIs, add a numeric suffix and increment it each time
            nsmap = {}
            global namespace_start_tag
            namespaces = [ns for ns in getUniqueItems(getNamespaces(tree)) if ns[0] != namespace_start_tag]
            print(namespaces)
            for ns in namespaces:
                nsmap[ns[0]] = ns[1]
            
            # xpath 1.0 doesn't support the default namespace, it needs to be mapped to a prefix
            # TODO: cater for multiple default namespaces (i.e. on different elements) here / or in the code above
            defaultNSURI = nsmap.pop(None, None)
            if defaultNSURI is not None:
                nsmap[defaultNamespacePrefix] = defaultNSURI
            
            try:
                xpath = etree.XPath(query, namespaces = nsmap)
            except Exception as e:
                sublime.status_message(str(e)) # show parsing error in status bar
                return None
            
            contexts = []
            
            # allow starting the search from the element at the cursor position - i.e. set the context nodes
            
            #if self.live_mode or query.startswith('/'): # if it is an absolute path, there is no need to set the context, so just use the root/entry point of the tree
            contexts.append(tree)
            #else:
                # for cursor in (r for r in self.view.sel() if region.contains(r)):
                #     # TODO: use namespace maps, and include default: prefix where applicable
                #     contextPath = '/'.join(getXPathStringAtPositions(self.view, [cursor], True, False)[0].split('/')[2:]) # ignore root element when searching path
                #     contextElement = tree.find(contextPath)
                #     contexts.append(contextElement)
        
            
            for context in contexts:
                matches += xpath(context)
        
        # TODO: only get unique items if a nodeset? and if multiple contexts were used
        return getUniqueItems(matches)
    
    def _getTagNameWithPrefix(self, node):  # NOTE: this can be static
        tag = node.tag.split('}')[-1]
        
        if node.prefix:
            tag = node.prefix + ':' + tag
        
        return tag
    
    def _collapseWhitespace(self, text, maxlen): # NOTE: this can be static
        return (text or '').strip().replace('\n', ' ').replace('\t', ' ').replace('  ', ' ')[0:maxlen]
    
    def _getElementLocation(self, node): # NOTE: this can be static
        global namespace_start_tag
        ns = node.nsmap[namespace_start_tag].split('/')
        col = int(ns[-1]) + 1
        row = int(ns[-3])
        return (row, col)
    
    def _getElementXML(self, node, maxlen): # NOTE: this can be static
        # NOTE: we can't use built in tostring method because it repeats all xmlns attributes unnecessarily
        # response = etree.tostring(node, encoding='unicode')
        
        # add opening tag
        tagName = self._getTagNameWithPrefix(node)
        response = '<' + tagName
        # add attributes
        for attrib in node.attrib:
            splitNS = attrib.split('}')
            localName = splitNS[-1]
            prefix = ''
            if len(splitNS) == 2:
                splitNS[0] = splitNS[0][len('{'):]
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
                response += self._collapseWhitespace(node.text, remaining_size) # remove whitespace
            
            # loop through children
            for child in node.iterchildren():
                remaining_size = maxlen - len(response)
                if remaining_size <= 0:
                    break
                else:
                    response += self._getElementXML(child, remaining_size) + self._collapseWhitespace(child.tail, remaining_size) # remove whitespace
            
            response += '</' + tagName + '>'
            
        return response[0:maxlen]
    
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
        self.view.window().show_quick_panel([[self._getTagNameWithPrefix(e), self._collapseWhitespace(e.text, maxlen), self._getElementXML(e, maxlen)] for e in self.results], self.xpath_selection_done, sublime.KEEP_OPEN_ON_FOCUS_LOST, -1, self.xpath_selection_changed)
        
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
            row, col = self._getElementLocation(node)
            
            char_index = self.view.text_point(row - 1, col)
            char_index_end = char_index #+ len(self.getTagNameWithPrefix(node))
            
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
