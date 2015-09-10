import sublime
import sublime_plugin
import os

changeCounters = {}
XPaths = {}
supportHTML = True
settings = None

def settingsChanged():
    """Clear change counters and cached xpath regions for all views, and recalculate xpath regions for the current view."""
    global changeCounters
    global XPaths
    changeCounters.clear()
    XPaths.clear()
    updateStatusIfSGML(sublime.active_window().active_view())

def addPath(view, start, end, path):
    global XPaths
    XPaths[view.id()].append([sublime.Region(start, end), '/'.join(path)])

def clearPathsForView(view):
    """Clear all cached xpaths for the specified view."""
    global XPaths
    XPaths.pop(view.id(), None)

def buildPathsForView(view):
    """Clear and recreate a cache of all xpaths for the XML in the specified view."""
    clearPathsForView(view)
    global XPaths
    XPaths[view.id()] = []
    
    path = ['']
    levelCounters = [{}]
    firstIndexInXPath = 1
    
    tagRegions = view.find_by_selector('entity.name.tag.')
    position = 0
    
    global settings
    settings = sublime.load_settings('xpath.sublime-settings')
    settings.clear_on_change('reparse')
    settings.add_on_change('reparse', settingsChanged)
    wanted_attributes = settings.get('attributes_to_include', [])
    all_attributes = settings.get('show_all_attributes', "False") == "True"
    case_sensitive = settings.get('case_sensitive', "True") == "True"
    
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
            addPath(view, position, region.end() + 1, path)
            path.pop()
            levelCounters.pop()
            position = region.end() + 1
        
    addPath(view, position, view.size(), path)

def getXPathAtPositions(view, positions):
    """Given a sorted array of regions, return the xpath strings that relate to each region."""
    global XPaths
    count = len(positions)
    current = 0
    matches = []
    for path in XPaths[view.id()]:
        if path[0].intersects(positions[current]) or path[0].begin() == positions[current].begin():
            matches.append(path[1])
            current += 1
            if current == count:
                break
    return matches

def isSGML(view):
    """Return True if the view's syntax is XML or HTML."""
    currentSyntax = view.settings().get('syntax')
    if currentSyntax is not None:
        XMLSyntax = 'Packages/XML/'
        HTMLSyntax = 'Packages/HTML/'
        global supportHTML
        return currentSyntax.startswith(XMLSyntax) or (supportHTML and currentSyntax.startswith(HTMLSyntax))
    else:
        return False

def updateStatusIfSGML(view):
    """Update the status bar with the relevant xpath at the cursor if the syntax is XML."""
    if isSGML(view):
        updateStatus(view)

def updateStatus(view):
    """If the XML has changed since the xpaths were cached, recreate the cache. Updates the status bar with the xpath at the location of the first selection in the view."""
    global changeCounters
    newCount = view.change_count()
    oldCount = changeCounters.get(view.id(), None)
    if oldCount is None or newCount > oldCount:
        changeCounters[view.id()] = newCount
        view.set_status('xpath', 'XPath being calculated...')
        buildPathsForView(view)
    
    response = getXPathAtPositions(view, [view.sel()[0]])
    showPath = ''
    if len(response) == 1:
        showPath = response[0]
    view.set_status('xpath', 'XPath: ' + showPath)

class XpathCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view

        if isSGML(view):
            sublime.set_clipboard(os.linesep.join(getXPathAtPositions(view, view.sel())))
            sublime.status_message('xpath(s) copied to clipboard')
        else:
            global supportHTML
            message = 'xpath not copied to clipboard - ensure syntax is set to xml'
            if supportHTML:
                message += ' or html'
            sublime.status_message(message)


class XpathListener(sublime_plugin.EventListener):
    def on_selection_modified_async(self, view):
        updateStatusIfSGML(view)
    def on_activated_async(self, view):
        updateStatusIfSGML(view)
    def on_pre_close(self, view):
        clearPathsForView(view)
