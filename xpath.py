import sublime
import sublime_plugin
import os

def buildPath(view, selection):
    path = ['']
    levelCounters = [{}]
    firstIndexInXPath = 1
    
    tagRegions = view.find_by_selector('entity.name.tag.')
    selfEndingTag = False
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
        elif prevChar == '/':
            if selection.end() > region.end():
                path.pop()
                levelCounters.pop()
            selfEndingTag = False
    
    if selfEndingTag and tagScope.end() <= selection.begin():
        path.pop()
        levelCounters.pop() # technically not necessary because unused, but here for correctness
    return path

def isSGML(view):
    currentSyntax = view.settings().get('syntax')
    XMLSyntax = 'Packages/XML/'
    HTMLSyntax = 'Packages/HTML/'
    return currentSyntax.startswith(XMLSyntax) or currentSyntax.startswith(HTMLSyntax)

def updateStatusIfSGML(view):
    if isSGML(view):
        updateStatus(view)

def updateStatus(view):
    view.set_status('xpath', 'XPath being calculated...')
    path = buildPath(view, view.sel()[0])
    response = '/'.join(path)
    view.set_status('xpath', 'XPath: ' + response)

class XpathCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view

        if isSGML(view):
            xpaths = []
            for selection in view.sel():
                path = buildPath(view, selection)
                xpaths.append('/'.join(path))
            sublime.set_clipboard(os.linesep.join(xpaths))
            sublime.status_message('xpath(s) copied to clipboard')
        else:
            sublime.status_message('xpath not copied to clipboard - ensure syntax is set to xml or html')


class XpathListener(sublime_plugin.EventListener):
    def on_selection_modified_async(self, view):
        updateStatusIfSGML(view)
    def on_activated_async(self, view):
        updateStatusIfSGML(view)
