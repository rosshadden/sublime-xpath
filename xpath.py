import sublime
import sublime_plugin
import os

changeCounter = None
currentXPathRange = None

def buildPath(view, selection):
    path = ['']
    levelCounters = [{}]
    firstIndexInXPath = 1
    
    tagRegions = view.find_by_selector('entity.name.tag.')
    selfEndingTag = False
    insideElement = False
    prevStartTagOpenPos = -1
    for region in tagRegions:
        if region.begin() > selection.end():
            break;
        
        prevChar = view.substr(sublime.Region(region.begin() - 1, region.begin()))
        tagName = view.substr(region)
        
        if selfEndingTag:
            path.pop()
            levelCounters.pop()
        if prevChar == '<':
            # check last char before end of tag, to see if it is self closing or not...
            tagScope = view.extract_scope(region.end())
            selfEndingTag = view.substr(tagScope)[-2] == '/'
            
            levelCounters[len(levelCounters) - 1][tagName] = levelCounters[len(levelCounters) - 1].setdefault(tagName, firstIndexInXPath - 1) + 1
            level = levelCounters[len(levelCounters) - 1].get(tagName)
            path.append(tagName + '[' + str(level) + ']')
            levelCounters.append({})
            
            insideElement = True
            prevStartTagOpenPos = region.begin()
            prevTagClosePos = tagScope.end()
        elif prevChar == '/':
            if selection.end() > region.end():
                path.pop()
                levelCounters.pop()
                insideElement = False
                prevTagClosePos = region.end()
            selfEndingTag = False
        prevRegion = region
    
    if selfEndingTag and tagScope.end() <= selection.begin():
        path.pop()
        insideElement = False
        levelCounters.pop() # technically not necessary because unused, but here for correctness
    
    if insideElement:
        xpathStart = prevStartTagOpenPos
        if prevChar == '/':
            xpathEnd = prevRegion.end()
        elif selfEndingTag:
            xpathEnd = tagScope.end() - 1
        else:
            prevChar = view.substr(sublime.Region(region.begin() - 1, region.begin()))
            if prevChar == '/':
                xpathEnd = region.end()
            else:
                xpathEnd = region.begin() - 1
    elif selfEndingTag:
        xpathStart = tagScope.end()
    else:
        xpathStart = prevTagClosePos + 1
    if not insideElement:
        prevChar = view.substr(sublime.Region(region.begin() - 1, region.begin()))
        if prevChar == '/':
            xpathEnd = region.end()
        elif xpathStart > prevRegion.end():
            xpathEnd = region.begin() - 1
        else:
            xpathEnd = prevRegion.end()
    
    return [[xpathStart, xpathEnd], path]

def isSGML(view):
    currentSyntax = view.settings().get('syntax')
    if currentSyntax is not None:
        XMLSyntax = 'Packages/XML/'
        HTMLSyntax = 'Packages/HTML/'
        return currentSyntax.startswith(XMLSyntax) or currentSyntax.startswith(HTMLSyntax)
    else:
        return false

def updateStatusIfSGML(view):
    if isSGML(view):
        updateStatus(view)

def updateStatus(view):
    sel = view.sel()[0]
    newCount = view.change_count()
    global changeCounter
    global currentXPathRange
    if changeCounter is None or newCount > changeCounter or (sel.begin() < currentXPathRange[0] or sel.end() > currentXPathRange[1]):
        changeCounter = newCount
        view.set_status('xpath', 'XPath being calculated...')
        path = buildPath(view, sel)
        response = '/'.join(path[1])
        view.set_status('xpath', 'XPath: ' + response)
        currentXPathRange = path[0]

class XpathCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view

        if isSGML(view):
            view.set_status('xpath', 'XPath(s) being calculated...')
            xpaths = []
            for selection in view.sel():
                path = buildPath(view, selection)
                xpaths.append('/'.join(path[1]))
            sublime.set_clipboard(os.linesep.join(xpaths))
            sublime.status_message('xpath(s) copied to clipboard')
        else:
            sublime.status_message('xpath not copied to clipboard - ensure syntax is set to xml or html')


class XpathListener(sublime_plugin.EventListener):
    def on_selection_modified_async(self, view):
        updateStatusIfSGML(view)
    def on_activated_async(self, view):
        updateStatusIfSGML(view)
