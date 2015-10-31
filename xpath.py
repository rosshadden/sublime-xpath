import sublime
import sublime_plugin
import os
from itertools import takewhile
import xml.etree.ElementTree as etree

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
    """find all xml and html scopes in the specified view."""
    return view.find_by_selector('text.xml') + view.find_by_selector('text.html')

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
    return containsSGML(view) and len(getXPathIndexesAtPositions(view, view.sel())) > 0

def updateStatusIfSGML(view):
    """Update the status bar with the relevant xpath at the cursor if the view contains XML or HTML syntax."""
    if containsSGML(view):
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

def copyXPathsToClipboard(view, includeIndexes, includeAttributes, unique):
    """Copy the XPath(s) at the cursor(s) to the clipboard."""
    if containsSGML(view):
        ensureXpathCacheIsCurrent(view)
        paths = getXPathStringAtPositions(view, view.sel(), includeIndexes, includeAttributes)
        if unique:
            unique = []
            for path in paths:
                if path not in unique:
                    unique.append(path)
            paths = unique
        
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
    def run(self, edit, **args): # example usage from python console: sublime.active_window().active_view().run_command('goto_relative', 'direction': 'prev'})
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

class queryXpathCommand(sublime_plugin.TextCommand):
    input_panel = None
    items = None # results from query
    previous_input = '' # remember previous query so that when the user next runs this command, it will be prepopulated
    
    def run(self, edit):
        self.input_panel = self.view.window().show_input_panel('enter xpath', self.previous_input, self.xpath_input_done, self.change, self.cancel)
    
    def xpath_input_done(self, value):
        self.input_panel = None
        self.previous_input = value
        self.show_results_for_query(value)
        
    def show_results_for_query(self, query):
        # parse the view as xml # TODO: parse only the SGML region the cursor is in
        xmlString = self.view.substr(sublime.Region(0, self.view.size()))
        root = etree.fromstring(xmlString)
        xml = etree.ElementTree(root) # convert from a root element to an element tree, so that we don't need to perform relative xpath queries from the root
        
        # allow starting the search from the element at the cursor position, i.e. a relative search, if there is one selection
        if query.startswith('./') and len(view.sel()) == 1:
            startQueryFrom = xml.find('TODO: current xpath at cursor')
        else:
            startQueryFrom = xml
        
        self.items = startQueryFrom.findall(query)
        
        if len(self.items) == 0:
            sublime.status_message('no results found matching xpath expression "' + query + '"')
        elif len(self.items) == 1:
            sublime.status_message('one result found')
            self.xpath_selection_done(0)
        else:
            # truncate each xml result at 60 chars so that it appears correctly in the quick panel
            self.view.window().show_quick_panel([[e.tag, e.text, etree.tostring(e, encoding="unicode")[0:60]] for e in self.items], self.xpath_selection_done)
        
    def xpath_selection_done(self, selected_index):
        if selected_index > -1: # quick panel wasn't cancelled
            
            # TODO: move the cursor to the selected node
            # option 1: - use an xml parser that returns line and column information
            # option 2: - traverse the hierarchy to find the full, absolute xpath of the selected element
            #             for example, query was //c, selection was made in the quick panel of 2nd index, lets say the full xpath would be (/a/b[1]/c[2])
            #           - then lookup our stored xpaths and find a match, and as we store the position with it, we know where to move the cursor to
            
            print(self.items[selected_index])
            print(etree.tostring(self.items[selected_index], encoding="unicode"))
        
        self.items = None
    def change(self, value):
        # NOTE: this doesn't work in real time because showing a quick panel steals the focus, and re-focusing the input box closes the quick panel because it lost the focus...
        #self.show_results_for_query(value)
        #self.view.window().focus_view(self.input_panel)
        pass
    def cancel(self):
        self.input_panel = None
    def is_enabled(self, **args):
        return isCursorInsideSGML(self.view)
    def is_visible(self):
        return containsSGML(self.view)
