import sublime
import sublime_plugin
import re


def buildPath(view, selection):
    path = ['']
    
    tagRegions = view.find_by_selector('entity.name.tag.')
    selfEndingTag = False
    for region in tagRegions:
        if region.begin() > selection.end():
            break;
        
        firstChar = view.substr(sublime.Region(region.begin() - 1, region.begin()))
        tagName = view.substr(region)
        
        if selfEndingTag:
            path.pop()
        if firstChar == '<':
            # check last char before end tag...
            tagScope = view.extract_scope(region.end())
            selfEndingTag = view.substr(tagScope)[-2] == '/'
            
            path.append(tagName)
        elif firstChar == '/':
            if selection.end() > region.end():
                path.pop()
            selfEndingTag = False
    
    if selfEndingTag and tagScope.end() <= selection.begin():
        path.pop();
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
    path = buildPath(view, view.sel()[0])
    response = '/'.join(path)
    view.set_status('xpath', response)

class XpathCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view

        if isSGML(view):
            response = ''
            selections = view.sel()
            for s, selection in enumerate(selections):
                path = buildPath(view, selection)
                response += '/'.join(path)
                if s != len(selections) - 1:
                    response += '\n'
            sublime.set_clipboard(response)
        else:
            sublime.status_message('xpath not copied to clipboard - ensure syntax is set to xml or html')


class XpathListener(sublime_plugin.EventListener):
    def on_selection_modified_async(self, view):
        updateStatusIfSGML(view)
