import sublime
import sublime_plugin
import re


def buildPath(view, selection):
    path = ['']
    lines = []

    region = sublime.Region(0, selection.end())
    for line in view.lines(region):
        contents = view.substr(line)
        lines.append(contents)

    level = -1
    spaces = re.compile('^\s+')
    for line in lines:
        space = spaces.findall(line)
        current = len(space[0]) if len(space) else 0
        node = re.sub(r'\s*<\??([\w.]:)?([\w\-.]+)(\s.)?>.*', r'\2', line)
        node = re.sub(r'\s*<(\S+)[^>]*>', r'\1', node)
        if current == level:
            path.pop()
            path.append(node)
        elif current > level:
            path.append(node)
            level = current
        elif current < level:
            path.pop()
            level = current

    return path

def isXML(view):
    currentSyntax = view.settings().get('syntax')
    XMLSyntax = 'Packages/XML/'
    return currentSyntax.startswith(XMLSyntax)

def updateStatusIfXML(view):
    if isXML(view):
        updateStatus(view)

def updateStatus(view):
    path = buildPath(view, view.sel()[0])
    response = '/'.join(path)
    view.set_status('xpath', response)

class XpathCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view

        if isXML(view):
            response = ''
            selections = view.sel()
            for s, selection in enumerate(selections):
                path = buildPath(view, selection)
                response += '/'.join(path)
                if s != len(selections) - 1:
                    response += '\n'
            sublime.set_clipboard(response)
        else:
            sublime.status_message('xpath not copied to clipboard - ensure syntax is set to xml')


class XpathListener(sublime_plugin.EventListener):
    def on_selection_modified_async(self, view):
        updateStatusIfXML(view)
