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


def updateStatus(view):
    path = buildPath(view, view.sel()[0])
    response = '/'.join(path)
    view.set_status('xpath', response)


def isXML(view):
    ext = re.sub(
        r'.*\.(\w+)$',
        r'\1',
        view.file_name()
    )
    return ext == 'xml'


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
            sublime.status_message('xpath not copied to clipboard - file must have xml extension')


class XpathListener(sublime_plugin.EventListener):
    #def post_text_command(self, view, command_name, args):
    def on_text_command(self, view, command_name, args):
        if isXML(view) and (command_name == "move" or command_name == "drag_select"):
            updateStatus(view)
        #print command_name
    #def on_selection_modified_async(self, view):
        #print 'sel modified'
    def on_activated_async(self, view):
        if isXML(view):
            updateStatus(view)
